"""Async analysis jobs. Analysis (stylometry over many samples, infra scans,
graph traversal) shouldn't block the HTTP request — the API enqueues a job and
returns a job id; the dashboard polls /api/jobs/{id} for status."""
from app.db.session import SessionLocal
from app.services.infra_scan.scanner import scan_target
from app.services.pipeline import run_full_analysis
from app.services.stylometry.classifier import similarity_score
from app.workers.celery_app import celery_app


@celery_app.task(name="tasks.run_infra_scan")
def run_infra_scan(onion_address: str, clearnet_host: str | None = None) -> list[dict]:
    findings = scan_target(onion_address, clearnet_host)
    return [{"finding_type": f.finding_type, "detail": f.detail} for f in findings]


@celery_app.task(name="tasks.run_stylometry_match")
def run_stylometry_match(text_a: str, text_b: str) -> float:
    return similarity_score(text_a, text_b)


@celery_app.task(name="tasks.reanalyze_all")
def reanalyze_all() -> dict:
    """Runs when a new lead is submitted (POST /api/leads): re-derives every
    actor cluster from the full set of raw personas, including the new one."""
    db = SessionLocal()
    try:
        actors = run_full_analysis(db)
        return {
            "actor_count": len(actors),
            "actors": [
                {"id": str(a.id), "label": a.label, "confidence_score": a.confidence_score}
                for a in actors
            ],
        }
    finally:
        db.close()
