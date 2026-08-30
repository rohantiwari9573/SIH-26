"""Pulls the public breach directory from Have I Been Pwned (no API key
required — this is the /breaches list endpoint, distinct from HIBP's
per-email lookup which does require a paid key Argus doesn't hold).

This is breach *metadata* only: name, domain, scale, what categories of
data were exposed. It is not a record of any specific person or email
address, and Argus must not present it as such — see
ARGUS_DATA_RESOURCES.md #8's limitation note.

Usage: python scripts/ingest_hibp.py [--limit N]
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.external import BreachRecord  # noqa: E402


def _now() -> datetime:
    return datetime.now(timezone.utc)

BREACHES_URL = "https://haveibeenpwned.com/api/v3/breaches"


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_datetime(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def main(limit: int) -> None:
    resp = httpx.get(
        BREACHES_URL,
        headers={"User-Agent": "Argus-SIH26151-Research"},
        timeout=30,
    )
    resp.raise_for_status()
    breaches: list[dict] = resp.json()

    breaches = sorted(
        breaches, key=lambda b: b.get("AddedDate") or "", reverse=True
    )[:limit]

    db = SessionLocal()
    try:
        upserted = 0
        for b in breaches:
            existing = db.query(BreachRecord).filter(BreachRecord.name == b["Name"]).first()
            if existing is None:
                existing = BreachRecord(name=b["Name"])
                db.add(existing)

            existing.domain = b.get("Domain") or None
            existing.breach_date = _parse_date(b.get("BreachDate"))
            existing.added_date = _parse_datetime(b.get("AddedDate"))
            existing.pwn_count = b.get("PwnCount", 0)
            existing.data_classes = b.get("DataClasses", [])
            existing.is_verified = bool(b.get("IsVerified", False))
            # See ingest_onionoo.py's _now() comment — same fix: bump on
            # every upsert so a re-run against already-known breaches still
            # advances source-registry's "most recent sync" timestamp.
            existing.ingested_at = _now()
            upserted += 1

        db.commit()
        print(f"HIBP: upserted {upserted} breach record(s) from {BREACHES_URL}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    main(args.limit)
