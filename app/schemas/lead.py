from pydantic import BaseModel, Field


class LeadCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=255)
    sample_text: str | None = None
    wallet: str | None = None
    pgp_key: str | None = None
    onion_address: str | None = None
    vouched_by: list[str] = Field(default_factory=list)


class LeadSubmitted(BaseModel):
    lead_id: str
    task_id: str


class JobStatus(BaseModel):
    task_id: str
    status: str  # PENDING | STARTED | SUCCESS | FAILURE
    result: dict | None = None
