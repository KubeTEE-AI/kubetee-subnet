"""rancher_proxy: strict allowlist + hotkey auth + upstream-error handling.

Tests cover the three enforcement layers (path / method / query), the hotkey
auth flow (good sig, bad sig, unknown hotkey, expired ts, missing headers),
and upstream-error mapping (5xx -> 502 with no body leakage).

bittensor_core (the Rust binding) is NOT required — we monkeypatch
`rancher_proxy._verify_sr25519` so the tests run anywhere.
"""

import io
import json
import logging
import time
import urllib.parse

import pytest

import rancher_proxy

# A known-good hotkey for the mock metagraph.
HOTKEY_A = "5GmS1wtCfR4tK5SSgnZbVT4kYw5W8NmxmijcsxCQE6oLW6A8"
NETUID = 90
LOG = logging.getLogger("test_proxy")


# Minimal stand-in for chain_state.Miner — only .hotkey is used by the proxy.
class Miner:
    def __init__(self, uid, hotkey, is_validator=True):
        self.uid = uid
        self.hotkey = hotkey
        self.is_validator = is_validator


class FakeChain:
    """ChainState stand-in whose metagraph() returns two known hotkeys."""

    def metagraph(self, netuid):
        return [
            Miner(uid=0, hotkey=HOTKEY_A, is_validator=True),
            Miner(uid=1, hotkey="5Other", is_validator=True),
        ]


class FakeRancher:
    """RancherClient stand-in returning deterministic payloads."""

    def list_clusters(self):
        return [{"id": "c-1", "name": "alpha"}]

    def list_nodes(self, cluster_id):
        return [{"id": "n-1", "clusterId": cluster_id}]


class BrokenRancher:
    """RancherClient stand-in that always raises (upstream error)."""

    def list_clusters(self):
        raise RuntimeError("upstream timeout")

    def list_nodes(self, cluster_id):
        raise RuntimeError("upstream timeout")


class FakeServer:
    """Stands in for _ProxyServer — holds the injected chain/rancher/log."""

    def __init__(self, chain, rancher, netuid=NETUID, log=LOG):
        self.chain = chain
        self.rancher = rancher
        self.netuid = netuid
        self.log = log


def _build_handler(method, path, headers=None, server=None):
    """Build a real _ProxyHandler with a mocked socket + server.

    Returns (handler, status, body, sent_headers) — status/body/headers are
    populated as the handler writes its response.
    """
    status = [None]
    sent_headers = {}
    body_chunks = []

    # _ProxyHandler is a BaseHTTPRequestHandler; we construct it without
    # running the request loop, then call the do_<METHOD> directly.
    handler = rancher_proxy._ProxyHandler.__new__(rancher_proxy._ProxyHandler)

    # Patch the I/O methods the handler calls.
    def send_response(code, _msg=None):
        status[0] = code

    def send_header(k, v):
        sent_headers[k] = v

    def end_headers():
        pass

    class Wfile:
        def write(self, b):
            body_chunks.append(b)

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers
    handler.wfile = Wfile()
    handler.log_message = lambda *a, **kw: None
    handler.command = method
    handler.path = path
    # Case-insensitive header lookup (BaseHTTPRequestHandler uses email.Message)
    hdrs = {k.lower(): v for k, v in (headers or {}).items()}
    handler.headers = type(
        "HD", (), {"get": lambda self, k, d="": hdrs.get(k.lower(), d)}
    )()
    handler.server = server or FakeServer(FakeChain(), FakeRancher())
    return handler, status, body_chunks, sent_headers


def _auth_headers(path, hotkey=HOTKEY_A, ts=None):
    """Build the three BT-Validator-* headers with a deterministic ts."""
    ts = ts if ts is not None else int(time.time())
    return {
        "BT-Validator-Hotkey": hotkey,
        "BT-Validator-Signature": "aa" * 64,
        "BT-Validator-Ts": str(ts),
    }


# --- allowlist tests (the protection) ---------------------------------------


@pytest.fixture(autouse=True)
def _bypass_sig(monkeypatch):
    """Default: bypass sr25519 verification (allowlist tests don't need it)."""
    monkeypatch.setattr(
        rancher_proxy,
        "_verify_sr25519",
        lambda message, signature, ss58, log: True,
    )


def test_get_clusters_allowed():
    h, status, body, hdrs = _build_handler(
        "GET",
        "/v3/clusters",
        _auth_headers("/v3/clusters"),
    )
    rancher_proxy._ProxyHandler.do_GET(h)
    assert status[0] == 200
    parsed = json.loads(b"".join(body))
    assert parsed["data"] == [{"id": "c-1", "name": "alpha"}]


def test_get_nodes_with_clusterid_allowed():
    h, status, body, hdrs = _build_handler(
        "GET",
        "/v3/nodes?clusterId=c-1",
        _auth_headers("/v3/nodes?clusterId=c-1"),
    )
    rancher_proxy._ProxyHandler.do_GET(h)
    assert status[0] == 200
    parsed = json.loads(b"".join(body))
    assert parsed["data"] == [{"id": "n-1", "clusterId": "c-1"}]


def test_trailing_slash_rejected():
    h, status, _, _ = _build_handler(
        "GET",
        "/v3/clusters/",
        _auth_headers("/v3/clusters/"),
    )
    rancher_proxy._ProxyHandler.do_GET(h)
    assert status[0] == 403


def test_subpath_rejected():
    h, status, _, _ = _build_handler(
        "GET",
        "/v3/clusters/c-1",
        _auth_headers("/v3/clusters/c-1"),
    )
    rancher_proxy._ProxyHandler.do_GET(h)
    assert status[0] == 403


def test_nodes_without_clusterid_rejected():
    h, status, _, _ = _build_handler(
        "GET",
        "/v3/nodes",
        _auth_headers("/v3/nodes"),
    )
    rancher_proxy._ProxyHandler.do_GET(h)
    assert status[0] == 403


@pytest.mark.parametrize(
    "path",
    [
        "/v3/secrets",
        "/v3/users",
        "/v3/projects",
        "/v3/clusterrolebindings",
        "/v3/tokens",
        "/v3/settings",
        "/v3/authx",
    ],
)
def test_sensitive_endpoints_rejected(path):
    h, status, _, _ = _build_handler("GET", path, _auth_headers(path))
    rancher_proxy._ProxyHandler.do_GET(h)
    assert status[0] == 403, f"{path} should be 403"


def test_unknown_query_param_rejected():
    h, status, _, _ = _build_handler(
        "GET",
        "/v3/clusters?labelSelector=foo",
        _auth_headers("/v3/clusters?labelSelector=foo"),
    )
    rancher_proxy._ProxyHandler.do_GET(h)
    assert status[0] == 403


def test_content_type_is_json():
    h, status, body, hdrs = _build_handler(
        "GET",
        "/v3/clusters",
        _auth_headers("/v3/clusters"),
    )
    rancher_proxy._ProxyHandler.do_GET(h)
    assert status[0] == 200
    assert hdrs.get("Content-Type") == "application/json"


# --- method tests (structurally read-only) -----------------------------------


def test_post_rejected():
    h, status, _, _ = _build_handler(
        "POST", "/v3/clusters", _auth_headers("/v3/clusters")
    )
    rancher_proxy._ProxyHandler.do_POST(h)
    assert status[0] == 403


def test_put_rejected():
    h, status, _, _ = _build_handler(
        "PUT", "/v3/clusters/c-1", _auth_headers("/v3/clusters/c-1")
    )
    rancher_proxy._ProxyHandler.do_PUT(h)
    assert status[0] == 403


def test_delete_rejected():
    h, status, _, _ = _build_handler(
        "DELETE", "/v3/nodes/n-1", _auth_headers("/v3/nodes/n-1")
    )
    rancher_proxy._ProxyHandler.do_DELETE(h)
    assert status[0] == 403


def test_patch_rejected():
    h, status, _, _ = _build_handler(
        "PATCH", "/v3/clusters", _auth_headers("/v3/clusters")
    )
    rancher_proxy._ProxyHandler.do_PATCH(h)
    assert status[0] == 403


# --- auth tests (verify_hotkey_with_msg directly) ----------------------------


def test_good_hotkey_signature_passes_auth():
    ts = int(time.time())
    msg = f"/v3/clusters\n{ts}".encode()
    ok = rancher_proxy._verify_hotkey_with_msg(
        FakeChain(), NETUID, HOTKEY_A, "aa" * 64, str(ts), msg, LOG
    )
    assert ok is True


def test_bad_signature_rejected(monkeypatch):
    monkeypatch.setattr(
        rancher_proxy,
        "_verify_sr25519",
        lambda message, signature, ss58, log: False,
    )
    ts = int(time.time())
    msg = f"/v3/clusters\n{ts}".encode()
    ok = rancher_proxy._verify_hotkey_with_msg(
        FakeChain(), NETUID, HOTKEY_A, "bb" * 64, str(ts), msg, LOG
    )
    assert ok is False


def test_unknown_hotkey_rejected():
    ts = int(time.time())
    msg = f"/v3/clusters\n{ts}".encode()
    ok = rancher_proxy._verify_hotkey_with_msg(
        FakeChain(),
        NETUID,
        "5UnknownHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH",
        "aa" * 64,
        str(ts),
        msg,
        LOG,
    )
    assert ok is False


def test_miner_without_validator_permit_rejected():
    """A registered miner (is_validator=False) must NOT access the proxy."""

    class MinerOnlyChain:
        def metagraph(self, netuid):
            return [
                Miner(uid=0, hotkey=HOTKEY_A, is_validator=False),
                Miner(uid=1, hotkey="5Other", is_validator=True),
            ]

    ts = int(time.time())
    msg = f"/v3/clusters\n\n{ts}".encode()
    ok = rancher_proxy._verify_hotkey_with_msg(
        MinerOnlyChain(),
        NETUID,
        HOTKEY_A,  # registered but is_validator=False
        "aa" * 64,
        str(ts),
        msg,
        LOG,
    )
    assert ok is False


def test_validator_with_permit_accepted():
    """A registered validator (is_validator=True) MUST pass the check."""
    ts = int(time.time())
    msg = f"/v3/clusters\n\n{ts}".encode()
    ok = rancher_proxy._verify_hotkey_with_msg(
        FakeChain(),  # HOTKEY_A is_validator=True
        NETUID,
        HOTKEY_A,
        "aa" * 64,
        str(ts),
        msg,
        LOG,
    )
    assert ok is True


def test_expired_timestamp_rejected():
    ts = int(time.time()) - 120
    msg = f"/v3/clusters\n{ts}".encode()
    ok = rancher_proxy._verify_hotkey_with_msg(
        FakeChain(), NETUID, HOTKEY_A, "aa" * 64, str(ts), msg, LOG
    )
    assert ok is False


def test_future_timestamp_rejected():
    ts = int(time.time()) + 120
    msg = f"/v3/clusters\n{ts}".encode()
    ok = rancher_proxy._verify_hotkey_with_msg(
        FakeChain(), NETUID, HOTKEY_A, "aa" * 64, str(ts), msg, LOG
    )
    assert ok is False


def test_missing_headers_rejected():
    msg = b"/v3/clusters\n"
    assert (
        rancher_proxy._verify_hotkey_with_msg(
            FakeChain(), NETUID, "", "aa" * 64, str(int(time.time())), msg, LOG
        )
        is False
    )
    assert (
        rancher_proxy._verify_hotkey_with_msg(
            FakeChain(), NETUID, HOTKEY_A, "", str(int(time.time())), msg, LOG
        )
        is False
    )
    assert (
        rancher_proxy._verify_hotkey_with_msg(
            FakeChain(), NETUID, HOTKEY_A, "aa" * 64, "", msg, LOG
        )
        is False
    )


def test_bad_ts_value_rejected():
    msg = b"/v3/clusters\n"
    assert (
        rancher_proxy._verify_hotkey_with_msg(
            FakeChain(), NETUID, HOTKEY_A, "aa" * 64, "not-a-number", msg, LOG
        )
        is False
    )


def test_bad_signature_hex_rejected():
    ts = int(time.time())
    msg = f"/v3/clusters\n{ts}".encode()
    assert (
        rancher_proxy._verify_hotkey_with_msg(
            FakeChain(), NETUID, HOTKEY_A, "nothex", str(ts), msg, LOG
        )
        is False
    )


def test_metagraph_failure_fail_closed(monkeypatch):
    """A chain read error must fail-closed (reject), not crash the proxy."""

    class BrokenChain:
        def metagraph(self, netuid):
            raise RuntimeError("rpc timeout")

    ts = int(time.time())
    msg = f"/v3/clusters\n{ts}".encode()
    ok = rancher_proxy._verify_hotkey_with_msg(
        BrokenChain(), NETUID, HOTKEY_A, "aa" * 64, str(ts), msg, LOG
    )
    assert ok is False


# --- upstream-error tests ----------------------------------------------------


def test_upstream_error_returns_502_no_leakage():
    h, status, body, hdrs = _build_handler(
        "GET",
        "/v3/clusters",
        _auth_headers("/v3/clusters"),
        server=FakeServer(FakeChain(), BrokenRancher()),
    )
    rancher_proxy._ProxyHandler.do_GET(h)
    assert status[0] == 502
    body_bytes = b"".join(body)
    assert b"upstream" in body_bytes
    # No upstream error message leakage
    assert b"timeout" not in body_bytes


# --- allowlist table sanity --------------------------------------------------


def test_allowlist_only_two_endpoints():
    """The proxy must only allowlist exactly two endpoints."""
    assert set(rancher_proxy._ALLOWLIST.keys()) == {
        "/v3/clusters",
        "/v3/nodes",
    }
