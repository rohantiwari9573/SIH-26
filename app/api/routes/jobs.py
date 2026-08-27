from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.schemas.lead import JobStatus
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)])


@router.get("/{task_id}", response_model=JobStatus)
def get_job_status(task_id: str):
    result = celery_app.AsyncResult(task_id)
    return JobStatus(
        task_id=task_id,
        status=result.status,
        result=result.result if result.successful() else None,
    )
