"""Dashboard-level aggregate views. Every number here is a real query against
Argus's own tables — no hardcoded/placeholder figures. Where a real trend or
sparkline can't be honestly computed yet (not enough historical spread in
the data), the field is omitted rather than filled with a fake value; see
StatCard's docstring."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.actor import Actor, AttributionEdge, Identifier, InfraFinding, RawPersona
from app.models.external import (
    AbuseReport,
    BreachRecord,
    MaliciousUrl,
    MalwareSample,
    ThreatEvent,
    TorRelay,
)
from app.schemas.dashboard import (
    BreachRecordOut,
    DashboardStatsOut,
    DataSourceStatusOut,
    HibpLookupOut,
    InfraFindingRowOut,
    SourceBreakdownItem,
    StatCard,
    ThreatEventOut,
    TimelineEventOut,
    TopLinkOut,
    TopLinkSignal,
    TorRelayOut,
)
from app.services.hibp_lookup import check_email_breaches
from app.services.scoring import WEIGHTS

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
def get_dashboard_timeline(limit: int = 20, db: Session = Depends(get_db)):
    """Real events only, unioned from tables that carry a genuine
    observation timestamp — no synthetic activity feed."""
    events: list[TimelineEventOut] = []

    for actor in db.query(Actor).order_by(Actor.created_at.desc()).limit(limit).all():
        events.append(
            TimelineEventOut(
                event_type="actor_created",
                occurred_at=actor.created_at,
                summary=f"Actor derived: {actor.label}",
                actor_id=str(actor.id),
            )
        )

    finding_query = db.query(InfraFinding).order_by(InfraFinding.discovered_at.desc()).limit(limit)
    for finding in finding_query.all():
        events.append(
            TimelineEventOut(
                event_type="infra_finding",
                occurred_at=finding.discovered_at,
                summary=f"{finding.finding_type} on {finding.onion_address}",
                actor_id=str(finding.actor_id) if finding.actor_id else None,
            )
        )

    for lead in db.query(RawPersona).order_by(RawPersona.submitted_at.desc()).limit(limit).all():
        events.append(
            TimelineEventOut(
                event_type="lead_submitted",
                occurred_at=lead.submitted_at,
                summary=f"Lead observed: {lead.username} on {lead.platform}",
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
        out.append(
            DataSourceStatusOut(
                key=key,
                label=label,
                category=category,
                record_count=count,
                most_recent_at=most_recent_at,
                configured=configured_flags.get(key, True),
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
