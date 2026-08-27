"""app.services.pipeline.run_full_analysis against a real (SQLite) DB session,
with Neo4j writes mocked out — this is the function POST /api/leads and
scripts/ingest_and_attribute.py both call, so its correctness matters more
than either caller individually.
"""
from unittest.mock import MagicMock

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


def test_same_username_on_different_platforms_are_kept_as_distinct_personas(tmp_path, monkeypatch):
    """RawPersona explicitly allows the same username to legitimately appear
    on two different platforms as two different real people (that's what its
    upsert-on-(username, platform) semantics assume). A prior version of the
    pipeline keyed everything by bare username, which silently dropped one
    persona's wallet/PGP/style data when this happened — no crash, just
    quietly wrong results. Both must now persist correctly, unmerged, since
    nothing here links them (different wallets, no shared PGP key, no
    matching writing style)."""
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)

    db.add(
        RawPersona(
            username="shadow_vendor",
            platform="platform_1",
            wallet="wallet_from_platform_1",
        )
    )
    db.add(
        RawPersona(
            username="shadow_vendor",
            platform="platform_2",
            wallet="wallet_from_platform_2",
        )
    )
    db.commit()

    actors = pipeline.run_full_analysis(db)

    assert len(actors) == 2, "two distinct personas sharing a username must not collapse into one"

    identifiers = db.query(Identifier).filter(Identifier.identifier_type == "wallet").all()
    wallets = {ident.value for ident in identifiers}
    assert wallets == {"wallet_from_platform_1", "wallet_from_platform_2"}, (
        "both personas' wallet data must survive — a dict keyed by bare "
        "username would have silently dropped one"
    )


def _mock_session(dialect_name: str) -> MagicMock:
    db = MagicMock()
    db.bind.dialect.name = dialect_name
    db.query.return_value.all.return_value = []
    return db


def test_advisory_lock_acquired_on_postgres(monkeypatch):
    """Reproduced live: two POST /api/leads submitted close together enqueue
    two Celery tasks that ran in parallel worker processes, and one crashed
    with a ForeignKeyViolation deleting rows the other had just committed.
    pg_advisory_xact_lock serializes concurrent runs — confirm it's actually
    requested against Postgres."""
    monkeypatch.setattr(pipeline, "get_neo4j_client", lambda: MagicMock())
    db = _mock_session("postgresql")

    pipeline.run_full_analysis(db)

    assert db.execute.call_count == 1
    statement = db.execute.call_args_list[0].args[0]
    assert "pg_advisory_xact_lock" in statement.text


def test_advisory_lock_skipped_on_sqlite(monkeypatch):
    """SQLite (used in every other test in this file) has no
    pg_advisory_xact_lock function and doesn't need one — a single-file test
    DB has no real concurrent-connection risk. Calling it unconditionally
    would break every SQLite-backed test in this suite."""
    monkeypatch.setattr(pipeline, "get_neo4j_client", lambda: MagicMock())
    db = _mock_session("sqlite")

    pipeline.run_full_analysis(db)

    assert db.execute.call_count == 0
