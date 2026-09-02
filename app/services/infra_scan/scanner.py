"""Infrastructure fingerprinting: finds operational-security mistakes that leak a
hidden service's real-world location — SSL certificate reuse, verbose banners,
exposed default/status pages, and clock-skew inconsistencies.

Maps directly to the four examples SIH PS-26151 names for this pillar:
  - exposed server-status pages       -> check_default_page
  - SSL certs linked to clearnet      -> check_ssl_certificate
  - default service banners           -> check_http_banner, check_default_page
  - descriptor inconsistencies        -> check_clock_skew (see its docstring
                                          for why clock skew is the honest,
                                          implementable reading of this one)

Designed to run against a target the team controls (a mock onion service /
local test server with deliberately introduced leaks), per the project's
ethics policy — see docs/ETHICS.md. Do not point this at real onion services.
"""
import email.utils
import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from cryptography import x509


@dataclass
class InfraFinding:
    finding_type: str  # ssl_leak | banner | default_page | clock_skew
    detail: dict = field(default_factory=dict)


def check_ssl_certificate(host: str, port: int = 443, timeout: float = 5.0) -> InfraFinding | None:
    """Flags certs whose CN/SAN reveals a real-world hostname distinct from the .onion address —
    a well-documented deanonymization vector (cert reuse across clearnet + hidden service).

    Deliberately connects with verify_mode=CERT_NONE (hidden-service certs are
    typically self-signed / unverifiable — that's the whole scenario), which
    means ssl.SSLSocket.getpeercert() returns an empty dict: Python only
    populates that structured form for *validated* certs. binary_form=True
    still returns the raw DER regardless of validation, so it's parsed with
    `cryptography` instead.
    """
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                der_cert = ssock.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError):
        return None

    if not der_cert:
        return None

    cert = x509.load_der_x509_certificate(der_cert)
    cn_attrs = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    common_name = cn_attrs[0].value if cn_attrs else None

    try:
        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        san = san_ext.value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        san = []

    return InfraFinding(
        finding_type="ssl_leak",
        detail={"subject_cn": common_name, "san": san},
    )


def check_http_banner(base_url: str, timeout: float = 5.0) -> InfraFinding | None:
    """Flags server headers / default pages that reveal software stack or hosting identity.

    verify=False is intentional: the target is an adversarial hidden service
    whose certificate is expected to be self-signed or otherwise untrusted —
    the whole point of this scan is to inspect a cert we'd never normally
    accept, not to make a "safe" verified connection.
    """
    try:
        response = httpx.get(base_url, timeout=timeout, follow_redirects=True, verify=False)
    except httpx.HTTPError:
        return None

    server_header = response.headers.get("server")
    powered_by = response.headers.get("x-powered-by")

    if not server_header and not powered_by:
        return None

    return InfraFinding(
        finding_type="banner",
        detail={
            "server": server_header,
            "x_powered_by": powered_by,
            "status": response.status_code,
        },
    )


# Signatures for well-known default-install/status pages left exposed
# instead of being replaced with real content or locked down — real,
# frequently-found misconfigurations, not hypothetical ones. Matched as a
# case-sensitive substring of the response body: cheap, and these are
# framework/distro-fixed strings (not something a real marketplace page
# would coincidentally contain), so false positives aren't a practical
# concern here.
_DEFAULT_PAGE_SIGNATURES = {
    "Apache2 Ubuntu Default Page": "apache_default_page",
    "Welcome to nginx": "nginx_default_page",
    "IIS Windows Server": "iis_default_page",
}
# mod_status's own banner text — present regardless of which vhost/app is
# behind it, so this is matched independently of the default-page table above.
_SERVER_STATUS_SIGNATURE = "Apache Server Status"

_STATUS_PATHS = ("/", "/server-status", "/server-info")


def check_default_page(base_url: str, timeout: float = 5.0) -> InfraFinding | None:
    """Flags a default distro/framework install page or an exposed
    mod_status-style status page — the PS's "exposed server-status pages"
    example, plus the closely-related "default service banners" leak of
    never replacing the stock install page with real content. Checks a
    short, fixed list of well-known paths rather than a general crawl: this
    is a targeted misconfiguration check, not a content scanner.
    """
    for path in _STATUS_PATHS:
        try:
            response = httpx.get(
                f"{base_url}{path}", timeout=timeout, follow_redirects=True, verify=False
            )
        except httpx.HTTPError:
            continue
        if response.status_code != 200:
            continue
        body = response.text

        if _SERVER_STATUS_SIGNATURE in body:
            return InfraFinding(
                finding_type="default_page",
                detail={"path": path, "signature": "server_status_exposed"},
            )
        for signature, label in _DEFAULT_PAGE_SIGNATURES.items():
            if signature in body:
                return InfraFinding(
                    finding_type="default_page",
                    detail={"path": path, "signature": label},
                )
    return None


# Real HTTP/TCP clock-skew fingerprinting (per-machine drift from true UTC,
# e.g. an unsynced or never-NTP'd server) has documented use in Tor
# deanonymization research as a way to correlate a hidden service's
# published descriptor timestamps against a candidate clearnet host's own
# clock — a *temporal* metadata inconsistency, in the same family as the
# PS's "descriptor inconsistencies" example, and the honestly-implementable
# reading of it here: parsing/verifying real onion-service descriptors
# requires being a client on the live Tor network (see docs/ETHICS.md — this
# project deliberately never does that), so this checks the same underlying
# signal (server-side clock drift) the way it's actually measurable against
# a controlled HTTP(S) target.
_CLOCK_SKEW_THRESHOLD_SECONDS = 300


def check_clock_skew(
    base_url: str, timeout: float = 5.0, threshold_seconds: int = _CLOCK_SKEW_THRESHOLD_SECONDS
) -> InfraFinding | None:
    """Flags a target whose HTTP `Date` response header disagrees with real
    UTC by more than `threshold_seconds` — a genuinely different, unsynced
    machine clock than whatever the hidden service's own published metadata
    would show, not measurement noise at this threshold."""
    try:
        response = httpx.get(base_url, timeout=timeout, follow_redirects=True, verify=False)
    except httpx.HTTPError:
        return None

    date_header = response.headers.get("date")
    if not date_header:
        return None

    try:
        server_time = email.utils.parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return None
    if server_time.tzinfo is None:
        server_time = server_time.replace(tzinfo=timezone.utc)

    skew_seconds = (server_time - datetime.now(timezone.utc)).total_seconds()
    if abs(skew_seconds) <= threshold_seconds:
        return None

    return InfraFinding(
        finding_type="clock_skew",
        detail={"server_date": date_header, "skew_seconds": round(skew_seconds)},
    )


def scan_target(
    onion_address: str, clearnet_host: str | None = None, port: int = 443
) -> list[InfraFinding]:
    """Runs all infra checks against a mirrored/mock host for the given onion address.

    In the demo, `clearnet_host` points at the team's own test server that mirrors
    (with deliberate leaks) what the onion service would look like.
    """
    findings: list[InfraFinding] = []
    if clearnet_host is None:
        return findings

    if (finding := check_ssl_certificate(clearnet_host, port=port)) is not None:
        findings.append(finding)
    port_suffix = "" if port == 443 else f":{port}"
    base_url = f"https://{clearnet_host}{port_suffix}"
    if (finding := check_http_banner(base_url)) is not None:
        findings.append(finding)
    if (finding := check_default_page(base_url)) is not None:
        findings.append(finding)
    if (finding := check_clock_skew(base_url)) is not None:
        findings.append(finding)

    return findings
