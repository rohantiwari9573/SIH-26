"""app.services.ai_stylometry — pure, DB-free, deterministic. No network
calls, no model download (TfidfVectorizer trains on the two input documents
at call time, nothing pretrained/downloaded)."""
from app.services.ai_stylometry import (
    BehavioralVector,
    InsufficientData,
    PairAnalysis,
    behavioral_similarity,
    compare_personas,
)

SAMPLE_A = (
    "Stock updated today, quality checked as always, escrow recommended "
    "for new buyers this week. Ships same day, no exceptions, no delays "
    "unless the announcement thread says otherwise clearly."
)
SAMPLE_B = (
    "Stock updated once again, quality checked like usual, escrow is "
    "recommended for every new buyer this week too. Ships the same day, "
    "no exceptions at all, no delays unless the thread says otherwise."
)
UNRELATED = (
    "Order confirmation sent, tracking not provided, thank you for your "
    "continued business with us this month and every month going forward. "
    "Feedback is always appreciated once the package safely arrives at "
    "its destination, please leave a review whenever you get the chance."
)
TOO_SHORT = "Order shipped today."


def test_similar_texts_score_high_on_character_and_word_signals():
    result = compare_personas(SAMPLE_A, SAMPLE_B, BehavioralVector(), BehavioralVector())
    assert isinstance(result, PairAnalysis)
    assert result.stylometric_similarity > 0.5
    char_signal = next(s for s in result.signals if s.name == "Character n-gram patterns")
    assert char_signal.bucket in ("High similarity", "Moderate similarity")


def test_dissimilar_texts_score_lower_than_similar_pair():
    similar = compare_personas(SAMPLE_A, SAMPLE_B, BehavioralVector(), BehavioralVector())
    dissimilar = compare_personas(SAMPLE_A, UNRELATED, BehavioralVector(), BehavioralVector())
    assert isinstance(similar, PairAnalysis)
    assert isinstance(dissimilar, PairAnalysis)
    assert similar.stylometric_similarity > dissimilar.stylometric_similarity


def test_identical_text_scores_maximum_similarity():
    result = compare_personas(SAMPLE_A, SAMPLE_A, BehavioralVector(), BehavioralVector())
    assert isinstance(result, PairAnalysis)
    assert result.stylometric_similarity > 0.999


def test_result_is_deterministic_across_repeated_calls():
    r1 = compare_personas(SAMPLE_A, SAMPLE_B, BehavioralVector(), BehavioralVector())
    r2 = compare_personas(SAMPLE_A, SAMPLE_B, BehavioralVector(), BehavioralVector())
    assert isinstance(r1, PairAnalysis) and isinstance(r2, PairAnalysis)
    assert r1.stylometric_similarity == r2.stylometric_similarity
    assert r1.behavioral_similarity == r2.behavioral_similarity


def test_short_sample_returns_insufficient_data_not_a_fabricated_score():
    result = compare_personas(TOO_SHORT, SAMPLE_B, BehavioralVector(), BehavioralVector())
    assert isinstance(result, InsufficientData)
    assert "Insufficient" in result.reason


def test_both_short_returns_insufficient_data():
    result = compare_personas(TOO_SHORT, TOO_SHORT, BehavioralVector(), BehavioralVector())
    assert isinstance(result, InsufficientData)


def test_behavioral_similarity_none_when_neither_side_has_classified_activity():
    assert behavioral_similarity(BehavioralVector(), BehavioralVector()) is None


def test_behavioral_similarity_real_zero_when_one_side_has_no_signal():
    a = BehavioralVector(category_counts={"drug_trafficking": 3})
    b = BehavioralVector()
    assert behavioral_similarity(a, b) == 0.0


def test_behavioral_similarity_high_for_matching_category_distribution():
    a = BehavioralVector(category_counts={"credential_data_theft": 4, "stolen_data": 1})
    b = BehavioralVector(category_counts={"credential_data_theft": 8, "stolen_data": 2})
    # Same proportions, different totals -- cosine similarity should be ~1.0
    # (direction, not magnitude), demonstrating it measures distribution
    # shape, not raw activity volume.
    assert behavioral_similarity(a, b) > 0.99


def test_behavioral_similarity_lower_for_different_category_distribution():
    a = BehavioralVector(category_counts={"credential_data_theft": 5})
    b = BehavioralVector(category_counts={"drug_trafficking": 5})
    assert behavioral_similarity(a, b) == 0.0


def test_compare_personas_includes_behavioral_signal_only_when_available():
    without = compare_personas(SAMPLE_A, SAMPLE_B, BehavioralVector(), BehavioralVector())
    assert isinstance(without, PairAnalysis)
    assert without.behavioral_similarity is None
    assert not any(s.name == "Activity behaviour" for s in without.signals)

    with_behavior = compare_personas(
        SAMPLE_A,
        SAMPLE_B,
        BehavioralVector(category_counts={"malware": 3}),
        BehavioralVector(category_counts={"malware": 5}),
    )
    assert isinstance(with_behavior, PairAnalysis)
    assert with_behavior.behavioral_similarity is not None
    assert any(s.name == "Activity behaviour" for s in with_behavior.signals)


def test_no_hardcoded_or_random_values_same_inputs_same_outputs_across_process_runs():
    """Guards against any accidental use of random.random()/uuid/time-based
    jitter sneaking into the scoring path."""
    results = [
        compare_personas(SAMPLE_A, SAMPLE_B, BehavioralVector(), BehavioralVector())
        for _ in range(5)
    ]
    scores = {r.stylometric_similarity for r in results if isinstance(r, PairAnalysis)}
    assert len(scores) == 1
