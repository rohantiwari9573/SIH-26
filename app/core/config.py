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

    # Number of most-recent MISP events per feed to expand into full-detail
    # real indicators (see scripts/ingest_misp_osint.py) — configurable
    # rather than hardcoded so a deeper backfill doesn't require a code
    # change. The CLI --indicator-limit flag still overrides this per-run.
    misp_max_events: int = 10

    # Hours between autonomous collection runs (celery beat, see
    # app.workers.celery_app / app.workers.tasks.run_scheduled_collection).
    # These are all low-churn public feeds (Tor relay list, MISP OSINT event
    # manifests, HIBP breach directory) — every few hours is real freshness
    # without hammering someone else's free public endpoint. A config value
    # rather than a hardcoded constant so a demo/panel run can shorten it
    # without a code change.
    scheduled_collection_interval_hours: int = 6


settings = Settings()
