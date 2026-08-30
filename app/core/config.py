from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    redis_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Optional third-party threat-intel credentials. All default to None (not
    # fabricated, not required to run Argus) — each gated integration checks
    # for its own key at ingestion time and reports NOT_CONFIGURED rather
    # than silently skipping or showing fake data when unset. See
    # scripts/ingest_urlhaus.py, ingest_malwarebazaar.py, ingest_chainabuse.py,
    # and app/services/hibp_lookup.py.
    urlhaus_api_key: str | None = None
    malwarebazaar_api_key: str | None = None
    chainabuse_api_key: str | None = None
    hibp_api_key: str | None = None


settings = Settings()
