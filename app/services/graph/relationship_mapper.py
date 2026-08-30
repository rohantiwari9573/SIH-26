"""Builds the entity graph across marketplaces: usernames, PGP keys, wallets,
and trust relationships (vouches, repeated co-occurrence in listings/reviews).
"""
from app.services.graph.neo4j_client import get_neo4j_client


def ingest_marketplace_record(record: dict) -> None:
    """record shape (from scraper/dataset):
    {
        "username": "shadow_vendor",
        "platform": "mock_marketplace_1",
        "pgp_key": "ABCD1234...",
        "wallet": "1A2b3C...",
        "vouched_by": ["other_username"],
        "onion_address": "abcd1234....onion",  # optional — confirmed infra leak
    }
    """
    client = get_neo4j_client()

    client.upsert_identifier("username", record["username"], record["platform"])

    # platform_a scopes the username-side match — see Neo4jClient.link_identifiers.
    # Wallet/PGP-key sides don't need it: those nodes merge by value alone.
    if record.get("pgp_key"):
        client.upsert_identifier("pgp_key", record["pgp_key"], record["platform"])
        client.link_identifiers(
            record["username"], record["pgp_key"], "USES_KEY", platform_a=record["platform"]
        )

    if record.get("wallet"):
        client.upsert_identifier("wallet", record["wallet"], record["platform"])
        client.link_identifiers(
            record["username"], record["wallet"], "USES_WALLET", platform_a=record["platform"]
        )

    for voucher in record.get("vouched_by", []):
        client.upsert_identifier("username", voucher, record["platform"])
        client.link_identifiers(
            voucher,
            record["username"],
            "VOUCHES_FOR",
            platform_a=record["platform"],
            platform_b=record["platform"],
        )

    # Infra-fingerprinting pillar (app.services.infra_scan) previously only
    # ever reached Postgres (InfraFinding, actor_id FK) and a boolean flag in
    # scoring — it had no representation in the relationship graph at all, so
    # an actor tied to a confirmed leak looked identical in Neo4j to one with
    # no infra evidence. This is what wires it in as a real graph edge.
    if record.get("onion_address"):
        client.upsert_identifier("onion_address", record["onion_address"], record["platform"])
        client.link_identifiers(
            record["username"],
            record["onion_address"],
            "RELATED_TO",
            platform_a=record["platform"],
        )


def find_related_identifiers(value: str, depth: int = 2) -> list[dict]:
    client = get_neo4j_client()
    return client.get_connected_component(value, depth=depth)


def get_actor_graph(identifier_values: list[str], depth: int = 1) -> dict:
    """Nodes + edges for the dashboard's graph view, seeded from an actor's
    known identifiers (not just one) so the whole cluster's neighborhood shows
    up, not just whatever one node happens to be reachable from."""
    if not identifier_values:
        return {"nodes": [], "edges": []}
    client = get_neo4j_client()
    return client.get_subgraph(identifier_values, depth=depth)
