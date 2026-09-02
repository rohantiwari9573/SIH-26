"""app.services.entity_linkage — real-world entity attribution, derived
strictly from data Argus already holds (InfraFinding cert hostnames,
CorrelationEvidence rows tying infra to HIBP/MISP records that carry a real
name). Never fabricates an organization or ownership claim — see that
module's docstring.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.actor import Actor, InfraFinding, RealWorldEntity
from app.models.external import BreachRecord, CorrelationEvidence, ThreatEvent
from app.services.entity_linkage import derive_real_world_entities


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'entity_linkage_test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _actor(db, label="Actor: test_vendor") -> Actor:
    actor = Actor(label=label)
    db.add(actor)
    db.flush()
    return actor


def test_cert_hostname_produces_unverified_domain_entity(tmp_path):
    db = _session(tmp_path)
    actor = _actor(db)
    finding = InfraFinding(
        actor_id=actor.id,
        onion_address="leaky.onion",
        finding_type="ssl_leak",
        detail={"subject_cn": "mail.realcompany-demo.example", "san": ["alt.example.test"]},
    )
    db.add(finding)
    db.commit()

    entities = derive_real_world_entities(db)

    names = {e.entity_name for e in entities}
    assert names == {"mail.realcompany-demo.example", "alt.example.test"}
    for e in entities:
        assert e.actor_id == actor.id
        assert e.entity_type == "domain"
        assert e.relationship_type == "cert_hostname"
        assert e.confidence == "unverified_domain_reference"
        assert e.source == "infra_scan"
        assert "not independently verified" in e.explanation


def test_non_ssl_leak_finding_produces_no_cert_hostname_entity(tmp_path):
    """A banner/default_page/clock_skew finding carries no cert CN — must
    not fabricate a domain entity from it."""
    db = _session(tmp_path)
    actor = _actor(db)
    db.add(
        InfraFinding(
            actor_id=actor.id,
            onion_address="leaky.onion",
            finding_type="banner",
            detail={"server": "Apache/2.4.41"},
        )
    )
    db.commit()

    entities = derive_real_world_entities(db)
    assert entities == []


def test_hibp_correlation_evidence_produces_organization_entity(tmp_path):
    db = _session(tmp_path)
    actor = _actor(db)
    db.add(BreachRecord(name="ExampleBreach Corp", domain="leaked.example.org"))
    db.add(
        CorrelationEvidence(
            source="hibp",
            source_record_id="ExampleBreach Corp",
            evidence_type="breach_domain",
            matched_value="leaked.example.org",
            actor_id=actor.id,
            description="HIBP breach 'ExampleBreach Corp' affects domain leaked.example.org",
        )
    )
    db.commit()

    entities = derive_real_world_entities(db)

    assert len(entities) == 1
    entity = entities[0]
    assert entity.entity_name == "ExampleBreach Corp"
    assert entity.entity_type == "organization"
    assert entity.relationship_type == "external_org_match"
    assert entity.confidence == "external_breach_directory_match"
    assert entity.source == "hibp"
    assert entity.actor_id == actor.id


def test_misp_correlation_evidence_with_org_name_produces_organization_entity(tmp_path):
    db = _session(tmp_path)
    actor = _actor(db)
    db.add(
        ThreatEvent(
            source="misp_circl_osint",
            event_uuid="evt-1",
            org_name="CIRCL",
            info="Some real threat event",
        )
    )
    db.add(
        CorrelationEvidence(
            source="misp_circl_osint",
            source_record_id="evt-1",
            evidence_type="threat_indicator",
            matched_value="real-server.example.com",
            actor_id=actor.id,
            description="MISP event evt-1 lists domain real-server.example.com",
        )
    )
    db.commit()

    entities = derive_real_world_entities(db)

    assert len(entities) == 1
    assert entities[0].entity_name == "CIRCL"
    assert entities[0].confidence == "external_threat_event_match"
    assert entities[0].source == "misp_circl_osint"


def test_misp_correlation_evidence_without_org_name_produces_no_entity(tmp_path):
    """A ThreatEvent with no org_name (real, common case — see
    scripts/ingest_misp_osint.py) must not fabricate a placeholder name."""
    db = _session(tmp_path)
    actor = _actor(db)
    db.add(ThreatEvent(source="misp_circl_osint", event_uuid="evt-2", org_name=None, info="x"))
    db.add(
        CorrelationEvidence(
            source="misp_circl_osint",
            source_record_id="evt-2",
            evidence_type="threat_indicator",
            matched_value="v",
            actor_id=actor.id,
            description="d",
        )
    )
    db.commit()

    assert derive_real_world_entities(db) == []


def test_tor_onionoo_evidence_produces_no_entity(tmp_path):
    """Deliberate exclusion — a Tor relay operator is not a hidden-service
    operator; see the module docstring for why this source is skipped."""
    db = _session(tmp_path)
    actor = _actor(db)
    db.add(
        CorrelationEvidence(
            source="tor_onionoo",
            source_record_id="fingerprint123",
            evidence_type="infrastructure",
            matched_value="203.0.113.5",
            actor_id=actor.id,
            description="d",
        )
    )
    db.commit()

    assert derive_real_world_entities(db) == []


def test_rerun_rebuilds_from_scratch_without_duplicating(tmp_path):
    db = _session(tmp_path)
    actor = _actor(db)
    db.add(
        InfraFinding(
            actor_id=actor.id,
            onion_address="leaky.onion",
            finding_type="ssl_leak",
            detail={"subject_cn": "mail.example.test", "san": []},
        )
    )
    db.commit()

    first = derive_real_world_entities(db)
    second = derive_real_world_entities(db)

    assert len(first) == 1
    assert len(second) == 1
    assert db.query(RealWorldEntity).count() == 1
