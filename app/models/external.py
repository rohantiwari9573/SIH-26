"""Data ingested from real external intelligence sources (see
data/external/ and scripts/ingest_*.py), as opposed to app.models.actor's
tables which hold Argus's own derived/submitted data. Kept in a separate
module so it's obvious at a glance which tables represent third-party
observations versus Argus's own analysis output."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TorRelay(Base):
    """A Tor relay's metadata as last observed via the Tor Project's Onionoo
    API (metrics.torproject.org). Infrastructure/network intelligence only —
    this identifies relay operators, not dark-web hidden-service operators or
    threat actors; see ARGUS_DATA_RESOURCES.md's limitation note."""

    __tablename__ = "tor_relays"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(255))
    ip_addresses: Mapped[list] = mapped_column(JSON, default=list)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    running: Mapped[bool] = mapped_column(Boolean, default=False)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ThreatEvent(Base):
    """One event/report from a real threat-intelligence feed (currently:
    CIRCL's public MISP OSINT feed). Event-level metadata only (title, date,
    tags) — the manifest endpoint doesn't include per-attribute IOC detail,
    and pulling all 1,680+ individual event files was judged not worth the
    ingestion cost for a dashboard-level view."""

    __tablename__ = "threat_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(64), default="misp_circl_osint")
    event_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    org_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    info: Mapped[str] = mapped_column(String(1024))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    threat_level_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
