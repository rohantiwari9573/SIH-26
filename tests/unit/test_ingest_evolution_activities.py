"""Regression test for a real bug found in Phase 5: listings_sample.tsv has
one row per *scrape* of a listing, not one row per listing (2999 rows over
only 72 unique lids in the committed sample) — source_record_id must map
1:1 to a real unique constraint, and _upsert_raw_activities must not crash
or duplicate-insert when its input list contains the same source_record_id
twice (SessionLocal is autoflush=False, so a naive per-item
query-then-insert can miss an in-batch duplicate — see that function's
docstring in scripts/ingest_evolution.py).
"""
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import ingest_evolution  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.models.actor import RawActivity, RawPersona  # noqa: E402


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ingest_test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_upsert_raw_activities_dedupes_repeated_source_record_id(tmp_path):
    db = _session(tmp_path)
    persona = RawPersona(username="vendor_a", platform="evolution_market")
    db.add(persona)
    db.flush()

    activities = [
        {
            "source_record_id": "evolution_market:listing:3",
            "title": "Old title",
            "text": "First scrape of this listing",
            "observed_at": None,
        },
        {
            "source_record_id": "evolution_market:listing:3",
            "title": "Old title",
            "text": "Second scrape of the same listing (repeated lid)",
            "observed_at": None,
        },
    ]

    count = ingest_evolution._upsert_raw_activities(db, persona.id, "evolution_market", activities)
    db.commit()

    assert count == 2  # both processed, but...
    rows = (
        db.query(RawActivity)
        .filter(RawActivity.source_record_id == "evolution_market:listing:3")
        .all()
    )
    assert len(rows) == 1, "duplicate source_record_id in one batch must not create two rows"
    # The second (later-processed) item's content wins, matching upsert semantics.
    assert rows[0].text == "Second scrape of the same listing (repeated lid)"
