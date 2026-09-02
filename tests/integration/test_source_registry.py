"""GET /api/dashboard/source-registry — collection_mode/last_run_status/
next_scheduled_at, derived from the real most-recent scheduled_collection
AnalysisJob (see app.workers.tasks.run_scheduled_collection), not
fabricated. Same fixture pattern as test_dashboard_intelligence.py."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.actor import AnalysisJob


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


def _by_key(rows, key):
    return next(r for r in rows if r["key"] == key)


def test_no_scheduled_run_yet_reports_never_run(client):
    test_client, _ = client
    headers = _auth_headers(test_client)

    resp = test_client.get("/api/dashboard/source-registry", headers=headers)
    assert resp.status_code == 200
    rows = resp.json()

    onionoo = _by_key(rows, "tor_onionoo")
    assert onionoo["collection_mode"] == "scheduled"
    assert onionoo["last_run_status"] == "never_run"
    assert onionoo["next_scheduled_at"] is None

    darkforums = _by_key(rows, "darkforums")
    assert darkforums["collection_mode"] == "not_applicable"
    assert darkforums["last_run_status"] is None


def test_scheduled_run_reports_per_source_status_and_next_run(client):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)

    completed_at = datetime.now(timezone.utc)
    db = SessionLocal()
    db.add(
        AnalysisJob(
            job_type="scheduled_collection",
            status="success",
            target="onionoo + misp_osint + hibp -> full pipeline reanalysis",
            result={
                "sources": {
                    "onionoo": "ok",
                    "misp_osint": "failed: feed unreachable",
                    "hibp": "ok",
                },
                "actor_count": 0,
            },
            completed_at=completed_at,
        )
    )
    db.commit()
    db.close()

    resp = test_client.get("/api/dashboard/source-registry", headers=headers)
    assert resp.status_code == 200
    rows = resp.json()

    onionoo = _by_key(rows, "tor_onionoo")
    assert onionoo["last_run_status"] == "ok"
    expected_next = completed_at + timedelta(hours=settings.scheduled_collection_interval_hours)
    assert onionoo["next_scheduled_at"] is not None
    # SQLite (used in this test) doesn't preserve tzinfo on round-trip — the
    # API's own value comes back naive even though it was computed
    # tz-aware; normalize both sides to compare, same as the endpoint's own
    # _in_range does for the same reason.
    actual_next = datetime.fromisoformat(onionoo["next_scheduled_at"])
    if actual_next.tzinfo is None:
        actual_next = actual_next.replace(tzinfo=timezone.utc)
    assert abs((actual_next - expected_next).total_seconds()) < 2

    misp_circl = _by_key(rows, "misp_circl_osint")
    misp_botvrij = _by_key(rows, "misp_botvrij_osint")
    assert misp_circl["last_run_status"] == "failed"
    assert misp_botvrij["last_run_status"] == "failed"

    hibp = _by_key(rows, "hibp")
    assert hibp["last_run_status"] == "ok"

    urlhaus = _by_key(rows, "urlhaus")
    assert urlhaus["collection_mode"] == "manual"
    assert urlhaus["last_run_status"] is None


def test_running_job_is_ignored_as_not_yet_a_real_result(client):
    """A scheduled_collection job still in progress has no result yet — must
    not be treated as the latest completed run."""
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)

    db = SessionLocal()
    db.add(
        AnalysisJob(
            job_type="scheduled_collection",
            status="running",
            target="onionoo + misp_osint + hibp -> full pipeline reanalysis",
        )
    )
    db.commit()
    db.close()

    resp = test_client.get("/api/dashboard/source-registry", headers=headers)
    assert resp.status_code == 200
    onionoo = _by_key(resp.json(), "tor_onionoo")
    assert onionoo["last_run_status"] == "never_run"
