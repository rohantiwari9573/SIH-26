"""app.services.pipeline.run_full_analysis against a real (SQLite) DB session,
with Neo4j writes mocked out — this is the function POST /api/leads and
scripts/ingest_and_attribute.py both call, so its correctness matters more
than either caller individually.
"""
from unittest.mock import MagicMock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.services.pipeline as pipeline
from app.db.base import Base
from app.models.actor import (
    Actor,
    Identifier,
    InfraFinding,
    RawActivity,
    RawPersona,
    ThreatActivity,
)


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


def test_rerun_does_not_crash_when_correlation_evidence_references_infra_finding(
    tmp_path, monkeypatch
):
    """Regression test: CorrelationEvidence.infra_finding_id/actor_id FK-
    reference infra_findings/actors with no DB-level cascade. The bulk
    `db.query(InfraFinding).delete()` / `db.query(Actor).delete()` calls
    below are raw-SQL deletes that bypass ORM relationship cascades, so
    without explicitly clearing CorrelationEvidence first, this crashed
    with a real ForeignKeyViolation the moment any correlation match
    existed and a second lead was submitted — reproduced live against
    Postgres before this test was written."""
    from app.models.external import CorrelationEvidence

    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)

    db.add(
        RawPersona(
            username="leaky_vendor",
            platform="platform_1",
            onion_address="leaky.onion",
        )
    )
    db.commit()

    pipeline.run_full_analysis(db)

    finding = db.query(InfraFinding).one()
    actor = db.query(Actor).one()
    db.add(
        CorrelationEvidence(
            source="hibp",
            source_record_id="TestBreach",
            evidence_type="breach_domain",
            matched_value="leaky.example.com",
            actor_id=actor.id,
            infra_finding_id=finding.id,
            description="manufactured for regression test",
        )
    )
    db.commit()

    # SQLite doesn't enforce foreign keys by default (unlike the real
    # Postgres this bug was actually reproduced against) — turn it on for
    # this session's connection so this test is a genuine regression guard
    # rather than one that would pass even without the fix in pipeline.py.
    db.execute(text("PRAGMA foreign_keys=ON"))

    # Must not raise IntegrityError/ForeignKeyViolation.
    pipeline.run_full_analysis(db)


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


def test_threat_activity_is_classified_and_linked_to_actor(tmp_path, monkeypatch):
    """A RawActivity with a clear category signal produces a ThreatActivity
    row linked to the actor its persona was clustered into, without altering
    that actor's confidence_score (attribution and categorization are
    separate pipelines — see app.services.pipeline)."""
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)

    persona = RawPersona(username="vendor_a", platform="platform_1", wallet="w1")
    db.add(persona)
    db.commit()

    db.add(
        RawActivity(
            raw_persona_id=persona.id,
            platform="platform_1",
            source_record_id="platform_1:listing:1",
            title="Fresh dumps",
            text="Offering stolen credentials, fully checked and verified.",
        )
    )
    db.commit()

    actors = pipeline.run_full_analysis(db)
    actor = next(a for a in actors if "vendor_a" in a.label)
    confidence_before = actor.confidence_score

    activities = db.query(ThreatActivity).all()
    assert len(activities) == 1
    activity = activities[0]
    assert activity.category == "credential_data_theft"
    assert activity.actor_id == actor.id
    assert activity.persona_username == "vendor_a"
    assert activity.classification_method == "keyword_rule"

    # Re-fetch the actor and confirm scoring wasn't touched by classification.
    refreshed = db.query(Actor).filter(Actor.id == actor.id).first()
    assert refreshed.confidence_score == confidence_before


def test_ambiguous_activity_stays_unclassified_and_no_row_is_created(tmp_path, monkeypatch):
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)

    persona = RawPersona(username="chatty_user", platform="platform_1")
    db.add(persona)
    db.commit()

    db.add(
        RawActivity(
            raw_persona_id=persona.id,
            platform="platform_1",
            source_record_id="platform_1:post:1",
            title=None,
            text="Looking for a developer to help with a small project.",
        )
    )
    db.commit()

    pipeline.run_full_analysis(db)

    assert db.query(ThreatActivity).count() == 0


def test_multiple_activities_same_category_aggregate_under_one_actor(tmp_path, monkeypatch):
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)

    persona = RawPersona(username="vendor_b", platform="platform_1")
    db.add(persona)
    db.commit()

    db.add_all(
        [
            RawActivity(
                raw_persona_id=persona.id,
                platform="platform_1",
                source_record_id="platform_1:listing:1",
                text="Selling stolen credentials, verified working.",
            ),
            RawActivity(
                raw_persona_id=persona.id,
                platform="platform_1",
                source_record_id="platform_1:listing:2",
                text="More stolen accounts available, fresh batch.",
            ),
        ]
    )
    db.commit()

    actors = pipeline.run_full_analysis(db)
    actor = next(a for a in actors if "vendor_b" in a.label)

    rows = (
        db.query(ThreatActivity)
        .filter(
            ThreatActivity.actor_id == actor.id,
            ThreatActivity.category == "credential_data_theft",
        )
        .all()
    )
    assert len(rows) == 2


def test_same_category_from_multiple_sources_reports_both(tmp_path, monkeypatch):
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)

    persona = RawPersona(username="vendor_c", platform="platform_1")
    db.add(persona)
    db.commit()

    db.add_all(
        [
            RawActivity(
                raw_persona_id=persona.id,
                platform="platform_1",
                source_record_id="platform_1:listing:1",
                text="Stolen credentials for sale.",
            ),
            RawActivity(
                raw_persona_id=persona.id,
                platform="platform_2",
                source_record_id="platform_2:post:1",
                title="Leak",
                text="unrelated text",
                source_category="Leaks",
            ),
        ]
    )
    db.commit()

    pipeline.run_full_analysis(db)

    sources = {
        row.source_platform
        for row in db.query(ThreatActivity).all()
    }
    assert sources == {"platform_1", "platform_2"}


def test_actor_with_no_activity_produces_no_threat_activity_rows(tmp_path, monkeypatch):
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)

    db.add(RawPersona(username="silent_vendor", platform="platform_1", wallet="w1"))
    db.commit()

    pipeline.run_full_analysis(db)

    assert db.query(ThreatActivity).count() == 0


def test_rerun_does_not_duplicate_threat_activity_rows(tmp_path, monkeypatch):
    _mock_neo4j(monkeypatch)
    db = _session(tmp_path)

    persona = RawPersona(username="vendor_d", platform="platform_1")
    db.add(persona)
    db.commit()
    db.add(
        RawActivity(
            raw_persona_id=persona.id,
            platform="platform_1",
            source_record_id="platform_1:listing:1",
            text="Selling stolen credentials.",
        )
    )
    db.commit()

    pipeline.run_full_analysis(db)
    pipeline.run_full_analysis(db)

    assert db.query(ThreatActivity).count() == 1
    # RawActivity itself must survive across reruns — see its docstring.
    assert db.query(RawActivity).count() == 1


def test_advisory_lock_skipped_on_sqlite(monkeypatch):
    """SQLite (used in every other test in this file) has no
    pg_advisory_xact_lock function and doesn't need one — a single-file test
    DB has no real concurrent-connection risk. Calling it unconditionally
    would break every SQLite-backed test in this suite."""
    monkeypatch.setattr(pipeline, "get_neo4j_client", lambda: MagicMock())
    db = _mock_session("sqlite")

    pipeline.run_full_analysis(db)

    assert db.execute.call_count == 0
