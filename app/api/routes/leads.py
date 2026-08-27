from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.actor import RawPersona
from app.schemas.lead import LeadCreate, LeadSubmitted
from app.workers.tasks import reanalyze_all

router = APIRouter(prefix="/api/leads", tags=["leads"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=LeadSubmitted, status_code=202)
def submit_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    """Accepts one newly-collected persona and re-runs the full attribution
    pipeline against it plus everything already known — this is what turns
    'database collection' from a one-shot script into something the platform
    actually does at runtime. Analysis runs async (Celery): the response
    returns immediately with a task id to poll via GET /api/jobs/{task_id}.

    Upserts on (username, platform): the same username reappearing on the
    same platform is treated as new information about the same observed
    persona (e.g. "we now know their wallet") and merges in, rather than
    creating a second RawPersona row with the same username that the
    attribution pipeline has no principled way to reconcile.
    """
    lead = (
        db.query(RawPersona)
        .filter(
            RawPersona.username == payload.username,
            RawPersona.platform == payload.platform,
        )
        .first()
    )

    if lead is None:
        lead = RawPersona(username=payload.username, platform=payload.platform)
        db.add(lead)

    if payload.sample_text is not None:
        lead.sample_text = payload.sample_text
    if payload.wallet is not None:
        lead.wallet = payload.wallet
    if payload.pgp_key is not None:
        lead.pgp_key = payload.pgp_key
    if payload.onion_address is not None:
        lead.onion_address = payload.onion_address
    if payload.vouched_by:
        lead.vouched_by = payload.vouched_by

    db.commit()
    db.refresh(lead)

    task = reanalyze_all.delay()
    return LeadSubmitted(lead_id=str(lead.id), task_id=task.id)
