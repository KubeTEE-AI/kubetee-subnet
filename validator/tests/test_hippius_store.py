"""hippius_store: SigV4 signing + bucket/key pinning + public-read ACL."""

import datetime
import hashlib

from hippius_store import (
    DEFAULT_BUCKET,
    DEFAULT_CARD_KEY,
    DEFAULT_PAYOUT_KEY,
    HippiusStore,
    _signature_key,
    object_url,
)


def test_bucket_and_keys_pinned():
    assert DEFAULT_BUCKET == "kubetee-validator"
    assert DEFAULT_PAYOUT_KEY == "payout.json"
    assert DEFAULT_CARD_KEY == "price-card.json"
    assert (
        object_url("payout.json")
        == "https://s3.hippius.com/kubetee-validator/payout.json"
    )


def test_signature_key_derivation():
    # RFC reference: AWS4 signing key derivdeterministic chain
    k1 = _signature_key("secret", "20260101", "auto", "s3")
    k2 = _signature_key("secret", "20260101", "auto", "s3")
    assert k1 == k2 and isinstance(k1, bytes) and len(k1) == 32
    assert k1 != _signature_key("other", "20260101", "auto", "s3")


def test_put_uses_sigv4_and_public_read(monkeypatch):
    sent = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b""

    def fake_urlopen(request, timeout=0, context=None):
        sent["headers"] = dict(request.headers)
        sent["data"] = request.data
        return _Resp()

    import hippius_store

    monkeypatch.setattr(hippius_store.urllib.request, "urlopen", fake_urlopen)

    store = HippiusStore("AK", "SK")
    store.put_json(DEFAULT_CARD_KEY, {"usd_per_gpu_hour": {"H100": 3.0}})

    headers = sent["headers"]
    assert headers.get("X-amz-acl") == "public-read"
    auth = headers.get("Authorization", "")
    assert auth.startswith("AWS4-HMAC-SHA256")
    assert "Credential=AK/" in auth
    assert "x-amz-acl" in auth.split("SignedHeaders=")[1].split(",")[0]
    body = sent["data"]
    # payload includes the signed content hash header
    assert (
        headers.get("X-amz-content-sha256") == hashlib.sha256(body).hexdigest()
    )
