"""Generates a synthetic marketplace dataset for the pillar-owner teams to build
against. Entirely fabricated — no real scraped or leaked data, per docs/ETHICS.md.

Contains four storylines on purpose, so the demo can show a true positive, a
true negative, and the graded case in between — not just a binary yes/no:

1. `shadow_vendor` / `nightowl_88` — the flagship rebrand story: same wallet,
   same PGP key, and matching writing style across two marketplaces.
   High confidence (~0.84), all three signal types agree.
2. `quiet_trader` / `midnight_courier` — a negative control: different wallets,
   different PGP keys, distinct writing style. The system must NOT merge these,
   or a judge asking "what stops false positives" has an easy hit.
3. `careless_admin` — tied to a mock onion address with a deliberately leaky
   mirror target (see mock_leaky_service/), feeding the infra-scan pillar.
4. `frostbyte_dealer` / `javabean_vendor` — partial evidence: matching writing
   style (same distinctive phrasing tics) but no shared wallet or PGP key yet.
   Lower confidence than the flagship pair, and correctly so — this is the
   talking point for "the system doesn't just say yes/no, it grades how sure
   it is," and for demonstrating the live lead-submission flow (submitting a
   shared wallet for one of these later should raise its confidence live).

Run: python scripts/generate_synthetic_dataset.py
Writes: data/personas.json, data/wallet_transactions.json
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Sample texts are longer than a single post on purpose: real stylometry needs
# a persona's aggregated post history (dozens to hundreds of words), not one
# sentence — a single short post is documented in the literature as too noisy
# to attribute reliably, and testing this dataset with 1-2 sentence samples
# confirmed it (false-positive pairs scored nearly as high as the true match).
PERSONAS = [
    # Storyline 1: rebrand pair — should attribute to the same actor
    {
        "username": "shadow_vendor",
        "platform": "mock_marketplace_1",
        "sample_text": (
            "I think, honestly, that this batch is better than the last one. "
            "You should really trust the process, and I mean really trust it. "
            "Escrow is fine for new buyers, I have done this a long time and "
            "nobody has ever had a real problem with me, not once. Honestly "
            "I don't rush anything, I check everything twice before it goes "
            "out, because I think that is just how it should be done, really. "
            "If you message me and I don't reply right away it is because I "
            "am, honestly, dealing with ten other people at the same time, "
            "so please just trust the process and give it a day or two."
        ),
        "wallet": "1DemoWalletSharedBetweenBothPersonas0000",
        "pgp_key": "DEMO-PGP-KEY-FINGERPRINT-ABC123",
        "vouched_by": ["longtime_customer_1"],
    },
    {
        "username": "nightowl_88",
        "platform": "mock_marketplace_2",
        "sample_text": (
            "Honestly, I think this batch is better than before. You should "
            "really trust the process here, I really mean that. Escrow is "
            "fine, I have been doing this a long time now and honestly nobody "
            "has ever had a real problem with me here either, not once. I "
            "don't rush anything, I really do check everything twice before "
            "it goes out, because honestly I think that is just how it should "
            "be done. If I don't reply right away it is, honestly, because I "
            "am dealing with several other people at once, so please really "
            "just trust the process and give it a day or two, I mean it."
        ),
        "wallet": "1DemoWalletSharedBetweenBothPersonas0000",
        "pgp_key": "DEMO-PGP-KEY-FINGERPRINT-ABC123",
        "vouched_by": [],
    },
    # Storyline 2: negative control — must stay unmerged
    {
        "username": "quiet_trader",
        "platform": "mock_marketplace_1",
        "sample_text": (
            "Transaction completed. Shipment will arrive within 3-5 business "
            "days. Thank you for your purchase, please leave feedback when it "
            "arrives. All orders are packed according to standard procedure "
            "and dispatched the same day where possible. If there is a delay "
            "it will usually be posted in the announcements section, so check "
            "there first before sending a message. Refund requests are "
            "processed within 48 hours of the reported issue being confirmed. "
            "Bulk orders receive a discount automatically at checkout, no "
            "coupon code is required for that to apply."
        ),
        "wallet": "1UnrelatedWalletForQuietTrader1111",
        "pgp_key": "DEMO-PGP-KEY-UNRELATED-XYZ789",
        "vouched_by": [],
    },
    {
        "username": "midnight_courier",
        "platform": "mock_marketplace_2",
        "sample_text": (
            "Order shipped today, tracking not provided for privacy reasons. "
            "Message me only through the marketplace, not by email, since "
            "email is not checked regularly and will not get a response. "
            "Packaging is vacuum sealed and odor proof as standard practice "
            "for every single order regardless of size. New customers must "
            "complete one small order first before larger quantities will be "
            "considered for their account. Weekends usually see slower "
            "response times because of shipping schedules in this region."
        ),
        "wallet": "1AnotherUnrelatedWalletForCourier2222",
        "pgp_key": "DEMO-PGP-KEY-UNRELATED-DEF456",
        "vouched_by": [],
    },
    # Storyline 3: infra leak target
    {
        "username": "careless_admin",
        "platform": "mock_marketplace_1",
        "sample_text": (
            "New stock posted, contact for pricing on bulk orders. Site may "
            "be slow today, working on the server, apologies for any "
            "inconvenience this causes to regular buyers this week. Pricing "
            "is negotiable only for repeat customers who have ordered at "
            "least three times previously through this account. Server "
            "maintenance is usually done overnight to minimize downtime "
            "during normal business hours for everyone involved. Please be "
            "patient if pages load slowly, this will be resolved shortly."
        ),
        "wallet": "1CarelessAdminWallet3333",
        "pgp_key": "DEMO-PGP-KEY-CARELESS-GHI012",
        "onion_address": "demo3xample7onion0000.onion",
        "vouched_by": [],
    },
    # Storyline 4: partial evidence — stylometry agrees, no shared identifiers
    # yet. Deliberately a different voice/phrasing pattern from storyline 1
    # (clipped, informal, "look... real talk" tics instead of "honestly... I
    # mean... really") — reusing the same template with word-swaps was tried
    # first and it accidentally stylometrically merged with storyline 1's
    # pair, which defeated the point of having a separate partial-evidence
    # cluster. Verified via scripts/run_attribution_demo.py that this pair
    # clusters with each other but not with storyline 1, 2, or 3.
    {
        "username": "frostbyte_dealer",
        "platform": "mock_marketplace_1",
        "sample_text": (
            "look, not gonna lie, this batch is solid, real solid, better "
            "than what i had before honestly. been doing this a minute now "
            "and never burned nobody, not once, straight up, ask around if "
            "you want. i don't play games with quality, i check stuff twice "
            "before it ships, always, cause that's just how i move, no "
            "shortcuts here ever. if i'm slow to hit back it's cause i got "
            "a bunch of people messaging at once, so just chill and give it "
            "a minute, real talk, it'll get sorted."
        ),
        "wallet": "1FrostbyteWalletUnlinked4444",
        "pgp_key": "DEMO-PGP-KEY-FROSTBYTE-JKL345",
        "vouched_by": [],
    },
    {
        "username": "javabean_vendor",
        "platform": "mock_marketplace_3",
        "sample_text": (
            "not gonna lie, look, this batch is real solid, better than "
            "before honestly, for real. been doing this a minute and never "
            "burned nobody here either, not once, straight up, you can ask "
            "around. i don't play games with quality, i check stuff twice "
            "before it ships, always, that's just how i move, no shortcuts, "
            "ever. if i'm slow to hit back it's cause i got a bunch of "
            "people messaging me at once, so just chill, give it a minute, "
            "real talk."
        ),
        "wallet": "1JavabeanWalletUnlinked5555",
        "pgp_key": "DEMO-PGP-KEY-JAVABEAN-MNO678",
        "vouched_by": [],
    },
]

WALLET_TRANSACTIONS = [
    # Common-input-ownership: shadow_vendor's wallet co-spent with a second
    # address in the same transaction -> clusters together under wallet_cluster.
    {
        "tx_id": "tx_demo_1",
        "inputs": [
            "1DemoWalletSharedBetweenBothPersonas0000",
            "1DemoWalletSharedBetweenBothPersonas0000_change",
        ],
    },
    {
        "tx_id": "tx_demo_2",
        "inputs": ["1UnrelatedWalletForQuietTrader1111"],
    },
    {
        "tx_id": "tx_demo_3",
        "inputs": ["1AnotherUnrelatedWalletForCourier2222"],
    },
    {
        "tx_id": "tx_demo_4",
        "inputs": ["1FrostbyteWalletUnlinked4444"],
    },
    {
        "tx_id": "tx_demo_5",
        "inputs": ["1JavabeanWalletUnlinked5555"],
    },
]


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    personas_path = DATA_DIR / "personas.json"
    personas_path.write_text(json.dumps(PERSONAS, indent=2))
    print(f"Wrote {len(PERSONAS)} personas to {personas_path}")

    tx_path = DATA_DIR / "wallet_transactions.json"
    tx_path.write_text(json.dumps(WALLET_TRANSACTIONS, indent=2))
    print(f"Wrote {len(WALLET_TRANSACTIONS)} transactions to {tx_path}")


if __name__ == "__main__":
    main()
