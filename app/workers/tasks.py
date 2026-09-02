"""Async analysis jobs. Analysis (stylometry over many samples, infra scans,
graph traversal) shouldn't block the HTTP request — the API enqueues a job and
returns a job id; the dashboard polls /api/jobs/{id} for status."""
from datetime import datetime, timezone

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.actor import AnalysisJob
from app.services.infra_scan.scanner import scan_target
from app.services.pipeline import run_full_analysis
from app.services.stylometry.classifier import similarity_score
from app.workers.celery_app import celery_app

# Reuses the exact same importable main()s the manual CLI commands call
# (python scripts/ingest_onionoo.py etc.) — one implementation of "how to
# pull this feed," not a second copy for the scheduled path that could drift.
from scripts.ingest_hibp import main as ingest_hibp
from scripts.ingest_misp_osint import main as ingest_misp_osint
from scripts.ingest_onionoo import main as ingest_onionoo


def _now() -> datetime:
    return datetime.now(timezone.utc)


@celery_app.task(name="tasks.run_infra_scan")
def run_infra_scan(onion_address: str, clearnet_host: str | None = None) -> list[dict]:
    findings = scan_target(onion_address, clearnet_host)
    return [{"finding_type": f.finding_type, "detail": f.detail} for f in findings]


@celery_app.task(name="tasks.run_stylometry_match")
def run_stylometry_match(text_a: str, text_b: str) -> float:
    return similarity_score(text_a, text_b)


@celery_app.task(name="tasks.reanalyze_all", bind=True)
def reanalyze_all(self) -> dict:
    """Runs when a new lead is submitted (POST /api/leads): re-derives every
    actor cluster from the full set of raw personas, including the new one.

    Persists a real AnalysisJob row for this run — see that model's
    docstring for why this is the one path that populates it (CLI scripts
    call run_full_analysis directly, bypassing Celery)."""
    # Everything, including the initial job-row insert, lives inside this
    # try/finally — db.close() must run even if the *first* commit fails
    # (e.g. a transient DB error), or the session/connection leaks. This
    # task runs once per lead submission, so a leak here compounds across
    # runs until the connection pool is exhausted.
    db = SessionLocal()
    try:
        job = AnalysisJob(
            job_type="reanalyze_all",
            status="running",
            target="full pipeline reanalysis (all raw personas)",
            task_id=self.request.id,
        )
        db.add(job)
        db.commit()

        actors = run_full_analysis(db)
        result = {
            "actor_count": len(actors),
            "actors": [
                {"id": str(a.id), "label": a.label, "confidence_score": a.confidence_score}
                for a in actors
            ],
        }
        job.status = "success"
        job.result = result
        job.completed_at = _now()
        db.commit()
        return result
    except Exception as exc:
        # run_full_analysis may have left this session's transaction
        # aborted (e.g. a DB-level error mid-pipeline) — roll back before
        # recording failure, or this commit would itself raise.
        db.rollback()
        job.status = "failure"
        job.result = {"error": str(exc)[:500]}
        job.completed_at = _now()
        db.commit()
        raise
    finally:
        db.close()


@celery_app.task(name="tasks.run_scheduled_collection", bind=True)
def run_scheduled_collection(self) -> dict:
    """Runs on celery beat's fixed interval (see celery_app.py's
    beat_schedule) — the autonomous half of SIH PS-26151's "continuously
    gather footprints from reliable available sources": re-pulls the live
    public feeds Argus already knows how to ingest (Tor Onionoo relay list,
    MISP OSINT event/indicator feeds, HIBP breach directory), then re-runs
    the full pipeline so correlation reflects whatever's new — with no human
    having to trigger any of it.

    Each feed is best-effort and independent (mirrors
    scripts/ingest_misp_osint.py's own per-feed error handling): one feed
    being unreachable (network blip, feed reorganized) must not stop the
    others from ingesting, or block the pipeline re-run that follows using
    whatever data did land."""
    db = SessionLocal()
    try:
        job = AnalysisJob(
            job_type="scheduled_collection",
            status="running",
            target="onionoo + misp_osint + hibp -> full pipeline reanalysis",
            task_id=self.request.id,
        )
        db.add(job)
        db.commit()

        # Each ingest script opens/commits/closes its own SessionLocal
        # internally (see scripts/ingest_*.py) — independent of `db` above,
        # which is only used for this job's own bookkeeping and the
        # pipeline re-run, so a failure in one doesn't touch the others'
        # already-committed work.
        source_status: dict[str, str] = {}
        for source, run in (
            ("onionoo", lambda: ingest_onionoo(100)),
            ("misp_osint", lambda: ingest_misp_osint(200, settings.misp_max_events)),
            ("hibp", lambda: ingest_hibp(500)),
        ):
            try:
                run()
                source_status[source] = "ok"
            except Exception as exc:
                source_status[source] = f"failed: {str(exc)[:200]}"

        actors = run_full_analysis(db)
        result = {"sources": source_status, "actor_count": len(actors)}
        job.status = "success"
        job.result = result
        job.completed_at = _now()
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        job.status = "failure"
        job.result = {"error": str(exc)[:500]}
        job.completed_at = _now()
        db.commit()
        raise
    finally:
        db.close()
