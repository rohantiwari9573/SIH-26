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


def test_wallet_clustering_links_personas_with_different_co_spent_addresses():
    """Two personas whose wallets are provably the same owner (co-spent in one
    transaction) but who never reuse the exact same address string were
    previously invisible to attribution — this is the wiring that fixes it."""
    personas = [
        {
            "username": "vendor_x",
            "platform": "p1",
            "wallet": "addrA",
        },
        {
            "username": "vendor_y",
            "platform": "p2",
            "wallet": "addrB",
        },
        {
            "username": "vendor_unrelated",
            "platform": "p1",
            "wallet": "addrC",
        },
    ]
    transactions = [
        {"tx_id": "tx1", "inputs": ["addrA", "addrB"]},
        {"tx_id": "tx2", "inputs": ["addrC"]},
    ]

    without_transactions = build_clusters(personas)
    linked = next(c for c in without_transactions if "vendor_x" in c.usernames)
    assert linked.usernames == {"vendor_x"}, "exact-string matching alone must not link addrA/addrB"

    with_transactions = build_clusters(personas, wallet_transactions=transactions)
    linked = next(c for c in with_transactions if "vendor_x" in c.usernames)
    assert linked.usernames == {"vendor_x", "vendor_y"}
    assert linked.relationship_strength == 1.0

    unrelated = next(c for c in with_transactions if "vendor_unrelated" in c.usernames)
    assert unrelated.usernames == {"vendor_unrelated"}


def test_same_username_different_platforms_stay_distinct_when_unlinked():
    """The same username string on two different platforms, with nothing
    tying them together (different wallets, no shared PGP key, no matching
    writing style) must be treated as two separate personas — not silently
    collapsed into one by a bare-username identity key."""
    personas = [
        {"username": "shadow_vendor", "platform": "platform_1", "wallet": "wallet_1"},
        {"username": "shadow_vendor", "platform": "platform_2", "wallet": "wallet_2"},
    ]

    clusters = build_clusters(personas)

    assert len(clusters) == 2
    assert all(c.usernames == {"shadow_vendor"} for c in clusters)
    persona_keys = {key for c in clusters for key in c.persona_keys}
    assert persona_keys == {("shadow_vendor", "platform_1"), ("shadow_vendor", "platform_2")}


def test_same_username_different_platforms_merge_when_actually_linked():
    """The flip side: if the same-named personas on different platforms DO
    share a wallet, they should still merge — the fix must not accidentally
    prevent legitimate same-username linking, only the silent bare-username
    collision when they're actually unrelated."""
    personas = [
        {"username": "shadow_vendor", "platform": "platform_1", "wallet": "same_wallet"},
        {"username": "shadow_vendor", "platform": "platform_2", "wallet": "same_wallet"},
    ]

    clusters = build_clusters(personas)

    assert len(clusters) == 1
    assert clusters[0].persona_keys == {
        ("shadow_vendor", "platform_1"),
        ("shadow_vendor", "platform_2"),
    }
