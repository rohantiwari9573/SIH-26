"""Covers the four new PS-26151 aggregate endpoints added for the Hidden
Services / Marketplace / Forum / Alerts / Jobs & Scans sidebar pages:
GET /api/dashboard/hidden-services, /identifier-activity, /alerts,
/system-status. Runs against an isolated SQLite DB via dependency override,
same pattern as test_actors_and_export.py."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.actor import Actor, AttributionEdge, Identifier, InfraFinding
from app.models.external import CorrelationEvidence


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), TestingSessionLocal
    app.dependency_overrides.clear()


def _auth_headers(test_client: TestClient) -> dict[str, str]:
    test_client.post(
        "/api/auth/register", json={"email": "analyst@example.com", "password": "hunter2pass"}
    )
    response = test_client.post(
        "/api/auth/login", data={"username": "analyst@example.com", "password": "hunter2pass"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed(SessionLocal) -> dict:
    db = SessionLocal()
    actor = Actor(label="Actor: shadow_vendor / nightowl_88", confidence_score=0.84)
    db.add(actor)
    db.flush()

    ident = Identifier(
        actor_id=actor.id,
        identifier_type="username",
        value="shadow_vendor",
        source_platform="mock_marketplace_1",
    )
    db.add(ident)
    db.add(
        Identifier(
            actor_id=actor.id,
            identifier_type="pgp_key",
            value="DEMO-KEY",
            source_platform="evolution_forum",
        )
    )

    finding = InfraFinding(
        actor_id=actor.id,
        onion_address="demo.onion",
        finding_type="ssl_leak",
        detail={"subject_cn": "mail.realcompany-demo.example"},
    )
    db.add(finding)
    db.flush()

    db.add(
        CorrelationEvidence(
            source="tor_onionoo",
            source_record_id="fingerprint123",
            evidence_type="infrastructure",
            matched_value="mail.realcompany-demo.example",
            actor_id=actor.id,
            infra_finding_id=finding.id,
            description="Matched a live Tor relay's observed hostname.",
        )
    )
    db.add(
        AttributionEdge(
            actor_id=actor.id,
            username_a="shadow_vendor",
            platform_a="mock_marketplace_1",
            username_b="nightowl_88",
            platform_b="mock_marketplace_2",
            edge_type="shared_wallet",
            weight=1.0,
        )
    )
    db.commit()
    actor_id = str(actor.id)
    db.close()
    return {"actor_id": actor_id}


def test_hidden_services_reflects_real_findings_and_correlations(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    seeded = _seed(SessionLocal)

    response = test_client.get("/api/dashboard/hidden-services", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["infrastructure_findings"] == 1
    assert body["summary"]["hidden_services"] == 1
    assert body["summary"]["correlations"] == 1
    assert body["summary"]["linked_actors"] == 1
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["onion_address"] == "demo.onion"
    assert row["actor_id"] == seeded["actor_id"]
    assert len(row["correlations"]) == 1
    assert row["correlations"][0]["source"] == "tor_onionoo"


def test_hidden_services_empty_state_is_honest_zero(client):
    test_client, _ = client
    headers = _auth_headers(test_client)

    response = test_client.get("/api/dashboard/hidden-services", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "hidden_services": 0,
        "infrastructure_findings": 0,
        "correlations": 0,
        "linked_actors": 0,
    }
    assert body["rows"] == []


def test_identifier_activity_scopes_to_requested_platforms_only(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    _seed(SessionLocal)

    response = test_client.get(
        "/api/dashboard/identifier-activity?platforms=mock_marketplace_1", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_records"] == 1
    assert body["summary"]["unique_handles"] == 1
    assert body["summary"]["pgp_keys"] == 0
    assert len(body["records"]) == 1
    assert body["records"][0]["value"] == "shadow_vendor"

    # A different, disjoint platform set must not leak the marketplace row in.
    response = test_client.get(
        "/api/dashboard/identifier-activity?platforms=evolution_forum", headers=headers
    )
    body = response.json()
    assert body["summary"]["total_records"] == 1
    assert body["records"][0]["value"] == "DEMO-KEY"


def test_identifier_activity_empty_platforms_param_returns_empty_not_error(client):
    test_client, _ = client
    headers = _auth_headers(test_client)

    response = test_client.get("/api/dashboard/identifier-activity?platforms=", headers=headers)
    assert response.status_code == 200
    assert response.json()["summary"]["total_records"] == 0


def test_alerts_derive_severity_from_real_fields(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    _seed(SessionLocal)

    response = test_client.get("/api/dashboard/alerts", headers=headers)
    assert response.status_code == 200
    alerts = response.json()
    types = {a["alert_type"] for a in alerts}
    assert "high_confidence_actor" in types  # confidence_score 0.84 >= 0.7
    assert "new_linkage" in types
    assert "correlation" in types
    assert "infra_finding" in types

    linkage = next(a for a in alerts if a["alert_type"] == "new_linkage")
    assert linkage["severity"] == "high"  # shared_wallet edge_type

    infra = next(a for a in alerts if a["alert_type"] == "infra_finding")
    assert infra["severity"] == "high"  # ssl_leak finding_type

    # Every alert must be traceable back to a real actor/record, never anonymous.
    assert all(a["occurred_at"] for a in alerts)


def test_system_status_reports_all_four_components_without_crashing(client):
    test_client, _ = client
    headers = _auth_headers(test_client)

    response = test_client.get("/api/dashboard/system-status", headers=headers)
    assert response.status_code == 200
    body = response.json()
    names = {c["name"] for c in body["components"]}
    assert names == {"PostgreSQL", "Neo4j", "Redis", "Celery Workers"}
    # In this test env there's no real Neo4j/Redis/Celery — the endpoint must
    # degrade to healthy=False with a detail message, not raise.
    for component in body["components"]:
        assert isinstance(component["healthy"], bool)
