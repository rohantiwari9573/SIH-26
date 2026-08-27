from app.services.stylometry.classifier import match_candidates, similarity_score
from app.services.stylometry.features import extract_features

SAMPLE_A_1 = (
    "I think, honestly, that this product is not what it seems. "
    "You should really be careful, and I mean really careful, before you buy."
)
SAMPLE_A_2 = (
    "Honestly, I think you should be careful with this one. "
    "It is not what it seems, and I really mean that."
)
SAMPLE_B = (
    "Transaction completed. Shipment will arrive within 3-5 business days. "
    "Thank you for your purchase, please leave feedback."
)


def test_extract_features_returns_expected_keys():
    features = extract_features(SAMPLE_A_1)
    assert "avg_sentence_len" in features
    assert "type_token_ratio" in features
    assert any(k.startswith("fw_") for k in features)


def test_similarity_score_is_bounded():
    score = similarity_score(SAMPLE_A_1, SAMPLE_B)
    assert 0.0 <= score <= 1.0


def test_same_author_scores_higher_than_different_author():
    same_author_score = similarity_score(SAMPLE_A_1, SAMPLE_A_2)
    different_author_score = similarity_score(SAMPLE_A_1, SAMPLE_B)
    assert same_author_score > different_author_score


def test_match_candidates_filters_by_threshold():
    candidates = {"vendor_new_alias": SAMPLE_A_2, "unrelated_vendor": SAMPLE_B}
    matches = match_candidates(SAMPLE_A_1, candidates, threshold=0.7)
    assert len(matches) == 1
    assert matches[0][0] == "vendor_new_alias"
