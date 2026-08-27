from neo4j import GraphDatabase

from app.core.config import settings


class Neo4jClient:
    def __init__(self):
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )

    def close(self):
        self._driver.close()

    def upsert_identifier(self, identifier_type: str, value: str, source_platform: str):
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
        self, value_a: str, value_b: str, relationship: str = "LINKED_TO", weight: float = 1.0
    ):
        query = """
        MATCH (a:Identifier {value: $value_a})
        MATCH (b:Identifier {value: $value_b})
        MERGE (a)-[r:LINKED_TO {relationship: $relationship}]->(b)
        SET r.weight = $weight
        """
        with self._driver.session() as session:
            session.run(
                query,
                value_a=value_a,
                value_b=value_b,
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

    def get_subgraph(self, values: list[str], depth: int = 1) -> dict:
        """Nodes + edges reachable within `depth` hops of any of `values` — the
        shape a UI needs to actually draw the relationship graph, not just list
        connected identifiers."""
        node_query = f"""
        UNWIND $values AS v
        MATCH (start:Identifier {{value: v}})
        OPTIONAL MATCH (start)-[*1..{depth}]-(connected)
        WITH collect(DISTINCT start) AS starts, collect(DISTINCT connected) AS others
        UNWIND starts + others AS n
        WITH DISTINCT n
        WHERE n IS NOT NULL
        RETURN n.type AS type, n.value AS value
        """
        edge_query = """
        UNWIND $values AS v
        MATCH (a:Identifier {value: v})-[r:LINKED_TO]->(b:Identifier)
        WHERE b.value IN $node_values
        RETURN DISTINCT a.value AS source, b.value AS target,
               r.relationship AS relationship, r.weight AS weight
        """
        with self._driver.session() as session:
            nodes = [dict(record) for record in session.run(node_query, values=values)]
            node_values = [n["value"] for n in nodes]
            edges = [
                dict(record)
                for record in session.run(edge_query, values=node_values, node_values=node_values)
            ]
        return {"nodes": nodes, "edges": edges}


_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
