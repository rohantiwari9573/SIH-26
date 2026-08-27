"""Runs the full attribution pipeline against data/personas.json and prints the
resulting clusters — this is the "does it actually work" sanity check to run
before wiring persistence, and a good live demo fallback if Docker isn't handy.

Run: python scripts/run_attribution_demo.py
"""
import json
from pathlib import Path

from app.services.attribution import build_clusters
from app.services.wallet_cluster.clustering import cluster_wallets

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    personas = json.loads((DATA_DIR / "personas.json").read_text())
    transactions = json.loads((DATA_DIR / "wallet_transactions.json").read_text())

    wallet_clusters = cluster_wallets(transactions)
    print("=== Wallet clusters (common-input-ownership) ===")
    for cluster in wallet_clusters:
        print(f"  {cluster}")

    # Simulate: infra_scan already flagged careless_admin's mirror as leaked.
    infra_leaked = {"careless_admin"}

    clusters = build_clusters(
        personas, infra_leaked_usernames=infra_leaked, wallet_transactions=transactions
    )

    print("\n=== Attribution clusters ===")
    for cluster in clusters:
        print(f"\nActor cluster: {cluster.usernames}")
        print(f"  confidence:              {cluster.confidence}")
        print(f"  stylometry_similarity:   {cluster.stylometry_similarity:.4f}")
        print(f"  relationship_strength:   {cluster.relationship_strength}")
        print(f"  infra_match:             {cluster.infra_match}")
        for edge in cluster.edges:
            print(f"  edge: {edge}")


if __name__ == "__main__":
    main()
