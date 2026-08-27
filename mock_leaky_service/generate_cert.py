"""Generates a self-signed TLS cert for the mock leaky target.

The CN/SAN deliberately names a plausible clearnet hostname
(mail.realcompany-demo.example) instead of anything onion-related — this is
the exact operational-security mistake documented in real Tor deanonymization
research (see docs/ETHICS.md + README): reusing/generating a certificate that
reveals a real-world hostname is how researchers have tied hidden services
back to their clearnet infrastructure. Entirely synthetic; the hostname is a
.example domain, not a real one.
"""
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

LEAKED_HOSTNAME = "mail.realcompany-demo.example"


def main() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, LEAKED_HOSTNAME)]
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(LEAKED_HOSTNAME)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    with open("key.pem", "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    with open("cert.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Generated cert.pem/key.pem with CN={LEAKED_HOSTNAME}")


if __name__ == "__main__":
    main()
