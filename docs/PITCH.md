# Pitch & Demo Script — SIH26151

Working notes for turning this into slides and for running the live demo.
Everything in the demo script below was actually run and verified working in
this session (browser UI, real downloaded files) — not aspirational.

## 30-second framing (opening slide)

NTRO's problem: threat actors hide behind Tor, and investigators need a way to
connect a dark-web persona back to a real-world identity. We built a platform
that does this three ways at once — infrastructure leaks, relationship graphs,
and writing-style fingerprinting — and combines them into one confidence
score per actor, not three disconnected reports.

## Requirement-coverage slide

Put this table directly in the deck. It preempts the "did you implement
everything in the PS" question before a judge has to ask it.

| PS requirement | Where it lives | Status |
|---|---|---|
| Infrastructure analysis (SSL leak, banner, exposed page) | `app/services/infra_scan` | Working, tested live against a real misconfigured target |
| Relationship mapping (username/PGP/wallet/trust graph) | `app/services/graph`, `app/services/attribution.py` | Working |
| Behavioral/stylometric analysis | `app/services/stylometry` (Burrows' Delta) | Working, validated discrimination margin |
| DB collection, storage, analysis pipeline | Postgres + Neo4j, `scripts/ingest_and_attribute.py` | Working |
| Query interface | React dashboard + API | Working |
| Actor profile (identifiers + infra + confidence together) | Dashboard profile view | Working |
| Export: CSV / JSON / report | Dashboard export buttons | Working, all 3 verified |

## Live demo script

Run this exact sequence on stage. It's the same flow verified in this session.

1. **Open the dashboard**, log in with the demo account.
2. **Show the search/list view** — point out the flagship result:
   `Actor: nightowl_88 / shadow_vendor` at **84% confidence**, and the two
   negative-control actors sitting at **0%** next to it.
   - Say explicitly: *"These two never merge, even though they're both real
     personas in our dataset — the system doesn't over-attribute."* This is
     your answer before anyone asks about false positives.
3. **Click into the flagship actor.** Walk through the identifiers table:
   two usernames, on two different marketplaces, sharing one wallet address
   and one PGP key.
4. **Explain the confidence score breakdown** (have this ready verbally, not
   just as a number): *shared wallet + PGP key contributes most of the score
   because it's close to a deterministic match; the writing-style similarity
   (94% vs. 62-87% for unrelated pairs) corroborates it independently.*
5. **Click all three export buttons** — CSV, JSON, PDF report — show the
   files land in Downloads with real content, live.
6. **Pull up `careless_admin`** (the low-confidence infra-only lead) to show
   the infra pillar working on its own, independent of the other two —
   this demonstrates pillar 1 isn't just decorative.

## Anticipated judge questions — have answers ready

**"Did you actually scrape the dark web?"**
No, by design — see `docs/ETHICS.md`. All data is synthetic; the infra-scan
pillar runs against our own deliberately misconfigured mock service, not a
real hidden service. State this proactively, don't wait to be asked.

**"How do you avoid false positives?"**
Point at the negative-control actors sitting at 0% confidence in the demo —
this is a live, running answer, not a claim.

**"Why those confidence weights?"**
Relationship evidence (shared wallet/PGP) is weighted highest because it's
close to deterministic — two personas reusing the same wallet is about as
strong as evidence gets in this domain. Stylometry is corroborating,
probabilistic evidence. Say plainly: these are a documented starting
hypothesis, not a claim of statistical rigor calibrated on real data — that
would need a labeled dataset we don't have and shouldn't fabricate.

**"Does stylometry work on short text?"**
Be honest: no, and we found this out by testing it, not by assuming — a
single-sentence sample nearly collapsed the discrimination margin
(0.05 gap). The current pipeline uses aggregated multi-post samples for
exactly this reason; a production version would require a minimum sample
length before attempting attribution at all.

**"How would this scale to real Tor traffic volume?"**
The analysis pipeline is already async (Celery), and Postgres + Neo4j are
each doing the job they're suited for. The honest gap: we haven't load-tested
it, and real dark-web crawling at scale is a different, much harder problem
(Tor circuit management, rate limits, takedown/rotation of hidden services)
that this prototype doesn't attempt to solve.

## What to say if a demo step fails live

Have `scripts/run_attribution_demo.py` output ready as a screenshot/backup —
it's the same pipeline without the UI, so a working fallback exists if the
browser or a container misbehaves on stage.
