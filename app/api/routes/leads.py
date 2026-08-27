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
    """
    lead = RawPersona(
        username=payload.username,
        platform=payload.platform,
        sample_text=payload.sample_text,
        wallet=payload.wallet,
        pgp_key=payload.pgp_key,
        onion_address=payload.onion_address,
        vouched_by=payload.vouched_by,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    task = reanalyze_all.delay()
    return LeadSubmitted(lead_id=str(lead.id), task_id=task.id)
