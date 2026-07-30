"""Contained, GET-only Rancher v3 client.

Reads only the two label-bearing collections scoring needs (clusters and
their nodes). Origin-pinned to the configured Rancher URL, an endpoint
allowlist, and fail-closed pagination. Any transport/HTTP/parse problem raises
RancherEvidenceError so the caller skips the whole cycle rather than blaming
miners.
"""

from __future__ import annotations

import json
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


def hotkey_of(cluster: dict) -> str:
    labels = cluster.get("labels") or {}
    return str(labels.get(_HOTKEY_LABEL) or labels.get(_HOTKEY_ALIAS) or "")


def is_banned(cluster: dict) -> bool:
    labels = cluster.get("labels") or {}
    return labels.get(_BAN_LABEL) == "true"


class RancherClient:
    def __init__(self, config: Config) -> None:
        self._base = config.rancher_url.rstrip("/")
        self._token = config.rancher_token
        self._ca_file = config.rancher_ca_file or None

    # -- transport ---------------------------------------------------------

    def _ssl_context(self):
        if not self._ca_file:
            return None
        import ssl

        return ssl.create_default_context(cafile=self._ca_file)

    def _get(self, path_and_query: str) -> dict:
        """GET a single Rancher v3 resource/collection (allowlisted origin)."""
        url = f"{self._base}{path_and_query}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                "User-Agent": _USER_AGENT,
            },
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
