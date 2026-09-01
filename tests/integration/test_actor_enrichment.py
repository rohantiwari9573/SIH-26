"""app.services.actor_enrichment / GET /api/actors/{id}/enrichment — verifies
the aggregation is a real derivation from RawActivity/RawPersona/Identifier
rows (not fabricated), correctly handles the honest-zero case, and matches
the exact (username, platform) join key app.services.pipeline itself uses
to map a RawPersona to an Actor.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.actor import Actor, Identifier, RawActivity, RawPersona, ThreatActivity
from app.services.actor_enrichment import compute_actor_enrichment


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
        "/api/auth/register", json={"email": "enrich@example.com", "password": "hunter2pass"}
    )
    response = test_client.post(
        "/api/auth/login", data={"username": "enrich@example.com", "password": "hunter2pass"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _now(days_ago: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _seed_multi_platform_actor(SessionLocal) -> str:
    """One actor with two personas on two platforms, sharing a wallet, with
    real timestamped RawActivity on each — the exact shape run_full_analysis
    itself produces, seeded directly so the test doesn't depend on Neo4j."""
    db = SessionLocal()
    actor = Actor(label="Actor: shadow_vendor / nightowl_88", confidence_score=0.84)
    db.add(actor)
    db.flush()

    persona_a = RawPersona(username="shadow_vendor", platform="mock_marketplace_1", wallet="w1")
    persona_b = RawPersona(username="nightowl_88", platform="mock_marketplace_2", wallet="w1")
    db.add_all([persona_a, persona_b])
    db.flush()

    db.add_all(
        [
            Identifier(
                actor_id=actor.id,
                identifier_type="username",
                value="shadow_vendor",
                source_platform="mock_marketplace_1",
            ),
            Identifier(
                actor_id=actor.id,
                identifier_type="wallet",
                value="w1",
                source_platform="mock_marketplace_1",
            ),
            Identifier(
                actor_id=actor.id,
                identifier_type="username",
                value="nightowl_88",
                source_platform="mock_marketplace_2",
            ),
            Identifier(
                actor_id=actor.id,
                identifier_type="wallet",
                value="w1",
                source_platform="mock_marketplace_2",
            ),
        ]
    )

    # persona_a: 2 activities, earlier in time; persona_b: 1 activity, later.
    db.add_all(
        [
            RawActivity(
                raw_persona_id=persona_a.id,
                platform="mock_marketplace_1",
                source_record_id="mp1:listing:1",
                text="selling stolen data dumps",
                source_category=None,
                observed_at=_now(days_ago=40),
            ),
            RawActivity(
                raw_persona_id=persona_a.id,
                platform="mock_marketplace_1",
                source_record_id="mp1:listing:2",
                text="restocked",
                source_category=None,
                observed_at=_now(days_ago=30),
            ),
            RawActivity(
                raw_persona_id=persona_b.id,
                platform="mock_marketplace_2",
                source_record_id="mp2:listing:1",
                text="new stock available",
                source_category=None,
                observed_at=_now(days_ago=10),
            ),
        ]
    )
    db.commit()
    actor_id = str(actor.id)
    db.close()
    return actor_id


def _seed_actor_with_classified_activity(SessionLocal) -> tuple[str, str]:
    db = SessionLocal()
    actor = Actor(label="Actor: careless_admin", confidence_score=0.15)
    db.add(actor)
    db.flush()
    persona = RawPersona(username="careless_admin", platform="mock_marketplace_1")
    db.add(persona)
    db.flush()
    db.add(
        Identifier(
            actor_id=actor.id,
            identifier_type="username",
            value="careless_admin",
            source_platform="mock_marketplace_1",
        )
    )
    activity = RawActivity(
        raw_persona_id=persona.id,
        platform="mock_marketplace_1",
        source_record_id="mp1:listing:99",
        text="selling stolen data",
        source_category=None,
        observed_at=_now(days_ago=5),
    )
    db.add(activity)
    db.flush()
    db.add(
        ThreatActivity(
            raw_activity_id=activity.id,
            actor_id=actor.id,
            persona_username="careless_admin",
            source_platform="mock_marketplace_1",
            source_record_id="mp1:listing:99",
            title="stolen data",
            observed_at=activity.observed_at,
            category="stolen_data",
            classification_reason="keyword: stolen data",
            classification_method="keyword_rule",
            classification_confidence="medium",
        )
    )
    activity_id = str(activity.id)
    db.commit()
    actor_id = str(actor.id)
    db.close()
    return actor_id, activity_id


def test_enrichment_aggregates_real_multi_platform_activity(client):
    _, SessionLocal = client
    actor_id = _seed_multi_platform_actor(SessionLocal)
    db = SessionLocal()
    actor = db.query(Actor).filter(Actor.id == uuid.UUID(actor_id)).one()
    result = compute_actor_enrichment(db, actor)
    db.close()

    assert result.total_activities == 3
    assert result.classified_activities == 0  # none classified in this fixture
    assert {p.platform for p in result.platforms} == {"mock_marketplace_1", "mock_marketplace_2"}

    by_platform = {p.platform: p for p in result.platforms}
    assert by_platform["mock_marketplace_1"].activity_count == 2
    assert by_platform["mock_marketplace_2"].activity_count == 1

    # Real derived span: earliest activity (40 days ago) to latest (10 days ago).
    assert result.active_duration_days == 30
    assert result.first_observed is not None
    assert result.last_observed is not None
    assert result.days_since_last_observed is not None

    # A wallet shared across both platforms' Identifier rows -> True.
    assert result.shared_wallet_across_platforms is True
    assert result.shared_pgp_key_across_platforms is False  # no PGP identifier seeded at all

    # mock_marketplace_1's activity (40 days ago) predates mock_marketplace_2's (10 days ago).
    assert result.platform_migration_order == ["mock_marketplace_1", "mock_marketplace_2"]


def test_enrichment_is_honest_zero_for_actor_with_no_linked_activity(client):
    """An actor whose Identifier rows have no matching RawPersona (e.g. a
    correlation/infra-only actor) must report real zeros/None, never a
    fabricated default — this is the exact case the PS's anti-fabrication
    requirement is about."""
    _, SessionLocal = client
    db = SessionLocal()
    actor = Actor(label="Actor: infra-only-persona", confidence_score=0.0)
    db.add(actor)
    db.flush()
    db.add(
        Identifier(
            actor_id=actor.id,
            identifier_type="username",
            value="ghost_handle",
            source_platform="tor_onionoo",  # no RawPersona exists with this (value, platform)
        )
    )
    db.commit()
    result = compute_actor_enrichment(db, actor)
    db.close()

    assert result.total_activities == 0
    assert result.classified_activities == 0
    assert result.first_observed is None
    assert result.last_observed is None
    assert result.active_duration_days is None
    assert result.posting_frequency_per_week is None
    assert result.days_since_last_observed is None
    assert result.shared_wallet_across_platforms is False
    assert result.shared_pgp_key_across_platforms is False
    # The identifier's own platform still shows up (0 activities, 1 identifier) —
    # presence is real even though activity isn't.
    assert len(result.platforms) == 1
    assert result.platforms[0].platform == "tor_onionoo"
    assert result.platforms[0].identifier_count == 1
    assert result.platforms[0].activity_count == 0


def test_enrichment_endpoint_matches_service_and_counts_classified_activity(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    actor_id, _ = _seed_actor_with_classified_activity(SessionLocal)

    response = test_client.get(f"/api/actors/{actor_id}/enrichment", headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert body["total_activities"] == 1
    assert body["classified_activities"] == 1  # the one RawActivity was also classified
    assert body["platforms"][0]["platform"] == "mock_marketplace_1"
    assert body["platforms"][0]["activity_count"] == 1
    assert body["first_observed"] is not None
    assert body["last_observed"] is not None


def test_enrichment_endpoint_requires_auth(client):
    test_client, SessionLocal = client
    actor_id = _seed_multi_platform_actor(SessionLocal)
    response = test_client.get(f"/api/actors/{actor_id}/enrichment")
    assert response.status_code == 401


def test_enrichment_endpoint_404s_for_unknown_actor(client):
    test_client, _ = client
    headers = _auth_headers(test_client)
    response = test_client.get(f"/api/actors/{uuid.uuid4()}/enrichment", headers=headers)
    assert response.status_code == 404
