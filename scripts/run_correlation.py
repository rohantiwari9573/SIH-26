"""Runs deterministic correlation (app.services.correlation) standalone,
without submitting a lead — useful after re-running the live-source ingest
scripts to check whether newly-fetched intel matches infra Argus already
knows about. (app.services.pipeline.run_full_analysis also runs this
automatically on every lead submission.)

Usage: python scripts/run_correlation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.services.correlation import run_correlation  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        results = run_correlation(db)
        for r in results:
            print(f"{r.source}: {r.matches_found} new match(es)")
        if not any(r.matches_found for r in results):
            print(
                "No new matches — expected against synthetic/self-hosted infrastructure "
                "with no real overlap with live external feeds. This means the correlation "
                "logic ran, not that it's broken."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
