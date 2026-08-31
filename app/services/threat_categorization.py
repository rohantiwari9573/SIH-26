"""Classifies one RawActivity (a single real marketplace listing or forum
post) into a controlled threat-category taxonomy — a SEPARATE analytical
pipeline from app.services.attribution/scoring. See app.models.actor's
ThreatActivity docstring: nothing produced here ever feeds
app.services.scoring.compute_confidence. This module answers "what kind of
activity is this," attribution answers "is this the same actor" — the two
questions are never mixed.

DELIBERATELY CONSERVATIVE, for two independent reasons documented inline
below (SOURCE_CATEGORY_MAP, CATEGORY_RULES): a username, PGP key, wallet, or
generic forum participation must NEVER by itself produce a category, and
ambiguous text is left unclassified rather than guessed at. Unclassified is
the CORRECT and expected result for most forum chatter — see
scripts/ingest_evolution.py's post_sample.tsv, which is overwhelmingly
community small talk, not activity descriptions.

Two independent classification paths, tried in order (first hit wins):

1. SOURCE-PROVIDED CATEGORY — the platform's own editorial category field,
   when the ingested dataset actually has one (currently only DarkForums'
   real "category" field, e.g. "Leaks"). This is the strongest evidence
   available: the forum operator itself labeled the content, Argus isn't
   inferring anything. classification_confidence="high".

2. KEYWORD / PHRASE RULE — a small, hand-written, documented set of
   multi-word phrases (never single ambiguous words) matched against the
   activity's title+text with word boundaries. classification_confidence=
   "medium" — a deterministic heuristic, not a certainty.

No ML/NLP/LLM dependency: the project's existing classification/matching
code (app.services.stylometry, app.services.correlation) is already
deterministic and explainable, and pulling in an external paid API for a
few hundred short listing/post strings would trade reproducibility and
demoability for no real accuracy benefit at this data volume.
"""
import re
from dataclasses import dataclass

# Controlled taxonomy — the only category values ThreatActivity.category may
# hold. "unclassified" is a valid outcome, never persisted as a row (see
# app.services.pipeline), but kept here as the explicit "no match" return.
CATEGORY_LABELS: dict[str, str] = {
    "credential_data_theft": "Credential / Data Theft",
    "hacking_services": "Hacking Services",
    "malware": "Malware",
    "financial_fraud": "Financial Fraud",
    "money_laundering": "Money Laundering",
    "drug_trafficking": "Drug Trafficking",
    "weapons_arms": "Weapons / Arms",
    "stolen_data": "Stolen Data",
    "other_cybercrime": "Other Cybercrime",
    "unclassified": "Unknown / Unclassified",
}


@dataclass
class ClassificationResult:
    category: str  # key into CATEGORY_LABELS, never "unclassified"
    reason: str
    method: str  # "source_provided" | "keyword_rule"
    confidence: str  # "high" | "medium"


# Real source-editorial category values seen in the actually-ingested
# datasets (see scripts/ingest_darkforums.py; data/external/darkforums_safe_
# corpus.json's every row has category="Leaks"). Deliberately a small,
# explicit mapping — an unrecognized source category falls through to the
# keyword path rather than being guessed at, and this map must never be
# extended with a category the source data doesn't actually contain.
SOURCE_CATEGORY_MAP: dict[str, str] = {
    "leaks": "stolen_data",
}

# (category, [phrase patterns]). Order is priority — checked top to bottom,
# first match wins, so a more specific category (e.g. malware) is listed
# before a broader one it could plausibly overlap with (hacking_services).
# Every pattern is a multi-word phrase or an unambiguous specific term with
# \b word boundaries — never a bare word like "hack", "drug", or "gun" that
# would fire on innocuous text. A username or platform name is never part of
# the input to this classifier (see classify_activity below).
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    (
        "malware",
        [
            r"remote access trojan",
            r"\bransomware\b",
            r"\bkeylogger\b",
            r"\bbotnet\b",
            r"\bspyware\b",
            r"\btrojan (horse|payload|builder)\b",
            r"\bmalware (builder|kit|for sale)\b",
        ],
    ),
    (
        "hacking_services",
        [
            r"hacking service",
            r"hire a hacker",
            r"ddos service",
            r"ddos attack for hire",
            r"exploit for sale",
            r"0.?day exploit",
            r"selling hacking services",
            r"website hacking service",
        ],
    ),
    (
        "credential_data_theft",
        [
            r"stolen credentials?",
            r"stolen (login|logins|account|accounts)",
            r"compromised account",
            r"account checker",
            r"credit card dump",
            r"\bcvv fullz\b",
            r"\bfullz\b",
            r"\bcarding\b",
            r"\bcardable\b",
            r"do not require (the )?cvv",
        ],
    ),
    (
        "stolen_data",
        [
            r"leaked database",
            r"database leak",
            r"data breach for sale",
            r"leaked (data|dataset|records)",
        ],
    ),
    (
        "financial_fraud",
        [
            r"credit card fraud",
            r"bank fraud",
            r"wire fraud",
            r"fraudulent (transfer|transaction)",
        ],
    ),
    (
        "money_laundering",
        [
            r"money laundering",
            r"launder(ing)? (your |the )?(money|funds|btc|crypto|cryptocurrency)",
            r"cash out service",
        ],
    ),
    (
        "drug_trafficking",
        [
            r"\bcocaine\b",
            r"\bheroin\b",
            r"\bmethamphetamine\b",
            r"\bmdma\b",
            r"\bfentanyl\b",
            r"kilos? of (coke|cocaine|meth)",
        ],
    ),
    (
        "weapons_arms",
        [
            r"\bfirearms?\b",
            r"\bammunition\b",
            r"\bassault rifle\b",
            r"guns? for sale",
        ],
    ),
    (
        "other_cybercrime",
        [
            r"\bphishing (kit|page|service)\b",
            r"\bcard skimmer\b",
            r"\bsim swap(ping)?\b",
        ],
    ),
]

_COMPILED_RULES: list[tuple[str, list[re.Pattern]]] = [
    (category, [re.compile(p, re.IGNORECASE) for p in patterns])
    for category, patterns in CATEGORY_RULES
]


def _classify_by_source_category(source_category: str | None) -> ClassificationResult | None:
    if not source_category:
        return None
    category = SOURCE_CATEGORY_MAP.get(source_category.strip().lower())
    if category is None:
        return None
    return ClassificationResult(
        category=category,
        reason=f"Source-provided category: \"{source_category}\"",
        method="source_provided",
        confidence="high",
    )


def _classify_by_keywords(text: str) -> ClassificationResult | None:
    if not text:
        return None
    for category, patterns in _COMPILED_RULES:
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return ClassificationResult(
                    category=category,
                    reason=f"Matched phrase \"{match.group(0)}\" in activity text",
                    method="keyword_rule",
                    confidence="medium",
                )
    return None


def classify_activity(
    *, title: str | None, text: str, source_category: str | None
) -> ClassificationResult | None:
    """Returns None (unclassified) rather than a fabricated guess when
    neither path finds real evidence. source_category is checked first
    (strongest evidence); the keyword path searches title+text together so a
    signal in either field is caught, but never searches the username,
    platform name, or any other identifier field — see this module's
    docstring on why identifiers must never influence classification."""
    result = _classify_by_source_category(source_category)
    if result is not None:
        return result
    combined = f"{title or ''} {text}".strip()
    return _classify_by_keywords(combined)
