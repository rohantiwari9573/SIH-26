"""Stylometric feature extraction for authorship attribution.

Deliberately dependency-light (no spaCy/NLTK) so it runs anywhere without model
downloads. Features are the classic "writeprint" style: function-word frequency,
punctuation ratios, and sentence-length statistics — cheap, interpretable, and
well documented in authorship-attribution literature.
"""
import re
from collections import Counter

FUNCTION_WORDS = [
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "with", "as", "at", "by", "is", "it", "this", "that", "not", "be", "are",
    "was", "were", "so", "i", "you", "we", "they",
]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def extract_features(text: str) -> dict[str, float]:
    words = _words(text)
    sentences = _sentences(text)
    word_count = max(len(words), 1)
    sentence_count = max(len(sentences), 1)

    counts = Counter(words)
    function_word_freq = {
        f"fw_{w}": counts.get(w, 0) / word_count for w in FUNCTION_WORDS
    }

    # Scaled to roughly 0-1 so they sit on the same footing as the frequency
    # features below — cosine similarity is dominated by whichever features
    # have the largest magnitude, and unscaled sentence/word length (~5-20)
    # swamped the actual stylistic signal, causing unrelated texts to score
    # almost as "similar" as true rebrand pairs. Divisors are soft caps, not
    # hard clamps: typical English sentence/word lengths, so most real text
    # lands under 1.0 but nothing breaks if it doesn't.
    avg_sentence_len = (word_count / sentence_count) / 25.0
    avg_word_len = (sum(len(w) for w in words) / word_count) / 8.0

    punctuation_counts = Counter(c for c in text if c in ",.;:!?-'\"")
    total_chars = max(len(text), 1)
    punctuation_ratio = {
        f"punct_{p}": punctuation_counts.get(p, 0) / total_chars
        for p in ",.;:!?-'\""
    }

    features: dict[str, float] = {
        "avg_sentence_len": avg_sentence_len,
        "avg_word_len": avg_word_len,
        "type_token_ratio": len(set(words)) / word_count,
    }
    features.update(function_word_freq)
    features.update(punctuation_ratio)
    return features
