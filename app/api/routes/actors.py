import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.actor import Actor, Identifier
from app.schemas.actor import ActorGraphOut, ActorProfileOut, ActorSearchResult
from app.services.graph.relationship_mapper import get_actor_graph

router = APIRouter(prefix="/api/actors", tags=["actors"], dependencies=[Depends(get_current_user)])


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
        )
        .filter(Actor.id == actor_id)
        .first()
    )
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return actor


@router.get("/{actor_id}/graph", response_model=ActorGraphOut)
def get_actor_relationship_graph(actor_id: uuid.UUID, db: Session = Depends(get_db)):
    """Relationship-mapping pillar's output, in the shape a UI can actually draw:
    nodes + edges around this actor's known identifiers, sourced live from Neo4j."""
    actor = (
        db.query(Actor)
        .options(selectinload(Actor.identifiers))
        .filter(Actor.id == actor_id)
        .first()
    )
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    identifier_values = [ident.value for ident in actor.identifiers]
    return get_actor_graph(identifier_values)


@router.get("", response_model=list[ActorSearchResult])
def list_actors(db: Session = Depends(get_db)):
    actors = db.query(Actor).order_by(Actor.confidence_score.desc()).limit(100).all()
    return [
        ActorSearchResult(id=a.id, label=a.label, confidence_score=a.confidence_score)
        for a in actors
    ]
