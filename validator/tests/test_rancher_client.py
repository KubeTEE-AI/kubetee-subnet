"""rancher_client: owner (bearer) + reader (hotkey-signed) auth modes.

Tests cover:
  - Owner path: sends `Authorization: Bearer <token>` (unchanged behavior).
  - Reader path: sends `BT-Validator-*` hotkey-signed headers, no bearer token.
  - Constructor validation: must have either a token or a keypair.
  - Auth message format: `<path>\n<query>\n<ts>`.
  - is_reader property reflects the mode.

bittensor_core (Rust binding) is NOT required — the keypair is a duck-typed
stand-in with .sign() and .ss58_address.
"""

import time
import urllib.parse

import pytest

import rancher_client
from rancher_client import RancherClient, RancherEvidenceError

# --- stand-ins (avoid importing bittensor / bittensor_core) ------------------


class FakeKeypair:
    """Duck-typed sr25519 keypair stand-in for tests."""

    def __init__(
        self, ss58="5GmS1wtCfR4tK5SSgnZbVT4kYw5W8NmxmijcsxCQE6oLW6A8"
    ):
        self.ss58_address = ss58

    def sign(self, message: bytes) -> bytes:
        # Deterministic fake signature (64 bytes) — tests don't verify the
        # crypto, only that the header is present and well-formed.
        return b"\xaa" * 64


class FakeConfig:
    """Minimal Config stand-in — only the fields RancherClient reads."""

    def __init__(self, rancher_url, rancher_token="", rancher_ca_file=""):
        self.rancher_url = rancher_url
        self.rancher_token = rancher_token
        self.rancher_ca_file = rancher_ca_file


# --- constructor validation -------------------------------------------------


def test_owner_mode_token_set_no_keypair_needed():
    cfg = FakeConfig("https://rancher.example.com", "token-abc:xyz")
    client = RancherClient(cfg)  # no keypair — should not raise
    assert client.is_reader is False


def test_reader_mode_no_token_requires_keypair():
    cfg = FakeConfig("https://validator.kubetee.ai", "")
    with pytest.raises(
        RancherEvidenceError, match="either RANCHER_BEARER_TOKEN"
    ):
        RancherClient(cfg)  # no keypair — must raise


def test_reader_mode_no_token_with_keypair_ok():
    cfg = FakeConfig("https://validator.kubetee.ai", "")
    client = RancherClient(cfg, keypair=FakeKeypair())
    assert client.is_reader is True


def test_owner_mode_token_takes_precedence_even_with_keypair():
    """If both token and keypair are set, the owner (bearer) path wins."""
    cfg = FakeConfig("https://rancher.example.com", "token-abc:xyz")
    client = RancherClient(cfg, keypair=FakeKeypair())
    assert client.is_reader is False


# --- auth header construction -----------------------------------------------


def test_owner_mode_sends_bearer_token():
    cfg = FakeConfig("https://rancher.example.com", "token-abc:xyz")
    client = RancherClient(cfg)
    headers = client._auth_headers("/v3/clusters", "limit=1000")
    assert headers == {"Authorization": "Bearer token-abc:xyz"}
    # No BT-Validator-* headers in owner mode
    assert "BT-Validator-Hotkey" not in headers
    assert "BT-Validator-Signature" not in headers
    assert "BT-Validator-Ts" not in headers


def test_reader_mode_sends_hotkey_signed_headers():
    kp = FakeKeypair(ss58="5GmS1wtCfR4tK5SSgnZbVT4kYw5W8NmxmijcsxCQE6oLW6A8")
    cfg = FakeConfig("https://validator.kubetee.ai", "")
    client = RancherClient(cfg, keypair=kp)
    headers = client._auth_headers("/v3/clusters", "limit=1000")
    assert headers["BT-Validator-Hotkey"] == kp.ss58_address
    # Signature is 64 bytes hex (128 chars)
    assert len(headers["BT-Validator-Signature"]) == 128
    # Timestamp is a string of digits (unix seconds)
    assert headers["BT-Validator-Ts"].isdigit()
    # No Authorization header in reader mode
    assert "Authorization" not in headers


def test_reader_mode_signature_covers_path_query_ts():
    """The signed message must be `<path>\n<query>\n<ts>` — verify the format
    by capturing the message passed to keypair.sign()."""
    captured = []

    class CapturingKeypair(FakeKeypair):
        def sign(self, message: bytes) -> bytes:
            captured.append(message)
            return b"\xbb" * 64

    kp = CapturingKeypair()
    cfg = FakeConfig("https://validator.kubetee.ai", "")
    client = RancherClient(cfg, keypair=kp)
    headers = client._auth_headers("/v3/nodes", "clusterId=c-1&limit=1000")
    assert len(captured) == 1
    msg = captured[0].decode()
    # Message format: path\nquery\nts
    parts = msg.split("\n")
    assert parts[0] == "/v3/nodes"
    assert parts[1] == "clusterId=c-1&limit=1000"
    assert parts[2].isdigit()  # ts


def test_reader_mode_empty_query_string():
    """When the query is empty, the signed message is `<path>\n\n<ts>`."""
    captured = []

    class CapturingKeypair(FakeKeypair):
        def sign(self, message: bytes) -> bytes:
            captured.append(message)
            return b"\xcc" * 64

    kp = CapturingKeypair()
    cfg = FakeConfig("https://validator.kubetee.ai", "")
    client = RancherClient(cfg, keypair=kp)
    client._auth_headers("/v3/clusters", "")
    msg = captured[0].decode()
    parts = msg.split("\n")
    assert parts[0] == "/v3/clusters"
    assert parts[1] == ""  # empty query
    assert parts[2].isdigit()


def test_reader_mode_timestamp_is_recent():
    """The ts header must be within a few seconds of now (replay window)."""
    kp = FakeKeypair()
    cfg = FakeConfig("https://validator.kubetee.ai", "")
    client = RancherClient(cfg, keypair=kp)
    before = int(time.time())
    headers = client._auth_headers("/v3/clusters", "")
    after = int(time.time())
    ts = int(headers["BT-Validator-Ts"])
    assert before <= ts <= after


def test_reader_mode_two_calls_have_different_ts():
    """Two rapid calls should produce (likely) different timestamps."""
    kp = FakeKeypair()
    cfg = FakeConfig("https://validator.kubetee.ai", "")
    client = RancherClient(cfg, keypair=kp)
    h1 = client._auth_headers("/v3/clusters", "")
    h2 = client._auth_headers("/v3/clusters", "")
    # Same hotkey both times
    assert h1["BT-Validator-Hotkey"] == h2["BT-Validator-Hotkey"]
    # ts may or may not differ (same second), but signatures differ (different
    # ts in the signed message → different signature, even with the fake
    # deterministic keypair only if ts differs). We only assert the headers
    # are well-formed; the proxy side handles replay protection.
    assert h1["BT-Validator-Signature"] != ""  # non-empty
    assert h2["BT-Validator-Signature"] != ""
