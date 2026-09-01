from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.actor import AnalysisJob
from app.schemas.lead import AnalysisJobOut, JobStatus, PaginatedAnalysisJobsOut
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=PaginatedAnalysisJobsOut)
def list_recent_jobs(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    """Real, persisted job history — see AnalysisJob's docstring for exactly
    which runs populate this table (Celery-triggered reanalyze_all only)."""
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
