import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IdentifierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    identifier_type: str
    value: str
    source_platform: str
    first_seen: datetime
    last_seen: datetime


class InfraFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    onion_address: str
    finding_type: str
    detail: dict
    severity: str | None
    scan_job_id: uuid.UUID | None
    resolved_ip: str | None
    discovered_at: datetime


class StyleProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    identifier_id: uuid.UUID
    feature_vector: dict
    sample_count: int


class AttributionEdgeOut(BaseModel):
    """One piece of evidence the attribution pipeline used to merge two
    personas into this actor — the 'why' behind the confidence score."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username_a: str
    platform_a: str
    username_b: str
    platform_b: str
    edge_type: str
    weight: float


class RealWorldEntityOut(BaseModel):
    """A SUSPECTED real-world entity this actor's infrastructure/correlation
    evidence points toward — see app.services.entity_linkage. `confidence`
    is always a qualitative, source-traceable label (never a fabricated
    float), and the UI MUST label this "Suspected Real-World Entity," never
    "Confirmed Identity" — see that module's docstring."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_name: str
    entity_type: str
    relationship_type: str
    evidence: dict
    source: str
    source_record_id: str
    observed_at: datetime | None
    confidence: str
    explanation: str
    created_at: datetime


class ActorProfileOut(BaseModel):
    """The single unified view the PS asks for: identifiers + infra + confidence, together."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    confidence_score: float
    created_at: datetime
    updated_at: datetime
    identifiers: list[IdentifierOut] = []
    infra_findings: list[InfraFindingOut] = []
    style_profiles: list[StyleProfileOut] = []
    attribution_edges: list[AttributionEdgeOut] = []
    real_world_entities: list[RealWorldEntityOut] = []


class GraphNode(BaseModel):
    type: str
    value: str
    source_platform: str | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str
    weight: float


class ActorGraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    node_count: int
    edge_count: int


class ActorSearchResult(BaseModel):
    id: uuid.UUID
    label: str
    confidence_score: float
    updated_at: datetime
    matched_identifier: str | None = None


class PaginatedActorsOut(BaseModel):
    """Server-side pagination for GET /api/actors — with 141 real derived
    actors already exceeding the old hardcoded limit=100, a flat array
    silently hid real actors rather than truncating honestly. total lets the
    UI show "showing 100 of 141" and page through the rest, instead of
    loading everything into React to hide most of it client-side."""

    items: list[ActorSearchResult]
    total: int
    page: int
    page_size: int


class AttributionSignal(BaseModel):
    label: str
    value: float  # 0-1
    weight: float  # 0-1, from app.services.scoring.WEIGHTS
    available: bool = True  # False when there's genuinely no signal to report


class AttributionBreakdownOut(BaseModel):
    """Explains confidence_score for one actor — the same three-signal
    computation dashboard.py's get_top_link already does for the single
    highest-confidence actor, generalized to any actor_id. Values are real
    aggregates over that actor's own AttributionEdge rows (see
    app.services.attribution/pipeline), never fabricated to make a UI look
    populated."""

    signals: list[AttributionSignal]
    evidence_count: int
    sources: list[str]


class ThreatActivityOut(BaseModel):
    """One classified activity (a single real listing/post) supporting a
    threat category for this actor — see app.models.actor.ThreatActivity.
    Answers who/what/where/when/from-which-source/what-evidence/what-
    category/how-confident in one row; never fed into confidence_score."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    persona_username: str
    source_platform: str
    source_record_id: str
    title: str | None
    observed_at: datetime | None
    category: str
    category_label: str
    classification_reason: str
    classification_method: str
    classification_confidence: str


class ThreatCategorySummary(BaseModel):
    """One category's aggregation across an actor's classified activities —
    the ActorProfileView "Threat Activity" section reads this, not the raw
    ThreatActivityOut list, for its top-level counts."""

    category: str
    category_label: str
    activity_count: int
    sources: list[str]


class ActorThreatActivityOut(BaseModel):
    """summary is always the full aggregation across ALL of this actor's
    activities (cheap — one row per category). activities is paginated —
    with real actors already returning 150+ evidence rows, the UI fetches
    one category's evidence page at a time (see ActorProfileView) rather
    than every activity up front. activities_total is the count for the
    current category filter (or all activities if none given), so the UI
    can render "page X of Y" without a second request."""

    summary: list[ThreatCategorySummary]
    activities: list[ThreatActivityOut]
    activities_total: int
    page: int
    page_size: int


class PlatformBreakdownOut(BaseModel):
    """One platform this actor was observed on, with real counts/timestamps
    from that platform's identifiers and RawActivity rows — see
    app.services.actor_enrichment."""

    platform: str
    identifier_count: int
    activity_count: int
    first_activity: datetime | None
    last_activity: datetime | None


class ActorEnrichmentOut(BaseModel):
    """Derived purely by aggregating this actor's existing RawActivity/
    Identifier/ThreatActivity rows — see app.services.actor_enrichment.
    Never fabricated, never fed into confidence_score. A None/0/empty value
    means the underlying evidence genuinely doesn't support that field
    (e.g. no RawActivity has an observed_at timestamp), not that Argus
    failed to look."""

    platforms: list[PlatformBreakdownOut]
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


class CorrelationEvidenceOut(BaseModel):
    """One deterministic match between a live/feed source and this actor's
    known infrastructure — see app.services.correlation. Enrichment, not an
    attribution signal: never fed into confidence_score."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    source_record_id: str
    evidence_type: str
    matched_value: str
    description: str
    confidence: str
    observed_at: datetime | None
    ingested_at: datetime
