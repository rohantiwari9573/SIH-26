"""Combines signal from all three pillars into one actor confidence score.

Weights are a starting point, not a claim of statistical rigor — document this
plainly to judges. Relationship evidence (a shared wallet address or PGP key
fingerprint) gets the largest weight because it's close to a deterministic
match, not a soft heuristic: two personas literally reusing the same wallet
is about as strong as evidence gets in this domain. Stylometry is
corroborating, probabilistic evidence — useful especially when no shared
identifier exists at all, which is the harder and more common real case.
Infra leaks are rare but decisive when found, so they still carry real
weight despite firing less often than the other two.
"""
from dataclasses import dataclass

WEIGHTS = {
    "stylometry": 0.20,
    "relationship": 0.65,
    "infra": 0.15,
}


@dataclass
class ConfidenceInputs:
    stylometry_similarity: float = 0.0  # 0-1, from classifier.similarity_score
    relationship_strength: float = 0.0  # 0-1, e.g. shared wallet/PGP key = 1.0
    infra_match: bool = False  # True if a leak directly ties infra to this actor


def compute_confidence(inputs: ConfidenceInputs) -> float:
    infra_score = 1.0 if inputs.infra_match else 0.0
    score = (
        WEIGHTS["stylometry"] * inputs.stylometry_similarity
        + WEIGHTS["relationship"] * inputs.relationship_strength
        + WEIGHTS["infra"] * infra_score
    )
    return round(min(max(score, 0.0), 1.0), 4)
