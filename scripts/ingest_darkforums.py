"""Loads the DarkForums Threat Intelligence Dataset (Zenodo 21991378,
data/external/darkforums_safe_corpus.json) as a clearly-labeled DEMO
OVERLAY, then re-runs full attribution so it shows up as real Actor data.

Important: the dataset's public "safe" release redacts every post's author
to one of two literal placeholder values ("[AUTHOR]" / "unknown") — there is
no real handle/persona diversity in this file, which defeats its documented
purpose (handle discovery, stylometric persona clustering). Per an explicit
user decision, this script assigns each of those two placeholders a
readable synthetic handle (not additional fabricated diversity beyond what
the source actually contains) and tags every row with
platform="darkforums_demo_overlay" so the UI can flag it clearly. The post
CONTENT itself is real (real leak-forum thread titles/text); only the
author identity is synthetic.

Usage: python scripts/ingest_darkforums.py
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.actor import RawActivity, RawPersona  # noqa: E402
from app.services.pipeline import run_full_analysis  # noqa: E402

CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "external" / "darkforums_safe_corpus.json"
PLATFORM = "darkforums_demo_overlay"

# Deliberately only these two — matches the only two author values the
# source data actually contains. Do not add more without more real signal.
HANDLE_MAP = {
    "[AUTHOR]": "df_demo_named_author",
    "unknown": "df_demo_unknown_author",
}


def _parse_post_date(value: str) -> datetime | None:
    for fmt in ("%d-%m-%y, %I:%M %p", "%m-%d-%y, %I:%M %p"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def main() -> None:
    if not CORPUS_PATH.exists():
        raise SystemExit(
            f"{CORPUS_PATH} not found — download safe_corpus.json from "
            "https://zenodo.org/records/21991378 first."
        )

    threads = [json.loads(line) for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()]

    # Bucket real post content by which of the two placeholder authors wrote
    # it. activities also keeps each individual post as its own record — the
    # real "category" field the source data provides (see RawActivity's
    # docstring) — rather than only the joined blob in sample_text.
    buckets: dict[str, list[str]] = {handle: [] for handle in HANDLE_MAP.values()}
    activities: dict[str, list[dict]] = {handle: [] for handle in HANDLE_MAP.values()}
    earliest: dict[str, datetime] = {}

    for thread in threads:
        thread_title = thread.get("title", "")
        thread_category = thread.get("category")
        for post in thread.get("posts", []):
            raw_author = post.get("author", "unknown")
            handle = HANDLE_MAP.get(raw_author, HANDLE_MAP["unknown"])
            content = re.sub(r"\s+", " ", post.get("content", "")).strip()
            if content:
                buckets[handle].append(f"[{thread_title}] {content}")
            observed = _parse_post_date(post.get("post_date", ""))
            if observed and (handle not in earliest or observed < earliest[handle]):
                earliest[handle] = observed
            post_id = post.get("post_id")
            if content and post_id:
                activities[handle].append(
                    {
                        "source_record_id": f"darkforums:post:{post_id}",
                        "title": thread_title or None,
                        "text": content[:4000],
                        "source_category": thread_category,
                        "observed_at": observed,
                    }
                )

    db = SessionLocal()
    try:
        upserted = 0
        activities_upserted = 0
        for handle, snippets in buckets.items():
            if not snippets:
                continue
            lead = (
                db.query(RawPersona)
                .filter(RawPersona.username == handle, RawPersona.platform == PLATFORM)
                .first()
            )
            if lead is None:
                lead = RawPersona(username=handle, platform=PLATFORM)
                db.add(lead)

            lead.sample_text = " ".join(snippets)[:20000]
            if handle in earliest:
                lead.submitted_at = earliest[handle]
            db.flush()

            for act in activities.get(handle, []):
                existing = (
                    db.query(RawActivity)
                    .filter(RawActivity.source_record_id == act["source_record_id"])
                    .first()
                )
                if existing is None:
                    existing = RawActivity(source_record_id=act["source_record_id"])
                    db.add(existing)
                existing.raw_persona_id = lead.id
                existing.platform = PLATFORM
                existing.title = act["title"]
                existing.text = act["text"]
                existing.source_category = act["source_category"]
                existing.observed_at = act["observed_at"]
                activities_upserted += 1

            upserted += 1

        db.commit()
        print(
            f"DarkForums demo overlay: upserted {upserted} synthetic-handle persona(s), "
            f"{activities_upserted} individual activity record(s)"
        )
    finally:
        db.close()

    db = SessionLocal()
    try:
        actors = run_full_analysis(db)
        print(f"Re-ran attribution: {len(actors)} actor(s) now derived.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
