from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class StatCard(BaseModel):
    """A single dashboard metric. `trend_pct` and `sparkline` are omitted
    (not null-faked) when there isn't enough real historical data to compute
    them honestly — see dashboard.py's _stat_card."""

    label: str
    value: int
    trend_pct: float | None = None
    sparkline: list[int] | None = None


class DashboardStatsOut(BaseModel):
    threat_actors: StatCard
    unique_handles: StatCard
    pgp_keys: StatCard
    wallets_tracked: StatCard
    attribution_links: StatCard
    high_confidence_links: StatCard


class TimelineEventOut(BaseModel):
    event_type: str  # actor_created | infra_finding | lead_submitted | threat_activity
    occurred_at: datetime
    summary: str
    actor_id: str | None = None
    # Real source/platform this event was observed on, when the underlying
    # row has one — None for actor_created (an Argus-internal derivation,
    # not something observed on a platform). Lets the UI answer "which
    # platforms were involved" per the PS's timeline-query requirement.
    source: str | None = None
    # Only meaningful for threat_activity events (see
    # app.services.threat_categorization.CATEGORY_LABELS) — None otherwise.
    category: str | None = None


class InfraFindingRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    onion_address: str
    finding_type: str
    detail: dict
    resolved_ip: str | None
    discovered_at: datetime
    actor_id: str | None
    actor_label: str | None


class SourceBreakdownItem(BaseModel):
    source_platform: str
    count: int


class TopLinkSignal(BaseModel):
    label: str
    value: float  # 0-1
    weight: float  # 0-1, from app.services.scoring.WEIGHTS


class TopLinkOut(BaseModel):
    actor_id: str
    actor_label: str
    confidence: float
    username_a: str
    platform_a: str
    username_b: str
    platform_b: str
    signals: list[TopLinkSignal]


class TorRelayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fingerprint: str
    nickname: str
    ip_addresses: list[str]
    country: str | None
    running: bool
    flags: list[str]
    first_seen: datetime | None
    last_seen: datetime | None


class ThreatEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    event_uuid: str
    org_name: str | None
    info: str
    tags: list[str]
    event_date: date | None
    threat_level_id: int | None


class BreachRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    domain: str | None
    breach_date: date | None
    pwn_count: int
    data_classes: list[str]
    is_verified: bool


class DataSourceStatusOut(BaseModel):
    """Real per-source record counts and the timestamp of the most recent
    row Argus actually holds for that source — never a fabricated
    "online/offline" status. A source with 0 records and configured=True
    simply hasn't been ingested yet; configured=False means no API
    credential is set at all (see app.core.config), which is a genuinely
    different state and must not be presented the same way in the UI."""

    key: str
    label: str
    category: str  # historical | continuously_refreshed | feed | api
    record_count: int
    most_recent_at: datetime | None
    configured: bool = True
    # scheduled | manual | not_applicable — "scheduled" only for the three
    # sources app.workers.tasks.run_scheduled_collection actually re-pulls
    # (see celery_app.py's beat_schedule); "manual" for a source ingested
    # via a CLI script with no recurring trigger; "not_applicable" for a
    # historical dataset that was never meant to be re-pulled.
    collection_mode: str = "manual"
    # ok | failed | never_run | None — this source's outcome in the MOST
    # RECENT scheduled_collection AnalysisJob's per-source result (see
    # run_scheduled_collection), or None for a source with no scheduled
    # collection at all. Real, not inferred — a genuinely different state
    # from "0 records" (a feed can be configured, scheduled, and still
    # currently failing, e.g. the remote API changed shape).
    last_run_status: str | None = None
    # When the next scheduled_collection run is expected, computed from the
    # most recent run's timestamp + settings.scheduled_collection_interval_hours
    # — None for a source with no scheduled collection.
    next_scheduled_at: datetime | None = None


class HibpLookupOut(BaseModel):
    configured: bool
    email: str
    breach_names: list[str] | None = None
    error: str | None = None


class HiddenServiceCorrelationOut(BaseModel):
    """One deterministic external-intel match against this specific finding
    — a subset of CorrelationEvidence scoped to infra_finding_id, not a
    separate fabricated concept."""

    source: str
    matched_value: str
    description: str


class HiddenServiceRowOut(BaseModel):
    """One InfraFinding, enriched with whatever real correlation evidence
    (app.services.correlation) points at it — the PS's 'hidden-service
    infrastructure correlation' capability, expressed with data Argus
    actually holds rather than a fabricated per-relay claim."""

    id: str
    onion_address: str
    finding_type: str
    detail: dict
    resolved_ip: str | None
    discovered_at: datetime
    actor_id: str | None
    actor_label: str | None
    correlations: list[HiddenServiceCorrelationOut]


class HiddenServicesSummaryOut(BaseModel):
    hidden_services: int  # distinct onion addresses with at least one finding
    infrastructure_findings: int  # total InfraFinding rows
    correlations: int  # total CorrelationEvidence rows tied to an infra finding
    linked_actors: int  # distinct actors with at least one finding


class HiddenServicesOut(BaseModel):
    summary: HiddenServicesSummaryOut
    rows: list[HiddenServiceRowOut]


class PersonaActivityRecordOut(BaseModel):
    """One Identifier row, in the shape Marketplace/Forum Intelligence need
    — real rows from the same table Actor Profile's Identifiers section
    reads, just pre-filtered to a caller-chosen set of source platforms."""

    identifier_type: str
    value: str
    source_platform: str
    actor_id: str | None
    actor_label: str | None
    last_seen: datetime


class PersonaActivitySummaryOut(BaseModel):
    total_records: int
    unique_handles: int
    linked_actors: int
    pgp_keys: int
    wallets: int
    by_source: list[SourceBreakdownItem]


class PersonaActivityOut(BaseModel):
    summary: PersonaActivitySummaryOut
    records: list[PersonaActivityRecordOut]


class AlertOut(BaseModel):
    """A real, already-persisted event reframed for investigator scanning —
    never a synthetic notification. `severity` is computed purely from real
    fields already on the underlying row (confidence_score, edge_type,
    finding_type), the same values the Dashboard/Actor Profile already
    display; it is not a new judgment invented for this view."""

    alert_type: str  # high_confidence_actor | new_linkage | correlation | infra_finding
    severity: str  # high | medium | low
    summary: str
    occurred_at: datetime
    actor_id: str | None = None


class ComponentStatusOut(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None


class SystemStatusOut(BaseModel):
    checked_at: datetime
    components: list[ComponentStatusOut]
