import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
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
