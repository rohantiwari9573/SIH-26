"""Adds one fully-populated "showcase" actor to the dataset for panel demos —
three real (synthetic/controlled, labeled as such in the UI) personas across
mock_marketplace_1/2/3 sharing a wallet and PGP key, one onion-address infra
flag, and a real spread of RawActivity rows (some genuinely classifiable via
the existing threat_categorization keyword rules, most ordinary vendor
chatter — matching the honest real-world ratio, not a wall of crime).

Every number this actor ends up showing (activity counts, dates, threat
categories, attribution confidence) is computed by the real, unmodified
pipeline (app.services.pipeline.run_full_analysis / app.services.scoring) —
this script writes nothing but RawPersona/RawActivity input rows, exactly
like a real lead submission would. It does NOT touch scoring.py's weights,
does NOT set confidence_score directly, and does NOT fabricate a correlation
against a live external feed (Tor Onionoo/MISP/HIBP) just to fill a section
— see the "Threat & Infrastructure Intelligence" note in the README/PITCH
docs on why that section is expected to stay empty here, same as it is for
every other actor with no genuine external-feed match.

Purely additive: does not touch any existing RawPersona/RawActivity row.
Safe to re-run (deletes only this showcase actor's own prior rows by
username first, matching the project's existing idempotent-reingest
pattern — see scripts/ingest_evolution.py).

Run: docker compose exec api python scripts/seed_showcase_actor.py
"""
from datetime import datetime, timedelta, timezone

from app.db.session import SessionLocal
from app.models.actor import RawActivity, RawPersona, ThreatActivity
from app.services.pipeline import run_full_analysis

USERNAMES = ["obsidian_broker99", "phantomtrade_88", "cipherline_vendor"]

PERSONAS = [
    {
        "username": "obsidian_broker99",
        "platform": "mock_marketplace_1",
        "sample_text": (
            "Stock updated. Ships same day, no exceptions, no delays unless "
            "stated otherwise in the announcement thread. PGP only for "
            "sensitive messages, plaintext gets ignored, no exceptions to "
            "that either. Quantities above the listed max need a direct "
            "message first, don't just order it, I'll cancel it. Returns "
            "aren't accepted past 48 hours, check the listing photos "
            "closely before you buy, they're accurate. Vouches available on "
            "request, I've been around, ask the regulars if you're unsure."
        ),
        "wallet": "1PerfectShowcaseWalletDemo000009999",
        "pgp_key": "DEMO-PGP-KEY-SHOWCASE-PERFECT999",
        "onion_address": "demoshowcase9perfectactor0000.onion",
        "vouched_by": [],
    },
    {
        "username": "phantomtrade_88",
        "platform": "mock_marketplace_2",
        "sample_text": (
            "Stock updated again. Ships same day, no exceptions, no delays "
            "unless the announcement thread says otherwise. PGP only for "
            "anything sensitive, plaintext messages get ignored here too, "
            "no exceptions. Quantities above the listed max need a direct "
            "message first, don't just place the order, it'll get "
            "cancelled. Returns aren't accepted past 48 hours, check the "
            "listing photos closely, they're accurate every time."
        ),
        "wallet": "1PerfectShowcaseWalletDemo000009999",
        "pgp_key": "DEMO-PGP-KEY-SHOWCASE-PERFECT999",
        "vouched_by": ["verified_reseller_2024"],
    },
    {
        "username": "cipherline_vendor",
        "platform": "mock_marketplace_3",
        "sample_text": (
            "Stock updated once more. Ships same day, no exceptions, no "
            "delays unless the thread says otherwise. PGP only for "
            "sensitive messages, plaintext gets ignored, no exceptions "
            "here either. Quantities above the listed max need a direct "
            "message first, don't just order it, it will be cancelled. "
            "Returns aren't accepted past 48 hours, check the listing "
            "photos closely before buying, they are always accurate."
        ),
        "wallet": "1PerfectShowcaseWalletDemo000009999",
        "pgp_key": "DEMO-PGP-KEY-SHOWCASE-PERFECT999",
        "vouched_by": [],
    },
]

# (platform, days_ago, title, text) — real activity content. Some rows
# contain exact phrases app.services.threat_categorization's keyword rules
# recognize (classification is genuinely computed from this text, never
# assigned by this script); most rows are ordinary vendor chatter, matching
# that module's documented real-world ratio.
ACTIVITIES = [
    ("mock_marketplace_1", 88, "New batch restocked",
     "New batch restocked today, quality checked as always, escrow recommended for new buyers."),
    ("mock_marketplace_1", 81, "Selling stolen credentials",
     "Selling stolen credentials in bulk, fresh checked accounts, message for pricing on volume."),
    ("mock_marketplace_1", 74, "Credit card dump available",
     "Credit card dump available now, cvv fullz included, discount on bulk orders this week."),
    ("mock_marketplace_1", 60, "Shipping update",
     "Shipping is running a little slow this week, please be patient, all orders will go out."),
    ("mock_marketplace_1", 45, "Feedback appreciated",
     "Feedback is appreciated once your package arrives, message me directly with any issues."),
    ("mock_marketplace_1", 30, "Restock announcement",
     "Restock announcement, same quality as before, orders processed same day where possible."),
    ("mock_marketplace_2", 70, "Leaked database for sale",
     "Leaked database for sale, verified records, sample available on request before purchase."),
    ("mock_marketplace_2", 63, "Account checker service",
     "Account checker service now available, fast turnaround, bulk pricing for resellers."),
    ("mock_marketplace_2", 50, "Order confirmation",
     "Order confirmation sent, tracking not provided, thank you for your continued business."),
    ("mock_marketplace_2", 35, "New stock posted",
     "New stock posted this morning, contact for pricing, repeat customers get priority."),
    ("mock_marketplace_2", 20, "Weekend hours notice",
     "Weekend hours are slower than usual, response times may be delayed until Monday."),
    ("mock_marketplace_3", 55, "Compromised account bundle",
     "Compromised account bundle for sale, mixed regions, discount for the full set."),
    ("mock_marketplace_3", 40, "Hacking service offered",
     "Hacking service offered for hire, website hacking service available, message with details."),
    ("mock_marketplace_3", 25, "Standard restock",
     "Standard restock posted, nothing new to report otherwise, business as usual this week."),
    ("mock_marketplace_3", 10, "Thanks for the order",
     "Thanks for the order, feedback appreciated, message me if anything is wrong on arrival."),
]


def main() -> None:
    db = SessionLocal()
    try:
        old_personas = db.query(RawPersona).filter(RawPersona.username.in_(USERNAMES)).all()
        old_persona_ids = [p.id for p in old_personas]
        if old_persona_ids:
            old_activity_ids = [
                r.id
                for r in db.query(RawActivity.id).filter(
                    RawActivity.raw_persona_id.in_(old_persona_ids)
                )
            ]
            if old_activity_ids:
                # A prior run's ThreatActivity rows still reference these
                # RawActivity ids (run_full_analysis only rebuilds
                # ThreatActivity when it runs, which hasn't happened yet in
                # THIS invocation) -- must go first or the FK blocks the
                # RawActivity delete below.
                db.query(ThreatActivity).filter(
                    ThreatActivity.raw_activity_id.in_(old_activity_ids)
                ).delete(synchronize_session=False)
            db.query(RawActivity).filter(
                RawActivity.raw_persona_id.in_(old_persona_ids)
            ).delete(synchronize_session=False)
            db.query(RawPersona).filter(RawPersona.id.in_(old_persona_ids)).delete(
                synchronize_session=False
            )
        db.flush()

        persona_rows: dict[str, RawPersona] = {}
        for p in PERSONAS:
            row = RawPersona(
                username=p["username"],
                platform=p["platform"],
                sample_text=p["sample_text"],
                wallet=p.get("wallet"),
                pgp_key=p.get("pgp_key"),
                onion_address=p.get("onion_address"),
                vouched_by=p.get("vouched_by", []),
            )
            db.add(row)
            persona_rows[p["username"]] = row
        db.flush()

        username_by_platform = {p["platform"]: p["username"] for p in PERSONAS}
        now = datetime.now(timezone.utc)
        for i, (platform, days_ago, title, text) in enumerate(ACTIVITIES):
            username = username_by_platform[platform]
            db.add(
                RawActivity(
                    raw_persona_id=persona_rows[username].id,
                    platform=platform,
                    source_record_id=f"showcase:{platform}:{i}",
                    title=title,
                    text=text,
                    source_category=None,
                    observed_at=now - timedelta(days=days_ago),
                )
            )
        db.commit()

        actors = run_full_analysis(db)
        showcase = next(
            (a for a in actors if any(u in a.label for u in USERNAMES)),
            None,
        )
        if showcase:
            print(
                f"Showcase actor: {showcase.id} ({showcase.label}) "
                f"confidence={showcase.confidence_score}"
            )
        else:
            print("WARNING: showcase actor not found among re-derived actors")
        print(f"Total actors after re-analysis: {len(actors)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
