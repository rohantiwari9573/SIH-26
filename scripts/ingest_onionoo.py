"""Pulls a slice of live Tor relay metadata from the Tor Project's public
Onionoo API (no auth required) and upserts it into tor_relays.

Real, continuously-refreshed infrastructure data (see
ARGUS_DATA_RESOURCES.md #3) — but it identifies relay operators, not
dark-web hidden-service operators. Never treat a relay by itself as
attribution evidence for a threat actor.

Usage: python scripts/ingest_onionoo.py [--limit N]
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.external import TorRelay  # noqa: E402

ONIONOO_URL = "https://onionoo.torproject.org/details"
FIELDS = "fingerprint,nickname,or_addresses,country,running,flags,first_seen,last_seen"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def main(limit: int) -> None:
    resp = httpx.get(ONIONOO_URL, params={"limit": limit, "fields": FIELDS}, timeout=30)
    resp.raise_for_status()
    relays = resp.json().get("relays", [])

    db = SessionLocal()
    try:
        upserted = 0
        for relay in relays:
            fingerprint = relay.get("fingerprint")
            if not fingerprint:
                continue
            ip_addresses = [addr.rsplit(":", 1)[0] for addr in relay.get("or_addresses", [])]

            existing = db.query(TorRelay).filter(TorRelay.fingerprint == fingerprint).first()
            if existing is None:
                existing = TorRelay(fingerprint=fingerprint)
                db.add(existing)

            existing.nickname = relay.get("nickname", "")
            existing.ip_addresses = ip_addresses
            existing.country = relay.get("country")
            existing.running = bool(relay.get("running", False))
            existing.flags = relay.get("flags", [])
            existing.first_seen = _parse_dt(relay.get("first_seen"))
            existing.last_seen = _parse_dt(relay.get("last_seen"))
            upserted += 1

        db.commit()
        print(f"Onionoo: upserted {upserted} relay(s) from {ONIONOO_URL}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    main(args.limit)
