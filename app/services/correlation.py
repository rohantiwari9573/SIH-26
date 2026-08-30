"""Deterministic correlation between real external intelligence (Tor
Onionoo, MISP CIRCL, MISP botvrij.eu, HIBP breach directory) and what Argus
already independently knows about an actor's infrastructure.

DELIBERATELY CONSERVATIVE. This module creates a CorrelationEvidence row
(and a Neo4j edge) ONLY when an exact value match exists — e.g. a Tor
relay's IP address is the literal same string as an InfraFinding's
resolved_ip. No fuzzy matching, no "both exist in the database so they must
be related," and — critically — nothing here touches
app.services.scoring's confidence formula. This is enrichment evidence an
investigator can inspect, not an attribution signal. Given Argus's
demo/synthetic infrastructure (a self-hosted mock service) has no reason to
share a real IP/domain with the live Tor network or real threat feeds,
finding zero matches on a given run is the CORRECT and expected result, not
a bug — see run_correlation()'s docstring.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.actor import InfraFinding
from app.models.external import BreachRecord, CorrelationEvidence, MispIndicator, TorRelay
from app.services.graph.neo4j_client import get_neo4j_client

IP_INDICATOR_TYPES = {"ip-dst", "ip-src", "ip-dst|port", "ip-src|port"}
HOSTNAME_INDICATOR_TYPES = {"domain", "hostname", "domain|ip"}


@dataclass
class CorrelationResult:
    source: str
    matches_found: int


def _infra_lookup(db: Session) -> tuple[dict[str, InfraFinding], dict[str, InfraFinding]]:
    """Returns (by_ip, by_hostname) — every value Argus's own infra-scan
    pillar (app.services.infra_scan) has actually observed, keyed for O(1)
    lookup. Hostnames come from the SSL certificate's CN/SAN (the actual
    leak the scanner flags), not the onion address itself."""
    by_ip: dict[str, InfraFinding] = {}
    by_hostname: dict[str, InfraFinding] = {}
    for finding in db.query(InfraFinding).all():
        if finding.resolved_ip:
            by_ip[finding.resolved_ip] = finding
        detail = finding.detail or {}
        cn = detail.get("subject_cn")
        if cn:
            by_hostname[cn] = finding
        for san in detail.get("san") or []:
            by_hostname[san] = finding
    return by_ip, by_hostname


def _record_evidence(
    db: Session,
    *,
    source: str,
    source_record_id: str,
    evidence_type: str,
    matched_value: str,
    finding: InfraFinding,
    description: str,
    observed_at=None,
) -> bool:
    """Upserts one CorrelationEvidence row; returns True if it's new. Also
    pushes the matched external node into Neo4j, linked to the same
    onion-address Identifier node app.services.graph.relationship_mapper
    already created for this finding's actor — so the correlation is
    visible in the actor's real relationship graph, not just a table."""
    existing = (
        db.query(CorrelationEvidence)
        .filter(
            CorrelationEvidence.source == source,
            CorrelationEvidence.source_record_id == source_record_id,
            CorrelationEvidence.matched_value == matched_value,
        )
        .first()
    )
    is_new = existing is None
    if existing is None:
        existing = CorrelationEvidence(
            source=source, source_record_id=source_record_id, matched_value=matched_value
        )
        db.add(existing)
    existing.evidence_type = evidence_type
    existing.actor_id = finding.actor_id
    existing.infra_finding_id = finding.id
    existing.description = description
    existing.observed_at = observed_at

    if finding.onion_address:
        client = get_neo4j_client()
        node_type = f"corr:{source}"
        client.upsert_identifier(node_type, matched_value, source)
        client.link_identifiers(
            finding.onion_address, matched_value, "MATCHES", platform_b=source
        )
    return is_new


def correlate_tor_relays(db: Session) -> CorrelationResult:
    """Tor Onionoo relay IPs vs. Argus's own infra-scan findings. Relay
    metadata never implies actor identity by itself (see
    scripts/ingest_onionoo.py) — this only records a match when a relay's
    IP is the exact same string as a resolved_ip Argus's scanner itself
    observed."""
    by_ip, _ = _infra_lookup(db)
    matches = 0
    for relay in db.query(TorRelay).all():
        for ip in relay.ip_addresses or []:
            finding = by_ip.get(ip)
            if finding is None:
                continue
            if _record_evidence(
                db,
                source="tor_onionoo",
                source_record_id=relay.fingerprint,
                evidence_type="infrastructure",
                matched_value=ip,
                finding=finding,
                description=(
                    f"Tor relay {relay.nickname} ({relay.fingerprint[:12]}...) shares IP "
                    f"{ip} with a confirmed infra leak."
                ),
                observed_at=relay.last_seen,
            ):
                matches += 1
    return CorrelationResult(source="tor_onionoo", matches_found=matches)


def correlate_misp_indicators(db: Session) -> CorrelationResult:
    """MISP (CIRCL + botvrij.eu) attribute-level IOCs vs. Argus's infra
    findings' resolved IP and certificate hostname (CN/SAN). Requires
    MispIndicator rows, which only exist for the small number of most-recent
    events each feed's ingest script expands to full detail — see
    scripts/ingest_misp_osint.py."""
    by_ip, by_hostname = _infra_lookup(db)
    matches = 0
    for indicator in db.query(MispIndicator).all():
        finding = None
        if indicator.indicator_type in IP_INDICATOR_TYPES:
            finding = by_ip.get(indicator.value)
        elif indicator.indicator_type in HOSTNAME_INDICATOR_TYPES:
            finding = by_hostname.get(indicator.value)
        if finding is None:
            continue
        if _record_evidence(
            db,
            source=indicator.source,
            source_record_id=indicator.event_uuid,
            evidence_type="threat_indicator",
            matched_value=indicator.value,
            finding=finding,
            description=f"MISP event {indicator.event_uuid} lists {indicator.indicator_type} "
            f"{indicator.value}, matching a confirmed infra leak.",
        ):
            matches += 1
    return CorrelationResult(source="misp_indicators", matches_found=matches)


def correlate_hibp_breaches(db: Session) -> CorrelationResult:
    """HIBP breach directory's affected domain vs. Argus's infra findings'
    certificate hostname (CN/SAN). This never implies "the actor caused the
    breach" — only that a domain tied to a confirmed infra leak also
    appears in a public breach record, which is supporting context for an
    investigator to look at, not a conclusion."""
    _, by_hostname = _infra_lookup(db)
    matches = 0
    for breach in db.query(BreachRecord).filter(BreachRecord.domain.isnot(None)).all():
        finding = by_hostname.get(breach.domain)
        if finding is None:
            continue
        if _record_evidence(
            db,
            source="hibp",
            source_record_id=breach.name,
            evidence_type="breach_domain",
            matched_value=breach.domain,
            finding=finding,
            description=f"HIBP breach '{breach.name}' affects domain {breach.domain}, "
            f"matching a confirmed infra leak's certificate hostname.",
            observed_at=breach.breach_date,
        ):
            matches += 1
    return CorrelationResult(source="hibp", matches_found=matches)


def run_correlation(db: Session) -> list[CorrelationResult]:
    """Runs all three correlators and commits. Called at the end of
    app.services.pipeline.run_full_analysis (same "rebuild from scratch"
    session, after infra findings are persisted) so a new lead submission's
    infra evidence is immediately checked against every live/feed source
    already ingested — matching this module's evidence to the demo flow in
    STEP 18 of the phase-2 spec. Zero matches is the expected, honest result
    against synthetic/self-hosted infrastructure; it means the correlation
    logic ran and found nothing real to report, not that it's broken."""
    results = [
        correlate_tor_relays(db),
        correlate_misp_indicators(db),
        correlate_hibp_breaches(db),
    ]
    db.commit()
    return results
