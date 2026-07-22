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
import functools
import http.client
import json
import math
import re
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

USER_AGENT = "kubetee-validator/0.1"
DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_COLLECTION_ITEMS = 100_000
DEFAULT_MAX_COLLECTION_BYTES = 256 * 1024 * 1024
DEFAULT_COLLECTION_TIMEOUT = 30.0
_HTTP_READ_CHUNK_BYTES = 64 * 1024
_REQUEST_DEADLINE_ATTRIBUTE = "_kubetee_absolute_deadline"
_KNOWN_PAGINATION_FIELDS = {
    "first",
    "next",
    "last",
    "limit",
    "total",
    "partial",
}
_PAGINATION_QUERY_FIELDS = {"limit", "marker", "page"}
_CLUSTER_ID_PART = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_NODE_ID_PART = r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?"
_CLUSTER_ID = re.compile(rf"^{_CLUSTER_ID_PART}$")
_NODE_ID = re.compile(rf"^{_CLUSTER_ID_PART}:{_NODE_ID_PART}$")


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


def validate_node_id(value: object) -> str:
    """Return a canonical Rancher node ID or raise."""
    if not isinstance(value, str) or not _NODE_ID.fullmatch(value):
        raise ValueError("invalid node id")
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


class _MalformedResponseBody(Exception):
    pass


class _DuplicateJSONKey(ValueError):
    pass


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise _DuplicateJSONKey
        obj[key] = value
    return obj


def _reject_json_constant(_value: str):
    raise ValueError


class _DeadlineSocketFile:
    def __init__(self, reader, sock, deadline: float) -> None:
        self._reader = reader
        self._socket = sock
        self._deadline = deadline
        self._buffer = bytearray()

    @property
    def raw(self):
        return self._reader.raw

    @property
    def closed(self) -> bool:
        return bool(self._reader.closed)

    def close(self) -> None:
        self._reader.close()

    def flush(self) -> None:
        self._reader.flush()

    def _read_underlying(self, amount: int) -> bytes:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        self._socket.settimeout(remaining)
        read = getattr(self._reader, "read1", None)
        data = read(amount) if callable(read) else self._reader.read(amount)
        if time.monotonic() >= self._deadline:
            raise TimeoutError
        if not isinstance(data, bytes):
            raise OSError
        return data

    def _take_buffer(self, amount: int) -> bytes:
        taken = bytes(self._buffer[:amount])
        del self._buffer[:amount]
        return taken

    def read1(self, amount: int = -1) -> bytes:
        if amount == 0:
            return b""
        if amount < 0:
            amount = _HTTP_READ_CHUNK_BYTES
        if self._buffer:
            return self._take_buffer(min(amount, len(self._buffer)))
        return self._read_underlying(amount)

    def read(self, amount: int = -1) -> bytes:
        if amount == 0:
            return b""
        chunks = []
        if self._buffer:
            buffered_amount = (
                len(self._buffer)
                if amount < 0
                else min(amount, len(self._buffer))
            )
            chunks.append(self._take_buffer(buffered_amount))
        while amount < 0 or sum(map(len, chunks)) < amount:
            remaining_amount = (
                _HTTP_READ_CHUNK_BYTES
                if amount < 0
                else min(
                    _HTTP_READ_CHUNK_BYTES,
                    amount - sum(map(len, chunks)),
                )
            )
            chunk = self._read_underlying(remaining_amount)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def readinto(self, buffer) -> int:
        data = self.read1(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def readline(self, limit: int = -1) -> bytes:
        if limit == 0:
            return b""
        line = bytearray()
        while limit < 0 or len(line) < limit:
            if self._buffer:
                available = (
                    len(self._buffer)
                    if limit < 0
                    else min(len(self._buffer), limit - len(line))
                )
                newline = self._buffer.find(b"\n", 0, available)
                taken = newline + 1 if newline >= 0 else available
                line.extend(self._take_buffer(taken))
                if newline >= 0 or (limit >= 0 and len(line) == limit):
                    break
            chunk = self._read_underlying(_HTTP_READ_CHUNK_BYTES)
            if not chunk:
                break
            self._buffer.extend(chunk)
        return bytes(line)


class _DeadlineHTTPResponse(http.client.HTTPResponse):
    def __init__(self, sock, *args, deadline: float, **kwargs) -> None:
        super().__init__(sock, *args, **kwargs)
        if self.fp is None:
            raise OSError
        self.fp = _DeadlineSocketFile(self.fp, sock, deadline)


class _DeadlineHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, deadline: float, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.response_class = functools.partial(
            _DeadlineHTTPResponse, deadline=deadline
        )


class _DeadlineHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, deadline: float, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.response_class = functools.partial(
            _DeadlineHTTPResponse, deadline=deadline
        )


def _request_deadline(request: urllib.request.Request) -> float:
    deadline = getattr(request, _REQUEST_DEADLINE_ATTRIBUTE, None)
    if not isinstance(deadline, float) or not math.isfinite(deadline):
        raise urllib.error.URLError("request deadline unavailable")
    return deadline


class _DeadlineHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(
            _DeadlineHTTPConnection,
            req,
            deadline=_request_deadline(req),
        )


class _DeadlineHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(
            _DeadlineHTTPSConnection,
            req,
            context=self._context,
            deadline=_request_deadline(req),
        )


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
            _DeadlineHTTPSHandler(context=context),
            _DeadlineHTTPHandler(),
        )
        self._max_response_bytes = max_response_bytes

    @staticmethod
    def _remaining_budget(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        return remaining

    @staticmethod
    def _set_socket_timeout(response, timeout: float) -> None:
        for path in (
            ("fp", "raw", "_sock"),
            ("fp", "fp", "raw", "_sock"),
        ):
            candidate = response
            for attribute in path:
                candidate = getattr(candidate, attribute, None)
                if candidate is None:
                    break
            settimeout = getattr(candidate, "settimeout", None)
            if callable(settimeout):
                settimeout(timeout)
                return
        http_response = (
            response
            if isinstance(response, http.client.HTTPResponse)
            else (
                response.fp
                if isinstance(response, urllib.error.HTTPError)
                and isinstance(response.fp, http.client.HTTPResponse)
                else None
            )
        )
        if http_response is not None and not http_response.isclosed():
            raise OSError

    def _read_bounded(self, response, deadline: float) -> bytes:
        read = getattr(response, "read1", None)
        if not callable(read):
            remaining = self._remaining_budget(deadline)
            self._set_socket_timeout(response, remaining)
            body = response.read(self._max_response_bytes + 1)
            if time.monotonic() >= deadline:
                raise TimeoutError
            return body
        body = bytearray()
        limit = self._max_response_bytes + 1
        while len(body) < limit:
            remaining = self._remaining_budget(deadline)
            self._set_socket_timeout(response, remaining)
            chunk = read(min(_HTTP_READ_CHUNK_BYTES, limit - len(body)))
            if time.monotonic() >= deadline:
                raise TimeoutError
            if not chunk:
                break
            body.extend(chunk)
        return bytes(body)

    def request(self, method: str, url: str, headers: dict, timeout: float):
        deadline = time.monotonic() + timeout
        req = urllib.request.Request(url, headers=headers, method=method)
        setattr(req, _REQUEST_DEADLINE_ATTRIBUTE, deadline)
        try:
            with self._opener.open(
                req, timeout=self._remaining_budget(deadline)
            ) as resp:
                self._remaining_budget(deadline)
                content_length = resp.headers.get("Content-Length")
                if (
                    content_length is not None
                    and content_length.isdigit()
                    and int(content_length) > self._max_response_bytes
                ):
                    raise _ResponseTooLarge(
                        "Rancher response exceeds byte limit"
                    )
                body = self._read_bounded(resp, deadline)
                if len(body) > self._max_response_bytes:
                    raise _ResponseTooLarge(
                        "Rancher response exceeds byte limit"
                    )
                try:
                    text = body.decode("utf-8")
                except UnicodeDecodeError:
                    raise _MalformedResponseBody from None
                return resp.status, text
        except urllib.error.HTTPError as exc:
            try:
                self._remaining_budget(deadline)
                return exc.code, ""
            finally:
                exc.close()
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
        max_collection_bytes: int = DEFAULT_MAX_COLLECTION_BYTES,
        collection_timeout: float = DEFAULT_COLLECTION_TIMEOUT,
        ca_file: str | None = None,
        monotonic=time.monotonic,
    ) -> None:
        origin = normalize_https_origin(base_url)
        if not token or not token.strip():
            raise ValueError("Rancher token must be non-empty")
        for name, value in (
            ("max_pages", max_pages),
            ("max_response_bytes", max_response_bytes),
            ("max_collection_items", max_collection_items),
            ("max_collection_bytes", max_collection_bytes),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(collection_timeout, bool)
            or not isinstance(collection_timeout, (int, float))
            or not math.isfinite(collection_timeout)
            or collection_timeout <= 0
        ):
            raise ValueError(
                "collection_timeout must be a positive finite number"
            )
        if not callable(monotonic):
            raise ValueError("monotonic must be callable")
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
        self._max_collection_bytes = max_collection_bytes
        self._collection_timeout = float(collection_timeout)
        self._monotonic = monotonic

    def __repr__(self) -> str:  # never include the token
        return f"RancherClient(origin={self._origin!r})"

    __str__ = __repr__

    # -- public allowlisted surface -----------------------------------------

    def list_clusters(self) -> list[dict]:
        return self._collect(f"{self._origin}/v3/clusters?limit=-1")

    def list_nodes(self, cluster_id: str) -> list[dict]:
        cid = self._validate_id(cluster_id)
        return self._collect(
            f"{self._origin}/v3/nodes?clusterId={cid}&limit=-1"
        )

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

    def _raw(
        self,
        method: str,
        url: str,
        timeout: float | None = None,
    ) -> tuple[int, str]:
        if not url.startswith(self._origin + "/"):
            raise IncompleteEnumeration(
                "request URL escapes the configured origin"
            )
        headers = {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": self._user_agent,
            "Accept": "application/json",
        }
        try:
            status, body = self._transport.request(
                method,
                url,
                headers,
                self._timeout if timeout is None else timeout,
            )
        except _MalformedResponseBody:
            raise RancherError(
                ErrorCategory.MALFORMED,
                "Rancher response body is not valid UTF-8",
            ) from None
        except Exception:  # transport failures are reduced to a fixed reason
            raise RancherError(
                ErrorCategory.TRANSPORT,
                "Rancher transport failure",
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
            raise RancherError(
                ErrorCategory.AUTH, f"HTTP {status} from Rancher"
            )
        if 300 <= status < 400:
            raise RancherError(
                ErrorCategory.TRANSPORT, f"redirect HTTP {status} refused"
            )
        if method == "GET" and status != 200:
            raise RancherError(
                ErrorCategory.TRANSPORT, f"HTTP {status} from Rancher"
            )
        if method == "DELETE" and status not in (200, 202, 204, 404, 409):
            raise RancherError(
                ErrorCategory.TRANSPORT,
                f"HTTP {status} from Rancher",
            )
        return status, body

    def _request(
        self,
        method: str,
        url: str,
        timeout: float | None = None,
    ) -> str:
        _, body = self._raw(method, url, timeout)
        return body

    def _parse_json(self, body: str) -> dict:
        try:
            parsed = json.loads(
                body,
                object_pairs_hook=_strict_json_object,
                parse_constant=_reject_json_constant,
            )
        except ValueError:
            raise RancherError(
                ErrorCategory.MALFORMED, "response body is not valid JSON"
            ) from None
        if not isinstance(parsed, dict):
            raise RancherError(
                ErrorCategory.MALFORMED, "unexpected JSON shape"
            )
        return parsed

    def _collect(self, first_url: str) -> list[dict]:
        """Follow marker pagination to exhaustion, failing closed otherwise."""
        items: list[dict] = []
        seen_ids: set[str] = set()
        visited_urls = {first_url}
        url = first_url
        first_parts = urlsplit(first_url)
        if first_parts.path == "/v3/clusters":
            validate_item_id = validate_cluster_id
            expected_resource_type = "cluster"
        elif first_parts.path == "/v3/nodes":
            validate_item_id = validate_node_id
            expected_resource_type = "node"
        else:
            raise IncompleteEnumeration(
                "collection resource is not allowlisted"
            )
        first_query = parse_qs(first_parts.query, keep_blank_values=True)
        expected_filters = {
            key: values
            for key, values in first_query.items()
            if key not in _PAGINATION_QUERY_FIELDS
        }
        expected_total: int | None = None
        cumulative_bytes = 0
        deadline = self._monotonic() + self._collection_timeout
        for _ in range(self._max_pages):
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise IncompleteEnumeration("collection deadline exceeded")
            body = self._request("GET", url, min(self._timeout, remaining))
            cumulative_bytes += len(body.encode("utf-8"))
            if cumulative_bytes > self._max_collection_bytes:
                raise IncompleteEnumeration("collection byte budget exceeded")
            if self._monotonic() > deadline:
                raise IncompleteEnumeration("collection deadline exceeded")
            doc = self._parse_json(body)
            data = doc.get("data")
            pagination = doc.get("pagination")
            if (
                doc.get("type") != "collection"
                or doc.get("resourceType") != expected_resource_type
            ):
                raise RancherError(
                    ErrorCategory.MALFORMED,
                    "collection envelope has an unexpected resource type",
                )
            if not isinstance(data, list):
                raise RancherError(
                    ErrorCategory.MALFORMED, "collection lacks data list"
                )
            if len(items) + len(data) > self._max_collection_items:
                raise IncompleteEnumeration(
                    "collection exceeds the item limit"
                )
            if not all(isinstance(item, dict) for item in data):
                raise RancherError(
                    ErrorCategory.MALFORMED,
                    "collection contains a non-object item",
                )
            if not all(
                item.get("type") == expected_resource_type for item in data
            ):
                raise RancherError(
                    ErrorCategory.MALFORMED,
                    "collection item has an unexpected resource type",
                )
            try:
                page_ids = [validate_item_id(item.get("id")) for item in data]
            except ValueError:
                raise RancherError(
                    ErrorCategory.MALFORMED,
                    "collection item lacks a valid id",
                ) from None
            if len(page_ids) != len(set(page_ids)) or seen_ids.intersection(
                page_ids
            ):
                raise IncompleteEnumeration(
                    "collection contains duplicate ids"
                )
            seen_ids.update(page_ids)
            if not isinstance(pagination, dict):
                raise IncompleteEnumeration(
                    "collection lacks pagination metadata"
                )
            unknown = set(pagination) - _KNOWN_PAGINATION_FIELDS
            if unknown:
                raise IncompleteEnumeration(
                    "pagination has unrecognized fields"
                )
            total = pagination.get("total")
            if (
                isinstance(total, bool)
                or not isinstance(total, int)
                or total < 0
            ):
                raise IncompleteEnumeration("pagination.total is invalid")
            if total > self._max_collection_items:
                raise IncompleteEnumeration(
                    "pagination.total exceeds collection item limit"
                )
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise IncompleteEnumeration(
                    "pagination.total changed between pages"
                )
            items.extend(data)
            if len(items) > expected_total:
                raise IncompleteEnumeration(
                    "collection exceeds pagination.total"
                )
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
                    f"{next_parts.scheme}://{next_parts.netloc}"
                    != self._origin
                    or next_parts.path != first_parts.path
                    or next_parts.fragment
                    or next_filters != expected_filters
                ):
                    raise IncompleteEnumeration(
                        "pagination.next escapes the allowlisted collection"
                    )
                if next_url in visited_urls:
                    raise IncompleteEnumeration(
                        "pagination.next repeats a page"
                    )
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
