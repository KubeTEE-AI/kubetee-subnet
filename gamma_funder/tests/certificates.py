"""Offline four-leaf mTLS material, issued once per pytest temp directory."""
from datetime import datetime, timedelta, timezone
import hashlib
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def issue_certificates(root, *, fourth_client=False, serial_offset=0):
    roles = ["gateway-server", "gateway-client", "worker-server"]
    if fourth_client:
        roles.append("worker-client")
    if not (root / "ca.crt").exists():
        def identity(role, usage=None, dns=None, ca=None, ca_key=None, serial=1):
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, role)])
            now = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)
            builder = (x509.CertificateBuilder().subject_name(subject)
                .issuer_name(ca.subject if ca is not None else subject)
                .public_key(key.public_key()).serial_number(serial + serial_offset)
                .not_valid_before(now).not_valid_after(now + timedelta(hours=1))
                .add_extension(x509.BasicConstraints(ca=ca is None, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=ca is not None,
                    key_cert_sign=ca is None, crl_sign=ca is None, content_commitment=False,
                    data_encipherment=False, key_agreement=False, encipher_only=False,
                    decipher_only=False), critical=True)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False))
            if ca is None:
                ca_key = key
            else:
                builder = builder.add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
                builder = builder.add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            if dns:
                builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(dns)]), critical=False)
            cert = builder.sign(ca_key, hashes.SHA256())
            (root / (role + ".crt")).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            (root / (role + ".key")).write_bytes(key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            return cert, key

        ca, ca_key = identity("ca")
        for role, usage, dns, serial in (
            ("gateway-server", ExtendedKeyUsageOID.SERVER_AUTH,
             "litellm-gateway-mtls.litellm.svc.cluster.local", 2),
            ("gateway-client", ExtendedKeyUsageOID.CLIENT_AUTH, None, 3),
            ("worker-server", ExtendedKeyUsageOID.SERVER_AUTH,
             "gamma-funder.kubetee-ops.svc.cluster.local", 4),
            ("worker-client", ExtendedKeyUsageOID.CLIENT_AUTH, None, 5),
        ):
            identity(role, usage, dns, ca, ca_key, serial)
    for name in ("projector.crt", "projector.pem"):
        (root / name).write_bytes((root / "ca.crt").read_bytes())
    (root / "worker.pem").write_bytes((root / "worker-server.crt").read_bytes())
    (root / "worker.key").write_bytes((root / "worker-server.key").read_bytes())
    return {role: (hashlib.sha256(peer.public_bytes(serialization.Encoding.DER)).hexdigest(),
                   peer.public_bytes(serialization.Encoding.DER))
            for role in roles
            for peer in [x509.load_pem_x509_certificate((root / (role + ".crt")).read_bytes())]}
