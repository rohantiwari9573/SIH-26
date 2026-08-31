# Playwright smoke suite

Minimal, deliberately small — Argus had no frontend test framework at all
before Phase 5 (audited: no Vitest/Jest/Playwright config, no `test` script).
This suite is a smoke check, not a full E2E regression suite: does every
page load, navigate, and render without a console error/crash, using real
data from whatever's currently in the dev DB.

## Prerequisites

The suite runs against an **already-running** stack — it does not start its
own server or seed data:

```bash
docker compose up -d
```

Frontend must be reachable at `http://localhost:5173` (override with
`ARGUS_BASE_URL`).

## Running

```bash
cd frontend
npm install
npx playwright install chromium   # one-time browser download
npm run test:e2e
```

## What's covered

- Registration + login (a fresh throwaway account per run, never a
  committed test credential)
- Every sidebar view loads and renders a real heading with zero console
  errors (Dashboard, Threat Actors, Infrastructure, AI Attribution,
  Timeline Explorer, Sources & Feeds, Hidden Services, Marketplaces,
  Forums, Alerts, Indicators, Reports, Jobs & Scans)
- Jobs & Scans shows real system status / source ingestion / analysis-jobs
  panels (not a fabricated "recent jobs" list)
- Actor profile: attribution breakdown, relationship graph, Observed Threat
  Categories (expand a category → real per-item evidence: source, persona,
  activity text, classification reason, observed date), and a real CSV
  export download
- Honest empty states: `actor-profile.spec.ts` asserts the "No classifiable
  activity found" message when an actor genuinely has none, rather than
  requiring a populated table to exist

## What's NOT covered (accepted scope boundary for a minimal smoke suite)

- Visual/pixel regression
- Mobile/tablet viewports (see docs/ARCHITECTURE.md's Phase 5 accessibility
  note for what was checked manually instead)
- The Controlled Demo's full submit-lead → Celery → re-attribution flow
  (async, timing-sensitive; better exercised manually or with a longer,
  separate test)
- CI wiring — not added to `.github/workflows/ci.yml` in this phase, since
  CI has no running `docker compose` stack for these tests to target. Run
  locally against the dev stack for now; wiring a CI job would need either
  a docker-compose-in-CI step or a mocked API layer, which is more scope
  than "minimal smoke suite" implies.
