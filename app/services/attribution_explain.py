"""Shared "why this attribution?" computation — used by both
GET /api/actors/{id}/attribution-breakdown and the PDF/CSV export, so the
API and the exported report can never disagree about what evidence
actually supports an actor's confidence_score. Does not touch
scoring.py's compute_confidence/WEIGHTS; this only explains an
already-computed score, it doesn't recompute or influence it.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.actor import Actor, AttributionEdge
from app.models.external import CorrelationEvidence
from app.services.scoring import WEIGHTS


@dataclass
class Signal:
    label: str
    value: float
    weight: float
    available: bool = True


@dataclass
class AttributionExplanation:
    signals: list[Signal]
    evidence_count: int
    sources: list[str]


def explain_attribution(db: Session, actor: Actor) -> AttributionExplanation:
    edges = db.query(AttributionEdge).filter(AttributionEdge.actor_id == actor.id).all()
    max_stylometry = max((e.weight for e in edges if e.edge_type == "stylometry"), default=0.0)
    has_shared_id = any(e.edge_type.startswith("shared_") for e in edges)
    has_stylometry_edges = any(e.edge_type == "stylometry" for e in edges)

    correlation_count = (
        db.query(CorrelationEvidence).filter(CorrelationEvidence.actor_id == actor.id).count()
    )
    sources = sorted({ident.source_platform for ident in actor.identifiers})

    return AttributionExplanation(
        signals=[
            Signal(
                label="Relationship evidence",
                value=1.0 if has_shared_id else 0.0,
                weight=WEIGHTS["relationship"],
                available=True,
            ),
            Signal(
                label="Stylometric evidence",
                value=max_stylometry,
                weight=WEIGHTS["stylometry"],
                available=has_stylometry_edges,
            ),
            Signal(
                label="Infrastructure evidence",
                value=1.0 if actor.infra_findings else 0.0,
                weight=WEIGHTS["infra"],
                available=True,
            ),
        ],
        evidence_count=len(edges) + correlation_count,
        sources=sources,
    )
