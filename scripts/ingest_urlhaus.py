"""Pulls recent malicious-URL entries from abuse.ch's URLhaus API into
malicious_urls. Requires an abuse.ch Auth-Key (free account, not fabricated
here) — see https://auth.abuse.ch/ to obtain one.

NOT CONFIGURED behavior: if URLHAUS_API_KEY is unset, this script prints a
clear NOT CONFIGURED message and exits 0 (not an error — an unconfigured
optional source is expected state, not a failure) without touching the
database. It never falls back to fabricated/sample rows.

Usage: python scripts/ingest_urlhaus.py [--limit N]
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.external import MaliciousUrl  # noqa: E402

# URLhaus's "recent URLs" bulk endpoint — see
# https://urlhaus-api.abuse.ch/ (payload=urls, no filtering by date).
RECENT_URL = "https://urlhaus-api.abuse.ch/v1/urls/recent/"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def main(limit: int) -> None:
    if not settings.urlhaus_api_key:
        print("URLhaus: NOT CONFIGURED — set URLHAUS_API_KEY to enable this source.")
        return

    resp = httpx.post(
        RECENT_URL,
        headers={"Auth-Key": settings.urlhaus_api_key},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("query_status") != "ok":
        raise SystemExit(f"URLhaus API returned: {payload.get('query_status')}")

    entries = payload.get("urls", [])[:limit]

    db = SessionLocal()
    try:
        upserted = 0
        for entry in entries:
            url = entry.get("url")
            if not url:
                continue
            existing = db.query(MaliciousUrl).filter(MaliciousUrl.url == url).first()
            if existing is None:
                existing = MaliciousUrl(url=url)
                db.add(existing)

            existing.url_status = entry.get("url_status")
            existing.threat = entry.get("threat")
            existing.host = entry.get("host")
            existing.tags = entry.get("tags") or []
            existing.date_added = _parse_dt(entry.get("date_added"))
            existing.ingested_at = _now()
            upserted += 1

        db.commit()
        print(f"URLhaus: upserted {upserted} URL(s) from {RECENT_URL}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    main(args.limit)
