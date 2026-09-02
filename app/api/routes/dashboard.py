"""Dashboard-level aggregate views. Every number here is a real query against
Argus's own tables — no hardcoded/placeholder figures. Where a real trend or
sparkline can't be honestly computed yet (not enough historical spread in
the data), the field is omitted rather than filled with a fake value; see
StatCard's docstring."""
import uuid
from datetime import date, datetime, timedelta, timezone

import redis
from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.actor import (
    Actor,
    AnalysisJob,
    AttributionEdge,
    Identifier,
    InfraFinding,
    RawPersona,
    ThreatActivity,
)
from app.models.external import (
    AbuseReport,
    BreachRecord,
    CorrelationEvidence,
    MaliciousUrl,
    MalwareSample,
    ThreatEvent,
    TorRelay,
)
from app.schemas.dashboard import (
    AlertOut,
    BreachRecordOut,
    ComponentStatusOut,
    DashboardStatsOut,
    DataSourceStatusOut,
    HibpLookupOut,
    HiddenServiceCorrelationOut,
    HiddenServiceRowOut,
    HiddenServicesOut,
    HiddenServicesSummaryOut,
    InfraFindingRowOut,
    PersonaActivityOut,
    PersonaActivityRecordOut,
    PersonaActivitySummaryOut,
    SourceBreakdownItem,
    StatCard,
    SystemStatusOut,
    ThreatEventOut,
    TimelineEventOut,
    TopLinkOut,
    TopLinkSignal,
    TorRelayOut,
)
from app.services.graph.neo4j_client import get_neo4j_client
from app.services.hibp_lookup import check_email_breaches
from app.services.scoring import WEIGHTS
from app.services.threat_categorization import CATEGORY_LABELS
from app.workers.celery_app import celery_app

router = APIRouter(
    prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)]
)

HIGH_CONFIDENCE_THRESHOLD = 0.7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stat_card(label: str, total: int, recent_count: int, older_count: int) -> StatCard:
    """recent_count: rows created in the last 7 days. older_count: rows that
    existed before that window. A trend % is only meaningful once there's a
    real "before" baseline to compare against — with older_count == 0 (e.g.
    a freshly-seeded demo DB) any percentage would be either infinite or a
    fabricated number, so it's left out entirely rather than shown as 0%."""
    trend_pct = None
    if older_count > 0:
        trend_pct = round((recent_count / older_count) * 100 - 100, 1)
    return StatCard(label=label, value=total, trend_pct=trend_pct)


def _counts(db: Session, model, timestamp_col, extra_filter=None):
    query = db.query(model)
    if extra_filter is not None:
        query = query.filter(extra_filter)
    total = query.count()

    cutoff = _now() - timedelta(days=7)
    recent = query.filter(timestamp_col >= cutoff).count()
    older = total - recent
    return total, recent, older


@router.get("/stats", response_model=DashboardStatsOut)
def get_dashboard_stats(db: Session = Depends(get_db)):
    actor_total, actor_recent, actor_older = _counts(db, Actor, Actor.created_at)

    handle_total, handle_recent, handle_older = _counts(
        db, Identifier, Identifier.first_seen, Identifier.identifier_type == "username"
    )
    pgp_total, pgp_recent, pgp_older = _counts(
        db, Identifier, Identifier.first_seen, Identifier.identifier_type == "pgp_key"
    )
    wallet_total, wallet_recent, wallet_older = _counts(
        db, Identifier, Identifier.first_seen, Identifier.identifier_type == "wallet"
    )
    edge_total, edge_recent, edge_older = _counts(db, AttributionEdge, AttributionEdge.created_at)

    high_conf_query = db.query(Actor).filter(Actor.confidence_score >= HIGH_CONFIDENCE_THRESHOLD)
    high_conf_total = high_conf_query.count()
    cutoff = _now() - timedelta(days=7)
    high_conf_recent = high_conf_query.filter(Actor.created_at >= cutoff).count()
    high_conf_older = high_conf_total - high_conf_recent

    return DashboardStatsOut(
        threat_actors=_stat_card(
            "Threat Actors Identified", actor_total, actor_recent, actor_older
        ),
        unique_handles=_stat_card("Unique Handles", handle_total, handle_recent, handle_older),
        pgp_keys=_stat_card("PGP Keys", pgp_total, pgp_recent, pgp_older),
        wallets_tracked=_stat_card("Wallets Tracked", wallet_total, wallet_recent, wallet_older),
        attribution_links=_stat_card("Attribution Links", edge_total, edge_recent, edge_older),
        high_confidence_links=_stat_card(
            "High Confidence Links", high_conf_total, high_conf_recent, high_conf_older
        ),
    )


@router.get("/timeline", response_model=list[TimelineEventOut])
def get_dashboard_timeline(
    limit: int = 20,
    start_date: date | None = None,
    end_date: date | None = None,
    actor_id: uuid.UUID | None = None,
    source: str | None = None,
    category: str | None = None,
    event_type: str | None = None,
    db: Session = Depends(get_db),
):
    """Real events only, unioned from tables that carry a genuine
    observation timestamp — no synthetic activity feed.

    Real querying, not just display: start_date/end_date filter each
    event's own observed timestamp (inclusive, end_date treated as
    end-of-day), actor_id/source/event_type/category are applied as real
    SQL WHERE clauses per underlying table before the union — this answers
    the PS's "query the database across a chosen timeline" requirement
    (what did this actor do between two dates, on which platforms, what
    categories), not just render a fixed-size feed. All filters are
    optional and combine with AND; omitting all of them reproduces the
    previous unfiltered "most recent N" behavior.

    `source` matches: a RawPersona/ThreatActivity's own platform value, or
    the fixed string "infra_scan" for infra_finding events (those have no
    per-row platform — see InfraFindingOut). `category` only ever matches
    threat_activity events; combined with event_type=lead_submitted it
    correctly yields zero rows rather than silently ignoring the filter.
    """
    start_dt = (
        datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        if start_date
        else None
    )
    end_dt = (
        datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
        if end_date
        else None
    )

    def _in_range(value: datetime) -> bool:
        # SQLite (used in tests) does not preserve tzinfo on a
        # DateTime(timezone=True) column round-trip — rows come back naive
        # even though they were written tz-aware; Postgres (production)
        # preserves it. Normalizing a naive read as UTC keeps this endpoint
        # correct on both without special-casing the dialect.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if start_dt and value < start_dt:
            return False
        if end_dt and value >= end_dt:
            return False
        return True

    events: list[TimelineEventOut] = []
    include_types = {event_type} if event_type else None

    if (
        (include_types is None or "actor_created" in include_types)
        and source is None
        and category is None
    ):
        query = db.query(Actor)
        if actor_id is not None:
            query = query.filter(Actor.id == actor_id)
        for actor in query.order_by(Actor.created_at.desc()).limit(limit).all():
            if not _in_range(actor.created_at):
                continue
            events.append(
                TimelineEventOut(
                    event_type="actor_created",
                    occurred_at=actor.created_at,
                    summary=f"Actor derived: {actor.label}",
                    actor_id=str(actor.id),
                )
            )

    if (
        (include_types is None or "infra_finding" in include_types)
        and category is None
        and (source is None or source == "infra_scan")
    ):
        finding_query = db.query(InfraFinding)
        if actor_id is not None:
            finding_query = finding_query.filter(InfraFinding.actor_id == actor_id)
        for finding in finding_query.order_by(InfraFinding.discovered_at.desc()).limit(limit).all():
            if not _in_range(finding.discovered_at):
                continue
            events.append(
                TimelineEventOut(
                    event_type="infra_finding",
                    occurred_at=finding.discovered_at,
                    summary=f"{finding.finding_type} on {finding.onion_address}",
                    actor_id=str(finding.actor_id) if finding.actor_id else None,
                    source="infra_scan",
                )
            )

    if (
        (include_types is None or "lead_submitted" in include_types)
        and category is None
        and actor_id is None
    ):
        lead_query = db.query(RawPersona)
        if source is not None:
            lead_query = lead_query.filter(RawPersona.platform == source)
        for lead in lead_query.order_by(RawPersona.submitted_at.desc()).limit(limit).all():
            if not _in_range(lead.submitted_at):
                continue
            events.append(
                TimelineEventOut(
                    event_type="lead_submitted",
                    occurred_at=lead.submitted_at,
                    summary=f"Lead observed: {lead.username} on {lead.platform}",
                    source=lead.platform,
                )
            )

    if include_types is None or "threat_activity" in include_types:
        # Real classified activity — see app.services.threat_categorization.
        # observed_at can be null (source data with no parseable date);
        # those rows are excluded from a *timestamped* timeline rather than
        # shown with a fabricated "now".
        activity_query = db.query(ThreatActivity).filter(ThreatActivity.observed_at.isnot(None))
        if actor_id is not None:
            activity_query = activity_query.filter(ThreatActivity.actor_id == actor_id)
        if source is not None:
            activity_query = activity_query.filter(ThreatActivity.source_platform == source)
        if category is not None:
            activity_query = activity_query.filter(ThreatActivity.category == category)
        activity_query = activity_query.order_by(ThreatActivity.observed_at.desc()).limit(limit)
        for activity in activity_query.all():
            if not _in_range(activity.observed_at):
                continue
            label = CATEGORY_LABELS.get(activity.category, activity.category)
            events.append(
                TimelineEventOut(
                    event_type="threat_activity",
                    occurred_at=activity.observed_at,
                    summary=(
                        f"{label}: {activity.persona_username} on {activity.source_platform}"
                    ),
                    actor_id=str(activity.actor_id) if activity.actor_id else None,
                    source=activity.source_platform,
                    category=activity.category,
                )
            )

    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events[:limit]


@router.get("/sources", response_model=list[SourceBreakdownItem])
def get_source_breakdown(db: Session = Depends(get_db)):
    """Real breakdown of which platform each known identifier was actually
    observed on — not a fixed/fake source-category taxonomy."""
    rows = (
        db.query(Identifier.source_platform, func.count(Identifier.id))
        .group_by(Identifier.source_platform)
        .order_by(func.count(Identifier.id).desc())
        .all()
    )
    return [SourceBreakdownItem(source_platform=platform, count=count) for platform, count in rows]


@router.get("/top-link", response_model=TopLinkOut | None)
def get_top_link(db: Session = Depends(get_db)):
    """The single strongest piece of attribution evidence currently on
    record — highest-weight edge belonging to the highest-confidence actor
    that actually has edges. Returns null (not a fake example) if no
    attribution edges exist yet."""
    edge = (
        db.query(AttributionEdge)
        .join(Actor, Actor.id == AttributionEdge.actor_id)
        .order_by(Actor.confidence_score.desc(), AttributionEdge.weight.desc())
        .first()
    )
    if edge is None:
        return None

    actor = db.query(Actor).filter(Actor.id == edge.actor_id).first()
    actor_edges = (
        db.query(AttributionEdge).filter(AttributionEdge.actor_id == actor.id).all()
    )
    max_stylometry = max(
        (e.weight for e in actor_edges if e.edge_type == "stylometry"), default=0.0
    )
    has_shared_id = any(e.edge_type.startswith("shared_") for e in actor_edges)

    # Signals reflect the *whole cluster's* evidence (matching how
    # confidence_score was actually computed — see app.services.attribution),
    # not just this one displayed edge pair.
    signals = [
        TopLinkSignal(
            label="Stylometric similarity", value=max_stylometry, weight=WEIGHTS["stylometry"]
        ),
        TopLinkSignal(
            label="Shared identifier (wallet / PGP key)",
            value=1.0 if has_shared_id else 0.0,
            weight=WEIGHTS["relationship"],
        ),
        TopLinkSignal(
            label="Infrastructure leak match",
            value=1.0 if actor.infra_findings else 0.0,
            weight=WEIGHTS["infra"],
        ),
    ]

    return TopLinkOut(
        actor_id=str(actor.id),
        actor_label=actor.label,
        confidence=actor.confidence_score,
        username_a=edge.username_a,
        platform_a=edge.platform_a,
        username_b=edge.username_b,
        platform_b=edge.platform_b,
        signals=signals,
    )


@router.get("/infra-findings", response_model=list[InfraFindingRowOut])
def get_infra_findings(limit: int = 20, db: Session = Depends(get_db)):
    """Global (cross-actor) view of InfraFinding rows — real data, same
    table the per-actor profile page reads from."""
    rows = (
        db.query(InfraFinding)
        .options(joinedload(InfraFinding.actor))
        .order_by(InfraFinding.discovered_at.desc())
        .limit(limit)
        .all()
    )
    return [
        InfraFindingRowOut(
            id=str(row.id),
            onion_address=row.onion_address,
            finding_type=row.finding_type,
            detail=row.detail,
            resolved_ip=row.resolved_ip,
            discovered_at=row.discovered_at,
            actor_id=str(row.actor_id) if row.actor_id else None,
            actor_label=row.actor.label if row.actor else None,
        )
        for row in rows
    ]


@router.get("/tor-relays", response_model=list[TorRelayOut])
def get_tor_relays(limit: int = 50, db: Session = Depends(get_db)):
    """Real relay data from the Tor Project's Onionoo API (see
    scripts/ingest_onionoo.py). Infrastructure/network intel, not
    actor attribution — see ARGUS_DATA_RESOURCES.md #3."""
    return (
        db.query(TorRelay)
        .order_by(TorRelay.last_seen.desc().nullslast())
        .limit(limit)
        .all()
    )


@router.get("/threat-events", response_model=list[ThreatEventOut])
def get_threat_events(limit: int = 50, db: Session = Depends(get_db)):
    """Real event metadata from public MISP-format OSINT feeds (see
    scripts/ingest_misp_osint.py). A feed entry is not proof of actor
    ownership — see ARGUS_DATA_RESOURCES.md #4."""
    return (
        db.query(ThreatEvent)
        .order_by(ThreatEvent.event_date.desc().nullslast())
        .limit(limit)
        .all()
    )


@router.get("/breaches", response_model=list[BreachRecordOut])
def get_breach_records(limit: int = 50, db: Session = Depends(get_db)):
    """Real breach directory metadata from Have I Been Pwned's public
    /breaches endpoint (see scripts/ingest_hibp.py). This is breach-level
    metadata, not a record of any individual person's exposure — see
    ARGUS_DATA_RESOURCES.md #8."""
    return (
        db.query(BreachRecord)
        .order_by(BreachRecord.added_date.desc().nullslast())
        .limit(limit)
        .all()
    )


@router.get("/source-registry", response_model=list[DataSourceStatusOut])
def get_source_registry(db: Session = Depends(get_db)):
    """Real per-source record counts and most-recent-observation timestamps,
    queried live from Argus's own tables — never a fabricated online/offline
    indicator (see ARGUS_DATA_RESOURCES.md #13's "Sources online: N/M"
    example, reinterpreted honestly as "records held per source"). Sources
    that require a credential Argus doesn't hold (URLhaus, MalwareBazaar,
    Chainabuse) are still listed, with configured=False and 0 records — a
    real state, not a hidden gap."""
    darkforums_filter = RawPersona.platform == "darkforums_demo_overlay"
    evo_market_filter = RawPersona.platform == "evolution_market"
    evo_forum_filter = RawPersona.platform == "evolution_forum"
    misp_circl_filter = ThreatEvent.source == "misp_circl_osint"
    misp_botvrij_filter = ThreatEvent.source == "misp_botvrij_osint"
    sources = [
        (
            "darkforums", "DarkForums Dataset", "historical",
            darkforums_filter, RawPersona.submitted_at,
        ),
        (
            "evolution_market", "Evolution Dataset — Market", "historical",
            evo_market_filter, RawPersona.submitted_at,
        ),
        (
            "evolution_forum", "Evolution Dataset — Forum", "historical",
            evo_forum_filter, RawPersona.submitted_at,
        ),
        ("tor_onionoo", "Tor Onionoo", "continuously_refreshed", None, TorRelay.observed_at),
        (
            "misp_circl_osint", "MISP — CIRCL OSINT Feed", "feed",
            misp_circl_filter, ThreatEvent.ingested_at,
        ),
        (
            "misp_botvrij_osint", "MISP — botvrij.eu OSINT Feed", "feed",
            misp_botvrij_filter, ThreatEvent.ingested_at,
        ),
        ("hibp", "Have I Been Pwned", "api", None, BreachRecord.ingested_at),
        ("urlhaus", "URLhaus", "feed", None, MaliciousUrl.ingested_at),
        ("malwarebazaar", "MalwareBazaar", "feed", None, MalwareSample.ingested_at),
        ("chainabuse", "Chainabuse", "api", None, AbuseReport.ingested_at),
    ]
    configured_flags = {
        "urlhaus": bool(settings.urlhaus_api_key),
        "malwarebazaar": bool(settings.malwarebazaar_api_key),
        "chainabuse": bool(settings.chainabuse_api_key),
    }

    # Registry key -> the key run_scheduled_collection's own result dict
    # uses for that feed (see app.workers.tasks.run_scheduled_collection) —
    # one ingest_misp_osint() call covers both MISP registry rows, so they
    # share a single "misp_osint" status rather than each getting their own
    # (there is genuinely only one real run to report per feed call).
    SCHEDULED_SOURCE_KEYS = {
        "tor_onionoo": "onionoo",
        "misp_circl_osint": "misp_osint",
        "misp_botvrij_osint": "misp_osint",
        "hibp": "hibp",
    }

    # Most recent scheduled_collection run (see celery_app.py's
    # beat_schedule) — a single query, reused for every scheduled source
    # below rather than one query per row.
    latest_scheduled_job = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.job_type == "scheduled_collection", AnalysisJob.status != "running")
        .order_by(AnalysisJob.created_at.desc())
        .first()
    )
    latest_run_at = None
    per_source_status: dict[str, str] = {}
    if latest_scheduled_job is not None:
        latest_run_at = latest_scheduled_job.completed_at or latest_scheduled_job.created_at
        per_source_status = (latest_scheduled_job.result or {}).get("sources", {})

    out = []
    for key, label, category, extra_filter, timestamp_col in sources:
        model = timestamp_col.class_
        query = db.query(model)
        if extra_filter is not None:
            query = query.filter(extra_filter)
        count = query.count()
        most_recent = query.order_by(timestamp_col.desc().nullslast()).first()
        most_recent_at = (
            getattr(most_recent, timestamp_col.key, None) if most_recent else None
        )

        scheduled_key = SCHEDULED_SOURCE_KEYS.get(key)
        if scheduled_key is not None:
            collection_mode = "scheduled"
            if latest_run_at is None:
                last_run_status = "never_run"
                next_scheduled_at = None
            else:
                raw_status = per_source_status.get(scheduled_key)
                last_run_status = "ok" if raw_status == "ok" else "failed" if raw_status else None
                next_scheduled_at = latest_run_at + timedelta(
                    hours=settings.scheduled_collection_interval_hours
                )
        elif category == "historical":
            collection_mode = "not_applicable"
            last_run_status = None
            next_scheduled_at = None
        else:
            collection_mode = "manual"
            last_run_status = None
            next_scheduled_at = None

        out.append(
            DataSourceStatusOut(
                key=key,
                label=label,
                category=category,
                record_count=count,
                most_recent_at=most_recent_at,
                configured=configured_flags.get(key, True),
                collection_mode=collection_mode,
                last_run_status=last_run_status,
                next_scheduled_at=next_scheduled_at,
            )
        )
    return out


@router.get("/hibp-lookup", response_model=HibpLookupOut)
def hibp_lookup(email: str):
    """On-demand per-email breach check (distinct from /breaches, the public
    directory). Returns configured=False rather than fake results when
    HIBP_API_KEY is unset — see app.services.hibp_lookup."""
    result = check_email_breaches(email)
    return HibpLookupOut(
        configured=result.configured,
        email=result.email,
        breach_names=result.breach_names,
        error=result.error,
    )


# PS-26151 capability A: Tor hidden-service / infrastructure deanonymization.
# Backs the Hidden Services page — every row here is a real InfraFinding
# from app.services.infra_scan, enriched with whatever real correlation
# evidence (app.services.correlation) points at that specific finding.
@router.get("/hidden-services", response_model=HiddenServicesOut)
def get_hidden_services(limit: int = 100, db: Session = Depends(get_db)):
    findings = (
        db.query(InfraFinding)
        .options(joinedload(InfraFinding.actor))
        .order_by(InfraFinding.discovered_at.desc())
        .limit(limit)
        .all()
    )
    finding_ids = [f.id for f in findings]

    # One grouped query for every finding's correlations, not one query per
    # row — the InfraFinding <-> CorrelationEvidence relationship has no
    # ORM-level back_populates (they live in separate modules), so this is
    # a plain filtered query rather than a relationship eager-load.
    correlations_by_finding: dict = {}
    if finding_ids:
        for ev in (
            db.query(CorrelationEvidence)
            .filter(CorrelationEvidence.infra_finding_id.in_(finding_ids))
            .all()
        ):
            correlations_by_finding.setdefault(ev.infra_finding_id, []).append(ev)

    rows = [
        HiddenServiceRowOut(
            id=str(f.id),
            onion_address=f.onion_address,
            finding_type=f.finding_type,
            detail=f.detail,
            resolved_ip=f.resolved_ip,
            discovered_at=f.discovered_at,
            actor_id=str(f.actor_id) if f.actor_id else None,
            actor_label=f.actor.label if f.actor else None,
            correlations=[
                HiddenServiceCorrelationOut(
                    source=ev.source, matched_value=ev.matched_value, description=ev.description
                )
                for ev in correlations_by_finding.get(f.id, [])
            ],
        )
        for f in findings
    ]

    total_findings = db.query(InfraFinding).count()
    distinct_onions = db.query(func.count(func.distinct(InfraFinding.onion_address))).scalar() or 0
    total_correlations = (
        db.query(CorrelationEvidence)
        .filter(CorrelationEvidence.infra_finding_id.isnot(None))
        .count()
    )
    linked_actors = (
        db.query(func.count(func.distinct(InfraFinding.actor_id)))
        .filter(InfraFinding.actor_id.isnot(None))
        .scalar()
        or 0
    )

    return HiddenServicesOut(
        summary=HiddenServicesSummaryOut(
            hidden_services=distinct_onions,
            infrastructure_findings=total_findings,
            correlations=total_correlations,
            linked_actors=linked_actors,
        ),
        rows=rows,
    )


# PS-26151 capability B: cross-platform threat-actor mapping. One generic,
# platform-filtered view over Identifier reused by both the Marketplace
# Intelligence and Forum Intelligence pages — the caller picks which real
# source_platform values count as "marketplace" vs "forum" (see
# MARKETPLACE_PLATFORMS/FORUM_PLATFORMS in the frontend), Argus never
# invents a marketplace/forum taxonomy the database doesn't already have.
@router.get("/identifier-activity", response_model=PersonaActivityOut)
def get_identifier_activity(platforms: str, limit: int = 200, db: Session = Depends(get_db)):
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
    if not platform_list:
        return PersonaActivityOut(
            summary=PersonaActivitySummaryOut(
                total_records=0, unique_handles=0, linked_actors=0,
                pgp_keys=0, wallets=0, by_source=[],
            ),
            records=[],
        )

    base_filter = Identifier.source_platform.in_(platform_list)

    rows = (
        db.query(Identifier)
        .options(joinedload(Identifier.actor))
        .filter(base_filter)
        .order_by(Identifier.last_seen.desc())
        .limit(limit)
        .all()
    )
    records = [
        PersonaActivityRecordOut(
            identifier_type=r.identifier_type,
            value=r.value,
            source_platform=r.source_platform,
            actor_id=str(r.actor_id) if r.actor_id else None,
            actor_label=r.actor.label if r.actor else None,
            last_seen=r.last_seen,
        )
        for r in rows
    ]

    total_records = db.query(Identifier).filter(base_filter).count()
    unique_handles = (
        db.query(Identifier)
        .filter(base_filter, Identifier.identifier_type == "username")
        .count()
    )
    pgp_keys = (
        db.query(Identifier).filter(base_filter, Identifier.identifier_type == "pgp_key").count()
    )
    wallets = (
        db.query(Identifier).filter(base_filter, Identifier.identifier_type == "wallet").count()
    )
    linked_actors = (
        db.query(func.count(func.distinct(Identifier.actor_id)))
        .filter(base_filter, Identifier.actor_id.isnot(None))
        .scalar()
        or 0
    )
    by_source_rows = (
        db.query(Identifier.source_platform, func.count(Identifier.id))
        .filter(base_filter)
        .group_by(Identifier.source_platform)
        .order_by(func.count(Identifier.id).desc())
        .all()
    )

    return PersonaActivityOut(
        summary=PersonaActivitySummaryOut(
            total_records=total_records,
            unique_handles=unique_handles,
            linked_actors=linked_actors,
            pgp_keys=pgp_keys,
            wallets=wallets,
            by_source=[
                SourceBreakdownItem(source_platform=p, count=c) for p, c in by_source_rows
            ],
        ),
        records=records,
    )


# Real derived alerts — every row is sourced from an existing, already-real
# table (Actor/AttributionEdge/CorrelationEvidence/InfraFinding). `severity`
# is computed only from fields already persisted on that row (confidence
# tier, edge_type, finding_type); nothing here is randomly generated or
# invented to populate the page. See AlertOut's docstring.
@router.get("/alerts", response_model=list[AlertOut])
def get_alerts(limit: int = 30, db: Session = Depends(get_db)):
    alerts: list[AlertOut] = []

    high_conf_actors = (
        db.query(Actor)
        .filter(Actor.confidence_score >= HIGH_CONFIDENCE_THRESHOLD)
        .order_by(Actor.updated_at.desc())
        .limit(limit)
        .all()
    )
    for actor in high_conf_actors:
        alerts.append(
            AlertOut(
                alert_type="high_confidence_actor",
                severity="high",
                summary=(
                    f"High-confidence attribution: {actor.label} "
                    f"({actor.confidence_score * 100:.0f}%)"
                ),
                occurred_at=actor.updated_at,
                actor_id=str(actor.id),
            )
        )

    edges = (
        db.query(AttributionEdge).order_by(AttributionEdge.created_at.desc()).limit(limit).all()
    )
    for edge in edges:
        severity = "high" if edge.edge_type.startswith("shared_") else "medium"
        alerts.append(
            AlertOut(
                alert_type="new_linkage",
                severity=severity,
                summary=(
                    f"New linkage: {edge.username_a} ({edge.platform_a}) <-> "
                    f"{edge.username_b} ({edge.platform_b}) — {edge.edge_type}"
                ),
                occurred_at=edge.created_at,
                actor_id=str(edge.actor_id),
            )
        )

    correlations = (
        db.query(CorrelationEvidence)
        .order_by(CorrelationEvidence.ingested_at.desc())
        .limit(limit)
        .all()
    )
    for ev in correlations:
        alerts.append(
            AlertOut(
                alert_type="correlation",
                severity="medium",
                summary=f"{ev.source}: {ev.matched_value} — {ev.description}",
                occurred_at=ev.ingested_at,
                actor_id=str(ev.actor_id) if ev.actor_id else None,
            )
        )

    findings = (
        db.query(InfraFinding).order_by(InfraFinding.discovered_at.desc()).limit(limit).all()
    )
    for finding in findings:
        alerts.append(
            AlertOut(
                alert_type="infra_finding",
                severity="high" if finding.finding_type == "ssl_leak" else "medium",
                summary=(
                    f"Infrastructure finding: {finding.finding_type} "
                    f"on {finding.onion_address}"
                ),
                occurred_at=finding.discovered_at,
                actor_id=str(finding.actor_id) if finding.actor_id else None,
            )
        )

    alerts.sort(key=lambda a: a.occurred_at, reverse=True)
    return alerts[:limit]


# PS-26151 "autonomous/continuous intelligence pipeline" — real, live
# component health, not a static/fabricated status page. Every check is a
# genuine round-trip to the dependency at request time.
@router.get("/system-status", response_model=SystemStatusOut)
def get_system_status(db: Session = Depends(get_db)):
    components: list[ComponentStatusOut] = []

    try:
        db.execute(text("SELECT 1"))
        components.append(ComponentStatusOut(name="PostgreSQL", healthy=True))
    except Exception as exc:  # noqa: BLE001 — genuinely any failure means "unhealthy"
        components.append(
            ComponentStatusOut(name="PostgreSQL", healthy=False, detail=str(exc)[:200])
        )

    try:
        client = get_neo4j_client()
        with client._driver.session() as session:
            session.run("RETURN 1").consume()
        components.append(ComponentStatusOut(name="Neo4j", healthy=True))
    except Exception as exc:  # noqa: BLE001
        components.append(ComponentStatusOut(name="Neo4j", healthy=False, detail=str(exc)[:200]))

    try:
        redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
        components.append(ComponentStatusOut(name="Redis", healthy=True))
    except Exception as exc:  # noqa: BLE001
        components.append(ComponentStatusOut(name="Redis", healthy=False, detail=str(exc)[:200]))

    try:
        pong = celery_app.control.inspect(timeout=1.5).ping() or {}
        worker_count = len(pong)
        components.append(
            ComponentStatusOut(
                name="Celery Workers",
                healthy=worker_count > 0,
                detail=f"{worker_count} worker(s) responding",
            )
        )
    except Exception as exc:  # noqa: BLE001
        components.append(
            ComponentStatusOut(name="Celery Workers", healthy=False, detail=str(exc)[:200])
        )

    return SystemStatusOut(checked_at=_now(), components=components)
