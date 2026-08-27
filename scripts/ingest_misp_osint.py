"""Pulls event-level metadata from CIRCL's public MISP OSINT feed (no auth
required) and upserts it into threat_events.

This is the feed's manifest — titles, dates, org, tags — not per-attribute
IOC detail (that would mean fetching 1,600+ individual event files, judged
not worth it for a dashboard-level view). Real threat-intel event data (see
ARGUS_DATA_RESOURCES.md #4), but a feed entry is not proof any specific
actor owns/controls anything it mentions.

Usage: python scripts/ingest_misp_osint.py [--limit N]
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.external import ThreatEvent  # noqa: E402

MANIFEST_URL = "https://www.circl.lu/doc/misp/feed-osint/manifest.json"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def main(limit: int) -> None:
    resp = httpx.get(MANIFEST_URL, timeout=30)
    resp.raise_for_status()
    manifest: dict = resp.json()

    # Most-recent-first: the manifest has no guaranteed order, so sort by date.
    events = sorted(
        manifest.items(), key=lambda kv: kv[1].get("date") or "", reverse=True
    )[:limit]

    db = SessionLocal()
    try:
        upserted = 0
        for event_uuid, event in events:
            existing = (
                db.query(ThreatEvent).filter(ThreatEvent.event_uuid == event_uuid).first()
            )
            if existing is None:
                existing = ThreatEvent(event_uuid=event_uuid, source="misp_circl_osint")
                db.add(existing)

            existing.org_name = (event.get("Orgc") or {}).get("name")
            existing.info = event.get("info", "")[:1024]
            existing.tags = [t.get("name") for t in event.get("Tag", []) if t.get("name")]
            existing.event_date = _parse_date(event.get("date"))
            existing.threat_level_id = event.get("threat_level_id")
            upserted += 1

        db.commit()
        print(f"MISP OSINT: upserted {upserted} event(s) from {MANIFEST_URL}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    main(args.limit)
