"""Pulls event-level metadata from public MISP-format OSINT feeds (no auth
required) and upserts it into threat_events. Two independent community
feeds are used, both listed at misp-project.org/feeds/:
  - CIRCL's OSINT feed
  - botvrij.eu's OSINT feed (CUDESO)

The manifest is titles/dates/org/tags only, not per-attribute IOC detail —
fetching full detail for every event in either feed (thousands of files)
was judged not worth it for a dashboard-level view. But with NO real
indicator values ingested anywhere, genuine correlation against Argus's own
infrastructure data (app.services.correlation) is architecturally
impossible — so, in addition to the manifest, this script also fetches full
event JSON for the --indicator-limit most-recent events per feed and stores
their real domain/IP/URL/hash attributes in misp_indicators. Confirmed live
against both feeds: CIRCL's per-event JSON is unwrapped (fields at the top
level); botvrij.eu's is wrapped in an "Event" key — both are handled below,
each verified against a real response, not assumed identical.

Usage: python scripts/ingest_misp_osint.py [--limit N] [--indicator-limit N]
(--limit applies per feed, not to the combined total; --indicator-limit is
the number of most-recent events per feed to expand into real indicators)
"""
import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.external import MispIndicator, ThreatEvent  # noqa: E402

FEED_BASES = {
    "misp_circl_osint": "https://www.circl.lu/doc/misp/feed-osint/",
    "misp_botvrij_osint": "https://www.botvrij.eu/data/feed-osint/",
}
FEEDS = {source: base + "manifest.json" for source, base in FEED_BASES.items()}

# Only these attribute types are useful for deterministic correlation
# (app.services.correlation) — a free-text "comment" or "External analysis"
# link attribute has no matchable value shape.
CORRELATABLE_TYPES = {"ip-dst", "ip-src", "domain", "hostname", "url", "md5", "sha1", "sha256"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _fetch_indicators(db, source: str, base_url: str, event_uuid: str) -> int:
    try:
        resp = httpx.get(f"{base_url}{event_uuid}.json", timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError:
        return 0  # a missing/renamed event file shouldn't abort the whole run
    raw = resp.json()
    event = raw.get("Event", raw)  # botvrij.eu wraps in "Event"; CIRCL doesn't

    upserted = 0
    for attr in event.get("Attribute", []):
        attr_type = attr.get("type")
        value = attr.get("value")
        if attr_type not in CORRELATABLE_TYPES or not value:
            continue
        existing = (
            db.query(MispIndicator)
            .filter(
                MispIndicator.event_uuid == event_uuid,
                MispIndicator.indicator_type == attr_type,
                MispIndicator.value == value,
            )
            .first()
        )
        if existing is None:
            db.add(
                MispIndicator(
                    event_uuid=event_uuid,
                    source=source,
                    indicator_type=attr_type,
                    value=value,
                    category=attr.get("category"),
                )
            )
            upserted += 1
    return upserted


def main(limit: int, indicator_limit: int) -> None:
    db = SessionLocal()
    try:
        total_upserted = 0
        total_indicators = 0
        for source, manifest_url in FEEDS.items():
            resp = httpx.get(manifest_url, timeout=30)
            resp.raise_for_status()
            manifest: dict = resp.json()

            # Most-recent-first: the manifest has no guaranteed order, so sort by date.
            events = sorted(
                manifest.items(), key=lambda kv: kv[1].get("date") or "", reverse=True
            )[:limit]

            upserted = 0
            for event_uuid, event in events:
                existing = (
                    db.query(ThreatEvent).filter(ThreatEvent.event_uuid == event_uuid).first()
                )
                if existing is None:
                    existing = ThreatEvent(event_uuid=event_uuid, source=source)
                    db.add(existing)

                existing.org_name = (event.get("Orgc") or {}).get("name")
                existing.info = event.get("info", "")[:1024]
                existing.tags = [t.get("name") for t in event.get("Tag", []) if t.get("name")]
                existing.event_date = _parse_date(event.get("date"))
                existing.threat_level_id = event.get("threat_level_id")
                # See ingest_onionoo.py's _now() comment — same stale-timestamp
                # issue: without this, re-running against an event already in
                # the DB never bumps ingested_at, so source-registry's
                # "most recent" would only move when a brand-new event_uuid
                # appears, not on every real sync.
                existing.ingested_at = _now()
                upserted += 1

            db.commit()
            print(f"MISP OSINT: upserted {upserted} event(s) from {manifest_url}")
            total_upserted += upserted

            indicator_events = events[:indicator_limit]
            feed_indicators = 0
            for event_uuid, _event in indicator_events:
                feed_indicators += _fetch_indicators(db, source, FEED_BASES[source], event_uuid)
            db.commit()
            print(
                f"MISP OSINT: upserted {feed_indicators} real indicator(s) from "
                f"{len(indicator_events)} expanded event(s) ({source})"
            )
            total_indicators += feed_indicators

        print(
            f"MISP OSINT: {total_upserted} event(s), {total_indicators} indicator(s) "
            f"across {len(FEEDS)} feed(s)"
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--indicator-limit", type=int, default=10)
    args = parser.parse_args()
    main(args.limit, args.indicator_limit)
