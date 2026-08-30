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
    matched_identifier: str | None = None


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
    observed_at: datetime | None
    ingested_at: datetime
