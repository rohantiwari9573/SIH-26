"""Loads a sample of the Evolution Dark Web Cryptomarket Dataset (Zenodo
10171217) into RawPersona as two real historical platforms:
"evolution_market" (vendor listings) and "evolution_forum" (forum posts).

Unlike DarkForums (see ingest_darkforums.py), this dataset's public release
keeps real per-user handles — vendors.tsv has real usernames and real PGP
keys, user.tsv has real forum usernames, and forum-market/user-matching.tsv
records genuine analyst-confirmed cross-platform links between a forum
identity and a market identity for the same real person. That matching
file is used here as real GROUND TRUTH: this script preferentially ingests
matched pairs so Argus's own attribution pipeline can be checked against a
real answer key, not just against itself.

Only a slice is ingested, for two concrete reasons, both documented rather
than silently applied:
  1. The full dataset is ~2GB uncompressed (497,997 forum users, 133,844
     vendor-scrape rows, a 732MB listings file, a 298MB post file) — everything
     was streamed/sampled at extraction time (see data/external/evolution/),
     not re-read from the original 332MB archive here.
  2. app.services.attribution's stylometric pairing is O(n^2) over every
     persona that has sample_text — thousands of personas would make
     run_full_analysis impractically slow for a demo dataset.

Real PGP keys are hashed (SHA-256 of the full ASCII-armored key) rather than
stored verbatim — RawPersona.pgp_key is a fingerprint-shaped column
(String(512)) matching how the rest of Argus treats pgp_key (an identifier,
not a key-material blob), and armored keys here run well past that length.
The hash is computed from the real key text, not fabricated.

Usage: python scripts/ingest_evolution.py [--max-personas N]
"""
import argparse
import csv
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.actor import RawActivity, RawPersona  # noqa: E402
from app.services.pipeline import run_full_analysis  # noqa: E402

csv.field_size_limit(10_000_000)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "external" / "evolution"
MARKET_PLATFORM = "evolution_market"
FORUM_PLATFORM = "evolution_forum"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()


def _pgp_fingerprint(raw_key: str) -> str | None:
    if not raw_key or "BEGIN PGP" not in raw_key:
        return None
    return "sha256:" + hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _load_scrape_dates() -> dict[str, datetime]:
    dates: dict[str, datetime] = {}
    path = DATA_DIR / "market_scrapes.tsv"
    if not path.exists():
        return dates
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                dates[row["mscrape_id"]] = datetime(
                    int(row["scrape_year"]), int(row["scrape_month"]), int(row["scrape_day"]),
                    tzinfo=timezone.utc,
                )
            except (ValueError, KeyError):
                continue
    return dates


def _load_vendor_info(target_vids: set[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Streams vendors.tsv (123MB) rather than loading it fully — only keeps
    the first real username/PGP key seen per vid we actually need. Returns
    (usernames, pgp_fingerprints)."""
    usernames: dict[str, str] = {}
    keys: dict[str, str] = {}
    path = DATA_DIR / "vendors.tsv"
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            vid = row.get("vid")
            if vid not in target_vids:
                continue
            if vid not in usernames and row.get("username"):
                usernames[vid] = row["username"]
            if vid not in keys:
                fp = _pgp_fingerprint(row.get("pgp_key", ""))
                if fp:
                    keys[vid] = fp
    return usernames, keys


def _load_forum_usernames(target_uids: set[str]) -> dict[str, str]:
    usernames: dict[str, str] = {}
    path = DATA_DIR / "user.tsv"
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            uid = row.get("uid")
            if uid in target_uids and uid not in usernames:
                usernames[uid] = row["username"]
    return usernames


def _upsert_raw_activities(db, raw_persona_id, platform: str, activities: list[dict]) -> int:
    """Upserts by source_record_id (the exact real listing/post id) rather
    than blindly inserting, so re-running this script doesn't duplicate rows
    for the same underlying source item. Explicit db.flush() after each
    add — SessionLocal is autoflush=False (see app/db/session.py), so
    without this, two activities sharing a source_record_id within the same
    `activities` list (shouldn't happen given the caller dedupes by lid, but
    this function has no way to enforce that on its input) would both query
    "not found" and both get inserted, crashing the batch INSERT on the real
    unique constraint — reproduced live before this fix."""
    count = 0
    for act in activities:
        existing = (
            db.query(RawActivity)
            .filter(RawActivity.source_record_id == act["source_record_id"])
            .first()
        )
        if existing is None:
            existing = RawActivity(source_record_id=act["source_record_id"])
            db.add(existing)
        existing.raw_persona_id = raw_persona_id
        existing.platform = platform
        existing.title = act["title"]
        existing.text = act["text"]
        existing.source_category = None
        existing.observed_at = act.get("observed_at")
        db.flush()
        count += 1
    return count


def main(max_personas: int) -> None:
    if not (DATA_DIR / "vendors.tsv").exists() or not (DATA_DIR / "user.tsv").exists():
        raise SystemExit(
            f"{DATA_DIR}/vendors.tsv and/or user.tsv not found — these are 123MB/27MB and "
            "not committed to the repo. Re-extract them from the full archive:\n"
            "  curl -L -o data/external/evolution_data.zip "
            "'https://zenodo.org/records/10171217/files/data-and-readme.zip?download=1'\n"
            "  unzip -p data/external/evolution_data.zip market/vendors.tsv "
            "> data/external/evolution/vendors.tsv\n"
            "  unzip -p data/external/evolution_data.zip forum/user.tsv "
            "> data/external/evolution/user.tsv\n"
            "(The other files this script reads — user-matching.tsv, listings_sample.tsv, "
            "post_sample.tsv, market_scrapes.tsv — are small and already committed.)"
        )

    with (DATA_DIR / "user-matching.tsv").open(encoding="utf-8") as f:
        matches = list(csv.DictReader(f, delimiter="\t"))

    with (DATA_DIR / "listings_sample.tsv").open(encoding="utf-8") as f:
        listing_rows = list(csv.DictReader(f, delimiter="\t"))
    with (DATA_DIR / "post_sample.tsv").open(encoding="utf-8") as f:
        post_rows = list(csv.DictReader(f, delimiter="\t"))

    listing_vids = {row["vid"] for row in listing_rows}
    post_uids = {row["uid"] for row in post_rows}

    # Matched pairs with real text on both sides are ingested first (these
    # are the genuine ground-truth cross-platform links); remaining budget
    # fills in with any other vendor/forum-user that has real text.
    matched = [m for m in matches if m["vid"] in listing_vids and m["uid"] in post_uids]
    max_pairs = max_personas // 2
    chosen = matched[:max_pairs]

    chosen_vids = {m["vid"] for m in chosen}
    chosen_uids = {m["uid"] for m in chosen}
    remaining = max_personas - 2 * len(chosen)
    for vid in listing_vids - chosen_vids:
        if remaining <= 0:
            break
        chosen_vids.add(vid)
        remaining -= 1
    for uid in post_uids - chosen_uids:
        if remaining <= 0:
            break
        chosen_uids.add(uid)
        remaining -= 1

    scrape_dates = _load_scrape_dates()
    vendor_usernames, vendor_pgp = _load_vendor_info(chosen_vids)
    forum_usernames = _load_forum_usernames(chosen_uids)

    # market_activities/forum_activities: real, individual per-listing/per-
    # post records — the input to threat categorization (see
    # app.services.threat_categorization). Built alongside, not instead of,
    # market_text/forum_text (the joined blob StyleProfile/attribution still
    # needs) — see RawActivity's docstring for why per-item granularity has
    # to be captured here rather than reconstructed later from sample_text.
    market_text: dict[str, list[str]] = {}
    market_activities: dict[str, list[dict]] = {}
    market_date: dict[str, datetime] = {}
    for row in listing_rows:
        vid = row["vid"]
        if vid not in chosen_vids:
            continue
        title = (row.get("title") or "").strip()
        desc = _strip_html(row.get("description", ""))
        if desc:
            market_text.setdefault(vid, []).append(f"[{title}] {desc}")
        scrape_date = scrape_dates.get(row.get("mscrape_id"))
        if scrape_date and (vid not in market_date or scrape_date < market_date[vid]):
            market_date[vid] = scrape_date
        # listings_sample.tsv has one row per *scrape* of a listing, not one
        # row per listing — the same lid recurs many times (2999 rows over
        # only 72 unique lids in the committed sample; confirmed by
        # inspection, not assumed). Each lid must map to exactly ONE
        # RawActivity (source_record_id is a real unique constraint) — keep
        # the earliest-observed scrape's title/description as the
        # representative content for that listing, updating in place if an
        # earlier scrape than what's already stored is found (rows are not
        # guaranteed sorted by date).
        if title or desc:
            key = f"evolution_market:listing:{row['lid']}"
            existing_acts = market_activities.setdefault(vid, [])
            match = next((a for a in existing_acts if a["source_record_id"] == key), None)
            if match is None:
                existing_acts.append(
                    {
                        "source_record_id": key,
                        "title": title or None,
                        "text": (desc or title)[:4000],
                        "observed_at": scrape_date,
                    }
                )
            elif scrape_date and (
                match["observed_at"] is None or scrape_date < match["observed_at"]
            ):
                match["title"] = title or match["title"]
                match["text"] = (desc or title)[:4000]
                match["observed_at"] = scrape_date

    forum_text: dict[str, list[str]] = {}
    forum_activities: dict[str, list[dict]] = {}
    forum_date: dict[str, datetime] = {}
    for row in post_rows:
        uid = row["uid"]
        if uid not in chosen_uids:
            continue
        text = _strip_html(row.get("text", ""))
        if text:
            forum_text.setdefault(uid, []).append(text)
        try:
            post_date = datetime(
                int(row["year"]), int(row["month"]), int(row["day"]), tzinfo=timezone.utc
            )
        except (ValueError, KeyError):
            post_date = None
        if post_date and (uid not in forum_date or post_date < forum_date[uid]):
            forum_date[uid] = post_date
        if text:
            forum_activities.setdefault(uid, []).append(
                {
                    "source_record_id": f"evolution_forum:post:{row['pid']}",
                    "title": None,
                    "text": text[:4000],
                    "observed_at": post_date,
                }
            )

    db = SessionLocal()
    try:
        upserted = 0
        activities_upserted = 0
        for vid, snippets in market_text.items():
            username = vendor_usernames.get(vid)
            if not username:
                continue
            lead = (
                db.query(RawPersona)
                .filter(RawPersona.username == username, RawPersona.platform == MARKET_PLATFORM)
                .first()
            )
            if lead is None:
                lead = RawPersona(username=username, platform=MARKET_PLATFORM)
                db.add(lead)
            lead.sample_text = " ".join(snippets)[:20000]
            lead.pgp_key = vendor_pgp.get(vid)
            if vid in market_date:
                lead.submitted_at = market_date[vid]
            db.flush()
            activities_upserted += _upsert_raw_activities(
                db, lead.id, MARKET_PLATFORM, market_activities.get(vid, [])
            )
            upserted += 1

        for uid, snippets in forum_text.items():
            username = forum_usernames.get(uid)
            if not username:
                continue
            lead = (
                db.query(RawPersona)
                .filter(RawPersona.username == username, RawPersona.platform == FORUM_PLATFORM)
                .first()
            )
            if lead is None:
                lead = RawPersona(username=username, platform=FORUM_PLATFORM)
                db.add(lead)
            lead.sample_text = " ".join(snippets)[:20000]
            if uid in forum_date:
                lead.submitted_at = forum_date[uid]
            db.flush()
            activities_upserted += _upsert_raw_activities(
                db, lead.id, FORUM_PLATFORM, forum_activities.get(uid, [])
            )
            upserted += 1

        db.commit()
        print(f"Evolution dataset: upserted {upserted} persona(s) "
              f"({len(chosen)} from genuine matched ground-truth pairs), "
              f"{activities_upserted} individual activity record(s)")
    finally:
        db.close()

    db = SessionLocal()
    try:
        actors = run_full_analysis(db)
        print(f"Re-ran attribution: {len(actors)} actor(s) now derived.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-personas", type=int, default=150)
    args = parser.parse_args()
    main(args.max_personas)
