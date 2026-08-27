from app.services.wallet_cluster.clustering import cluster_wallets, wallets_linked

TRANSACTIONS = [
    {"tx_id": "tx1", "inputs": ["addrA", "addrB"]},
    {"tx_id": "tx2", "inputs": ["addrB", "addrC"]},
    {"tx_id": "tx3", "inputs": ["addrD"]},
]


def test_cluster_wallets_groups_common_inputs():
    clusters = cluster_wallets(TRANSACTIONS)
    cluster_containing_a = next(c for c in clusters if "addrA" in c)
    assert cluster_containing_a == {"addrA", "addrB", "addrC"}


def test_unrelated_wallet_is_its_own_cluster():
    clusters = cluster_wallets(TRANSACTIONS)
    cluster_containing_d = next(c for c in clusters if "addrD" in c)
    assert cluster_containing_d == {"addrD"}


def test_wallets_linked_true_for_common_cluster():
    assert wallets_linked("addrA", "addrC", TRANSACTIONS) is True


def test_wallets_linked_false_across_clusters():
    assert wallets_linked("addrA", "addrD", TRANSACTIONS) is False
