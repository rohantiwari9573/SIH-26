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
from app.models.actor import Actor, AnalysisJob, InfraFinding, RealWorldEntity
from app.services.infra_scan.scanner import InfraFinding as ScannerFinding


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


def test_run_infra_scan_persists_findings_with_severity_job_and_actor_linkage(
    tmp_path, monkeypatch
):
    """This is what closes the real gap the audit found: run_infra_scan
    previously computed real findings but never wrote them anywhere, and no
    API route ever called it. Now every finding must land in InfraFinding
    with this run's scan_job_id and (when given) actor_id set."""
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(tasks, "SessionLocal", SessionLocal)

    db = SessionLocal()
    actor = Actor(label="Actor: test_vendor", confidence_score=0.5)
    db.add(actor)
    db.commit()
    actor_id = actor.id
    db.close()

    fake_findings = [
        ScannerFinding(finding_type="ssl_leak", detail={"subject_cn": "mail.example.test"}),
        ScannerFinding(finding_type="banner", detail={"server": "Apache/2.4.41"}),
    ]
    monkeypatch.setattr(
        tasks, "scan_target", lambda onion, host, port=443: fake_findings
    )

    result = tasks.run_infra_scan.apply(
        kwargs={
            "onion_address": "demo.onion",
            "clearnet_host": "127.0.0.1",
            "actor_id": str(actor_id),
        }
    )
    assert result.result["finding_count"] == 2

    db = SessionLocal()
    job = db.query(AnalysisJob).one()
    findings = db.query(InfraFinding).order_by(InfraFinding.finding_type).all()
    db.close()

    assert job.job_type == "infra_scan"
    assert job.status == "success"

    assert len(findings) == 2
    ssl_finding = next(f for f in findings if f.finding_type == "ssl_leak")
    banner_finding = next(f for f in findings if f.finding_type == "banner")

    assert ssl_finding.actor_id == actor_id
    assert ssl_finding.scan_job_id == job.id
    assert ssl_finding.severity == "high"
    assert ssl_finding.detail["subject_cn"] == "mail.example.test"

    assert banner_finding.actor_id == actor_id
    assert banner_finding.scan_job_id == job.id
    assert banner_finding.severity == "low"

    # The real-world-entity signal this scan just produced (a cert hostname
    # tied to a currently-valid actor linkage) must be derived and
    # persisted NOW, while that linkage is still fresh — see
    # run_infra_scan's own docstring for why waiting for the next full
    # pipeline rebuild would be too late.
    db = SessionLocal()
    entity = db.query(RealWorldEntity).one()
    db.close()
    assert entity.actor_id == actor_id
    assert entity.entity_name == "mail.example.test"
    assert entity.relationship_type == "cert_hostname"


def test_run_infra_scan_without_actor_id_persists_unlinked_findings(tmp_path, monkeypatch):
    """An exploratory scan not yet tied to a known actor is still stored —
    just with actor_id left null, not dropped or fabricated a link."""
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(tasks, "SessionLocal", SessionLocal)
    monkeypatch.setattr(
        tasks,
        "scan_target",
        lambda onion, host, port=443: [
            ScannerFinding(finding_type="clock_skew", detail={"skew_seconds": 1200})
        ],
    )

    tasks.run_infra_scan.apply(
        kwargs={"onion_address": "demo.onion", "clearnet_host": "127.0.0.1"}
    )

    db = SessionLocal()
    finding = db.query(InfraFinding).one()
    db.close()

    assert finding.actor_id is None
    assert finding.severity == "low"


def test_run_infra_scan_persists_failure_job_on_scan_error(tmp_path, monkeypatch):
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(tasks, "SessionLocal", SessionLocal)

    def _boom(onion, host, port=443):
        raise RuntimeError("target unreachable")

    monkeypatch.setattr(tasks, "scan_target", _boom)

    result = tasks.run_infra_scan.apply(
        kwargs={"onion_address": "demo.onion", "clearnet_host": "127.0.0.1"}
    )
    assert result.failed()

    db = SessionLocal()
    job = db.query(AnalysisJob).one()
    finding_count = db.query(InfraFinding).count()
    db.close()

    assert job.job_type == "infra_scan"
    assert job.status == "failure"
    assert "target unreachable" in job.result["error"]
    assert finding_count == 0
