"""AI/ML stylometric & behavioural persona-comparison engine — the "does this
writing/behaviour resemble another persona?" question (PS-26151's AI-based
analysis requirement), kept architecturally SEPARATE from attribution
confidence (app.services.scoring/attribution — "is this the same actor?").
Nothing in this module writes to Actor.confidence_score or any input to
compute_confidence; it is a supporting-evidence layer, exactly like
app.services.threat_categorization and app.services.correlation are.

FOUR real, reproducible, CPU-only signals — no LLM, no downloaded embedding
model, no network calls, no hardcoded/random scores:

1. Character n-gram similarity (the headline "stylometric similarity"):
   TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4)) over each
   persona's concatenated real RawActivity text, compared by cosine
   similarity. Character n-grams capture surface writing style (spelling
   habits, punctuation spacing, capitalization patterns) largely independent
   of topic — the standard first-choice feature in published
   authorship-attribution literature (e.g. Kjell 1994; Grieve 2007).

2. Word n-gram similarity ("vocabulary distribution" signal):
   TfidfVectorizer(ngram_range=(1,2)) over the same text, cosine similarity.
   Captures shared vocabulary/phrasing choices — a different, complementary
   feature space from (1): two personas can share vocabulary without sharing
   character-level style, or vice versa.

3. Structural similarity ("sentence structure" signal): REUSES the
   project's existing app.services.stylometry.classifier.similarity_score
   (Burrows' Delta over function-word frequency, punctuation ratio, and
   sentence/word-length features from features.py) — the same function
   already feeding attribution.py's stylometry pillar. Not duplicated logic,
   just re-exposed here as one of several explainable signals instead of a
   single opaque number.

4. Behavioural similarity (the headline "behavioural similarity"): cosine
   similarity between two personas' real threat-category-distribution
   vectors (from ThreatActivity rows already classified by
   threat_categorization.py) — "do these two personas' observed activity
   fall into similar categories in similar proportions?" Falls back to 0.0
   contribution (not fabricated) when neither persona has any classified
   activity to compare.

All four are bucketed into "High / Moderate / Low similarity" using fixed,
documented thresholds (>=0.6 High, >=0.35 Moderate, else Low) for the
"Observed AI Signals" explanation table — never shown as an unexplained bare
percentage.

Minimum data requirement: each persona in a pair must have at least 2 real
RawActivity rows with non-empty text, combining to at least 25 words total.
Below that, app.services.stylometry.classifier's own validated finding is
that the technique's signal separation "nearly vanishes" (see that module's
docstring) — so this returns an explicit insufficient-data result rather
than a number that looks precise but isn't reliable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.services.stylometry.classifier import similarity_score as structural_similarity_score
from app.services.threat_categorization import CATEGORY_LABELS

MIN_ACTIVITIES_PER_PERSONA = 2
MIN_WORDS_PER_PERSONA = 25

_CATEGORY_KEYS = [k for k in CATEGORY_LABELS if k != "unclassified"]

METHOD_DESCRIPTION = (
    "Character n-gram TF-IDF (2-4 grams) + cosine similarity; "
    "word n-gram TF-IDF (1-2 grams) + cosine similarity; "
    "Burrows' Delta stylometric features (function-word frequency, "
    "punctuation ratio, sentence/word length); "
    "threat-category-distribution cosine similarity."
)


def _bucket(score: float) -> str:
    if score >= 0.6:
        return "High similarity"
    if score >= 0.35:
        return "Moderate similarity"
    return "Low similarity"


def _word_count(text: str) -> int:
    return len(text.split())


def _tfidf_cosine(text_a: str, text_b: str, **vectorizer_kwargs) -> float:
    vectorizer = TfidfVectorizer(**vectorizer_kwargs)
    try:
        matrix = vectorizer.fit_transform([text_a, text_b])
    except ValueError:
        # Both texts reduced to nothing by the vectorizer's tokenizer (e.g.
        # pure punctuation/whitespace) -- a real "no signal" result, not an
        # error to hide.
        return 0.0
    return float(cosine_similarity(matrix[0], matrix[1])[0][0])


@dataclass
class BehavioralVector:
    category_counts: dict[str, int] = field(default_factory=dict)

    def has_signal(self) -> bool:
        return sum(self.category_counts.values()) > 0


def behavioral_similarity(vec_a: BehavioralVector, vec_b: BehavioralVector) -> float | None:
    """None (not 0.0) when NEITHER persona has any classified activity --
    that's "no comparable behavioural signal", a different honest state from
    "compared and found dissimilar" (which a real 0.0 would mean)."""
    if not vec_a.has_signal() and not vec_b.has_signal():
        return None
    a = [vec_a.category_counts.get(k, 0) for k in _CATEGORY_KEYS]
    b = [vec_b.category_counts.get(k, 0) for k in _CATEGORY_KEYS]
    if sum(a) == 0 or sum(b) == 0:
        return 0.0  # one side has signal, the other genuinely has none -> real 0
    return float(cosine_similarity([a], [b])[0][0])


@dataclass
class SignalRow:
    name: str
    score: float
    bucket: str


@dataclass
class PairAnalysis:
    stylometric_similarity: float
    behavioral_similarity: float | None
    signals: list[SignalRow]


@dataclass
class InsufficientData:
    reason: str


def compare_personas(
    text_a: str,
    text_b: str,
    behavioral_a: BehavioralVector,
    behavioral_b: BehavioralVector,
) -> PairAnalysis | InsufficientData:
    """Pure function, DB-free by design (same rationale as
    app.services.attribution) -- independently unit-testable with fixed
    strings, no fixtures, no network, no model download."""
    if _word_count(text_a) < MIN_WORDS_PER_PERSONA or _word_count(text_b) < MIN_WORDS_PER_PERSONA:
        return InsufficientData(
            "Insufficient comparable activity for stylometric analysis."
        )

    char_ngram = _tfidf_cosine(text_a, text_b, analyzer="char_wb", ngram_range=(2, 4))
    word_ngram = _tfidf_cosine(text_a, text_b, ngram_range=(1, 2), stop_words="english")
    structural = structural_similarity_score(text_a, text_b)
    behavioral = behavioral_similarity(behavioral_a, behavioral_b)

    signals = [
        SignalRow("Character n-gram patterns", char_ngram, _bucket(char_ngram)),
        SignalRow("Vocabulary distribution", word_ngram, _bucket(word_ngram)),
        SignalRow("Sentence structure", structural, _bucket(structural)),
    ]
    if behavioral is not None:
        signals.append(SignalRow("Activity behaviour", behavioral, _bucket(behavioral)))

    return PairAnalysis(
        stylometric_similarity=char_ngram,
        behavioral_similarity=behavioral,
        signals=signals,
    )
