"""DB-facing orchestration for app.services.ai_stylometry — walks from an
Actor to its real clustered personas' RawActivity/ThreatActivity rows and
runs the pure AI/ML comparison (see that module for the actual algorithms)
for every persona pair already attributed into this actor. Purely additive
and read-only: touches no derived table, feeds nothing back into
attribution/scoring — the same architectural boundary
app.services.threat_categorization and app.services.correlation already
hold to.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.actor import Actor, RawActivity, RawPersona, ThreatActivity
from app.services.ai_stylometry import (
    BehavioralVector,
    InsufficientData,
    PairAnalysis,
    compare_personas,
)


@dataclass
class PersonaSummary:
    username: str
    platform: str
    sample_count: int
    combined_word_count: int


@dataclass
class EvidenceSample:
    persona_username: str
    platform: str
    source_record_id: str
    title: str | None
    observed_at: datetime | None


@dataclass
class PairResult:
    persona_a: PersonaSummary
    persona_b: PersonaSummary
    analysis: PairAnalysis | InsufficientData
    evidence_samples: list[EvidenceSample]


@dataclass
class ActorAIAnalysis:
    personas: list[PersonaSummary]
    pairs: list[PairResult]
    status_message: str | None  # set only when there is nothing at all to show


def _actor_personas(db: Session, actor: Actor) -> list[RawPersona]:
    """The exact (username, platform) personas already clustered into this
    actor — the same join key app.services.pipeline itself uses to decide
    cluster membership (see app.services.actor_enrichment for the identical
    technique, used there for the same reason)."""
    usernames_platforms = {
        (ident.value, ident.source_platform)
        for ident in actor.identifiers
        if ident.identifier_type == "username"
    }
    if not usernames_platforms:
        return []
    candidate_usernames = {u for u, _ in usernames_platforms}
    rows = db.query(RawPersona).filter(RawPersona.username.in_(candidate_usernames)).all()
    return [r for r in rows if (r.username, r.platform) in usernames_platforms]


def compute_actor_ai_analysis(db: Session, actor: Actor) -> ActorAIAnalysis:
    personas = _actor_personas(db, actor)

    if not personas:
        return ActorAIAnalysis(
            personas=[], pairs=[], status_message="No activity available for AI analysis."
        )

    activities_by_persona: dict[uuid.UUID, list[RawActivity]] = {
        persona.id: (
            db.query(RawActivity).filter(RawActivity.raw_persona_id == persona.id).all()
        )
        for persona in personas
    }

    persona_summaries: list[PersonaSummary] = []
    persona_text: dict[uuid.UUID, str] = {}
    persona_behavior: dict[uuid.UUID, BehavioralVector] = {}

    for persona in personas:
        activities = activities_by_persona[persona.id]
        combined_text = " ".join(
            f"{a.title or ''} {a.text}".strip() for a in activities if a.text
        )
        persona_text[persona.id] = combined_text
        persona_summaries.append(
            PersonaSummary(
                username=persona.username,
                platform=persona.platform,
                sample_count=len(activities),
                combined_word_count=len(combined_text.split()),
            )
        )

        category_counts: dict[str, int] = {}
        threat_rows = (
            db.query(ThreatActivity)
            .filter(
                ThreatActivity.actor_id == actor.id,
                ThreatActivity.persona_username == persona.username,
                ThreatActivity.source_platform == persona.platform,
            )
            .all()
        )
        for row in threat_rows:
            category_counts[row.category] = category_counts.get(row.category, 0) + 1
        persona_behavior[persona.id] = BehavioralVector(category_counts=category_counts)

    if len(personas) < 2:
        return ActorAIAnalysis(
            personas=persona_summaries,
            pairs=[],
            status_message="No comparable persona pair identified.",
        )

    if not any(persona_text.values()):
        return ActorAIAnalysis(
            personas=persona_summaries,
            pairs=[],
            status_message="Activity record does not contain analyzable text.",
        )

    summary_by_key = {(s.username, s.platform): s for s in persona_summaries}
    pairs: list[PairResult] = []
    for i in range(len(personas)):
        for j in range(i + 1, len(personas)):
            a, b = personas[i], personas[j]
            analysis = compare_personas(
                persona_text[a.id],
                persona_text[b.id],
                persona_behavior[a.id],
                persona_behavior[b.id],
            )
            evidence: list[EvidenceSample] = [
                EvidenceSample(
                    persona_username=persona.username,
                    platform=persona.platform,
                    source_record_id=activity.source_record_id,
                    title=activity.title,
                    observed_at=activity.observed_at,
                )
                for persona in (a, b)
                for activity in activities_by_persona[persona.id][:2]
            ]
            pairs.append(
                PairResult(
                    persona_a=summary_by_key[(a.username, a.platform)],
                    persona_b=summary_by_key[(b.username, b.platform)],
                    analysis=analysis,
                    evidence_samples=evidence,
                )
            )

    return ActorAIAnalysis(personas=persona_summaries, pairs=pairs, status_message=None)
