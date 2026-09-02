from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.actor import AnalysisJob
from app.schemas.lead import (
    AnalysisJobOut,
    InfraScanRequest,
    InfraScanTriggered,
    JobStatus,
    PaginatedAnalysisJobsOut,
)
from app.workers.celery_app import celery_app
from app.workers.tasks import run_infra_scan

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)])


@router.post("/infra-scan", response_model=InfraScanTriggered, status_code=202)
def trigger_infra_scan(payload: InfraScanRequest):
    """Runs the real infra-scan checks (SSL/banner/default-page/clock-skew/
    descriptor-inconsistency — app.services.infra_scan.scanner) against a
    controlled target and persists every finding. clearnet_host MUST be a
    target the team controls (see docs/ETHICS.md) — this endpoint does not
    validate that itself (same trust model as the rest of this internal
    tool), so only ever point it at a self-hosted mock target."""
    task = run_infra_scan.delay(
        onion_address=payload.onion_address,
        clearnet_host=payload.clearnet_host,
        port=payload.port,
        actor_id=str(payload.actor_id) if payload.actor_id else None,
    )
    return InfraScanTriggered(task_id=task.id)


@router.get("", response_model=PaginatedAnalysisJobsOut)
def list_recent_jobs(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    """Real, persisted job history — see AnalysisJob's docstring for exactly
    which runs populate this table (every Celery-triggered task: lead
    reanalysis, scheduled collection, and infra scans — not CLI scripts)."""
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    total = db.query(AnalysisJob).count()
    jobs = (
        db.query(AnalysisJob)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedAnalysisJobsOut(
        items=[AnalysisJobOut.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{task_id}", response_model=JobStatus)
def get_job_status(task_id: str):
    result = celery_app.AsyncResult(task_id)
    return JobStatus(
        task_id=task_id,
        status=result.status,
        result=result.result if result.successful() else None,
    )
