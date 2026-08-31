import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.actor import Actor, Identifier
from app.models.external import CorrelationEvidence
from app.schemas.actor import (
    ActorGraphOut,
    ActorProfileOut,
    ActorSearchResult,
    ActorThreatActivityOut,
    AttributionBreakdownOut,
    AttributionSignal,
    CorrelationEvidenceOut,
    ThreatActivityOut,
    ThreatCategorySummary,
)
from app.services.attribution_explain import explain_attribution
from app.services.graph.relationship_mapper import get_actor_graph
from app.services.threat_activity import get_actor_threat_activities, summarize_by_category
from app.services.threat_categorization import CATEGORY_LABELS

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
        .options(joinedload(Identifier.actor))
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
                updated_at=actor.updated_at,
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

    explanation = explain_attribution(db, actor)
    return AttributionBreakdownOut(
        signals=[AttributionSignal(**vars(s)) for s in explanation.signals],
        evidence_count=explanation.evidence_count,
        sources=explanation.sources,
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


@router.get("/{actor_id}/threat-activity", response_model=ActorThreatActivityOut)
def get_actor_threat_activity(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    """"What type of threat activity is this actor associated with?" — a
    SEPARATE question from attribution-breakdown's "why is this the same
    actor?" (see app.services.threat_categorization's module docstring).
    Every row is a real classified ThreatActivity; an empty summary/activity
    list is the honest, expected result for an actor with no classifiable
    activity content (e.g. one built only from Tor Onionoo/MISP/HIBP
    correlation, which carries no narrative activity text at all)."""
    actor = db.query(Actor).filter(Actor.id == actor_id).first()
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    rows = get_actor_threat_activities(db, actor_id)

    activities = [
        ThreatActivityOut(
            id=row.id,
            actor_id=row.actor_id,
            persona_username=row.persona_username,
            source_platform=row.source_platform,
            source_record_id=row.source_record_id,
            title=row.title,
            observed_at=row.observed_at,
            category=row.category,
            category_label=CATEGORY_LABELS.get(row.category, row.category),
            classification_reason=row.classification_reason,
            classification_method=row.classification_method,
            classification_confidence=row.classification_confidence,
        )
        for row in rows
    ]

    summary = [
        ThreatCategorySummary(
            category=s.category,
            category_label=s.category_label,
            activity_count=s.activity_count,
            sources=s.sources,
        )
        for s in summarize_by_category(rows)
    ]

    return ActorThreatActivityOut(summary=summary, activities=activities)


@router.get("", response_model=list[ActorSearchResult])
def list_actors(db: Session = Depends(get_db)):
    actors = db.query(Actor).order_by(Actor.confidence_score.desc()).limit(100).all()
    return [
        ActorSearchResult(
            id=a.id, label=a.label, confidence_score=a.confidence_score, updated_at=a.updated_at
        )
        for a in actors
    ]
