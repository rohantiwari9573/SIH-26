from app.services.attribution import build_clusters

REBRAND_TEXT_A = (
    "I think, honestly, that this batch is better than the last one. "
    "You should really trust the process, and I mean really trust it."
)
REBRAND_TEXT_B = (
    "Honestly, I think this batch is better than before. "
    "You should really trust the process here, I really mean that."
)
UNRELATED_TEXT = (
    "Transaction completed. Shipment will arrive within 3-5 business days. "
    "Thank you for your purchase, please leave feedback."
)

PERSONAS = [
    {
        "username": "shadow_vendor",
        "platform": "mock_marketplace_1",
        "sample_text": REBRAND_TEXT_A,
        "wallet": "1SharedWalletDemo",
        "pgp_key": "PGP-DEMO-1",
    },
    {
        "username": "nightowl_88",
        "platform": "mock_marketplace_2",
        "sample_text": REBRAND_TEXT_B,
        "wallet": "1SharedWalletDemo",
        "pgp_key": "PGP-DEMO-1",
    },
    {
        "username": "unrelated_vendor",
        "platform": "mock_marketplace_2",
        "sample_text": UNRELATED_TEXT,
        "wallet": "1DifferentWallet",
        "pgp_key": "PGP-OTHER",
    },
]


def test_linked_personas_merge_into_one_high_confidence_cluster():
    clusters = build_clusters(PERSONAS)
    top = clusters[0]
    assert top.usernames == {"shadow_vendor", "nightowl_88"}
    assert top.confidence > 0.6


def test_unrelated_persona_stays_in_its_own_cluster():
    clusters = build_clusters(PERSONAS)
    unrelated_cluster = next(c for c in clusters if "unrelated_vendor" in c.usernames)
    assert unrelated_cluster.usernames == {"unrelated_vendor"}
    assert unrelated_cluster.confidence == 0.0


def test_infra_leak_boosts_confidence_for_its_cluster():
    without_infra = build_clusters(PERSONAS)
    with_infra = build_clusters(PERSONAS, infra_leaked_usernames={"shadow_vendor"})

    top_without = next(c for c in without_infra if "shadow_vendor" in c.usernames)
    top_with = next(c for c in with_infra if "shadow_vendor" in c.usernames)

    assert top_with.confidence > top_without.confidence
    assert top_with.infra_match is True


def test_no_shared_identifiers_or_style_yields_singleton_clusters():
    isolated = [
        {"username": "solo_a", "platform": "p1", "sample_text": REBRAND_TEXT_A},
        {"username": "solo_b", "platform": "p2", "sample_text": UNRELATED_TEXT},
    ]
    clusters = build_clusters(isolated)
    assert len(clusters) == 2
    assert all(len(c.usernames) == 1 for c in clusters)
