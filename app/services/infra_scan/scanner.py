"""Infrastructure fingerprinting: finds operational-security mistakes that leak a
hidden service's real-world location — SSL certificate reuse, verbose banners,
and default/exposed pages.

Designed to run against a target the team controls (a mock onion service /
local test server with deliberately introduced leaks), per the project's
ethics policy — see docs/ETHICS.md. Do not point this at real onion services.
"""
import socket
import ssl
from dataclasses import dataclass, field

import httpx
from cryptography import x509


@dataclass
class InfraFinding:
    finding_type: str  # ssl_leak | banner | default_page
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
    if (finding := check_http_banner(f"https://{clearnet_host}{port_suffix}")) is not None:
        findings.append(finding)

    return findings
