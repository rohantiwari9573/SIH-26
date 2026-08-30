import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.actor import Actor, AttributionEdge, Identifier
from app.models.external import CorrelationEvidence
from app.schemas.actor import (
    ActorGraphOut,
    ActorProfileOut,
    ActorSearchResult,
    AttributionBreakdownOut,
    AttributionSignal,
    CorrelationEvidenceOut,
)
from app.services.graph.relationship_mapper import get_actor_graph
from app.services.scoring import WEIGHTS

router = APIRouter(prefix="/api/actors", tags=["actors"], dependencies=[Depends(get_current_user)])

# UI filter category -> real Neo4j node `type` values (see
# app.services.graph.neo4j_client.Neo4jClient.upsert_identifier and
# app.services.correlation for where each type string is actually written).
# Deliberately does NOT include categories the graph has no real node for
# (e.g. a standalone "Actor" node, a distinct "MISP Event" node, or a
# generic "Evidence" node) — Argus's Neo4j schema only ever stores
# Identifier nodes; inventing extra node types to fill out a checkbox list
# would violate the no-fake-data rule this project has held to throughout.
ENTITY_TYPE_GROUPS: dict[str, list[str]] = {
    "handles": ["username"],
    "wallets": ["wallet"],
    "pgp_keys": ["pgp_key"],
    "infrastructure": ["onion_address"],
    "tor_intelligence": ["corr:tor_onionoo"],
    "threat_intelligence": ["corr:misp_circl_osint", "corr:misp_botvrij_osint"],
    "breach_intelligence": ["corr:hibp"],
}

# UI filter category -> real Neo4j relationship `relationship` property
# values (see relationship_mapper.ingest_marketplace_record and
# app.services.correlation._record_evidence). "Attribution" is deliberately
# not mapped to a Neo4j edge — attribution merges are expressed by two
# personas sharing the same identifier node, not by a separate edge type;
# that evidence already lives in AttributionEdge (Postgres) and is exposed
# via the actor profile, not duplicated here as a fabricated relationship.
RELATIONSHIP_TYPE_GROUPS: dict[str, list[str]] = {
    "identity": ["USES_KEY", "VOUCHES_FOR"],
    "financial": ["USES_WALLET"],
    "infrastructure": ["RELATED_TO"],
    "threat_intelligence": ["MATCHES"],
}

# UI source filter -> real source_platform values written onto Neo4j nodes.
SOURCE_FILTER_VALUES: dict[str, str] = {
    "darkforums": "darkforums_demo_overlay",
    "evolution_market": "evolution_market",
    "evolution_forum": "evolution_forum",
    "tor_onionoo": "tor_onionoo",
    "misp_circl": "misp_circl_osint",
    "misp_botvrij": "misp_botvrij_osint",
    "hibp": "hibp",
}


def _resolve_csv_group(raw: str | None, groups: dict[str, list[str]]) -> list[str] | None:
    """Expands a comma-separated list of UI category keys (e.g.
    "wallets,pgp_keys") into the real values Neo4j stores, ignoring any
    unrecognized key rather than erroring — a stale/renamed filter option
    should degrade to "no filter for that key", not break the endpoint."""
    if not raw:
        return None
    resolved: list[str] = []
    for key in raw.split(","):
        resolved.extend(groups.get(key.strip(), []))
    return resolved or None


@router.get("/search", response_model=list[ActorSearchResult])
def search_actors(q: str, db: Session = Depends(get_db)):
    """Query interface: search by any known identifier value (username, wallet, PGP key)."""
    matches = (
        db.query(Identifier)
        .filter(Identifier.value.ilike(f"%{q}%"))
        .filter(Identifier.actor_id.isnot(None))
        .limit(50)
        .all()
    )

    results: dict[uuid.UUID, ActorSearchResult] = {}
    for identifier in matches:
        actor = identifier.actor
        if actor.id not in results:
            results[actor.id] = ActorSearchResult(
                id=actor.id,
                label=actor.label,
                confidence_score=actor.confidence_score,
                matched_identifier=identifier.value,
            )
    return list(results.values())


@router.get("/{actor_id}", response_model=ActorProfileOut)
def get_actor_profile(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    """Unified actor profile: identifiers + infra findings + confidence metrics, in one view."""
    actor = (
        db.query(Actor)
        .options(
            selectinload(Actor.identifiers),
            selectinload(Actor.infra_findings),
            selectinload(Actor.style_profiles),
            selectinload(Actor.attribution_edges),
        )
        .filter(Actor.id == actor_id)
        .first()
    )
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return actor


@router.get("/{actor_id}/graph", response_model=ActorGraphOut)
def get_actor_relationship_graph(
    actor_id: uuid.UUID,
    depth: int = 1,
    entity_types: str | None = None,
    relationship_types: str | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
):
    """Relationship-mapping pillar's output, in the shape a UI can actually draw:
    nodes + edges around this actor's known identifiers, sourced live from Neo4j.
    depth=1 (default) is direct identifiers/infra/correlation matches; depth=2
    also pulls in whatever those are connected to (e.g. another actor sharing
    the same wallet). Clamped to [1,3] — an investigative tool, not an
    invitation to pull the whole graph.

    entity_types/relationship_types: comma-separated UI category keys (see
    ENTITY_TYPE_GROUPS/RELATIONSHIP_TYPE_GROUPS above), applied as real
    Cypher WHERE clauses in Neo4jClient.get_subgraph — not hidden client-side
    with CSS, so the returned node_count/edge_count are always accurate for
    whatever's actually being displayed. source is a single UI source key
    (SOURCE_FILTER_VALUES); unrecognized/omitted means no filter."""
    depth = max(1, min(depth, 3))
    actor = (
        db.query(Actor)
        .options(selectinload(Actor.identifiers))
        .filter(Actor.id == actor_id)
        .first()
    )
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    identifier_values = [ident.value for ident in actor.identifiers]
    graph = get_actor_graph(
        identifier_values,
        depth=depth,
        entity_types=_resolve_csv_group(entity_types, ENTITY_TYPE_GROUPS),
        relationship_types=_resolve_csv_group(relationship_types, RELATIONSHIP_TYPE_GROUPS),
        source=SOURCE_FILTER_VALUES.get(source) if source else None,
    )
    return {**graph, "node_count": len(graph["nodes"]), "edge_count": len(graph["edges"])}


@router.get("/{actor_id}/attribution-breakdown", response_model=AttributionBreakdownOut)
def get_actor_attribution_breakdown(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    """"Why this attribution?" — the same per-signal computation
    dashboard.py's get_top_link already does for the single strongest
    actor, generalized to any actor. Does not touch scoring.py's
    compute_confidence/WEIGHTS — this only explains an already-computed
    confidence_score, it doesn't recompute or influence it."""
    actor = (
        db.query(Actor)
        .options(selectinload(Actor.identifiers), selectinload(Actor.infra_findings))
        .filter(Actor.id == actor_id)
        .first()
    )
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    edges = db.query(AttributionEdge).filter(AttributionEdge.actor_id == actor_id).all()
    max_stylometry = max((e.weight for e in edges if e.edge_type == "stylometry"), default=0.0)
    has_shared_id = any(e.edge_type.startswith("shared_") for e in edges)
    has_stylometry_edges = any(e.edge_type == "stylometry" for e in edges)

    correlation_count = (
        db.query(CorrelationEvidence).filter(CorrelationEvidence.actor_id == actor_id).count()
    )

    sources = sorted({ident.source_platform for ident in actor.identifiers})

    return AttributionBreakdownOut(
        signals=[
            AttributionSignal(
                label="Relationship evidence",
                value=1.0 if has_shared_id else 0.0,
                weight=WEIGHTS["relationship"],
                available=True,
            ),
            AttributionSignal(
                label="Stylometric evidence",
                value=max_stylometry,
                weight=WEIGHTS["stylometry"],
                available=has_stylometry_edges,
            ),
            AttributionSignal(
                label="Infrastructure evidence",
                value=1.0 if actor.infra_findings else 0.0,
                weight=WEIGHTS["infra"],
                available=True,
            ),
        ],
        evidence_count=len(edges) + correlation_count,
        sources=sources,
    )


@router.get("/{actor_id}/evidence", response_model=list[CorrelationEvidenceOut])
def get_actor_correlation_evidence(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    """Deterministic matches between this actor's confirmed infrastructure
    and real live/feed intelligence (Tor Onionoo, MISP CIRCL, MISP
    botvrij.eu, HIBP) — see app.services.correlation. Enrichment the
    investigator can inspect, not a hidden input to confidence_score; an
    empty list is the normal/expected state for most actors, since Argus's
    demo infrastructure has no reason to overlap with real external feeds."""
    actor = db.query(Actor).filter(Actor.id == actor_id).first()
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return (
        db.query(CorrelationEvidence)
        .filter(CorrelationEvidence.actor_id == actor_id)
        .order_by(CorrelationEvidence.ingested_at.desc())
        .all()
    )


@router.get("", response_model=list[ActorSearchResult])
def list_actors(db: Session = Depends(get_db)):
    actors = db.query(Actor).order_by(Actor.confidence_score.desc()).limit(100).all()
    return [
        ActorSearchResult(id=a.id, label=a.label, confidence_score=a.confidence_score)
        for a in actors
    ]
