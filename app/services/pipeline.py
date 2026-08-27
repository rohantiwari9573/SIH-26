"""The full "database collection, storage, analysis" pipeline the PS asks for,
as one reusable function: read every submitted RawPersona, re-derive actor
clusters from scratch, and persist the result. Shared by the CLI script
(`scripts/ingest_and_attribute.py`) and the Celery task that runs when a new
lead is submitted through the API — one implementation, not two copies that
drift apart.

Re-deriving from scratch on every run (rather than incrementally patching
existing Actor rows) is a deliberate simplicity choice: a new submission can
legitimately change an old conclusion (two previously-separate actors turning
out to share a wallet), and recomputing the whole clustering is the only way
to get that right without hand-rolling incremental-clustering logic that a
7-day hackathon build has no business attempting.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.actor import Actor, Identifier, InfraFinding, RawPersona, StyleProfile
from app.services.attribution import build_clusters
from app.services.graph.neo4j_client import get_neo4j_client
from app.services.graph.relationship_mapper import ingest_marketplace_record
from app.services.stylometry.features import extract_features

# Arbitrary fixed key for pg_advisory_xact_lock — see run_full_analysis.
_ANALYSIS_LOCK_KEY = 727181


def _persona_dict(raw: RawPersona) -> dict:
    return {
        "username": raw.username,
        "platform": raw.platform,
        "sample_text": raw.sample_text,
        "wallet": raw.wallet,
        "pgp_key": raw.pgp_key,
        "onion_address": raw.onion_address,
        "vouched_by": raw.vouched_by or [],
    }


def run_full_analysis(
    db: Session, wallet_transactions: list[dict] | None = None
) -> list[Actor]:
    """wallet_transactions: optional co-spending data (see
    app.services.wallet_cluster) feeding the wallet-clustering pillar into
    attribution. Omitted by the live POST /api/leads path — RawPersona has no
    transaction-level wallet data source yet, only a single address string
    per persona — but scripts/ingest_and_attribute.py passes
    data/wallet_transactions.json through so the demo dataset actually
    exercises this pillar rather than just falling back to exact-string
    wallet matching.
    """
    if db.bind.dialect.name == "postgresql":
        # Two POST /api/leads calls submitted close together each enqueue a
        # reanalyze_all Celery task, and Celery's default worker concurrency
        # runs multiple tasks in parallel processes — without this lock, one
        # task's "DELETE FROM identifiers" can hit a live ForeignKeyViolation
        # against rows another concurrently-running task just committed,
        # crashing and silently discarding that submission's contribution to
        # the analysis (reproduced live: two leads submitted back to back,
        # one task crashed, the other "succeeded" using a stale pre-second-lead
        # snapshot). pg_advisory_xact_lock serializes the whole read-rebuild-
        # write cycle across concurrent transactions and auto-releases at
        # commit/rollback, so no manual unlock is needed even on an exception.
        # Guarded to Postgres only — SQLite (used in tests) has no such
        # function and doesn't need it (no real concurrent-connection risk
        # in a single-file test DB).
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ANALYSIS_LOCK_KEY})

    raw_personas = db.query(RawPersona).all()
    personas = [_persona_dict(p) for p in raw_personas]

    # Cleared first, then fully re-pushed below — Neo4j MERGE only ever
    # adds/updates, so without this a persona removed from RawPersona would
    # keep showing up in relationship graphs indefinitely.
    get_neo4j_client().clear_all()
    for persona in personas:
        ingest_marketplace_record(
            {
                "username": persona["username"],
                "platform": persona["platform"],
                "pgp_key": persona.get("pgp_key"),
                "wallet": persona.get("wallet"),
                "vouched_by": persona.get("vouched_by", []),
            }
        )

    # Infra-scan results aren't re-run live here (see app/services/infra_scan —
    # it targets a controlled mock host, not arbitrary onion addresses); a
    # persona flagged with onion_address is treated as already-confirmed-leaked,
    # consistent with how scripts/ingest_and_attribute.py has always modeled it.
    infra_leaked_persona_keys = {
        (p["username"], p["platform"]) for p in personas if p.get("onion_address")
    }
    clusters = build_clusters(
        personas,
        infra_leaked_persona_keys=infra_leaked_persona_keys,
        wallet_transactions=wallet_transactions,
    )
    # Keyed by (username, platform), not bare username — RawPersona allows
    # the same username on two different platforms as two different real
    # personas, and a bare-username dict here would silently drop one of
    # them (whichever lost the key collision) instead of persisting both.
    personas_by_key = {(p["username"], p["platform"]): p for p in personas}

    # Derived tables are rebuilt from scratch each run — see module docstring.
    db.query(StyleProfile).delete()
    db.query(InfraFinding).delete()
    db.query(Identifier).delete()
    db.query(Actor).delete()
    db.flush()

    persisted_actors: list[Actor] = []
    for cluster in clusters:
        label = " / ".join(sorted(cluster.usernames))
        actor = Actor(label=f"Actor: {label}", confidence_score=cluster.confidence)
        db.add(actor)
        db.flush()

        for persona_key in cluster.persona_keys:
            username, _platform = persona_key
            persona = personas_by_key[persona_key]

            identifier = Identifier(
                actor_id=actor.id,
                identifier_type="username",
                value=username,
                source_platform=persona["platform"],
            )
            db.add(identifier)
            db.flush()

            if persona.get("wallet"):
                db.add(
                    Identifier(
                        actor_id=actor.id,
                        identifier_type="wallet",
                        value=persona["wallet"],
                        source_platform=persona["platform"],
                    )
                )
            if persona.get("pgp_key"):
                db.add(
                    Identifier(
                        actor_id=actor.id,
                        identifier_type="pgp_key",
                        value=persona["pgp_key"],
                        source_platform=persona["platform"],
                    )
                )
            if persona.get("sample_text"):
                db.add(
                    StyleProfile(
                        actor_id=actor.id,
                        identifier_id=identifier.id,
                        feature_vector=extract_features(persona["sample_text"]),
                        sample_count=1,
                    )
                )
            if persona.get("onion_address"):
                db.add(
                    InfraFinding(
                        actor_id=actor.id,
                        onion_address=persona["onion_address"],
                        finding_type="ssl_leak",
                        detail={"note": "matched via mock_leaky_service scan"},
                    )
                )

        persisted_actors.append(actor)

    db.commit()
    return persisted_actors
