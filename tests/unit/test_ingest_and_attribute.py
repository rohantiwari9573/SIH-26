"""scripts/ingest_and_attribute.py — regression coverage for a real bug
found in a full-codebase audit: main() used to run
`db.query(RawPersona).delete()` unconditionally before loading
data/personas.json's 7 demo personas, silently destroying every OTHER
RawPersona row in the database (real submitted leads, Evolution Market
data, DarkForums data, anything) on any non-empty database this script was
run against. Fixed to upsert by (username, platform), the same idempotent
pattern every other ingestion path in this codebase uses.
"""
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.ingest_and_attribute as ingest_and_attribute
from app.db.base import Base
from app.models.actor import RawPersona


def _session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ingest_and_attribute_test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_main_does_not_delete_unrelated_raw_personas(tmp_path, monkeypatch):
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(ingest_and_attribute, "SessionLocal", SessionLocal)
    monkeypatch.setattr(ingest_and_attribute, "run_full_analysis", lambda db, **kw: [])

    # Simulate a database that already holds real, unrelated data (a real
    # submitted lead, in this case) BEFORE this demo script is run.
    db = SessionLocal()
    db.add(RawPersona(username="real_submitted_lead", platform="darkforums_demo_overlay"))
    db.commit()
    db.close()

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "personas.json").write_text(
        json.dumps([{"username": "demo_vendor", "platform": "mock_marketplace_1"}])
    )
    (data_dir / "wallet_transactions.json").write_text("[]")
    monkeypatch.setattr(ingest_and_attribute, "DATA_DIR", data_dir)

    ingest_and_attribute.main()

    db = SessionLocal()
    usernames = {p.username for p in db.query(RawPersona).all()}
    db.close()

    assert "real_submitted_lead" in usernames, "unrelated pre-existing data must survive"
    assert "demo_vendor" in usernames


def test_main_is_idempotent_on_rerun(tmp_path, monkeypatch):
    """Running twice must upsert the same row, not duplicate it."""
    SessionLocal = _session_factory(tmp_path)
    monkeypatch.setattr(ingest_and_attribute, "SessionLocal", SessionLocal)
    monkeypatch.setattr(ingest_and_attribute, "run_full_analysis", lambda db, **kw: [])

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "personas.json").write_text(
        json.dumps([{"username": "demo_vendor", "platform": "mock_marketplace_1"}])
    )
    (data_dir / "wallet_transactions.json").write_text("[]")
    monkeypatch.setattr(ingest_and_attribute, "DATA_DIR", data_dir)

    ingest_and_attribute.main()
    ingest_and_attribute.main()

    db = SessionLocal()
    count = db.query(RawPersona).filter(RawPersona.username == "demo_vendor").count()
    db.close()
    assert count == 1
