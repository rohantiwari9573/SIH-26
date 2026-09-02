"""Real-world entity attribution: SIH PS-26151's objective statement is to
"link [threat actors] to suspect real-world entities" — a distinct, missing
layer this module adds, sitting one step past app.services.correlation
(which only says "this external record matches our infrastructure") to ask
"does that external record name an actual real-world entity."

STRICT RULE: every row here must be DERIVED from data Argus already
independently holds. Never invent an organization, never guess who owns a
domain, never claim a confirmed identity. Two derivation paths:

  1. cert_hostname — an actor's own InfraFinding (ssl_leak) already contains
     a real-world hostname read directly out of a leaked TLS certificate
     (see app.services.infra_scan.scanner.check_ssl_certificate). That
     hostname IS real, observed data — but Argus has not independently
     verified who controls it, so this is surfaced as an unverified domain
     reference, not an ownership claim.
  2. external_org_match — a CorrelationEvidence row (app.services.correlation)
     already ties the actor's infrastructure to a HIBP BreachRecord or MISP
     ThreatEvent, and those source records carry a real, publicly-known
     name (a breach's company name, or a MISP event's reporting Orgc name).
     Surfacing that name as a candidate entity, tied to the evidence that
     produced it, is not fabrication — the name was never invented here.

Deliberately excludes Tor relay (tor_onionoo) evidence: a relay operator is
not a hidden-service operator (see scripts/ingest_onionoo.py's own
limitation note), and treating a relay nickname as a "real-world entity" for
a threat actor would be exactly the kind of unsupported inference this
module exists to avoid.

Rebuilt from scratch inside app.services.pipeline.run_full_analysis, same
pattern as CorrelationEvidence/AttributionEdge/ThreatActivity."""
from sqlalchemy.orm import Session

from app.models.actor import InfraFinding, RealWorldEntity
from app.models.external import CorrelationEvidence, ThreatEvent


def _cert_hostname_entities(db: Session) -> list[RealWorldEntity]:
    entities: list[RealWorldEntity] = []
    findings = (
        db.query(InfraFinding)
        .filter(InfraFinding.actor_id.isnot(None), InfraFinding.finding_type == "ssl_leak")
        .all()
    )
    for finding in findings:
        cn = finding.detail.get("subject_cn")
        hostnames = {cn} if cn else set()
        hostnames.update(finding.detail.get("san") or [])
        hostnames.discard(None)

        for hostname in sorted(hostnames):
            entities.append(
                RealWorldEntity(
                    actor_id=finding.actor_id,
                    entity_name=hostname,
                    entity_type="domain",
                    relationship_type="cert_hostname",
                    evidence={
                        "subject_cn": cn,
                        "san": finding.detail.get("san"),
                        "onion_address": finding.onion_address,
                        "infra_finding_id": str(finding.id),
                    },
                    source="infra_scan",
                    source_record_id=str(finding.id),
                    observed_at=finding.discovered_at,
                    confidence="unverified_domain_reference",
                    explanation=(
                        f"Domain '{hostname}' was observed in a TLS certificate served "
                        f"by {finding.onion_address}. Argus has not independently "
                        f"verified who controls this domain — this names a candidate "
                        f"clearnet indicator for an investigator to check, not a "
                        f"confirmed owner."
                    ),
                )
            )
    return entities


def _external_org_match_entities(db: Session) -> list[RealWorldEntity]:
    entities: list[RealWorldEntity] = []
    evidence_rows = (
        db.query(CorrelationEvidence).filter(CorrelationEvidence.actor_id.isnot(None)).all()
    )

    misp_event_uuids = {
        ev.source_record_id
        for ev in evidence_rows
        if ev.source in ("misp_circl_osint", "misp_botvrij_osint")
    }
    org_name_by_event_uuid: dict[str, str] = {}
    if misp_event_uuids:
        for event in (
            db.query(ThreatEvent)
            .filter(ThreatEvent.event_uuid.in_(misp_event_uuids), ThreatEvent.org_name.isnot(None))
            .all()
        ):
            org_name_by_event_uuid[event.event_uuid] = event.org_name

    for ev in evidence_rows:
        org_name: str | None = None
        if ev.source == "hibp":
            # correlate_hibp_breaches sets source_record_id=breach.name — the
            # breach's real, publicly-known company/service name itself, no
            # further lookup needed.
            org_name = ev.source_record_id
        elif ev.source in ("misp_circl_osint", "misp_botvrij_osint"):
            org_name = org_name_by_event_uuid.get(ev.source_record_id)

        if not org_name:
            continue

        entities.append(
            RealWorldEntity(
                actor_id=ev.actor_id,
                entity_name=org_name,
                entity_type="organization",
                relationship_type="external_org_match",
                evidence={
                    "matched_value": ev.matched_value,
                    "evidence_type": ev.evidence_type,
                    "description": ev.description,
                    "correlation_evidence_id": str(ev.id),
                },
                source=ev.source,
                source_record_id=ev.source_record_id,
                observed_at=ev.observed_at,
                confidence=(
                    "external_breach_directory_match"
                    if ev.source == "hibp"
                    else "external_threat_event_match"
                ),
                explanation=(
                    f"'{org_name}' appears in {ev.source}'s public record for "
                    f"{ev.matched_value}, which independently matches this actor's "
                    f"confirmed infrastructure ({ev.description})"
                ),
            )
        )
    return entities


def derive_real_world_entities(db: Session) -> list[RealWorldEntity]:
    """Rebuilds real_world_entities from scratch from whatever InfraFinding/
    CorrelationEvidence rows already exist — call after both are persisted
    (see app.services.pipeline.run_full_analysis's call order). An empty
    result is the honest, expected outcome for most actors, same as
    CorrelationEvidence: Argus's demo/synthetic infrastructure has no reason
    to overlap with real external records."""
    db.query(RealWorldEntity).delete()
    db.flush()

    entities = _cert_hostname_entities(db) + _external_org_match_entities(db)
    db.add_all(entities)
    db.flush()
    return entities
