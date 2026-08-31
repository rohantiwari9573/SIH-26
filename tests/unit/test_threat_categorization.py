"""app.services.threat_categorization — deterministic, conservative activity
classification. Covers the exact examples from the feature spec (a clear
match, an ambiguous non-match, and source-provided vs keyword-rule paths)."""
from app.services.threat_categorization import CATEGORY_LABELS, classify_activity


def test_stolen_credentials_maps_to_credential_data_theft():
    result = classify_activity(
        title="Fresh accounts", text="Offering stolen credentials, fully checked.",
        source_category=None,
    )
    assert result is not None
    assert result.category == "credential_data_theft"
    assert result.method == "keyword_rule"
    assert result.confidence == "medium"


def test_remote_access_trojan_maps_to_malware():
    result = classify_activity(
        title=None, text="Selling a custom remote access trojan, undetected.",
        source_category=None,
    )
    assert result is not None
    assert result.category == "malware"


def test_selling_hacking_services_maps_to_hacking_services():
    result = classify_activity(
        title=None, text="We are selling hacking services, contact for pricing.",
        source_category=None,
    )
    assert result is not None
    assert result.category == "hacking_services"


def test_money_laundering_service_maps_to_money_laundering():
    result = classify_activity(
        title=None, text="Professional money laundering service, BTC accepted.",
        source_category=None,
    )
    assert result is not None
    assert result.category == "money_laundering"


def test_ambiguous_text_is_not_classified():
    """The spec's own example: generic/ambiguous text must stay unclassified
    — never guessed at."""
    result = classify_activity(
        title=None, text="Looking for a developer to help with a small project.",
        source_category=None,
    )
    assert result is None


def test_generic_forum_chatter_is_not_classified():
    """A welcome message must not be classified just because it exists on a
    marketplace/forum platform — see module docstring."""
    result = classify_activity(
        title=None,
        text="Thank you for giving me the opportunity to be a part of this new marketplace!",
        source_category=None,
    )
    assert result is None


def test_username_or_platform_alone_never_influences_classification():
    """A username like 'ShadowX' must never itself cause a category — the
    classifier only ever receives title/text/source_category, never an
    identifier field, so this is really a signature-shape guarantee: calling
    with genuinely empty activity content must return None regardless of
    what the persona is named."""
    result = classify_activity(title=None, text="", source_category=None)
    assert result is None


def test_source_provided_category_wins_and_is_high_confidence():
    """DarkForums' real 'category': 'Leaks' field — the strongest evidence
    path, checked before any keyword heuristic."""
    result = classify_activity(
        title="Some totally unrelated title",
        text="unrelated body text with no keyword matches",
        source_category="Leaks",
    )
    assert result is not None
    assert result.category == "stolen_data"
    assert result.method == "source_provided"
    assert result.confidence == "high"
    assert "Leaks" in result.reason


def test_unrecognized_source_category_falls_through_to_keywords():
    result = classify_activity(
        title=None, text="stolen credentials for sale", source_category="General Discussion"
    )
    assert result is not None
    assert result.category == "credential_data_theft"
    assert result.method == "keyword_rule"


def test_every_rule_category_key_has_a_label():
    from app.services.threat_categorization import CATEGORY_RULES

    for category, _patterns in CATEGORY_RULES:
        assert category in CATEGORY_LABELS
