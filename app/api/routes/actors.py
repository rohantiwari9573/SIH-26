import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.actor import Actor, Identifier
from app.models.external import CorrelationEvidence
from app.schemas.actor import (
    ActorEnrichmentOut,
    ActorGraphOut,
    ActorProfileOut,
    ActorSearchResult,
    ActorThreatActivityOut,
    AttributionBreakdownOut,
    AttributionSignal,
    CorrelationEvidenceOut,
    PaginatedActorsOut,
    PlatformBreakdownOut,
    ThreatActivityOut,
    ThreatCategorySummary,
)
from app.schemas.ai_analysis import (
    ActorAIAnalysisOut,
    AIEvidenceSampleOut,
    AIPairAnalysisOut,
    AIPersonaSummary,
    AISignalOut,
)
from app.services.actor_ai_analysis import compute_actor_ai_analysis
from app.services.actor_enrichment import compute_actor_enrichment
from app.services.ai_stylometry import METHOD_DESCRIPTION, InsufficientData, PairAnalysis
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
            selectinload(Actor.real_world_entities),
        )
        .filter(Actor.id == actor_id)
        .first()
    )
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return actor


@router.get("/{actor_id}/enrichment", response_model=ActorEnrichmentOut)
def get_actor_enrichment(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    """Derived activity/behavioral/cross-platform statistics for this actor,
    aggregated purely from RawActivity/Identifier/ThreatActivity rows already
    tied to it — see app.services.actor_enrichment. Adds no new data source
    and never touches confidence_score."""
    actor = (
        db.query(Actor)
        .options(selectinload(Actor.identifiers))
        .filter(Actor.id == actor_id)
        .first()
    )
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    enrichment = compute_actor_enrichment(db, actor)
    return ActorEnrichmentOut(
        platforms=[PlatformBreakdownOut(**vars(p)) for p in enrichment.platforms],
        total_activities=enrichment.total_activities,
        classified_activities=enrichment.classified_activities,
        first_observed=enrichment.first_observed,
        last_observed=enrichment.last_observed,
        active_duration_days=enrichment.active_duration_days,
        days_since_last_observed=enrichment.days_since_last_observed,
        posting_frequency_per_week=enrichment.posting_frequency_per_week,
        shared_wallet_across_platforms=enrichment.shared_wallet_across_platforms,
        shared_pgp_key_across_platforms=enrichment.shared_pgp_key_across_platforms,
        platform_migration_order=enrichment.platform_migration_order,
    )


@router.get("/{actor_id}/ai-analysis", response_model=ActorAIAnalysisOut)
def get_actor_ai_analysis(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    """AI/ML stylometric + behavioural comparison between this actor's
    already-clustered personas — see app.services.ai_stylometry /
    app.services.actor_ai_analysis. Deliberately separate from
    attribution-breakdown: this answers "how similar is their writing/
    behaviour", not "how strong is the total attribution evidence" —
    never touches confidence_score."""
    actor = (
        db.query(Actor)
        .options(selectinload(Actor.identifiers))
        .filter(Actor.id == actor_id)
        .first()
    )
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    result = compute_actor_ai_analysis(db, actor)

    pairs_out: list[AIPairAnalysisOut] = []
    for pair in result.pairs:
        if isinstance(pair.analysis, PairAnalysis):
            pairs_out.append(
                AIPairAnalysisOut(
                    persona_a=AIPersonaSummary(**vars(pair.persona_a)),
                    persona_b=AIPersonaSummary(**vars(pair.persona_b)),
                    stylometric_similarity=pair.analysis.stylometric_similarity,
                    behavioral_similarity=pair.analysis.behavioral_similarity,
                    signals=[AISignalOut(**vars(s)) for s in pair.analysis.signals],
                    evidence_samples=[
                        AIEvidenceSampleOut(**vars(e)) for e in pair.evidence_samples
                    ],
                    insufficient_data_reason=None,
                )
            )
        else:
            assert isinstance(pair.analysis, InsufficientData)
            pairs_out.append(
                AIPairAnalysisOut(
                    persona_a=AIPersonaSummary(**vars(pair.persona_a)),
                    persona_b=AIPersonaSummary(**vars(pair.persona_b)),
                    stylometric_similarity=None,
                    behavioral_similarity=None,
                    signals=[],
                    evidence_samples=[],
                    insufficient_data_reason=pair.analysis.reason,
                )
            )

    return ActorAIAnalysisOut(
        personas=[AIPersonaSummary(**vars(p)) for p in result.personas],
        pairs=pairs_out,
        status_message=result.status_message,
        method=METHOD_DESCRIPTION,
    )


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
def get_actor_threat_activity(
    actor_id: uuid.UUID,
    category: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """"What type of threat activity is this actor associated with?" — a
    SEPARATE question from attribution-breakdown's "why is this the same
    actor?" (see app.services.threat_categorization's module docstring).
    Every row is a real classified ThreatActivity; an empty summary/activity
    list is the honest, expected result for an actor with no classifiable
    activity content (e.g. one built only from Tor Onionoo/MISP/HIBP
    correlation, which carries no narrative activity text at all).

    `summary` always reflects ALL of this actor's activities (cheap
    aggregation). `activities` is filtered to `category` (if given) and
    paginated — a real actor can have 150+ activities in one category, and
    the UI fetches one category's evidence page at a time rather than every
    row up front (see ActorProfileView). Exports (app.api.routes.export) use
    the underlying un-paginated, un-filtered service function directly, so a
    report always contains everything regardless of what page the UI last
    viewed."""
    actor = db.query(Actor).filter(Actor.id == actor_id).first()
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    rows = get_actor_threat_activities(db, actor_id)

    summary = [
        ThreatCategorySummary(
            category=s.category,
            category_label=s.category_label,
            activity_count=s.activity_count,
            sources=s.sources,
        )
        for s in summarize_by_category(rows)
    ]

    filtered = [r for r in rows if category is None or r.category == category]
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    start = (page - 1) * page_size
    page_rows = filtered[start : start + page_size]

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
        for row in page_rows
    ]

    return ActorThreatActivityOut(
        summary=summary,
        activities=activities,
        activities_total=len(filtered),
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=PaginatedActorsOut)
def list_actors(page: int = 1, page_size: int = 100, db: Session = Depends(get_db)):
    """Server-side paginated — see PaginatedActorsOut's docstring. page/
    page_size are clamped, not trusted blindly: an investigative tool, not
    an invitation to request an unbounded page."""
    page = max(1, page)
    page_size = max(1, min(page_size, 200))

    total = db.query(Actor).count()
    actors = (
        db.query(Actor)
        .order_by(Actor.confidence_score.desc(), Actor.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedActorsOut(
        items=[
            ActorSearchResult(
                id=a.id, label=a.label, confidence_score=a.confidence_score,
                updated_at=a.updated_at,
            )
            for a in actors
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
