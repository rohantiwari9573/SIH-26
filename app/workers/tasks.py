"""Async analysis jobs. Analysis (stylometry over many samples, infra scans,
graph traversal) shouldn't block the HTTP request — the API enqueues a job and
returns a job id; the dashboard polls /api/jobs/{id} for status."""
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models.actor import AnalysisJob
from app.services.infra_scan.scanner import scan_target
from app.services.pipeline import run_full_analysis
from app.services.stylometry.classifier import similarity_score
from app.workers.celery_app import celery_app


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
    db = SessionLocal()
    job = AnalysisJob(
        job_type="reanalyze_all",
        status="running",
        target="full pipeline reanalysis (all raw personas)",
        task_id=self.request.id,
    )
    db.add(job)
    db.commit()
    try:
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
