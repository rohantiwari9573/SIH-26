"""End-to-end: register, log in, query the unified actor profile, and pull all
three export formats. Runs against an isolated SQLite DB via FastAPI dependency
override, not the real Postgres engine — fast and self-contained for CI, but it
exercises the real ORM models, real Pydantic schemas, and real auth flow.

This is the test that should have existed from day one: writing it after the
fact caught nothing new here, but a manual run of this exact flow earlier
caught two bugs that would have broken the real deployment (a missing
email-validator dependency, and an incompatible bcrypt/passlib pairing) —
this test is what makes sure they can't come back unnoticed.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.routes.actors as actors_route
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.actor import Actor, Identifier, InfraFinding, StyleProfile


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
        "/api/auth/register", json={"email": "team@example.com", "password": "hunter2pass"}
    )
    response = test_client.post(
        "/api/auth/login", data={"username": "team@example.com", "password": "hunter2pass"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_actor(SessionLocal) -> str:
    db = SessionLocal()
    actor = Actor(label="Actor: shadow_vendor / nightowl_88", confidence_score=0.84)
    db.add(actor)
    db.flush()

    identifier = Identifier(
        actor_id=actor.id,
        identifier_type="username",
        value="shadow_vendor",
        source_platform="mock_marketplace_1",
    )
    db.add(identifier)
    db.add(
        InfraFinding(
            actor_id=actor.id,
            onion_address="demo.onion",
            finding_type="ssl_leak",
            detail={"subject_cn": "mail.realcompany-demo.example"},
        )
    )
    db.flush()
    db.add(
        StyleProfile(
            actor_id=actor.id,
            identifier_id=identifier.id,
            feature_vector={"avg_word_len": 0.5},
            sample_count=1,
        )
    )
    db.commit()
    actor_id = str(actor.id)
    db.close()
    return actor_id


def test_query_and_export_flow(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    actor_id = _seed_actor(SessionLocal)

    response = test_client.get("/api/actors", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = test_client.get("/api/actors/search?q=shadow", headers=headers)
    assert response.status_code == 200
    assert response.json()[0]["matched_identifier"] == "shadow_vendor"

    response = test_client.get(f"/api/actors/{actor_id}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["identifiers"]) == 1
    assert len(body["infra_findings"]) == 1
    assert len(body["style_profiles"]) == 1

    for fmt in ("json", "csv", "report"):
        response = test_client.get(f"/api/export/{actor_id}/{fmt}", headers=headers)
        assert response.status_code == 200
        assert len(response.content) > 0


def test_actor_graph_endpoint(client, monkeypatch):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    actor_id = _seed_actor(SessionLocal)

    fake_graph = {
        "nodes": [
            {"type": "username", "value": "shadow_vendor"},
            {"type": "wallet", "value": "1DemoWalletShared"},
        ],
        "edges": [
            {
                "source": "shadow_vendor",
                "target": "1DemoWalletShared",
                "relationship": "USES_WALLET",
                "weight": 1.0,
            }
        ],
    }
    monkeypatch.setattr(actors_route, "get_actor_graph", lambda values, depth=1: fake_graph)

    response = test_client.get(f"/api/actors/{actor_id}/graph", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    assert body["edges"][0]["relationship"] == "USES_WALLET"


def test_actor_graph_depth_param_is_forwarded_and_clamped(client, monkeypatch):
    """depth is clamped to [1,3] server-side — an investigative tool, not an
    invitation to pull an unbounded subgraph."""
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    actor_id = _seed_actor(SessionLocal)

    seen_depth = {}

    def fake_get_actor_graph(values, depth=1):
        seen_depth["value"] = depth
        return {"nodes": [], "edges": []}

    monkeypatch.setattr(actors_route, "get_actor_graph", fake_get_actor_graph)

    test_client.get(f"/api/actors/{actor_id}/graph?depth=2", headers=headers)
    assert seen_depth["value"] == 2

    test_client.get(f"/api/actors/{actor_id}/graph?depth=99", headers=headers)
    assert seen_depth["value"] == 3


def test_actor_evidence_endpoint_returns_correlation_evidence(client):
    """CorrelationEvidence (app.services.correlation) surfaced per-actor,
    scoped to that actor only — the endpoint the actor profile's Threat &
    Infrastructure Intelligence section reads from."""
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    actor_id = _seed_actor(SessionLocal)

    db = SessionLocal()
    import uuid as uuid_mod

    from app.models.actor import InfraFinding
    from app.models.external import CorrelationEvidence

    actor_uuid = uuid_mod.UUID(actor_id)
    finding = db.query(InfraFinding).filter(InfraFinding.actor_id == actor_uuid).first()
    db.add(
        CorrelationEvidence(
            source="hibp",
            source_record_id="ExampleBreach",
            evidence_type="breach_domain",
            matched_value="mail.realcompany-demo.example",
            actor_id=actor_uuid,
            infra_finding_id=finding.id,
            description="test evidence row",
        )
    )
    db.commit()
    db.close()

    response = test_client.get(f"/api/actors/{actor_id}/evidence", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["source"] == "hibp"
    assert body[0]["evidence_type"] == "breach_domain"


def test_actor_endpoints_require_auth(client):
    test_client, SessionLocal = client
    actor_id = _seed_actor(SessionLocal)

    assert test_client.get("/api/actors").status_code == 401
    assert test_client.get(f"/api/actors/{actor_id}").status_code == 401
    assert test_client.get(f"/api/actors/{actor_id}/graph").status_code == 401
    assert test_client.get(f"/api/export/{actor_id}/json").status_code == 401


def test_search_excludes_identifiers_with_no_linked_actor(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)

    db = SessionLocal()
    db.add(
        Identifier(
            actor_id=None,
            identifier_type="username",
            value="unattributed_lead",
            source_platform="mock_marketplace_1",
        )
    )
    db.commit()
    db.close()

    response = test_client.get("/api/actors/search?q=unattributed", headers=headers)
    assert response.status_code == 200
    assert response.json() == []
