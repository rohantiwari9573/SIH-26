import os

# Settings are required fields with no defaults (by design — production must set
# them explicitly). Tests don't hit a real DB/Neo4j/Redis, so provide harmless
# placeholders before anything imports app.core.config.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret")
