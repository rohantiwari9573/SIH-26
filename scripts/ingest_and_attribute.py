"""Loads data/personas.json as RawPersona rows (simulating raw collected leads
with no known attribution yet) and runs the full analysis pipeline
(app.services.pipeline.run_full_analysis) to derive actor clusters from them.

This is the CLI equivalent of what happens automatically when someone submits
a new lead through POST /api/leads — same pipeline function, so the two paths
can't drift apart.

Requires Postgres + Neo4j running (docker compose up).
Run: docker compose exec api python scripts/ingest_and_attribute.py
"""
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.models.actor import RawPersona
from app.services.pipeline import run_full_analysis

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    personas = json.loads((DATA_DIR / "personas.json").read_text())
    wallet_transactions = json.loads((DATA_DIR / "wallet_transactions.json").read_text())

    db = SessionLocal()
    try:
        db.query(RawPersona).delete()
        for persona in personas:
            db.add(
                RawPersona(
                    username=persona["username"],
                    platform=persona["platform"],
                    sample_text=persona.get("sample_text"),
                    wallet=persona.get("wallet"),
                    pgp_key=persona.get("pgp_key"),
                    onion_address=persona.get("onion_address"),
                    vouched_by=persona.get("vouched_by", []),
                )
            )
        db.commit()

        actors = run_full_analysis(db, wallet_transactions=wallet_transactions)
        for actor in actors:
            print(f"Persisted actor {actor.id} ({actor.label}) confidence={actor.confidence_score}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
