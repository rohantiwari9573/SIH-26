from neo4j import GraphDatabase

from app.core.config import settings


class Neo4jClient:
    def __init__(self):
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )

    def close(self):
        self._driver.close()

    def clear_all(self) -> None:
        """Wipes every Identifier node and relationship. Used by
        run_full_analysis before re-pushing the current RawPersona set, so
        Neo4j stays in sync with the "derive Postgres tables from scratch on
        every run" model the rest of the pipeline uses — without this, a
        persona removed from RawPersona would keep showing up in relationship
        graphs indefinitely, since MERGE only ever adds/updates, never removes."""
        with self._driver.session() as session:
            session.run("MATCH (n:Identifier) DETACH DELETE n")

    def upsert_identifier(self, identifier_type: str, value: str, source_platform: str):
        """Usernames are platform-scoped handles that can coincidentally
        collide across different marketplaces for different real people, so
        a username node's MERGE key includes source_platform. Wallet/PGP-key
        values, by contrast, ARE the same real-world entity regardless of
        which platform observed them — merging those by value alone is
        correct and is exactly what makes the "shared wallet across
        platforms" linking mechanism work, so their key deliberately
        excludes platform."""
        if identifier_type == "username":
            query = """
            MERGE (n:Identifier {
                type: $identifier_type, value: $value, source_platform: $source_platform
            })
            RETURN n
            """
        else:
            query = """
            MERGE (n:Identifier {type: $identifier_type, value: $value})
            SET n.source_platform = $source_platform
            RETURN n
            """
        with self._driver.session() as session:
            session.run(
                query,
                identifier_type=identifier_type,
                value=value,
                source_platform=source_platform,
            )

    def link_identifiers(
        self,
        value_a: str,
        value_b: str,
        relationship: str = "LINKED_TO",
        weight: float = 1.0,
        platform_a: str | None = None,
        platform_b: str | None = None,
    ):
        """platform_a/platform_b disambiguate a username-type endpoint when
        the same username string could exist on multiple platforms as
        different people (see upsert_identifier) — pass the platform
        whenever that side's value is a username. Wallet/PGP-key values
        don't need it since those nodes merge by value alone regardless of
        platform. Without this, MATCH {value: $value_a} would match every
        node with that value across all platforms and link all of them."""
        match_a = (
            "{value: $value_a, source_platform: $platform_a}" if platform_a else "{value: $value_a}"
        )
        match_b = (
            "{value: $value_b, source_platform: $platform_b}" if platform_b else "{value: $value_b}"
        )
        query = f"""
        MATCH (a:Identifier {match_a})
        MATCH (b:Identifier {match_b})
        MERGE (a)-[r:LINKED_TO {{relationship: $relationship}}]->(b)
        SET r.weight = $weight
        """
        with self._driver.session() as session:
            session.run(
                query,
                value_a=value_a,
                value_b=value_b,
                platform_a=platform_a,
                platform_b=platform_b,
                relationship=relationship,
                weight=weight,
            )

    def get_connected_component(self, value: str, depth: int = 2) -> list[dict]:
        query = f"""
        MATCH (start:Identifier {{value: $value}})
        MATCH path = (start)-[*1..{depth}]-(connected)
        RETURN DISTINCT connected.type AS type, connected.value AS value
        """
        with self._driver.session() as session:
            result = session.run(query, value=value)
            return [dict(record) for record in result]

    def get_subgraph(
        self,
        values: list[str],
        depth: int = 1,
        entity_types: list[str] | None = None,
        relationship_types: list[str] | None = None,
        source: str | None = None,
    ) -> dict:
        """Nodes + edges reachable within `depth` hops of any of `values` — the
        shape a UI needs to actually draw the relationship graph, not just list
        connected identifiers.

        entity_types/relationship_types/source are applied as real Cypher WHERE
        clauses (not post-hoc filtering of an already-fetched result, and
        definitely not CSS-hiding in the frontend) — see
        app/api/routes/actors.py's ENTITY_TYPE_GROUPS/RELATIONSHIP_TYPE_GROUPS
        for how UI category checkboxes map to these real node `type` /
        relationship `relationship` values. None means "no filter" for that
        dimension. Filtering by entity_types can legitimately remove a root
        identifier node too (e.g. filtering to just "Indicators" on an actor
        with no correlation evidence returns an empty graph) — that's honest
        investigator behavior, not a bug."""
        # elementId(n) identifies the EXACT node instances node_query already
        # selected, not just their value string — edge_query below matches
        # edges between those specific nodes by id, not by re-matching on
        # value alone. This matters because a username node's real identity
        # includes its source_platform (see upsert_identifier/
        # link_identifiers's own comments): two different platforms can
        # coincidentally share the same literal username string as two
        # different real people, and a value-only edge match would wrongly
        # attribute an edge between those two unrelated nodes.
        node_query = f"""
        UNWIND $values AS v
        MATCH (start:Identifier {{value: v}})
        OPTIONAL MATCH (start)-[*1..{depth}]-(connected)
        WITH collect(DISTINCT start) AS starts, collect(DISTINCT connected) AS others
        UNWIND starts + others AS n
        WITH DISTINCT n
        WHERE n IS NOT NULL
          AND ($entity_types IS NULL OR n.type IN $entity_types)
          AND ($source IS NULL OR n.source_platform = $source)
        RETURN n.type AS type, n.value AS value, n.source_platform AS source_platform,
               elementId(n) AS node_id
        """
        edge_query = """
        MATCH (a:Identifier)-[r:LINKED_TO]->(b:Identifier)
        WHERE elementId(a) IN $node_ids AND elementId(b) IN $node_ids
          AND ($relationship_types IS NULL OR r.relationship IN $relationship_types)
        RETURN DISTINCT a.value AS source, b.value AS target,
               r.relationship AS relationship, r.weight AS weight
        """
        with self._driver.session() as session:
            raw_nodes = [
                dict(record)
                for record in session.run(
                    node_query, values=values, entity_types=entity_types, source=source
                )
            ]
            node_ids = [n["node_id"] for n in raw_nodes]
            nodes = [{k: v for k, v in n.items() if k != "node_id"} for n in raw_nodes]
            edges = [
                dict(record)
                for record in session.run(
                    edge_query,
                    node_ids=node_ids,
                    relationship_types=relationship_types,
                )
            ]
        return {"nodes": nodes, "edges": edges}


_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
