"""Wallet clustering via the common-input-ownership heuristic: if multiple
addresses are used as inputs in the same transaction, they're very likely
controlled by the same entity (a standard, well-documented blockchain
forensics technique — not novel research, but effective and easy to justify
to judges).

Operates on transaction records rather than live-querying a chain explorer,
so it works fully offline against a demo dataset.
"""


def cluster_wallets(transactions: list[dict]) -> list[set[str]]:
    """transactions: [{"inputs": ["addr1", "addr2", ...], "tx_id": "..."}]
    Returns disjoint clusters of addresses believed to share a common owner.
    """
    parent: dict[str, str] = {}

    def find(addr: str) -> str:
        parent.setdefault(addr, addr)
        while parent[addr] != addr:
            parent[addr] = parent[parent[addr]]
            addr = parent[addr]
        return addr

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_a] = root_b

    for tx in transactions:
        inputs = tx.get("inputs", [])
        for addr in inputs:
            find(addr)
        for i in range(1, len(inputs)):
            union(inputs[0], inputs[i])

    clusters: dict[str, set[str]] = {}
    for addr in parent:
        root = find(addr)
        clusters.setdefault(root, set()).add(addr)

    return list(clusters.values())


def wallets_linked(address_a: str, address_b: str, transactions: list[dict]) -> bool:
    clusters = cluster_wallets(transactions)
    return any(address_a in c and address_b in c for c in clusters)
