# Architecture

## Data flow

```
                        +--------------------------+
                        |   Demo / seed data        |
                        | (synthetic + mock target)  |
                        +------------+---------------+
                                     |
        +----------------------------+----------------------------+
        |                            |                             |
        v                            v                             v
+---------------+          +------------------+          +-------------------+
| infra_scan    |          | graph /           |          | stylometry        |
| (SSL/banner/  |          | relationship_mapper|          | (feature extract  |
| default page) |          | -> Neo4j graph     |          | + similarity)      |
+-------+-------+          +---------+----------+          +---------+---------+
        |                            |                                |
        v                            v                                v
+------------------------------------------------------------------------------+
|                    Celery async jobs (app/workers/tasks.py)                   |
+------------------------------------------------------------------------------+
        |
        v
+------------------------------------------------------------------------------+
| Unified store: Actor, Identifier, InfraFinding, StyleProfile (PostgreSQL)     |
| + confidence score (app/services/scoring.py, combines all 3 pillars)         |
+------------------------------------------------------------------------------+
        |
        v
+------------------------------------------------------------------------------+
| Query API (app/api/routes/actors.py) + Export (CSV / JSON / PDF report)      |
+------------------------------------------------------------------------------+
        |
        v
                 Dashboard (frontend/) — search, actor profile,
                 relationship graph view, export buttons
```

## A second, separate pipeline: threat categorization

Attribution (above) answers "is this the same actor?" Threat categorization
answers a different question — "what kind of activity is this actor
associated with?" — and is kept architecturally separate: it never touches
`app/services/scoring.py`'s confidence formula, and a category is never
inferred from an identifier (username, wallet, PGP key) alone.

```
Real per-item activity content (RawActivity — one row per real listing/post,
ingested once by scripts/ingest_evolution.py / ingest_darkforums.py, never
rebuilt)
        |
        v
app/services/threat_categorization.py
  1. source-provided category, if the dataset has one (e.g. DarkForums'
     real "category": "Leaks" field) -> confidence "high"
  2. else: conservative keyword/phrase rules over title+text -> "medium"
  3. else: unclassified (not persisted)
        |
        v
ThreatActivity (evidence: category, matched reason, source, observed_at) —
rebuilt each run_full_analysis, actor_id resolved fresh each run, exactly
like CorrelationEvidence
        |
        v
GET /api/actors/{id}/threat-activity -> ActorProfileView "Observed Threat
Categories" + Timeline Explorer + exports
```

## Why async jobs, not inline analysis

Stylometry over many samples, graph traversal, and infra scanning can each
take real time. The API enqueues work to Celery and returns a job id
immediately; the frontend polls job status. This keeps the API responsive and
matches how a real production system would need to behave.

## Autonomous collection loop

`app/workers/tasks.py:run_scheduled_collection`, fired on a fixed interval
by `celery -A app.workers.celery_app beat` (see `celery_app.py`'s
`beat_schedule`, and the `beat` service in `docker-compose.prod.yml`),
re-pulls the live public feeds Argus already knows how to ingest — Tor
Onionoo, MISP OSINT, HIBP breach directory (the same `main()`s the manual
`scripts/ingest_*.py` commands call) — then re-runs `run_full_analysis` so
fresh correlation evidence surfaces without anyone manually re-triggering
it. Each feed is independent and best-effort; one being unreachable doesn't
stop the others or block the pipeline re-run. Every run leaves a real
`AnalysisJob` row (`job_type="scheduled_collection"`), visible in the same
Jobs & Scans view as manually-triggered runs. Not enabled in local dev
(`docker-compose.yml` has no `beat` service) — a dev's machine shouldn't be
silently polling real external APIs on a fixed schedule just because
`docker compose up` was run.

## Why a relational store AND a graph store

Postgres holds the canonical actor/identifier/finding records — the stuff the
query interface and exports need in a straightforward tabular form. Neo4j
holds the relationship graph specifically, because graph traversal queries
("what's connected to this wallet within 2 hops") are what Postgres is bad at
and Neo4j is built for. The two are kept in sync by identifier value.

## Confidence scoring

See `app/services/scoring.py` (`WEIGHTS`, kept as the single source of truth
— if this doc and the code ever disagree, trust the code). Three weighted
signals:
- Relationship strength, e.g. shared wallet/PGP key (0.65) — near-deterministic when present
- Stylometric similarity (0.20) — corroborating behavioral signal
- Infra match (0.15) — rare but decisive when found

Be ready to defend these weights as a starting hypothesis, not a proven model
— that's an honest answer judges will respect more than false precision.
Threat-category classification (see above) is deliberately NOT a fourth
signal here — it answers a different question and must never move this score.
