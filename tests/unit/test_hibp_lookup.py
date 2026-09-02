"""app.services.hibp_lookup.check_email_breaches — regression coverage for
a real bug found in a full-codebase audit: the submitted email was spliced
directly into the request URL with no percent-encoding, so an address
containing a URL-meaningful character (#, ?, %, unencoded non-ASCII) would
produce a malformed or semantically wrong request instead of querying HIBP
for the literal address submitted.
"""
import httpx

import app.services.hibp_lookup as hibp_lookup


class _FakeResponse:
    def __init__(self, status_code: int, json_body=None):
        self.status_code = status_code
        self._json_body = json_body
        self.is_success = 200 <= status_code < 300

    def json(self):
        return self._json_body


def test_email_with_url_meaningful_characters_is_percent_encoded(monkeypatch):
    captured_url = {}

    def fake_get(url, headers, params, timeout):
        captured_url["url"] = url
        return _FakeResponse(404)

    monkeypatch.setattr(hibp_lookup.settings, "hibp_api_key", "fake-key")
    monkeypatch.setattr(httpx, "get", fake_get)

    result = hibp_lookup.check_email_breaches("weird+addr#tag@example.com")

    assert result.configured is True
    # The raw '#' and '+' must not appear un-encoded in the path — '#'
    # especially would otherwise truncate the URL at the fragment.
    assert "#" not in captured_url["url"]
    assert "weird" in captured_url["url"]
    assert "example.com" in captured_url["url"]


def test_normal_email_still_works(monkeypatch):
    captured_url = {}

    def fake_get(url, headers, params, timeout):
        captured_url["url"] = url
        return _FakeResponse(200, json_body=[{"Name": "ExampleBreach"}])

    monkeypatch.setattr(hibp_lookup.settings, "hibp_api_key", "fake-key")
    monkeypatch.setattr(httpx, "get", fake_get)

    result = hibp_lookup.check_email_breaches("plain@example.com")

    assert result.breach_names == ["ExampleBreach"]
    assert captured_url["url"].endswith("plain%40example.com")
