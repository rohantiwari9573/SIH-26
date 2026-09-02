"""app.workers.tasks.reanalyze_all persists a real AnalysisJob row — see
that model's docstring for why this is the one path that populates it.
Runs the Celery task synchronously via .apply() (no broker/worker needed)
against a real SQLite session, with run_full_analysis itself mocked out
(that function's own correctness is covered by tests/unit/test_pipeline.py).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.workers.tasks as tasks
from app.db.base import Base
from app.models.actor import AnalysisJob


def _session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs_test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_reanalyze_all_persists_success_job(tmp_path, monkeypatch):
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(tasks, "SessionLocal", SessionLocal)
    monkeypatch.setattr(tasks, "run_full_analysis", lambda db: [])

    result = tasks.reanalyze_all.apply()
    assert result.result == {"actor_count": 0, "actors": []}

    db = SessionLocal()
    job = db.query(AnalysisJob).one()
    db.close()

    assert job.job_type == "reanalyze_all"
    assert job.status == "success"
    assert job.task_id == result.id
    assert job.completed_at is not None
    assert job.result == {"actor_count": 0, "actors": []}


def test_reanalyze_all_persists_failure_job_and_reraises(tmp_path, monkeypatch):
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(tasks, "SessionLocal", SessionLocal)

    def _boom(db):
        raise RuntimeError("simulated pipeline failure")

    monkeypatch.setattr(tasks, "run_full_analysis", _boom)

    result = tasks.reanalyze_all.apply()
    assert result.failed()

    db = SessionLocal()
    job = db.query(AnalysisJob).one()
    db.close()

    assert job.status == "failure"
    assert "simulated pipeline failure" in job.result["error"]
    assert job.completed_at is not None


def test_scheduled_collection_persists_success_job_with_per_source_status(
    tmp_path, monkeypatch
):
    """One feed (misp_osint) fails, the other two succeed — the run as a
    whole must still succeed and record run_full_analysis's result, with the
    per-source outcome visible rather than swallowed."""
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(tasks, "SessionLocal", SessionLocal)
    monkeypatch.setattr(tasks, "run_full_analysis", lambda db: [])
    monkeypatch.setattr(tasks, "ingest_onionoo", lambda limit: None)
    monkeypatch.setattr(tasks, "ingest_hibp", lambda limit: None)

    def _boom(limit, indicator_limit):
        raise RuntimeError("feed unreachable")

    monkeypatch.setattr(tasks, "ingest_misp_osint", _boom)

    result = tasks.run_scheduled_collection.apply()
    assert result.result == {
        "sources": {"onionoo": "ok", "misp_osint": "failed: feed unreachable", "hibp": "ok"},
        "actor_count": 0,
    }

    db = SessionLocal()
    job = db.query(AnalysisJob).one()
    db.close()

    assert job.job_type == "scheduled_collection"
    assert job.status == "success"
    assert job.result["sources"]["misp_osint"].startswith("failed:")
    assert job.result["sources"]["onionoo"] == "ok"


def test_scheduled_collection_persists_failure_job_when_pipeline_itself_fails(
    tmp_path, monkeypatch
):
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(tasks, "SessionLocal", SessionLocal)
    monkeypatch.setattr(tasks, "ingest_onionoo", lambda limit: None)
    monkeypatch.setattr(tasks, "ingest_misp_osint", lambda limit, indicator_limit: None)
    monkeypatch.setattr(tasks, "ingest_hibp", lambda limit: None)

    def _boom(db):
        raise RuntimeError("simulated pipeline failure")

    monkeypatch.setattr(tasks, "run_full_analysis", _boom)

    result = tasks.run_scheduled_collection.apply()
    assert result.failed()

    db = SessionLocal()
    job = db.query(AnalysisJob).one()
    db.close()

    assert job.job_type == "scheduled_collection"
    assert job.status == "failure"
    assert "simulated pipeline failure" in job.result["error"]
