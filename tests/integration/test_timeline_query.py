"""GET /api/dashboard/timeline — real filtering, not just display. Verifies
start_date/end_date/actor_id/source/category/event_type are applied as
actual SQL WHERE clauses per underlying table, per the PS's "query the
database across a chosen timeline" requirement. Same fixture pattern as
test_dashboard_intelligence.py."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.actor import Actor, InfraFinding, RawActivity, RawPersona, ThreatActivity


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


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _seed(SessionLocal) -> dict:
    """Two actors, each with one ThreatActivity in a different category, on
    different platforms, observed on different dates — enough to prove each
    filter dimension actually narrows the result independently."""
    db = SessionLocal()

    actor_a = Actor(label="Actor: nightowl88", confidence_score=0.7)
    actor_b = Actor(label="Actor: shadow_vendor", confidence_score=0.6)
    db.add_all([actor_a, actor_b])
    db.flush()

    persona_a = RawPersona(username="nightowl88", platform="mock_marketplace_1")
    persona_b = RawPersona(username="shadow_vendor", platform="mock_marketplace_2")
    db.add_all([persona_a, persona_b])
    db.flush()

    ra_a = RawActivity(
        raw_persona_id=persona_a.id,
        platform="mock_marketplace_1",
        source_record_id="mock_marketplace_1:listing:1",
        text="stolen credentials for sale",
    )
    ra_b = RawActivity(
        raw_persona_id=persona_b.id,
        platform="mock_marketplace_2",
        source_record_id="mock_marketplace_2:listing:1",
        text="hire a hacker for ddos",
    )
    db.add_all([ra_a, ra_b])
    db.flush()

    db.add(
        ThreatActivity(
            raw_activity_id=ra_a.id,
            actor_id=actor_a.id,
            persona_username="nightowl88",
            source_platform="mock_marketplace_1",
            source_record_id=ra_a.source_record_id,
            category="credential_data_theft",
            classification_reason="test",
            classification_method="keyword_rule",
            classification_confidence="medium",
            observed_at=_dt("2026-06-05"),
        )
    )
    db.add(
        ThreatActivity(
            raw_activity_id=ra_b.id,
            actor_id=actor_b.id,
            persona_username="shadow_vendor",
            source_platform="mock_marketplace_2",
            source_record_id=ra_b.source_record_id,
            category="hacking_services",
            classification_reason="test",
            classification_method="keyword_rule",
            classification_confidence="medium",
            observed_at=_dt("2026-07-20"),
        )
    )
    db.add(
        InfraFinding(
            actor_id=actor_a.id,
            onion_address="leaky.onion",
            finding_type="ssl_leak",
            detail={"subject_cn": "mail.example.test"},
            discovered_at=_dt("2026-06-10"),
        )
    )
    db.commit()
    return {"actor_a": str(actor_a.id), "actor_b": str(actor_b.id)}


def test_no_filters_returns_all_event_types(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    _seed(SessionLocal)

    resp = test_client.get("/api/dashboard/timeline?limit=50", headers=headers)
    assert resp.status_code == 200
    event_types = {e["event_type"] for e in resp.json()}
    assert event_types == {"actor_created", "infra_finding", "threat_activity", "lead_submitted"}


def test_date_range_excludes_events_outside_window(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    _seed(SessionLocal)

    resp = test_client.get(
        "/api/dashboard/timeline?limit=50&start_date=2026-06-01&end_date=2026-06-30",
        headers=headers,
    )
    assert resp.status_code == 200
    events = resp.json()
    # Every event's own occurred_at (actor_created's Actor.created_at is set
    # at seed time = "now", well outside June, so it's correctly excluded
    # too — the filter applies uniformly across event types) must fall
    # inside the requested June window.
    occurred_dates = {e["occurred_at"][:10] for e in events}
    assert "2026-07-20" not in occurred_dates
    assert all(d.startswith("2026-06") for d in occurred_dates)
    assert {e["event_type"] for e in events} == {"infra_finding", "threat_activity"}


def test_category_filter_only_matches_threat_activity(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    _seed(SessionLocal)

    resp = test_client.get(
        "/api/dashboard/timeline?limit=50&category=hacking_services", headers=headers
    )
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    assert events[0]["event_type"] == "threat_activity"
    assert events[0]["category"] == "hacking_services"


def test_source_filter_matches_platform(client):
    """Both the lead (RawPersona) and the classified activity for
    shadow_vendor are real, independent rows on mock_marketplace_2 — the
    filter must return both, not silently collapse them."""
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    _seed(SessionLocal)

    resp = test_client.get(
        "/api/dashboard/timeline?limit=50&source=mock_marketplace_2", headers=headers
    )
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 2
    assert {e["event_type"] for e in events} == {"lead_submitted", "threat_activity"}
    assert all(e["source"] == "mock_marketplace_2" for e in events)


def test_actor_id_filter_scopes_to_one_actor(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    ids = _seed(SessionLocal)

    resp = test_client.get(
        f"/api/dashboard/timeline?limit=50&actor_id={ids['actor_a']}", headers=headers
    )
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 1
    assert all(e["actor_id"] in (ids["actor_a"], None) for e in events)
    assert all(e["actor_id"] != ids["actor_b"] for e in events)


def test_event_type_filter_restricts_to_one_type(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    _seed(SessionLocal)

    resp = test_client.get(
        "/api/dashboard/timeline?limit=50&event_type=infra_finding", headers=headers
    )
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    assert events[0]["event_type"] == "infra_finding"


def test_combined_filters_apply_as_and(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)
    _seed(SessionLocal)

    # category=hacking_services (July) AND June date range -> zero results
    resp = test_client.get(
        "/api/dashboard/timeline?limit=50&category=hacking_services"
        "&start_date=2026-06-01&end_date=2026-06-30",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []
