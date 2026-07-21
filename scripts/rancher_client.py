"""Contained Rancher v3 client for the KubeTEE basic validator (g004 V2).

Containment contract (spec AC4/AC5, pinned by tests/fixtures/rancher/contract.json):
- one fixed https origin derived from RANCHER_URL; nothing else is ever dialed
- redirects are refused, never followed (a 3xx is a transport error)
- endpoint allowlist: scoring GETs plus exactly one DELETE (/v3/clusters/{id})
- pagination is followed to exhaustion; anything incomplete, truncated, or
  unrecognized fails closed with IncompleteEnumeration
- the bearer token never appears in exceptions, repr, or logs; upstream
  error bodies are never reproduced in messages
- Cloudflare fronts staging: every request sends an explicit User-Agent
"""

from __future__ import annotations

import enum
import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

USER_AGENT = "kubetee-validator/0.1"
_KNOWN_PAGINATION_FIELDS = {"first", "next", "last", "limit", "total", "partial"}
_CLUSTER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class ErrorCategory(enum.Enum):
    TRANSPORT = "transport"
    AUTH = "auth"
    MALFORMED = "malformed"
    INCOMPLETE = "incomplete"


class RancherError(Exception):
    """Rancher request failure with a fixed-enum category and no secrets."""

    def __init__(self, category: ErrorCategory, message: str):
        super().__init__(message)
        self.category = category


class IncompleteEnumeration(RancherError):
    """A collection could not be proven complete; callers must fail closed."""

    def __init__(self, message: str):
        super().__init__(ErrorCategory.INCOMPLETE, message)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibTransport:
    """Default stdlib transport. Returns (status, body_text); never redirects."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(_NoRedirect)

    def request(self, method: str, url: str, headers: dict, timeout: float):
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            # Connection-level failures (DNS, refused, timeout) propagate as transport errors
            return 0, f"URLError: {exc.reason}"


class RancherClient:
    """Allowlisted, origin-pinned Rancher v3 API client."""

    def __init__(
        self,
        base_url: str,
        token: str,
        transport=None,
        timeout: float = 30.0,
        user_agent: str = USER_AGENT,
        max_pages: int = 1000,
    ) -> None:
        parts = urlsplit(base_url.strip())
        if parts.scheme != "https" or not parts.netloc:
            raise ValueError("RANCHER_URL must be a https origin")
        if not token or not token.strip():
            raise ValueError("Rancher token must be non-empty")
        self._origin = f"https://{parts.netloc}"
        self._token = token.strip()
        self._transport = transport if transport is not None else UrllibTransport()
        self._timeout = timeout
        self._user_agent = user_agent
        self._max_pages = max_pages

    def __repr__(self) -> str:  # never include the token
        return f"RancherClient(origin={self._origin!r})"

    __str__ = __repr__

    # -- public allowlisted surface -----------------------------------------

    def list_clusters(self) -> list[dict]:
        return self._collect(f"{self._origin}/v3/clusters?limit=-1")

    def list_nodes(self, cluster_id: str) -> list[dict]:
        cid = self._validate_id(cluster_id)
        return self._collect(f"{self._origin}/v3/nodes?clusterId={cid}&limit=-1")

    def get_cluster(self, cluster_id: str) -> dict:
        cid = self._validate_id(cluster_id)
        body = self._request("GET", f"{self._origin}/v3/clusters/{cid}")
        return self._parse_json(body)

    def delete_cluster(self, cluster_id: str) -> int:
        """The single allowlisted mutation (spec 4.2a). Returns HTTP status."""
        cid = self._validate_id(cluster_id)
        url = f"{self._origin}/v3/clusters/{cid}"
        status, _ = self._raw("DELETE", url)
        return status

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _validate_id(cluster_id: str) -> str:
        cid = (cluster_id or "").strip()
        if not _CLUSTER_ID.match(cid):
            raise ValueError("invalid cluster id")
        return cid

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "<redacted-token>")

    def _raw(self, method: str, url: str) -> tuple[int, str]:
        if not url.startswith(self._origin + "/"):
            raise IncompleteEnumeration(
                f"refusing non-origin URL host={urlsplit(url).netloc!r}"
            )
        headers = {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": self._user_agent,
            "Accept": "application/json",
        }
        try:
            status, body = self._transport.request(
                method, url, headers, self._timeout
            )
        except Exception as exc:  # transport failures wrap, token scrubbed
            raise RancherError(
                ErrorCategory.TRANSPORT,
                self._scrub(f"transport failure: {type(exc).__name__}: {exc}"),
            ) from None
        if status in (401, 403):
            raise RancherError(ErrorCategory.AUTH, f"HTTP {status} from Rancher")
        if 300 <= status < 400:
            raise RancherError(
                ErrorCategory.TRANSPORT, f"redirect HTTP {status} refused"
            )
        if method == "GET" and status != 200:
            raise RancherError(ErrorCategory.TRANSPORT, f"HTTP {status} from Rancher")
        return status, body

    def _request(self, method: str, url: str) -> str:
        _, body = self._raw(method, url)
        return body

    def _parse_json(self, body: str) -> dict:
        try:
            parsed = json.loads(body)
        except ValueError:
            raise RancherError(
                ErrorCategory.MALFORMED, "response body is not valid JSON"
            ) from None
        if not isinstance(parsed, dict):
            raise RancherError(ErrorCategory.MALFORMED, "unexpected JSON shape")
        return parsed

    def _collect(self, first_url: str) -> list[dict]:
        """Follow marker pagination to exhaustion, failing closed otherwise."""
        items: list[dict] = []
        url = first_url
        for _ in range(self._max_pages):
            doc = self._parse_json(self._request("GET", url))
            data = doc.get("data")
            pagination = doc.get("pagination")
            if not isinstance(data, list):
                raise RancherError(ErrorCategory.MALFORMED, "collection lacks data list")
            if not isinstance(pagination, dict):
                raise IncompleteEnumeration("collection lacks pagination metadata")
            unknown = set(pagination) - _KNOWN_PAGINATION_FIELDS
            if unknown:
                raise IncompleteEnumeration(
                    f"unrecognized pagination fields: {sorted(unknown)}"
                )
            items.extend(item for item in data if isinstance(item, dict))
            next_url = pagination.get("next")
            if next_url:
                if not isinstance(next_url, str) or not next_url.startswith(
                    self._origin + "/"
                ):
                    raise IncompleteEnumeration("pagination.next escapes the origin")
                url = next_url
                continue
            if pagination.get("partial") and len(items) < int(
                pagination.get("total", len(items))
            ):
                raise IncompleteEnumeration(
                    "partial page without a next link; enumeration unprovable"
                )
            return items
        raise IncompleteEnumeration(
            f"pagination did not terminate after {self._max_pages} pages"
        )
