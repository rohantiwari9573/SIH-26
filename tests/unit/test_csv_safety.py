"""CSV/formula injection (OWASP): POST /api/leads lets an authenticated user
submit free-text values (wallet, pgp_key, onion_address, username) that flow
straight into the CSV export. A value starting with =, +, -, or @ is
interpreted as a formula by Excel/Sheets when the exported file is opened,
not as literal text — _csv_safe neutralizes that with a leading apostrophe.
"""
from app.api.routes.export import _csv_safe


def test_plain_values_pass_through_unchanged():
    assert _csv_safe("shadow_vendor") == "shadow_vendor"
    assert _csv_safe("mock_marketplace_1") == "mock_marketplace_1"


def test_formula_trigger_prefixes_are_neutralized():
    assert _csv_safe("=cmd|'/c calc'!A1") == "'=cmd|'/c calc'!A1"
    assert _csv_safe("+1234567890") == "'+1234567890"
    assert _csv_safe("-1+1") == "'-1+1"
    assert _csv_safe("@SUM(A1:A10)") == "'@SUM(A1:A10)"


def test_wallet_address_that_happens_to_start_with_dash_is_safe():
    # A real-looking value, not an obviously malicious one — this is the
    # realistic case: a wallet/address string that happens to start with a
    # trigger character, submitted in good faith through POST /api/leads.
    assert _csv_safe("-1DemoWallet0000").startswith("'")


def test_empty_and_none_values_do_not_crash():
    assert _csv_safe("") == ""
    assert _csv_safe(None) == "None"


def test_non_string_values_are_stringified_and_checked():
    assert _csv_safe({"note": "fine"}) == "{'note': 'fine'}"
