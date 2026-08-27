"""app.services.pipeline.run_full_analysis against a real (SQLite) DB session,
with Neo4j writes mocked out — this is the function POST /api/leads and
scripts/ingest_and_attribute.py both call, so its correctness matters more
than either caller individually.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.pipeline as pipeline
from app.db.base import Base
from app.models.actor import Actor, Identifier, RawPersona


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline_test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class _FakeNeo4jClient:
    def __init__(self):
        self.cleared = False

    def clear_all(self):
        self.cleared = True


def _mock_neo4j(monkeypatch) -> _FakeNeo4jClient:
    monkeypatch.setattr(pipeline, "ingest_marketplace_record", lambda record: None)
    fake_client = _FakeNeo4jClient()
    monkeypatch.setattr(pipeline, "get_neo4j_client", lambda: fake_client)
    return fake_client


def test_run_full_analysis_derives_clusters_from_raw_personas(tmp_path, monkeypatch):
    fake_neo4j = _mock_neo4j(monkeypatch)
    db = _session(tmp_path)

    shared_text_a = (
        "I think, honestly, that this batch is better than the last one. "
        "You should really trust the process, and I mean really trust it. "
        "Escrow is fine for new buyers, I have done this a long time and "
        "nobody has ever had a real problem with me, not once."
    )
    shared_text_b = (
        "Honestly, I think this batch is better than before. You should "
        "really trust the process here, I really mean that. Escrow is "
        "fine, I have been doing this a long time now and honestly nobody "
        "has ever had a real problem with me here either, not once."
    )

    db.add(
        RawPersona(
            username="vendor_a",
            platform="platform_1",
            sample_text=shared_text_a,
            wallet="shared_wallet",
            pgp_key="shared_key",
        )
    )
    db.add(
        RawPersona(
            username="vendor_b",
            platform="platform_2",
            sample_text=shared_text_b,
            wallet="shared_wallet",
            pgp_key="shared_key",
        )
    )
    db.add(RawPersona(username="solo_vendor", platform="platform_1", wallet="unrelated_wallet"))
    db.commit()

    actors = pipeline.run_full_analysis(db)

    labels = {a.label for a in actors}
    assert any("vendor_a" in label and "vendor_b" in label for label in labels)

    merged = next(a for a in actors if "vendor_a" in a.label and "vendor_b" in a.label)
    assert merged.confidence_score > 0.6

    solo = next(a for a in actors if a.label == "Actor: solo_vendor")
    assert solo.confidence_score == 0.0

    assert fake_neo4j.cleared, "run_full_analysis must clear stale Neo4j data before re-pushing"


def test_run_full_analysis_is_idempotent_on_rerun(tmp_path, monkeypatch):
    """Re-running against the same RawPersona set shouldn't accumulate
    duplicate Actor/Identifier rows — derived tables are rebuilt, not appended."""
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)

    db.add(RawPersona(username="only_vendor", platform="platform_1"))
    db.commit()

    pipeline.run_full_analysis(db)
    pipeline.run_full_analysis(db)

    assert db.query(Actor).count() == 1
    assert db.query(Identifier).count() == 1
