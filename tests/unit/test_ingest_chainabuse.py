"""scripts/ingest_chainabuse.py — regression coverage for a real bug found
in a full-codebase audit: `payload.get("data", payload if isinstance(...)
else [])` calls `.get()` on `payload` unconditionally, which raises
AttributeError immediately if the API ever returns a bare top-level list —
the list-handling branch was unreachable dead code.
"""

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.ingest_chainabuse as ingest_chainabuse
from app.db.base import Base
from app.models.external import AbuseReport


class _FakeResponse:
    def __init__(self, json_body):
        self._json_body = json_body

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_body


def _session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chainabuse_test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_bare_top_level_list_response_does_not_crash(tmp_path, monkeypatch):
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(ingest_chainabuse, "SessionLocal", SessionLocal)
    monkeypatch.setattr(ingest_chainabuse.settings, "chainabuse_api_key", "fake-key")

    bare_list_payload = [
        {
            "id": "report-1",
            "addresses": [{"address": "1FakeAddr", "chain": "bitcoin"}],
            "category": "scam",
            "createdAt": "2026-01-01T00:00:00Z",
        }
    ]
    monkeypatch.setattr(
        httpx, "get", lambda *a, **kw: _FakeResponse(bare_list_payload)
    )

    ingest_chainabuse.main(100)

    db = SessionLocal()
    report = db.query(AbuseReport).one()
    db.close()
    assert report.report_id == "report-1"
    assert report.address == "1FakeAddr"
    assert report.chain == "bitcoin"


def test_wrapped_data_key_response_still_works(tmp_path, monkeypatch):
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(ingest_chainabuse, "SessionLocal", SessionLocal)
    monkeypatch.setattr(ingest_chainabuse.settings, "chainabuse_api_key", "fake-key")

    wrapped_payload = {"data": [{"id": "report-2", "address": "1OtherAddr"}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse(wrapped_payload))

    ingest_chainabuse.main(100)

    db = SessionLocal()
    report = db.query(AbuseReport).one()
    db.close()
    assert report.report_id == "report-2"
