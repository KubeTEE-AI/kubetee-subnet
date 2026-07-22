"""Contained Rancher v3 client for the KubeTEE basic validator (g004 V2).

Containment contract (spec AC4/AC5, pinned by tests/fixtures/rancher/contract.json):
- one credential-free https origin derived from RANCHER_URL; nothing else is
  ever dialed; an optional custom CA is scoped to this transport
- redirects are refused, never followed (a 3xx is a transport error)
- endpoint allowlist: scoring GETs plus exactly one DELETE (/v3/clusters/{id})
- response bytes, pages, and unique collection items are bounded; pagination
  must preserve origin/resource/filters and prove an exact stable total
- the bearer token never appears in exceptions, repr, or logs; upstream
  error bodies are never reproduced in messages
- Cloudflare fronts staging: every request sends an explicit User-Agent
"""

from __future__ import annotations

import enum
import json
import re
import ssl
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

USER_AGENT = "kubetee-validator/0.1"
DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_COLLECTION_ITEMS = 100_000
_KNOWN_PAGINATION_FIELDS = {"first", "next", "last", "limit", "total", "partial"}
_PAGINATION_QUERY_FIELDS = {"limit", "marker", "page"}
_CLUSTER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def normalize_https_origin(value: str) -> str:
    """Validate and normalize a credential-free HTTPS origin."""
    if not isinstance(value, str):
        raise ValueError("RANCHER_URL must be a https origin")
    try:
        parts = urlsplit(value.strip())
        _ = parts.port  # force validation of malformed/out-of-range ports
    except ValueError:
        raise ValueError("RANCHER_URL must be a https origin") from None
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or re.search(r"\s", parts.netloc)
    ):
        raise ValueError("RANCHER_URL must be a https origin")
    return f"https://{parts.netloc}"


def validate_cluster_id(value: object) -> str:
    """Return a canonical allowlisted Rancher cluster ID or raise."""
    if not isinstance(value, str) or not _CLUSTER_ID.fullmatch(value):
        raise ValueError("invalid cluster id")
    return value


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


class _ResponseTooLarge(Exception):
    pass


class UrllibTransport:
    """Default stdlib transport. Returns (status, body_text); never redirects."""

    def __init__(
        self,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        ca_file: str | None = None,
    ) -> None:
        if ca_file is not None and (
            not isinstance(ca_file, str) or not ca_file.strip()
        ):
            raise ValueError("RANCHER_CA_FILE must be a non-empty path")
        try:
            context = ssl.create_default_context(cafile=ca_file)
        except (OSError, ssl.SSLError, ValueError):
            raise ValueError("RANCHER_CA_FILE could not be loaded") from None
        self._opener = urllib.request.build_opener(
            _NoRedirect(),
            urllib.request.HTTPSHandler(context=context),
        )
        self._max_response_bytes = max_response_bytes

    def request(self, method: str, url: str, headers: dict, timeout: float):
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                content_length = resp.headers.get("Content-Length")
                if (
                    content_length is not None
                    and content_length.isdigit()
                    and int(content_length) > self._max_response_bytes
                ):
                    raise _ResponseTooLarge("Rancher response exceeds byte limit")
                body = resp.read(self._max_response_bytes + 1)
                if len(body) > self._max_response_bytes:
                    raise _ResponseTooLarge("Rancher response exceeds byte limit")
                return resp.status, body.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            return exc.code, ""
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
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_collection_items: int = DEFAULT_MAX_COLLECTION_ITEMS,
        ca_file: str | None = None,
    ) -> None:
        origin = normalize_https_origin(base_url)
        if not token or not token.strip():
            raise ValueError("Rancher token must be non-empty")
        for name, value in (
            ("max_pages", max_pages),
            ("max_response_bytes", max_response_bytes),
            ("max_collection_items", max_collection_items),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        self._origin = origin
        self._token = token.strip()
        self._transport = (
            transport
            if transport is not None
            else UrllibTransport(
                max_response_bytes=max_response_bytes,
                ca_file=ca_file,
            )
        )
        self._timeout = timeout
        self._user_agent = user_agent
        self._max_pages = max_pages
        self._max_response_bytes = max_response_bytes
        self._max_collection_items = max_collection_items

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
        return validate_cluster_id(cluster_id)

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
        if not isinstance(body, str):
            raise RancherError(
                ErrorCategory.MALFORMED,
                "Rancher response body is not text",
            )
        if len(body.encode("utf-8")) > self._max_response_bytes:
            raise RancherError(
                ErrorCategory.TRANSPORT,
                "Rancher response exceeds byte limit",
            )
        if status in (401, 403):
            raise RancherError(ErrorCategory.AUTH, f"HTTP {status} from Rancher")
        if 300 <= status < 400:
            raise RancherError(
                ErrorCategory.TRANSPORT, f"redirect HTTP {status} refused"
            )
        if method == "GET" and status != 200:
            raise RancherError(ErrorCategory.TRANSPORT, f"HTTP {status} from Rancher")
        if method == "DELETE" and status not in (200, 202, 204, 404, 409):
            raise RancherError(
                ErrorCategory.TRANSPORT,
                f"HTTP {status} from Rancher",
            )
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
        seen_ids: set[str] = set()
        visited_urls = {first_url}
        url = first_url
        first_parts = urlsplit(first_url)
        first_query = parse_qs(first_parts.query, keep_blank_values=True)
        expected_filters = {
            key: values
            for key, values in first_query.items()
            if key not in _PAGINATION_QUERY_FIELDS
        }
        expected_total: int | None = None
        for _ in range(self._max_pages):
            doc = self._parse_json(self._request("GET", url))
            data = doc.get("data")
            pagination = doc.get("pagination")
            if not isinstance(data, list):
                raise RancherError(ErrorCategory.MALFORMED, "collection lacks data list")
            if len(items) + len(data) > self._max_collection_items:
                raise IncompleteEnumeration(
                    "collection exceeds the item limit"
                )
            if not all(isinstance(item, dict) for item in data):
                raise RancherError(
                    ErrorCategory.MALFORMED,
                    "collection contains a non-object item",
                )
            page_ids = [item.get("id") for item in data]
            if not all(isinstance(item_id, str) and item_id for item_id in page_ids):
                raise RancherError(
                    ErrorCategory.MALFORMED,
                    "collection item lacks a valid id",
                )
            if len(page_ids) != len(set(page_ids)) or seen_ids.intersection(
                page_ids
            ):
                raise IncompleteEnumeration("collection contains duplicate ids")
            seen_ids.update(page_ids)
            if not isinstance(pagination, dict):
                raise IncompleteEnumeration("collection lacks pagination metadata")
            unknown = set(pagination) - _KNOWN_PAGINATION_FIELDS
            if unknown:
                raise IncompleteEnumeration(
                    f"unrecognized pagination fields: {sorted(unknown)}"
                )
            total = pagination.get("total")
            if isinstance(total, bool) or not isinstance(total, int) or total < 0:
                raise IncompleteEnumeration("pagination.total is invalid")
            if total > self._max_collection_items:
                raise IncompleteEnumeration(
                    "pagination.total exceeds collection item limit"
                )
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise IncompleteEnumeration("pagination.total changed between pages")
            items.extend(data)
            if len(items) > expected_total:
                raise IncompleteEnumeration("collection exceeds pagination.total")
            next_url = pagination.get("next")
            if next_url is not None and not isinstance(next_url, str):
                raise IncompleteEnumeration("pagination.next is not a URL")
            if next_url:
                next_parts = urlsplit(next_url)
                next_query = parse_qs(
                    next_parts.query,
                    keep_blank_values=True,
                )
                next_filters = {
                    key: values
                    for key, values in next_query.items()
                    if key not in _PAGINATION_QUERY_FIELDS
                }
                if (
                    f"{next_parts.scheme}://{next_parts.netloc}" != self._origin
                    or next_parts.path != first_parts.path
                    or next_parts.fragment
                    or next_filters != expected_filters
                ):
                    raise IncompleteEnumeration(
                        "pagination.next escapes the allowlisted collection"
                    )
                if next_url in visited_urls:
                    raise IncompleteEnumeration("pagination.next repeats a page")
                visited_urls.add(next_url)
                url = next_url
                continue
            if len(items) != expected_total:
                raise IncompleteEnumeration(
                    "final collection size differs from pagination.total"
                )
            return items
        raise IncompleteEnumeration(
            f"pagination did not terminate after {self._max_pages} pages"
        )
