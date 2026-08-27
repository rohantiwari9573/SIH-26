"""Runs the real infra scanner against the real mock_leaky_service app, over an
actual TLS connection. Not a unit test with mocks — this exists because the
first version of scanner.py silently returned zero findings against a live
target (ssl.getpeercert() returns {} for unverified certs; httpx refused the
self-signed cert by default) and only manual testing against a running server
caught it. This test is what should have caught it, and stops it recurring.
"""
import datetime
import importlib.util
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.services.infra_scan.scanner import scan_target

MOCK_SERVICE_DIR = Path(__file__).resolve().parent.parent.parent / "mock_leaky_service"
LEAKED_COMMON_NAME = "mail.realcompany-demo.example"


def _load_mock_app():
    spec = importlib.util.spec_from_file_location("mock_leaky_app", MOCK_SERVICE_DIR / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


def _generate_test_cert(cert_path: Path, key_path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, LEAKED_COMMON_NAME)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(LEAKED_COMMON_NAME)]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


@pytest.fixture(scope="module")
def mock_target(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("mock_cert")
    cert_path, key_path = tmp_dir / "cert.pem", tmp_dir / "key.pem"
    _generate_test_cert(cert_path, key_path)

    port = 8543
    config = uvicorn.Config(
        _load_mock_app(),
        host="127.0.0.1",
        port=port,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
        server_header=False,
        log_level="error",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.1)
    else:
        pytest.fail("mock_leaky_service did not start in time")

    yield "127.0.0.1", port

    server.should_exit = True
    thread.join(timeout=5)


def test_ssl_leak_and_banner_detected_against_live_mock_target(mock_target):
    host, port = mock_target
    findings = scan_target("demo-onion-address.onion", clearnet_host=host, port=port)
    finding_types = {f.finding_type for f in findings}

    assert "ssl_leak" in finding_types, "SSL cert leak was not detected against a live target"
    assert "banner" in finding_types, "HTTP banner leak was not detected against a live target"

    ssl_finding = next(f for f in findings if f.finding_type == "ssl_leak")
    assert ssl_finding.detail["subject_cn"] == LEAKED_COMMON_NAME

    banner_finding = next(f for f in findings if f.finding_type == "banner")
    assert "Apache" in banner_finding.detail["server"]
    assert "uvicorn" not in banner_finding.detail["server"]
