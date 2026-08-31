import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LeadCreate(BaseModel):
    # max_length values mirror the RawPersona column limits (app/models/actor.py)
    # — without them, an over-long value passes validation here and then hits
    # a raw Postgres DataError on insert (500) instead of a clean 422.
    username: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=255)
    sample_text: str | None = None
    wallet: str | None = Field(default=None, max_length=512)
    pgp_key: str | None = Field(default=None, max_length=512)
    onion_address: str | None = Field(default=None, max_length=255)
    vouched_by: list[str] = Field(default_factory=list)


class LeadSubmitted(BaseModel):
    lead_id: str
    task_id: str


class JobStatus(BaseModel):
    task_id: str
    status: str  # PENDING | STARTED | SUCCESS | FAILURE
    result: dict | None = None


class AnalysisJobOut(BaseModel):
    """One real, persisted AnalysisJob row — see that model's docstring for
    exactly which pipeline runs populate this (Celery-triggered reanalyze_all
    only, not CLI scripts)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    status: str
    target: str
    task_id: str | None
    created_at: datetime
    completed_at: datetime | None


class PaginatedAnalysisJobsOut(BaseModel):
    items: list[AnalysisJobOut]
    total: int
    page: int
    page_size: int
