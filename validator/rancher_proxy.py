"""Hotkey-authenticated read-only Rancher v3 proxy.

Served by the subnet-owner's validator (only when RANCHER_URL +
RANCHER_BEARER_TOKEN are set). Third-party validators authenticate with their
Bittensor hotkey sr25519 signature; the proxy injects the production Rancher
bearer token and forwards a tiny allowlist of GET requests upstream.

Strict endpoint allowlist (the only protection the proxy needs):
  GET /v3/clusters            -> RancherClient.list_clusters()
  GET /v3/nodes?clusterId=X  -> RancherClient.list_nodes(X)
  everything else            -> 403

Enforcement is at three layers:
  1. Path: exact match only (no sub-paths, no trailing slashes).
  2. Method: GET only (POST/PUT/DELETE/PATCH -> 403).
  3. Query: clusterId required for /v3/nodes; only limit/marker accepted
     on either path. Unknown query params are dropped before forwarding.
"""

from __future__ import annotations

import http.server
import json
import logging
import time
import urllib.parse

# Type-only imports — kept lazy so the module imports cleanly in test
# environments without the bittensor_core Rust binding. The actual classes
# are only used at server-startup time (passed in by validator.py:main).
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chain_state import ChainState
    from rancher_client import RancherClient


# Hotkey auth headers (set by the reader validator on every request).
_HK_HEADER = "BT-Validator-Hotkey"
_SIG_HEADER = "BT-Validator-Signature"
_TS_HEADER = "BT-Validator-Ts"

# Replay protection window (seconds).
_TS_WINDOW = 60

# Allowlist: (path, required_query, optional_query). Anything not in this
# table is rejected at the path layer before any upstream call.
_ALLOWLIST = {
    "/v3/clusters": (None, ("limit", "marker")),
    "/v3/nodes": ("clusterId", ("limit", "marker")),
}

# HTTP status for auth/allowlist failures (do not leak why).
_FORBIDDEN = 403
_BAD_GATEWAY = 502


def _json_response(handler, status: int, body: bytes) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _bad_gateway(handler, log: logging.Logger) -> None:
    log.warning("proxy 502: upstream error")
    _json_response(handler, _BAD_GATEWAY, b'{"error":"upstream"}')


def _short_hotkey(hotkey: str) -> str:
    """SS58 address truncated to first 4 + last 4 chars for log readability."""
    if not hotkey or len(hotkey) < 10:
        return hotkey or ""
    return f"{hotkey[:4]}…{hotkey[-4:]}"


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    """One request handler. Built per-request with a bound auth message."""

    # Silence the default stderr logging (we log via the injected logger).
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._reject_method("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._reject_method("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._reject_method("DELETE")

    def do_PATCH(self) -> None:  # noqa: N802
        self._reject_method("PATCH")

    def _reject_method(self, method: str) -> None:
        hotkey = self.headers.get(_HK_HEADER, "")
        hk = f" hotkey={_short_hotkey(hotkey)}" if hotkey else ""
        self.server.log.info("proxy 403: method %s not allowed%s", method, hk)
        _json_response(self, _FORBIDDEN, b'{"error":"forbidden"}')

    def _handle(self, method: str) -> None:
        srv = self.server
        if method != "GET":
            hotkey = self.headers.get(_HK_HEADER, "")
            hk = f" hotkey={_short_hotkey(hotkey)}" if hotkey else ""
            srv.log.info("proxy 403: method %s not allowed%s", method, hk)
            _json_response(self, _FORBIDDEN, b'{"error":"forbidden"}')
            return
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

        # Path allowlist (exact match).
        if path not in _ALLOWLIST:
            hotkey = self.headers.get(_HK_HEADER, "")
            hk = f" hotkey={_short_hotkey(hotkey)}" if hotkey else ""
            srv.log.info("proxy 403: path %s not allowlisted%s", path, hk)
            _json_response(self, _FORBIDDEN, b'{"error":"forbidden"}')
            return

        required, optional = _ALLOWLIST[path]

        # Query allowlist.
        clean_query: dict[str, str] = {}
        if required:
            values = query.get(required)
            if not values or not values[0].strip():
                hotkey = self.headers.get(_HK_HEADER, "")
                hk = f" hotkey={_short_hotkey(hotkey)}" if hotkey else ""
                srv.log.info(
                    "proxy 403: missing required query %s path=%s%s",
                    required,
                    path,
                    hk,
                )
                _json_response(self, _FORBIDDEN, b'{"error":"forbidden"}')
                return
            clean_query[required] = values[0]
        for key in optional:
            values = query.get(key)
            if values:
                clean_query[key] = values[0]
        # Reject unknown query params (do not forward upstream filters).
        unknown = (
            set(query) - {required} - set(optional)
            if required
            else set(query) - set(optional)
        )
        if unknown:
            hotkey = self.headers.get(_HK_HEADER, "")
            hk = f" hotkey={_short_hotkey(hotkey)}" if hotkey else ""
            srv.log.info(
                "proxy 403: unknown query %s path=%s%s",
                sorted(unknown),
                path,
                hk,
            )
            _json_response(self, _FORBIDDEN, b'{"error":"forbidden"}')
            return

        # Auth: verify hotkey signature over <path>\n<query>\n<ts>.
        hotkey = self.headers.get(_HK_HEADER, "")
        sig_hex = self.headers.get(_SIG_HEADER, "")
        ts_raw = self.headers.get(_TS_HEADER, "")
        auth_msg = (
            f"{path}\n{urllib.parse.urlencode(clean_query)}\n{ts_raw}"
        ).encode()
        if not _verify_hotkey_with_msg(
            srv.chain, srv.netuid, hotkey, sig_hex, ts_raw, auth_msg, srv.log
        ):
            srv.log.info(
                "proxy 403: hotkey auth failed hotkey=%s path=%s",
                _short_hotkey(hotkey),
                path,
            )
            _json_response(self, _FORBIDDEN, b'{"error":"forbidden"}')
            return

        # Log the authenticated query: who asked for what.
        query_str = urllib.parse.urlencode(clean_query) if clean_query else "-"
        srv.log.info(
            "proxy query: hotkey=%s path=%s query=%s",
            _short_hotkey(hotkey),
            path,
            query_str,
        )

        # Forward to upstream Rancher via the existing client.
        try:
            if path == "/v3/clusters":
                payload = srv.rancher.list_clusters()
            else:  # /v3/nodes
                payload = srv.rancher.list_nodes(clean_query["clusterId"])
        except Exception as exc:  # noqa: BLE001 - upstream errors -> 502
            srv.log.warning("proxy upstream error: %s", exc)
            _bad_gateway(self, srv.log)
            return
        body = json.dumps({"data": payload}).encode()
        _json_response(self, 200, body)
        srv.log.info(
            "proxy 200: hotkey=%s path=%s items=%d bytes=%d",
            _short_hotkey(hotkey),
            path,
            len(payload),
            len(body),
        )


def _verify_hotkey_with_msg(
    chain: ChainState,
    netuid: int,
    hotkey: str,
    signature_hex: str,
    ts_raw: str,
    auth_msg: bytes,
    log: logging.Logger,
) -> bool:
    """Verify a reader validator's sr25519 signature over the auth message."""
    if not hotkey or not signature_hex or not ts_raw:
        return False
    try:
        ts = int(ts_raw)
    except ValueError:
        return False
    now = int(time.time())
    if abs(now - ts) > _TS_WINDOW:
        return False
    try:
        miners = chain.metagraph(netuid)
    except Exception as exc:  # noqa: BLE001 - fail-closed on chain errors
        log.warning("proxy: metagraph read failed: %s", exc)
        return False
    # The hotkey must be registered AND have a validator permit (1,000+ TAO
    # stake, top 64 by stake weight). Miners without a validator permit are
    # rejected — the proxy is for validators only.
    miner = next((m for m in miners if m.hotkey == hotkey), None)
    if miner is None:
        return False
    if not miner.is_validator:
        log.info(
            "proxy 403: hotkey %s is not a validator (no validator_permit)",
            _short_hotkey(hotkey),
        )
        return False
    try:
        sig = bytes.fromhex(signature_hex.strip())
    except ValueError:
        return False
    return _verify_sr25519(auth_msg, sig, hotkey, log)


def _verify_sr25519(
    message: bytes, signature: bytes, ss58: str, log: logging.Logger
) -> bool:
    """Verify an sr25519 signature against an SS58 address.

    Uses bittensor_core (Rust binding) when available; tests monkeypatch
    this function directly to avoid the binding dependency.
    """
    try:
        import bittensor_core  # noqa: PLC0415 - intentional lazy import

        return bool(bittensor_core.verify(message, signature, ss58, 1))
    except Exception as exc:  # noqa: BLE001 - fail-closed on verify errors
        log.warning("proxy: verify failed: %s", exc)
        return False


class _ProxyServer(http.server.ThreadingHTTPServer):
    """HTTP server with injected chain/rancher/netuid/log."""

    def __init__(self, addr, handler, chain, rancher, netuid, log):
        super().__init__(addr, handler)
        self.chain = chain
        self.rancher = rancher
        self.netuid = netuid
        self.log = log


def start_proxy_server(
    port: int,
    chain: ChainState,
    rancher: RancherClient,
    netuid: int,
    log: logging.Logger,
) -> None:
    """Run the hotkey-authenticated Rancher proxy on the given port.

    Blocks the calling thread (run in a daemon thread). Returns only on error.
    """
    addr = ("0.0.0.0", port)
    server = _ProxyServer(addr, _ProxyHandler, chain, rancher, netuid, log)
    log.info(
        "rancher proxy listening on 0.0.0.0:%d (allowlist: %s)",
        port,
        sorted(_ALLOWLIST),
    )
    server.serve_forever()
