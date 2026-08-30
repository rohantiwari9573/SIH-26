"""On-demand per-email breach lookup against Have I Been Pwned's v3 API
(distinct from scripts/ingest_hibp.py, which pulls the public breach
*directory* and needs no key). This endpoint requires a paid HIBP key —
Argus does not hold one, so this returns a clearly-marked NOT_CONFIGURED
result rather than fabricating exposure data for a submitted persona's
email. If HIBP_API_KEY is ever set, this starts working with no other
code changes needed.
"""
from dataclasses import dataclass

import httpx

from app.core.config import settings

BREACHED_ACCOUNT_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{email}"


@dataclass
class HibpLookupResult:
    configured: bool
    email: str
    breach_names: list[str] | None = None  # None means "not checked" (not configured, or error)
    error: str | None = None


def check_email_breaches(email: str) -> HibpLookupResult:
    if not settings.hibp_api_key:
        return HibpLookupResult(configured=False, email=email)

    try:
        resp = httpx.get(
            BREACHED_ACCOUNT_URL.format(email=email),
            headers={"hibp-api-key": settings.hibp_api_key, "User-Agent": "Argus-Research"},
            params={"truncateResponse": "true"},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        return HibpLookupResult(configured=True, email=email, error=str(exc))

    if resp.status_code == 404:
        return HibpLookupResult(configured=True, email=email, breach_names=[])
    if not resp.is_success:
        return HibpLookupResult(
            configured=True, email=email, error=f"HIBP returned {resp.status_code}"
        )

    breaches = resp.json()
    return HibpLookupResult(
        configured=True, email=email, breach_names=[b["Name"] for b in breaches]
    )
