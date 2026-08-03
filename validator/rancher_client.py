"""Contained, GET-only Rancher v3 client.

Reads only the two label-bearing collections scoring needs (clusters and
their nodes). Origin-pinned to the configured Rancher URL, an endpoint
allowlist, and fail-closed pagination. Any transport/HTTP/parse problem raises
RancherEvidenceError so the caller skips the whole cycle rather than blaming
miners.

Two auth modes:
  - Owner path (RANCHER_BEARER_TOKEN set): sends `Authorization: Bearer <token>`
    directly to staging-rancher.kubetee.ai. The token is scoped to GET-only
    on clusters + nodes.
  - Reader path (RANCHER_BEARER_TOKEN empty): signs each request with the
    validator hotkey (sr25519) and sends `BT-Validator-*` headers to the
    subnet-owner's proxy at validator.kubetee.ai. The proxy verifies the
    hotkey against the live metagraph and injects the bearer token upstream.
    The reader never sees the bearer token.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from config import Config


class RancherEvidenceError(RuntimeError):
    """Rancher evidence could not be obtained; skip the cycle."""


_HOTKEY_LABEL = "kubetee.ai/hotkey"
_HOTKEY_ALIAS = "kubetee.ai/miner-hotkey"
_BAN_LABEL = "kubetee.ai/ban"

_USER_AGENT = "kubetee-validator/0.1"

# Reader-mode auth headers (mirror the proxy's expected header names).
_HK_HEADER = "BT-Validator-Hotkey"
_SIG_HEADER = "BT-Validator-Signature"
_TS_HEADER = "BT-Validator-Ts"


def hotkey_of(cluster: dict) -> str:
    labels = cluster.get("labels") or {}
    return str(labels.get(_HOTKEY_LABEL) or labels.get(_HOTKEY_ALIAS) or "")


def is_banned(cluster: dict) -> bool:
    labels = cluster.get("labels") or {}
    return labels.get(_BAN_LABEL) == "true"


class RancherClient:
    def __init__(self, config: Config, keypair=None) -> None:
        """Construct the client.

        Args:
            config: validator config (rancher_url, rancher_token, rancher_ca_file).
            keypair: sr25519 Keypair for the reader (proxy) path. Required only
                when rancher_token is empty — the reader signs each request
                with this keypair. The owner path (token set) ignores it.
        """
        self._base = config.rancher_url.rstrip("/")
        self._token = config.rancher_token
        self._ca_file = config.rancher_ca_file or None
        self._keypair = keypair
        if not self._token and keypair is None:
            raise RancherEvidenceError(
                "RancherClient needs either RANCHER_BEARER_TOKEN (owner "
                "path) or a hotkey keypair (reader/proxy path); got neither."
            )

    @property
    def is_reader(self) -> bool:
        """True if this client uses the proxy (hotkey-signed) path."""
        return not self._token

    # -- transport ---------------------------------------------------------

    def _ssl_context(self):
        if not self._ca_file:
            return None
        import ssl

        return ssl.create_default_context(cafile=self._ca_file)

    def _auth_headers(self, path: str, query: str) -> dict[str, str]:
        """Build the auth headers for one request.

        Owner path: `Authorization: Bearer <token>`.
        Reader path: `BT-Validator-*` hotkey-signed headers (signed over
        `<path>\n<query>\n<ts>` with the validator's sr25519 keypair).
        """
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        # Reader/proxy path — sign with the hotkey.
        ts = str(int(time.time()))
        message = f"{path}\n{query}\n{ts}".encode()
        signature = bytes(self._keypair.sign(message)).hex()
        return {
            _HK_HEADER: self._keypair.ss58_address,
            _SIG_HEADER: signature,
            _TS_HEADER: ts,
        }

    def _get(self, path_and_query: str) -> dict:
        """GET a single Rancher v3 resource/collection (allowlisted origin)."""
        # Split path and query for the reader-mode auth message.
        parsed = urllib.parse.urlsplit(path_and_query)
        path = parsed.path
        query = parsed.query
        url = f"{self._base}{path_and_query}"
        headers = {
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }
        headers.update(self._auth_headers(path, query))
        request = urllib.request.Request(
            url,
            headers=headers,
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                request, context=self._ssl_context(), timeout=30
            ) as response:
                body = response.read()
        except urllib.error.URLError as exc:
            raise RancherEvidenceError(
                f"rancher GET {path_and_query}: {exc}"
            ) from exc
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RancherEvidenceError(
                f"rancher GET {path_and_query}: invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise RancherEvidenceError(
                f"rancher GET {path_and_query}: unexpected payload"
            )
        return payload

    def _get_all_pages(
        self, path: str, params: dict[str, str] | None = None
    ) -> list[dict]:
        """Fetch every page of a collection, fail-closed on pagination errors."""
        params = dict(params or {})
        params.setdefault("limit", "1000")
        marker: str | None = None
        items: list[dict] = []
        while True:
            page_params = dict(params)
            if marker:
                page_params["marker"] = marker
            query = urllib.parse.urlencode(page_params)
            payload = self._get(f"{path}?{query}")
            data = payload.get("data")
            if not isinstance(data, list):
                raise RancherEvidenceError(f"rancher GET {path}: no data list")
            items.extend(x for x in data if isinstance(x, dict))
            pagination = payload.get("pagination") or {}
            marker = pagination.get("marker") or None
            if not marker:
                return items

    # -- collections -------------------------------------------------------

    def list_clusters(self) -> list[dict]:
        """All Rancher clusters (management.cattle.io v3 /clusters)."""
        return self._get_all_pages("/v3/clusters")

    def list_nodes(self, cluster_id: str) -> list[dict]:
        """Nodes of one cluster (management.cattle.io v3 /nodes?clusterId=)."""
        return self._get_all_pages("/v3/nodes", {"clusterId": cluster_id})

    def cluster_id(self, cluster: dict) -> str:
        return str(cluster.get("id") or cluster.get("name") or "")
