# AI/ML Stylometric & Behavioural Analysis

Satisfies PS-26151's requirement to use "AI-based analysis, including
stylometric persona identification and behavioural profiling, to link
rebranded or migrated personas to known threat actors."

## 1. Why AI/ML is used

Handles, PGP keys, and wallets are strong evidence when they're reused
verbatim — but a threat actor who deliberately rebrands (new username, new
platform, no reused identifier) leaves no such direct link. Writing style
and behavioural pattern are the residual signal in that case: people don't
easily change *how* they write, even when they change *who* they claim to
be. This module gives Argus a second, independent evidence channel for
exactly that scenario.

## 2. What model/method is used

No LLM, no downloaded/pretrained embedding model, no third-party API call.
Four classical, CPU-only, deterministic techniques
(`app/services/ai_stylometry.py`):

1. **Character n-gram TF-IDF + cosine similarity** (the headline
   "stylometric similarity") — `sklearn.feature_extraction.text.TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4))`
   over each persona's concatenated real activity text. Captures
   topic-independent surface style (spelling habits, punctuation spacing,
   capitalization). Standard first-choice feature in published
   authorship-attribution literature.
2. **Word n-gram TF-IDF + cosine similarity** ("vocabulary distribution"
   signal) — `ngram_range=(1,2)` over the same text. Captures shared
   vocabulary/phrasing, a different feature space from (1).
3. **Structural similarity** ("sentence structure" signal) — reuses the
   project's existing `app/services/stylometry/classifier.py`
   (Burrows'-Delta-style z-scored function-word/punctuation/sentence-length
   features), already used by the attribution pipeline. Not duplicated
   logic — the same function, re-exposed as one explainable signal instead
   of a single opaque number.
4. **Behavioural similarity** (the headline "behavioural similarity") —
   cosine similarity between two personas' real threat-category-distribution
   vectors, computed from already-classified `ThreatActivity` rows.

### Why not `sentence-transformers`/embeddings?

Evaluated and rejected. A model such as `all-MiniLM-L6-v2` requires
PyTorch (700MB+ of dependencies) and a ~90MB model download, materially
increasing Docker image size, cold-start time, and RAM pressure on the
project's `t3.small` instance, which already runs Postgres, Neo4j, Redis,
the API, and a Celery worker concurrently. `scikit-learn` adds ~40MB of pure
CPU wheels, downloads nothing at runtime, and needs no network access —
appropriate for the project's free-tier constraint.

## 3. Features extracted

See `app/services/stylometry/features.py` (existing, reused) for the
structural feature set (function-word frequency, punctuation ratio,
sentence/word length, type-token ratio) and `app/services/ai_stylometry.py`
for the two new TF-IDF vector spaces (character n-grams, word n-grams).

## 4. How similarity is calculated

For a pair of personas already clustered into the same Actor:

1. Concatenate each persona's real `RawActivity.title` + `.text` rows into
   one document.
2. Require each document to have **≥25 words**, drawn from **≥2 real
   activity samples** — below that, `classifier.py`'s own validated finding
   is that the technique's signal separation "nearly vanishes" (see that
   module's docstring), so an honest `InsufficientData` result is returned
   instead of an unreliable-looking number.
3. Compute the four signals above between the two documents.
4. Bucket each into `High similarity` (≥0.6), `Moderate similarity`
   (≥0.35), or `Low similarity` (below 0.35) — fixed, documented
   thresholds, not tuned per-actor.

## 5. How behavioural similarity is calculated

Cosine similarity between two 9-dimensional vectors (one entry per real
`ThreatActivity.category` value), built from that persona's own classified
activity counts. `None` (not `0.0`) when *neither* persona has any
classified activity — a genuinely different state from "compared and found
dissimilar" (a real `0.0`, returned when one side has signal and the other
doesn't).

## 6. How the result relates to attribution — kept deliberately separate

| Concept | Question it answers | Where it lives |
|---|---|---|
| AI stylometric/behavioural similarity | "How similar are these two personas' writing/behaviour patterns?" | `GET /api/actors/{id}/ai-analysis` |
| Attribution confidence | "How strong is the total body of evidence connecting these identities?" | `GET /api/actors/{id}/attribution-breakdown`, `Actor.confidence_score` |
| Threat category | "What kind of activity did this persona post?" | `GET /api/actors/{id}/threat-activity` |

`ai_stylometry.py`/`actor_ai_analysis.py` are **read-only** relative to
`app.services.scoring`/`app.services.attribution`/`app.services.pipeline` —
nothing they compute is written to `Actor.confidence_score`, and the
existing `similarity_score()` function they reuse is the *same* function
`attribution.py` already calls at stylometry weight `0.20` (of 1.0) —
unchanged by this work. The AI/ML section shown here is a richer,
explainable *display* of that same class of evidence, computed from more
activity data (real per-listing/per-post `RawActivity` text, not just the
single `RawPersona.sample_text` blob attribution uses), not a new input to
the confidence formula.

## 7. Why similarity is NOT identity probability

An 87% stylometric similarity score means "these two writing samples are
87%-similar on this specific feature representation," not "there is an 87%
probability these are the same real-world person." The UI never phrases it
the second way. Two genuinely different people can write similarly by
coincidence (especially on short, template-like marketplace listings); one
person's writing can also vary across contexts. This is why the module
treats its output as *supporting* evidence, one signal among several
(shared wallet, shared PGP key, infrastructure, and now this), never a
standalone conclusion.

## 8. Limitations and false-positive considerations

- **Short-text unreliability**: the reference validation in
  `classifier.py` found the true-pair/unrelated-pair gap "nearly vanishes"
  on 1-2 sentence samples — this is why a 25-word/2-sample minimum is
  enforced, with an honest `InsufficientData` result below it.
- **Template text**: marketplace listings are often formulaic ("escrow
  recommended", "ships same day"), which can inflate character/word n-gram
  similarity between genuinely unrelated vendors who both use common
  marketplace phrasing. This is a real limitation of the technique, not
  specific to this implementation — mitigated, not eliminated, by requiring
  multiple real samples and showing all four signals rather than one
  blended number, so an investigator can see *which* signal is driving a
  result.
- **Scope**: only compares personas already clustered into the same Actor
  (i.e. already linked by some other evidence, or a single-persona actor
  with nothing to compare). It does not currently scan for stylometric
  matches *across* different actors to propose new links — see "Recommended
  next steps" in the implementation report for that as a possible follow-up.
- **English-only tuning**: `features.py`'s function-word list and this
  module's stop-word list (word n-gram signal) are English-specific.
