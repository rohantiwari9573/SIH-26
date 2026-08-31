import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Actor(Base):
    """A unified profile the platform believes corresponds to one real-world threat actor."""

    __tablename__ = "actors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    label: Mapped[str] = mapped_column(String(255))
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    identifiers: Mapped[list["Identifier"]] = relationship(back_populates="actor")
    infra_findings: Mapped[list["InfraFinding"]] = relationship(back_populates="actor")
    style_profiles: Mapped[list["StyleProfile"]] = relationship(back_populates="actor")
    attribution_edges: Mapped[list["AttributionEdge"]] = relationship()


class Identifier(Base):
    """A username, PGP key, or wallet seen on some platform, optionally linked to an Actor."""

    __tablename__ = "identifiers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True
    )
    identifier_type: Mapped[str] = mapped_column(String(32))  # username | pgp_key | wallet
    value: Mapped[str] = mapped_column(String(512))
    source_platform: Mapped[str] = mapped_column(String(255))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    actor: Mapped[Actor | None] = relationship(back_populates="identifiers")


class InfraFinding(Base):
    """A leak discovered while scanning a hidden service (SSL reuse, banner, exposed page)."""

    __tablename__ = "infra_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True
    )
    onion_address: Mapped[str] = mapped_column(String(255))
    finding_type: Mapped[str] = mapped_column(String(64))  # ssl_leak | banner | default_page
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    actor: Mapped[Actor | None] = relationship(back_populates="infra_findings")


class StyleProfile(Base):
    """Stylometric feature vector extracted from an identifier's writing samples."""

    __tablename__ = "style_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True
    )
    identifier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identifiers.id")
    )
    feature_vector: Mapped[dict] = mapped_column(JSON, default=dict)
    sample_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    actor: Mapped[Actor | None] = relationship(back_populates="style_profiles")


class AttributionEdge(Base):
    """One piece of evidence the attribution pipeline used to merge two
    personas into the same Actor cluster (see app.services.attribution) —
    persisted so the UI can show *why* an attribution was made, not just the
    final confidence score. Rebuilt from scratch alongside Actor on every
    run_full_analysis (see app/services/pipeline.py)."""

    __tablename__ = "attribution_edges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("actors.id"))
    username_a: Mapped[str] = mapped_column(String(255))
    platform_a: Mapped[str] = mapped_column(String(255))
    username_b: Mapped[str] = mapped_column(String(255))
    platform_b: Mapped[str] = mapped_column(String(255))
    edge_type: Mapped[str] = mapped_column(String(32))  # shared_wallet | shared_pgp_key | stylo
    weight: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RawPersona(Base):
    """A submitted lead, exactly as collected — the source-of-truth input to
    the attribution pipeline. Actor/Identifier/StyleProfile/InfraFinding are
    *derived* from the full set of these on each analysis run, not hand-edited
    directly, so a new submission can change existing attributions (e.g. two
    previously-unrelated personas turning out to share a wallet)."""

    __tablename__ = "raw_personas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(255))
    sample_text: Mapped[str | None] = mapped_column(String, nullable=True)
    wallet: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pgp_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    onion_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vouched_by: Mapped[list] = mapped_column(JSON, default=list)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RawActivity(Base):
    """One real, individual piece of activity content (a single marketplace
    listing, a single forum post) tied to the RawPersona that produced it —
    the source-of-truth input to threat categorization, exactly analogous to
    how RawPersona is the source-of-truth input to attribution.

    Populated ONCE at ingestion time (scripts/ingest_evolution.py,
    scripts/ingest_darkforums.py) directly from the real per-item rows in
    data/external/ — never from RawPersona.sample_text, which is a lossy
    concatenation of every item's text into one blob and cannot answer "which
    specific listing/post is this evidence from." Unlike the tables in
    app.services.pipeline's rebuild set, RawActivity is NOT deleted/rebuilt
    on every run_full_analysis — it is raw ingested content, kept stable so
    ThreatActivity (derived from it) always has a real, stable record to cite
    as evidence.

    source_record_id is the exact identifier of the original row (e.g.
    "evolution_market:listing:<lid>", "darkforums:thread:<tid>:post:<pid>")
    so a classification can always be traced back to one specific real line
    in the original dataset file, not just "some listing by this vendor.\""""

    __tablename__ = "raw_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    raw_persona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_personas.id"), index=True
    )
    platform: Mapped[str] = mapped_column(String(255))
    source_record_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    text: Mapped[str] = mapped_column(String(4000))
    # The forum/marketplace's OWN category label for this item, if the source
    # data provides one (e.g. DarkForums' real "category": "Leaks" field).
    # None for sources with no such field (e.g. Evolution Market listings).
    source_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    raw_persona: Mapped["RawPersona"] = relationship()


class ThreatActivity(Base):
    """The result of classifying one RawActivity into a controlled threat
    category — evidence/enrichment, exactly like CorrelationEvidence
    (app.models.external), and under the same architectural rule: NOTHING
    here feeds app.services.scoring's confidence formula. Activity
    classification and attribution are separate analytical concepts (see
    app.services.threat_categorization's module docstring); this table
    answers "what kind of activity is this actor associated with," not "how
    confident are we these personas are the same actor."

    Rebuilt from scratch inside app.services.pipeline.run_full_analysis,
    same pattern as CorrelationEvidence/AttributionEdge — actor_id is
    resolved fresh each run (Actor rows themselves are recreated with new
    UUIDs every run), while raw_activity_id anchors back to the immutable
    source record so evidence never goes stale. Only non-"unclassified"
    results are persisted here — an Unknown/Unclassified activity is real
    information (the classifier ran and found nothing conservative to say)
    but is deliberately not stored as a row, per the "don't clutter the
    profile with Unknown" product rule; it can always be recomputed from
    RawActivity if ever needed.

    persona_username/source_platform/source_record_id/title/observed_at are
    denormalized from RawActivity at classification time (not just a bare FK)
    so the API/exports/UI can show full "who did what, where, when" evidence
    in one row without a join — the same flat-evidence-row shape
    CorrelationEvidence and AttributionEdge already use."""

    __tablename__ = "threat_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    raw_activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_activities.id"), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True, index=True
    )
    # WHO
    persona_username: Mapped[str] = mapped_column(String(255))
    # WHERE / FROM WHICH SOURCE
    source_platform: Mapped[str] = mapped_column(String(255))
    source_record_id: Mapped[str] = mapped_column(String(255))
    # WHAT (headline evidence text; full text lives on the RawActivity row)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # WHEN
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # WHAT THREAT CATEGORY
    category: Mapped[str] = mapped_column(String(64))  # see CATEGORY_LABELS
    # WHAT EVIDENCE — the specific phrase/rule that fired, or the source's
    # own category field when that was the basis for classification.
    classification_reason: Mapped[str] = mapped_column(String(512))
    # source_provided | keyword_rule — see threat_categorization.py
    classification_method: Mapped[str] = mapped_column(String(32))
    # HOW CONFIDENT — qualitative, derived deterministically from method
    # (a source's own editorial category label is stronger evidence than a
    # keyword heuristic matching free text). Never a fabricated float.
    classification_confidence: Mapped[str] = mapped_column(String(16))  # high | medium
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("raw_activity_id", name="uq_threat_activity_raw_activity"),
    )


class AnalysisJob(Base):
    """Tracks async Celery jobs so the query interface can show job status."""

    __tablename__ = "analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_type: Mapped[str] = mapped_column(String(64))  # infra_scan | stylometry | graph | wallet
    status: Mapped[str] = mapped_column(String(32), default="pending")
    target: Mapped[str] = mapped_column(String(512))
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
