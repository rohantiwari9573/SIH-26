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


class GraphNode(BaseModel):
    type: str
    value: str


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str
    weight: float


class ActorGraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ActorSearchResult(BaseModel):
    id: uuid.UUID
    label: str
    confidence_score: float
    matched_identifier: str | None = None
