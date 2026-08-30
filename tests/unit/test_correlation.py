"""app.services.correlation — deterministic matching between real
external-source rows and Argus's own infra findings. Neo4j writes mocked
out (see test_pipeline.py's pattern); Postgres is a real SQLite session so
the actual query/match logic runs unmocked.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.correlation as correlation
from app.db.base import Base
from app.models.actor import Actor, InfraFinding
from app.models.external import BreachRecord, CorrelationEvidence, MispIndicator, TorRelay


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'correlation_test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class _FakeNeo4jClient:
    def __init__(self):
        self.upserts = []
        self.links = []

    def upsert_identifier(self, identifier_type, value, source_platform):
        self.upserts.append((identifier_type, value, source_platform))

    def link_identifiers(self, value_a, value_b, relationship, **kwargs):
        self.links.append((value_a, value_b, relationship))


def _mock_neo4j(monkeypatch) -> _FakeNeo4jClient:
    fake = _FakeNeo4jClient()
    monkeypatch.setattr(correlation, "get_neo4j_client", lambda: fake)
    return fake


def _actor_with_infra(db, *, onion_address="leaky.onion", resolved_ip=None, detail=None):
    actor = Actor(label="Actor: test_vendor")
    db.add(actor)
    db.flush()
    finding = InfraFinding(
        actor_id=actor.id,
        onion_address=onion_address,
        finding_type="ssl_leak",
        resolved_ip=resolved_ip,
        detail=detail or {},
    )
    db.add(finding)
    db.commit()
    return actor, finding


def test_tor_relay_ip_matching_infra_finding_creates_evidence(tmp_path, monkeypatch):
    fake_neo4j = _mock_neo4j(monkeypatch)
    db = _session(tmp_path)
    actor, finding = _actor_with_infra(db, resolved_ip="203.0.113.5")
    db.add(
        TorRelay(
            fingerprint="ABCDEF0123456789",
            nickname="relay1",
            ip_addresses=["203.0.113.5"],
        )
    )
    db.commit()

    result = correlation.correlate_tor_relays(db)

    assert result.matches_found == 1
    evidence = db.query(CorrelationEvidence).one()
    assert evidence.source == "tor_onionoo"
    assert evidence.actor_id == actor.id
    assert evidence.infra_finding_id == finding.id
    assert evidence.matched_value == "203.0.113.5"
    assert evidence.evidence_type == "infrastructure"
    # Pushed into Neo4j, linked to the same onion-address node the identity
    # graph uses — not a decorative/disconnected node.
    assert fake_neo4j.links == [("leaky.onion", "203.0.113.5", "MATCHES")]


def test_tor_relay_with_no_ip_overlap_creates_no_evidence(tmp_path, monkeypatch):
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)
    _actor_with_infra(db, resolved_ip="203.0.113.5")
    db.add(TorRelay(fingerprint="X", nickname="relay2", ip_addresses=["198.51.100.9"]))
    db.commit()

    result = correlation.correlate_tor_relays(db)

    assert result.matches_found == 0
    assert db.query(CorrelationEvidence).count() == 0


def test_misp_domain_indicator_matching_cert_hostname_creates_evidence(tmp_path, monkeypatch):
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)
    actor, finding = _actor_with_infra(
        db, detail={"subject_cn": "real-server.example.com", "san": []}
    )
    db.add(
        MispIndicator(
            event_uuid="evt-1",
            source="misp_circl_osint",
            indicator_type="domain",
            value="real-server.example.com",
        )
    )
    db.commit()

    result = correlation.correlate_misp_indicators(db)

    assert result.matches_found == 1
    evidence = db.query(CorrelationEvidence).one()
    assert evidence.source == "misp_circl_osint"
    assert evidence.evidence_type == "threat_indicator"
    assert evidence.actor_id == actor.id


def test_hibp_breach_domain_matching_cert_hostname_creates_evidence(tmp_path, monkeypatch):
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)
    actor, finding = _actor_with_infra(db, detail={"subject_cn": "leaked.example.org", "san": []})
    db.add(BreachRecord(name="ExampleBreach", domain="leaked.example.org"))
    db.commit()

    result = correlation.correlate_hibp_breaches(db)

    assert result.matches_found == 1
    evidence = db.query(CorrelationEvidence).one()
    assert evidence.source == "hibp"
    assert evidence.evidence_type == "breach_domain"


def test_rerunning_correlation_does_not_duplicate_evidence(tmp_path, monkeypatch):
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)
    _actor_with_infra(db, resolved_ip="203.0.113.5")
    db.add(TorRelay(fingerprint="ABC", nickname="relay1", ip_addresses=["203.0.113.5"]))
    db.commit()

    first = correlation.correlate_tor_relays(db)
    second = correlation.correlate_tor_relays(db)

    assert first.matches_found == 1
    assert second.matches_found == 0, "re-running against the same data must not re-count/duplicate"
    assert db.query(CorrelationEvidence).count() == 1
