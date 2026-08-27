"""POST /api/leads and GET /api/jobs/{id} — the live-submission flow. Celery
itself isn't available in the test environment, so `reanalyze_all.delay` and
the Celery result lookup are mocked; what's under test is the API contract
(the lead gets persisted, a task id comes back, job status is queryable), not
Celery's own machinery.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.routes.jobs as jobs_route
import app.api.routes.leads as leads_route
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.actor import RawPersona


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
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class _FakeAsyncResult:
    def __init__(self, task_id: str):
        self.id = task_id


def test_submit_lead_persists_and_enqueues(client, monkeypatch):
    test_client, SessionLocal = client
    headers = _auth_headers(test_client)

    monkeypatch.setattr(
        leads_route.reanalyze_all, "delay", lambda: _FakeAsyncResult("fake-task-id")
    )

    response = test_client.post(
        "/api/leads",
        json={
            "username": "new_lead_vendor",
            "platform": "mock_marketplace_3",
            "sample_text": "Some writing sample here for style analysis purposes.",
            "wallet": "1NewLeadWallet",
        },
        headers=headers,
    )
    assert response.status_code == 202
    body = response.json()
    assert body["task_id"] == "fake-task-id"
    assert body["lead_id"]

    db = SessionLocal()
    stored = db.query(RawPersona).filter(RawPersona.username == "new_lead_vendor").first()
    db.close()
    assert stored is not None
    assert stored.wallet == "1NewLeadWallet"


def test_submit_lead_requires_auth(client):
    test_client, _ = client
    response = test_client.post(
        "/api/leads", json={"username": "x", "platform": "p"}
    )
    assert response.status_code == 401


def test_job_status_endpoint(client, monkeypatch):
    test_client, _ = client
    headers = _auth_headers(test_client)

    class FakeResult:
        status = "SUCCESS"

        def successful(self):
            return True

        @property
        def result(self):
            return {"actor_count": 2, "actors": []}

    monkeypatch.setattr(jobs_route.celery_app, "AsyncResult", lambda task_id: FakeResult())

    response = test_client.get("/api/jobs/some-task-id", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["result"]["actor_count"] == 2
