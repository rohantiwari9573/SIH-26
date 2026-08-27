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
                 Dashboard (frontend, to be built) — search, actor profile,
                 relationship graph view, export buttons
```

## Why async jobs, not inline analysis

Stylometry over many samples, graph traversal, and infra scanning can each
take real time. The API enqueues work to Celery and returns a job id
immediately; the frontend polls job status. This keeps the API responsive and
matches how a real production system would need to behave.

## Why a relational store AND a graph store

Postgres holds the canonical actor/identifier/finding records — the stuff the
query interface and exports need in a straightforward tabular form. Neo4j
holds the relationship graph specifically, because graph traversal queries
("what's connected to this wallet within 2 hops") are what Postgres is bad at
and Neo4j is built for. The two are kept in sync by identifier value.

## Confidence scoring

See `app/services/scoring.py`. Three weighted signals:
- Stylometric similarity (0.40) — strongest behavioral signal
- Relationship strength, e.g. shared wallet/PGP key (0.35) — near-certain when present
- Infra match (0.25) — rare but decisive when found

Be ready to defend these weights as a starting hypothesis, not a proven model
— that's an honest answer judges will respect more than false precision.
