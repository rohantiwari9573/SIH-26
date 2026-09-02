"""Pulls reported-scam wallet addresses from Chainabuse into abuse_reports.
Requires a Chainabuse API key (not fabricated here) — see
https://www.chainabuse.com/api to request one.

NOT CONFIGURED behavior: if CHAINABUSE_API_KEY is unset, this script prints
a clear NOT CONFIGURED message and exits 0 without touching the database.
It never falls back to fabricated/sample rows.

UNVERIFIED RESPONSE SHAPE: unlike this project's other ingest_*.py scripts,
the field-parsing below has NOT been checked against a real authenticated
response — no Chainabuse key was available while building this. It follows
Chainabuse's public API documentation as of when this was written, but
should be re-verified (print a raw response and compare) the first time
someone actually runs this with a real key, before trusting the resulting
rows.

Usage: python scripts/ingest_chainabuse.py [--limit N]
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.external import AbuseReport  # noqa: E402

API_URL = "https://api.chainabuse.com/v0/reports"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def main(limit: int) -> None:
    if not settings.chainabuse_api_key:
        print("Chainabuse: NOT CONFIGURED — set CHAINABUSE_API_KEY to enable this source.")
        return

    resp = httpx.get(
        API_URL,
        headers={"Authorization": f"Bearer {settings.chainabuse_api_key}"},
        params={"perPage": min(limit, 100)},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    # See module docstring — this key/shape is best-effort from docs, not
    # verified live. If the API ever returns a bare top-level list, calling
    # .get() on it would crash — check the list case FIRST, not as a
    # fallback argument to .get() (which still evaluates .get() against a
    # list and raises AttributeError before the fallback is ever used).
    reports = (payload if isinstance(payload, list) else payload.get("data", []))[:limit]

    db = SessionLocal()
    try:
        upserted = 0
        for report in reports:
            report_id = str(report.get("id") or report.get("reportId") or "")
            if not report_id:
                continue
            existing = db.query(AbuseReport).filter(AbuseReport.report_id == report_id).first()
            if existing is None:
                existing = AbuseReport(report_id=report_id)
                db.add(existing)

            addresses = report.get("addresses") or []
            first_addr = addresses[0] if addresses else {}
            existing.address = report.get("address") or first_addr.get("address")
            existing.chain = report.get("chain") or first_addr.get("chain")
            existing.category = report.get("category") or report.get("scamCategory")
            existing.description = (report.get("description") or "")[:2048] or None
            existing.reported_at = _parse_dt(report.get("createdAt") or report.get("reportedAt"))
            existing.ingested_at = _now()
            upserted += 1

        db.commit()
        print(f"Chainabuse: upserted {upserted} report(s) from {API_URL}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    main(args.limit)
