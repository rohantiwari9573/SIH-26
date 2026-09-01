"""Derives actor-level intelligence purely by aggregating evidence Argus
already has — RawActivity, RawPersona, Identifier, ThreatActivity. Adds no
new external data, invents nothing, and NEVER touches confidence_score or
any input to app.services.scoring — this is a read-only summary layer over
existing rows, exactly like app.services.threat_activity and
app.services.attribution_explain.

Every number here must be traceable back to a real row already exposed
elsewhere in the API (identifiers, /threat-activity, /evidence). Absence
(None / 0 / empty list) is always the honest "not observable from current
evidence" state, never a fabricated default.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.actor import Actor, Identifier, RawActivity, RawPersona, ThreatActivity


@dataclass
class PlatformBreakdown:
    platform: str
    identifier_count: int
    activity_count: int
    first_activity: datetime | None
    last_activity: datetime | None


@dataclass
class ActorEnrichment:
    platforms: list[PlatformBreakdown]
    total_activities: int
    classified_activities: int
    first_observed: datetime | None
    last_observed: datetime | None
    active_duration_days: int | None
    days_since_last_observed: int | None
    posting_frequency_per_week: float | None
    shared_wallet_across_platforms: bool
    shared_pgp_key_across_platforms: bool
    platform_migration_order: list[str]


def _actor_raw_persona_ids(db: Session, actor_id: uuid.UUID) -> list[uuid.UUID]:
    """Personas belonging to this actor, found via the same (username,
    platform) key app.services.pipeline.run_full_analysis itself uses to
    decide which RawPersona a persona-derived Identifier came from — an
    actor's username-type Identifier rows carry that exact pair. This is
    the only non-fabricated way to walk from an Actor back to its raw,
    per-listing/per-post activity, since RawActivity has no direct actor_id
    (only classified rows get one, via ThreatActivity — see that model's
    docstring for why unclassified activity is real but unlabeled)."""
    rows = (
        db.query(RawPersona.id)
        .join(
            Identifier,
            and_(
                Identifier.value == RawPersona.username,
                Identifier.source_platform == RawPersona.platform,
            ),
        )
        .filter(Identifier.actor_id == actor_id, Identifier.identifier_type == "username")
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def _as_aware_utc(dt: datetime) -> datetime:
    """Postgres round-trips DateTime(timezone=True) as tz-aware; SQLite
    (used in tests, and by anyone running the app without Docker) silently
    drops the tzinfo and hands back a naive datetime. Every timestamp this
    module reads is written via app.models.actor._now(), which is always
    UTC, so treating a naive value as UTC is a safe, non-fabricating
    normalization — not a guess about what timezone it "really" was."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _shared_across_platforms(identifiers: list[Identifier], identifier_type: str) -> bool:
    by_value: dict[str, set[str]] = {}
    for ident in identifiers:
        if ident.identifier_type != identifier_type:
            continue
        by_value.setdefault(ident.value, set()).add(ident.source_platform)
    return any(len(platform_set) > 1 for platform_set in by_value.values())


def compute_actor_enrichment(db: Session, actor: Actor) -> ActorEnrichment:
    persona_ids = _actor_raw_persona_ids(db, actor.id)

    activities: list[RawActivity] = (
        db.query(RawActivity).filter(RawActivity.raw_persona_id.in_(persona_ids)).all()
        if persona_ids
        else []
    )

    classified_count = (
        db.query(ThreatActivity).filter(ThreatActivity.actor_id == actor.id).count()
    )

    # Identifier counts per platform (all identifier types — a platform
    # where only a wallet or PGP key was observed, with no username row,
    # should still be counted as a platform this actor was seen on).
    identifier_platform_counts: dict[str, int] = {}
    for ident in actor.identifiers:
        identifier_platform_counts[ident.source_platform] = (
            identifier_platform_counts.get(ident.source_platform, 0) + 1
        )

    activity_by_platform: dict[str, list[RawActivity]] = {}
    for a in activities:
        activity_by_platform.setdefault(a.platform, []).append(a)

    all_platforms = sorted(set(identifier_platform_counts) | set(activity_by_platform))
    platforms: list[PlatformBreakdown] = []
    for platform in all_platforms:
        items = activity_by_platform.get(platform, [])
        observed_dates = [a.observed_at for a in items if a.observed_at is not None]
        platforms.append(
            PlatformBreakdown(
                platform=platform,
                identifier_count=identifier_platform_counts.get(platform, 0),
                activity_count=len(items),
                first_activity=min(observed_dates) if observed_dates else None,
                last_activity=max(observed_dates) if observed_dates else None,
            )
        )
    # Display order: busiest platform first — matches how every other
    # count-based list in this app (threat category summary, source
    # breakdown) is already ordered.
    platforms.sort(key=lambda p: (-p.activity_count, p.platform))

    all_observed = [a.observed_at for a in activities if a.observed_at is not None]
    first_observed = min(all_observed) if all_observed else None
    last_observed = max(all_observed) if all_observed else None

    active_duration_days: int | None = None
    posting_frequency_per_week: float | None = None
    if first_observed is not None and last_observed is not None:
        active_duration_days = (last_observed - first_observed).days
        weeks = max(active_duration_days / 7, 1 / 7)
        posting_frequency_per_week = round(len(activities) / weeks, 2)

    days_since_last_observed: int | None = None
    if last_observed is not None:
        days_since_last_observed = (
            datetime.now(timezone.utc) - _as_aware_utc(last_observed)
        ).days

    # Migration order: platforms with a real timestamped first activity,
    # ordered earliest-first; platforms with activity but no timestamp (or
    # identifier-only platforms with no activity at all) are appended
    # afterward, alphabetically — present in the record, but genuinely not
    # orderable in time from current evidence.
    dated = sorted(
        (p for p in platforms if p.first_activity is not None), key=lambda p: p.first_activity
    )
    undated = sorted(p.platform for p in platforms if p.first_activity is None)
    platform_migration_order = [p.platform for p in dated] + undated

    return ActorEnrichment(
        platforms=platforms,
        total_activities=len(activities),
        classified_activities=classified_count,
        first_observed=first_observed,
        last_observed=last_observed,
        active_duration_days=active_duration_days,
        days_since_last_observed=days_since_last_observed,
        posting_frequency_per_week=posting_frequency_per_week,
        shared_wallet_across_platforms=_shared_across_platforms(actor.identifiers, "wallet"),
        shared_pgp_key_across_platforms=_shared_across_platforms(actor.identifiers, "pgp_key"),
        platform_migration_order=platform_migration_order,
    )
