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
    event_type: str  # actor_created | infra_finding | lead_submitted | attribution_edge
    occurred_at: datetime
    summary: str
    actor_id: str | None = None


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


class HibpLookupOut(BaseModel):
    configured: bool
    email: str
    breach_names: list[str] | None = None
    error: str | None = None
