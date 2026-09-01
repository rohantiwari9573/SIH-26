from datetime import datetime

from pydantic import BaseModel


class AIPersonaSummary(BaseModel):
    username: str
    platform: str
    sample_count: int
    combined_word_count: int


class AISignalOut(BaseModel):
    name: str
    score: float
    bucket: str


class AIEvidenceSampleOut(BaseModel):
    persona_username: str
    platform: str
    source_record_id: str
    title: str | None
    observed_at: datetime | None


class AIPairAnalysisOut(BaseModel):
    """Either a real result (stylometric_similarity/behavioral_similarity/
    signals populated) or an honest insufficient_data_reason — never both,
    never a fabricated score when data is insufficient."""

    persona_a: AIPersonaSummary
    persona_b: AIPersonaSummary
    stylometric_similarity: float | None
    behavioral_similarity: float | None
    signals: list[AISignalOut]
    evidence_samples: list[AIEvidenceSampleOut]
    insufficient_data_reason: str | None


class ActorAIAnalysisOut(BaseModel):
    """AI/ML stylometric + behavioural persona-comparison result for one
    actor — see app.services.ai_stylometry for the method. Deliberately
    separate from AttributionBreakdownOut/confidence_score: this answers
    "how similar are these personas' writing/behaviour patterns", not "how
    strong is the total attribution evidence" — see that module's docstring
    for why the two must never be conflated."""

    personas: list[AIPersonaSummary]
    pairs: list[AIPairAnalysisOut]
    status_message: str | None
    method: str
