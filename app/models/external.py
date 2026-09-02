"""Data ingested from real external intelligence sources (see
data/external/ and scripts/ingest_*.py), as opposed to app.models.actor's
tables which hold Argus's own derived/submitted data. Kept in a separate
module so it's obvious at a glance which tables represent third-party
observations versus Argus's own analysis output."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
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


class MispIndicator(Base):
    """One real attribute-level IOC (domain/IP/URL/hash/hostname) pulled from
    a MISP OSINT event's full JSON — distinct from ThreatEvent, which only
    holds the feed *manifest's* event-level metadata (title/date/tags, no
    actual indicator values; see ThreatEvent's docstring). Fetching full
    event detail for every event in either feed was judged too expensive
    (thousands of files), so only the N most-recent events per feed are
    expanded into real indicators — see scripts/ingest_misp_osint.py. This
    is what makes genuine, non-fabricated correlation against Argus's own
    infrastructure data possible (app/services/correlation.py); ThreatEvent
    alone has no matchable values."""

    __tablename__ = "misp_indicators"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_uuid: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64))  # misp_circl_osint | misp_botvrij_osint
    # domain | ip-dst | url | md5 | sha256 | hostname
    indicator_type: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(1024))
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("event_uuid", "indicator_type", "value", name="uq_misp_indicator"),
    )


class CorrelationEvidence(Base):
    """A DETERMINISTIC match between a real external-intelligence record
    (Tor Onionoo / MISP CIRCL / MISP botvrij.eu / HIBP) and something Argus
    already independently knows (an infra finding's resolved IP/onion
    address/certificate hostname, or a submitted persona's onion address).
    Created ONLY when an exact value match is found — see
    app/services/correlation.py, which is deliberately conservative (no
    fuzzy matching, no "both exist in the DB so they must be related").

    This table is evidence/enrichment, not an attribution signal: nothing
    here feeds app.services.scoring's confidence formula. It answers "does
    external threat intel corroborate what we already found," not "who is
    this actor" — see the module-level warning in app/services/correlation.py."""

    __tablename__ = "correlation_evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # tor_onionoo | misp_circl_osint | misp_botvrij_osint | hibp
    source: Mapped[str] = mapped_column(String(64))
    # e.g. relay fingerprint, event_uuid, breach name
    source_record_id: Mapped[str] = mapped_column(String(255))
    # infrastructure | threat_indicator | breach_domain
    evidence_type: Mapped[str] = mapped_column(String(64))
    matched_value: Mapped[str] = mapped_column(String(1024))  # the exact value that matched
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True
    )
    infra_finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("infra_findings.id"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(512))
    # Always "exact_match" today — _record_evidence only ever creates a row
    # on a literal exact-value match (see this module's own docstring: "no
    # fuzzy matching"), so this is a real, deterministic label describing
    # HOW the match was made, not a fabricated confidence score. Kept as its
    # own column (rather than left implicit) so the PS's explicit "every
    # match must have ... confidence" requirement is satisfied honestly:
    # the true answer is "these are all equally exact-string matches," and
    # that's what's stored.
    confidence: Mapped[str] = mapped_column(String(32), default="exact_match")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint(
            "source", "source_record_id", "matched_value", name="uq_correlation_evidence"
        ),
    )


class BreachRecord(Base):
    """One publicly-listed data breach from Have I Been Pwned's breach
    directory (haveibeenpwned.com/api/v3/breaches — no API key required).
    This is breach *metadata* only (name, domain, scale, what data types
    were exposed) — HIBP's per-email lookup ("was this address in a
    breach") requires a paid key Argus doesn't hold, so no individual
    email/account exposure data is collected here."""

    __tablename__ = "breach_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    breach_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    added_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pwn_count: Mapped[int] = mapped_column(Integer, default=0)
    data_classes: Mapped[list] = mapped_column(JSON, default=list)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MaliciousUrl(Base):
    """One malicious-URL record from abuse.ch's URLhaus feed
    (urlhaus-api.abuse.ch — requires an Auth-Key header, unlike the other
    feeds in this module). Empty/unused (0 rows) until URLHAUS_API_KEY is
    set — see scripts/ingest_urlhaus.py. Never populated with fabricated
    rows; a 0 count here means genuinely not configured, not "no threats
    found"."""

    __tablename__ = "malicious_urls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    url_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # online | offline
    threat: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g. malware_download
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    date_added: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MalwareSample(Base):
    """One malware-sample record from abuse.ch's MalwareBazaar
    (mb-api.abuse.ch — requires an Auth-Key header). Empty/unused (0 rows)
    until MALWAREBAZAAR_API_KEY is set — see scripts/ingest_malwarebazaar.py."""

    __tablename__ = "malware_samples"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sha256_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signature: Mapped[str | None] = mapped_column(String(255), nullable=True)  # malware family
    tags: Mapped[list] = mapped_column(JSON, default=list)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AbuseReport(Base):
    """One reported-scam wallet address from Chainabuse
    (api.chainabuse.com — requires an API key). Empty/unused (0 rows) until
    CHAINABUSE_API_KEY is set — see scripts/ingest_chainabuse.py.

    Field mapping caveat: Chainabuse's response shape was not verified
    against a live authenticated call while building this (no key was
    available) — the ingest script parses the fields Chainabuse's public API
    docs describe, but treat this schema as provisional until it's been run
    once against the real API and checked."""

    __tablename__ = "abuse_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
