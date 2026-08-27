from app.services.scoring import ConfidenceInputs, compute_confidence


def test_all_signals_present_yields_high_confidence():
    score = compute_confidence(
        ConfidenceInputs(stylometry_similarity=1.0, relationship_strength=1.0, infra_match=True)
    )
    assert score == 1.0


def test_no_signals_yields_zero_confidence():
    score = compute_confidence(ConfidenceInputs())
    assert score == 0.0


def test_infra_match_alone_contributes_its_weight():
    score = compute_confidence(ConfidenceInputs(infra_match=True))
    assert score == 0.15


def test_shared_identifier_alone_contributes_its_weight():
    score = compute_confidence(ConfidenceInputs(relationship_strength=1.0))
    assert score == 0.65


def test_score_is_clamped_between_zero_and_one():
    score = compute_confidence(
        ConfidenceInputs(stylometry_similarity=5.0, relationship_strength=5.0, infra_match=True)
    )
    assert score == 1.0
