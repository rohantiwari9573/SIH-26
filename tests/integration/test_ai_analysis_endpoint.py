"""GET /api/actors/{id}/ai-analysis — verifies the endpoint wires
app.services.actor_ai_analysis/ai_stylometry correctly, handles every honest
empty state, and never exposes a fabricated score. SQLite via FastAPI
dependency override, same pattern as test_actor_enrichment.py.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.actor import Actor, Identifier, RawActivity, RawPersona, ThreatActivity

LONG_TEXT_A = (
    "Stock updated today, quality checked as always, escrow recommended "
    "for new buyers this week. Ships same day, no exceptions, no delays "
    "unless the announcement thread says otherwise clearly this time."
)
LONG_TEXT_B = (
    "Stock updated once again, quality checked like usual, escrow is "
    "recommended for every new buyer this week too. Ships the same day, "
    "no exceptions at all, no delays unless the thread says otherwise."
)


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
        "/api/auth/register", json={"email": "ai@example.com", "password": "hunter2pass"}
    )
    response = test_client.post(
        "/api/auth/login", data={"username": "ai@example.com", "password": "hunter2pass"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_two_persona_actor(SessionLocal, with_activity: bool = True) -> str:
    db = SessionLocal()
    actor = Actor(label="Actor: vendor_a / vendor_b", confidence_score=0.9)
    db.add(actor)
    db.flush()

    persona_a = RawPersona(username="vendor_a", platform="mock_marketplace_1")
    persona_b = RawPersona(username="vendor_b", platform="mock_marketplace_2")
    db.add_all([persona_a, persona_b])
    db.flush()

    db.add_all(
        [
            Identifier(
                actor_id=actor.id, identifier_type="username",
                value="vendor_a", source_platform="mock_marketplace_1",
            ),
            Identifier(
                actor_id=actor.id, identifier_type="username",
                value="vendor_b", source_platform="mock_marketplace_2",
            ),
        ]
    )

    if with_activity:
        activity_a = RawActivity(
            raw_persona_id=persona_a.id, platform="mock_marketplace_1",
            source_record_id="mp1:1", title="Restock", text=LONG_TEXT_A,
        )
        activity_b = RawActivity(
            raw_persona_id=persona_b.id, platform="mock_marketplace_2",
            source_record_id="mp2:1", title="Restock", text=LONG_TEXT_B,
        )
        db.add_all([activity_a, activity_b])
        db.flush()
        db.add(
            ThreatActivity(
                raw_activity_id=activity_a.id, actor_id=actor.id,
                persona_username="vendor_a", source_platform="mock_marketplace_1",
                source_record_id="mp1:1", title="Restock", category="stolen_data",
                classification_reason="test", classification_method="keyword_rule",
                classification_confidence="medium",
            )
        )
    db.commit()
    actor_id = str(actor.id)
    db.close()
    return actor_id


def _seed_single_persona_actor(SessionLocal) -> str:
    db = SessionLocal()
    actor = Actor(label="Actor: lone_vendor", confidence_score=0.0)
    db.add(actor)
    db.flush()
    persona = RawPersona(username="lone_vendor", platform="mock_marketplace_1")
    db.add(persona)
    db.flush()
    db.add(
        Identifier(
            actor_id=actor.id, identifier_type="username",
            value="lone_vendor", source_platform="mock_marketplace_1",
        )
    )
    db.commit()
    actor_id = str(actor.id)
    db.close()
    return actor_id


def test_endpoint_returns_real_analysis_for_two_persona_actor(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    actor_id = _seed_two_persona_actor(SessionLocal)

    response = test_client.get(f"/api/actors/{actor_id}/ai-analysis", headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert len(body["personas"]) == 2
    assert len(body["pairs"]) == 1
    pair = body["pairs"][0]
    assert pair["insufficient_data_reason"] is None
    assert 0.0 <= pair["stylometric_similarity"] <= 1.0
    # Only vendor_a has a classified ThreatActivity; vendor_b has none, so
    # this is the real "one side has signal, other doesn't" case -> a real
    # 0.0, not None (None is reserved for "neither side has any signal").
    assert pair["behavioral_similarity"] == 0.0
    assert len(pair["signals"]) >= 3
    assert len(pair["evidence_samples"]) >= 1
    assert "Character n-gram" in body["method"]


def test_endpoint_single_persona_actor_returns_honest_status_message(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    actor_id = _seed_single_persona_actor(SessionLocal)

    response = test_client.get(f"/api/actors/{actor_id}/ai-analysis", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["pairs"] == []
    assert body["status_message"] == "No comparable persona pair identified."
    assert len(body["personas"]) == 1


def test_endpoint_no_activity_returns_honest_status_message(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    actor_id = _seed_two_persona_actor(SessionLocal, with_activity=False)

    response = test_client.get(f"/api/actors/{actor_id}/ai-analysis", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status_message"] == "Activity record does not contain analyzable text."
    assert body["pairs"] == []


def test_endpoint_requires_auth(client):
    test_client, SessionLocal = client
    actor_id = _seed_two_persona_actor(SessionLocal)
    response = test_client.get(f"/api/actors/{actor_id}/ai-analysis")
    assert response.status_code == 401


def test_endpoint_404s_for_unknown_actor(client):
    test_client, _ = client
    headers = _auth_headers(test_client)
    response = test_client.get(f"/api/actors/{uuid.uuid4()}/ai-analysis", headers=headers)
    assert response.status_code == 404


def test_response_never_contains_fabricated_score_alongside_insufficient_reason(client):
    """A pair result must be EITHER a real score OR an insufficient-data
    reason, never both — guards against a future edit accidentally leaving
    a stale/default score in place next to an insufficiency message."""
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    actor_id = _seed_two_persona_actor(SessionLocal)
    response = test_client.get(f"/api/actors/{actor_id}/ai-analysis", headers=headers)
    for pair in response.json()["pairs"]:
        if pair["insufficient_data_reason"] is not None:
            assert pair["stylometric_similarity"] is None
            assert pair["behavioral_similarity"] is None
            assert pair["signals"] == []
