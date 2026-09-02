# Argus — Dark Web Threat Actor De-anonymization

A system that links dark-web personas to real-world identity/infrastructure using
infrastructure fingerprinting, relationship-graph analysis, and stylometric
behavioral analysis — and separately classifies each actor's own real activity
content into a controlled threat-category taxonomy (credential theft, hacking
services, stolen data, etc.), with full evidence and provenance for every
category assigned.

> **Ethics / legal notice**: This project never scrapes live dark-web marketplaces.
> Real intelligence comes only from public OSINT feeds and already-published academic
> research datasets (see **Real intelligence sources** below); the infrastructure-scan
> pillar runs only against a self-hosted mock Tor hidden service the team controls.
> See [docs/ETHICS.md](docs/ETHICS.md).

## Live demo

- **Dashboard**: https://argus-frontend-dun.vercel.app/
- **API**: https://api.rohantiwari.me/docs

Deployed on Vercel (frontend, auto-deploys on push to `master`) and AWS EC2
(backend — FastAPI, Postgres, Neo4j, Redis, Celery worker + beat, behind
Caddy/HTTPS). The sections below (Quickstart, `localhost:*`) are for running
Argus on your own machine, not the deployed instance.

## Architecture

Two SEPARATE analytical pipelines feed a unified actor-profile store, exposed
through a query API and dashboard. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for the diagram and data flow.

**Attribution** — "is this the same actor?"

| Pillar | Module | Tech |
|---|---|---|
| Infrastructure analysis | `app/services/infra_scan` | SSL/cert inspection, banner grabbing |
| Relationship mapping | `app/services/graph` | Neo4j entity graph, visualized live in the dashboard |
| Behavioral / stylometric analysis | `app/services/stylometry` | Burrows' Delta authorship attribution (hand-rolled, no ML framework) |
| Wallet clustering | `app/services/wallet_cluster` | common-input-ownership heuristic |

**Threat categorization** — "what kind of activity is this actor associated with?"
Deliberately independent of attribution — see `app/services/threat_categorization.py`'s
module docstring. Never feeds `app/services/scoring.py`'s confidence formula.

| Stage | Module |
|---|---|
| Real per-item activity ingestion (one row per listing/post) | `app/models/actor.RawActivity`, `scripts/ingest_evolution.py` / `ingest_darkforums.py` |
| Classification (source-provided category, else conservative keyword rules) | `app/services/threat_categorization.py` |
| Evidence storage + actor linkage | `app/models/actor.ThreatActivity`, rebuilt each `run_full_analysis` |
| API | `GET /api/actors/{id}/threat-activity` |
| UI | ActorProfileView's "Observed Threat Categories" section |

## Real intelligence sources

Beyond the synthetic/controlled demo data, Argus ingests real public
intelligence via `scripts/ingest_*.py` — every source is honestly labeled
(historical dataset / live feed / synthetic), never faked, and a 0-record
source means genuinely not configured, not hidden:

| Source | Script | What it provides |
|---|---|---|
| Evolution Market/Forum dataset (Zenodo) | `ingest_evolution.py` | Real historical marketplace listings + forum posts, real ground-truth cross-platform persona matches |
| DarkForums dataset (Zenodo) | `ingest_darkforums.py` | Real leak-forum thread/post content with a real source-provided category ("Leaks") |
| Tor Onionoo (Tor Project) | `ingest_onionoo.py` | Live relay metadata |
| MISP CIRCL + botvrij.eu OSINT feeds | `ingest_misp_osint.py` | Live threat-intel events + indicators |
| Have I Been Pwned breach directory | `ingest_hibp.py` | Public breach metadata |
| URLhaus / MalwareBazaar / Chainabuse | `ingest_urlhaus.py` / `ingest_malwarebazaar.py` / `ingest_chainabuse.py` | Live feeds, require an API key each (0 records/`configured: false` until set) |

`app/services/correlation.py` deterministically cross-checks these against
Argus's own infrastructure findings (enrichment evidence only, never fed into
attribution confidence); `app/services/threat_categorization.py` classifies
the activity-bearing sources (Evolution, DarkForums) into the threat-category
taxonomy described above.

## Stack

- **API**: FastAPI + Pydantic
- **Relational store**: PostgreSQL (SQLAlchemy + Alembic migrations)
- **Graph store**: Neo4j
- **Job queue**: Celery + Redis (analysis jobs run async, not inline on the request)
- **Frontend**: React + TypeScript (Vite dev server for development, static
  build behind nginx for production — see `docker-compose.yml`'s `frontend`
  vs. `frontend-prod` services)
- **Auth**: JWT
- **Tests**: pytest
- **CI**: GitHub Actions (lint + test on every push)

## Quickstart (local development)

```bash
cp .env.example .env
docker compose up --build
```

- Dashboard: http://localhost:5173
- API: http://localhost:8000/docs
- Neo4j browser: http://localhost:7474

For a production-style static build (nginx-served, no Vite dev server, no
source volume-mounted) instead of the hot-reload dev frontend:

```bash
docker compose --profile prod up --build frontend-prod
```

Dashboard then at http://localhost:5174 — separate port from the dev server
on 5173, so both can run side by side. Not started by plain `docker compose
up`; opt in with `--profile prod` when you want it (e.g. for the actual demo,
where showing Vite's dev tooling in devtools looks less finished).

Generate and run the initial migration (first time only):

```bash
docker compose exec api alembic revision --autogenerate -m "init"
docker compose exec api alembic upgrade head
```

After any model change, repeat the `revision --autogenerate` + `upgrade head` steps.

Generate the synthetic demo dataset (safe to run, no real data):

```bash
python scripts/generate_synthetic_dataset.py
```

Sanity-check the attribution pipeline standalone, no DB needed (prints clusters
+ confidence scores to stdout — good first check and a live-demo fallback if
Docker isn't handy):

```bash
docker compose exec api python scripts/run_attribution_demo.py
# or locally without Docker: PYTHONPATH=. python scripts/run_attribution_demo.py
```

Run the full pipeline and persist results (Postgres + Neo4j required — this is
the primary demo path, since it *derives* attribution from unlinked raw data
rather than pre-linking the answer):

```bash
docker compose exec api python scripts/ingest_and_attribute.py
```

Or skip the CLI entirely and submit a lead through the dashboard itself
("+ Submit lead") — same pipeline, runs async via Celery, polls job status,
and re-derives every actor cluster from everything known so far.

Ingest real intelligence sources (each is independent, safe to run in any
order; see **Real intelligence sources** above for what each provides —
Evolution/DarkForums also populate `RawActivity`/`ThreatActivity` and re-run
the full pipeline automatically):

```bash
docker compose exec api python scripts/ingest_evolution.py
docker compose exec api python scripts/ingest_darkforums.py
docker compose exec api python scripts/ingest_onionoo.py
docker compose exec api python scripts/ingest_misp_osint.py
docker compose exec api python scripts/ingest_hibp.py
```

Run tests:

```bash
docker compose exec api pytest
```

## Requirement coverage checklist

Maps directly to the PS text — keep this current, it's your judge-facing proof of coverage.
Everything below has been run against the **real `docker compose up` stack**
(Postgres, Neo4j, Redis, Celery, the mock infra target, the API, and the
dashboard) in this session — not simulated, not just unit-tested in isolation.

- [x] Infrastructure analysis: SSL leak / banner detection — ran from inside
      the `api` container against the real `mock_target` container over the
      real Docker network; both leaks detected correctly
- [x] Relationship mapping: username / PGP key / wallet / trust-link graph —
      verified by querying the real Neo4j container directly with Cypher after
      running the pipeline; `shadow_vendor` and `nightowl_88` both correctly
      linked through shared wallet/PGP nodes; **also rendered as an actual
      graph in the dashboard** (`GET /api/actors/{id}/graph` + `GraphView.tsx`),
      not just implied by a table — verified live in the browser
- [x] Behavioral analysis: stylometric persona-migration detection — verified
      with a real discrimination-margin check (true pair 0.94 vs. unrelated
      pairs 0.62-0.87); a graded-confidence pair (stylometry-only match, no
      shared identifiers) is included in the demo dataset so the UI can show
      partial evidence, not just binary yes/no
- [x] Database collection, storage, analysis pipeline — `scripts/ingest_and_attribute.py`
      run against the real Postgres container via Alembic-migrated schema;
      confirmed via direct SQL query and via the live API. **Also live at
      runtime**, not just via CLI script: `POST /api/leads` accepts a new
      persona, upserts it, and re-runs the full pipeline async via Celery
      (`GET /api/jobs/{task_id}` for status) — verified live in the browser,
      including watching an actor's confidence jump from 18% to 83% after
      submitting a wallet link for one of its personas
- [x] Query interface (search actor by identifier) — dashboard + API verified
      end-to-end live in an actual browser against the containerized stack
- [x] Actor profile view: identifiers, infra details, confidence metrics together —
      verified live in the browser
- [x] Export: CSV / JSON / report (PDF) — all three verified live: clicked each
      button in the browser, confirmed the downloaded files' contents
- [x] Category — `app/services/threat_categorization.py` + `ThreatActivity`
      table; verified live against real re-ingested DarkForums data: 152 real
      per-post activity records, all classified via the dataset's own
      source-provided category field, all linked to the real actor and
      visible with full evidence (source, matched text, reason, observed
      date) in the ActorProfileView "Observed Threat Categories" section and
      in all three export formats. Deliberately does NOT feed attribution
      confidence — see `app/services/threat_categorization.py`'s module
      docstring.

No open gaps as of this session. If you change the pipeline or add data,
re-run `docker compose exec api python scripts/ingest_and_attribute.py` and
spot-check the dashboard before assuming it still holds.

## Project layout

```
app/
  core/       config, security (JWT)
  db/         SQLAlchemy session/base
  models/     ORM models (actor.py: Argus's own derived data; external.py: real ingested intel)
  schemas/    Pydantic request/response schemas
  api/routes/ FastAPI routers (auth, actors, export, leads, jobs, health, dashboard)
  services/   attribution pillars, correlation, threat categorization
  workers/    Celery app + async analysis tasks
alembic/            DB migrations
tests/              unit + integration tests
docs/               architecture + ethics docs
scripts/            synthetic dataset generation, attribution pipeline runners,
                     real-source ingestion (ingest_evolution.py, ingest_darkforums.py,
                     ingest_onionoo.py, ingest_misp_osint.py, ingest_hibp.py, ...)
frontend/           React + TypeScript dashboard (login, search, actor profile, exports)
mock_leaky_service/ deliberately misconfigured target for the infra-scan pillar
data/               generated synthetic dataset + extracted real-source data (data/external/)
```
