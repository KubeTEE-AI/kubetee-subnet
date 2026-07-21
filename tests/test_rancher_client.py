"""g004 V2: contained Rancher v3 client (TDD, red first).

Covers spec AC4 (containment: fixed https origin, redirects refused,
endpoint allowlist of scoring GETs plus exactly one DELETE, method+URL of
every emittable request asserted) and AC5 at the client layer (the token
never appears in errors or repr), plus exhaustive fail-closed pagination
per tests/fixtures/rancher/contract.json.
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.error

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from rancher_client import (
    ErrorCategory,
    IncompleteEnumeration,
    RancherClient,
    RancherError,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "rancher"
ORIGIN = "https://rancher.example"
TOKEN = "token-fake1:secretsecretsecret"


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


class FakeTransport:
    """Injectable transport recording every request it is asked to make."""

    def __init__(self, routes: dict[str, tuple[int, str]]):
        self.routes = routes
        self.requests: list[dict] = []

    def request(self, method: str, url: str, headers: dict, timeout: float):
        self.requests.append(
            {"method": method, "url": url, "headers": dict(headers)}
        )
        if url not in self.routes:
            raise AssertionError(f"unexpected request: {method} {url}")
        return self.routes[url]


def make_client(routes: dict[str, tuple[int, str]]) -> tuple[RancherClient, FakeTransport]:
    transport = FakeTransport(routes)
    client = RancherClient(base_url=ORIGIN, token=TOKEN, transport=transport)
    return client, transport


# --- construction / containment -------------------------------------------


def test_rejects_non_https_origin():
    with pytest.raises(ValueError):
        RancherClient(base_url="http://rancher.example", token=TOKEN)


def test_rejects_empty_token():
    with pytest.raises(ValueError):
        RancherClient(base_url=ORIGIN, token="  ")


def test_repr_and_str_never_contain_token():
    client, _ = make_client({})
    assert TOKEN not in repr(client)
    assert TOKEN not in str(client)


def test_every_request_is_get_except_the_single_delete():
    routes = {
        f"{ORIGIN}/v3/clusters?limit=-1": (200, load("clusters.json")),
        f"{ORIGIN}/v3/clusters/cluster-aaa": (200, json.dumps(
            json.loads(load("clusters.json"))["data"][0])),
        f"{ORIGIN}/v3/nodes?clusterId=cluster-aaa&limit=-1": (200, load("nodes.json")),
        f"{ORIGIN}/v3/clusters/cluster-bbb": (200, "{}"),
    }
    client, transport = make_client(routes)
    client.list_clusters()
    client.get_cluster("cluster-aaa")
    client.list_nodes("cluster-aaa")
    client.delete_cluster("cluster-bbb")
    methods = {(r["method"], r["url"]) for r in transport.requests}
    deletes = [m for m in methods if m[0] == "DELETE"]
    assert deletes == [("DELETE", f"{ORIGIN}/v3/clusters/cluster-bbb")]
    for method, url in methods:
        assert method in {"GET", "DELETE"}
        assert url.startswith(f"{ORIGIN}/v3/")


def test_auth_and_user_agent_headers_on_every_request():
    client, transport = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, load("clusters.json"))}
    )
    client.list_clusters()
    for req in transport.requests:
        assert req["headers"]["Authorization"] == f"Bearer {TOKEN}"
        assert req["headers"]["User-Agent"].startswith("kubetee-validator/")


def test_cluster_id_is_validated_before_url_interpolation():
    client, _ = make_client({})
    for bad in ("", "a/b", "x?y", "c m", "../local"):
        with pytest.raises(ValueError):
            client.get_cluster(bad)
        with pytest.raises(ValueError):
            client.delete_cluster(bad)


# --- pagination -------------------------------------------------------------


def test_pagination_followed_to_exhaustion():
    routes = {
        f"{ORIGIN}/v3/clusters?limit=-1": (200, load("clusters-page1.json")),
        f"{ORIGIN}/v3/clusters?limit=1&marker=cluster-bbb": (200, load("clusters-page2.json")),
    }
    client, transport = make_client(routes)
    clusters = client.list_clusters()
    assert [c["id"] for c in clusters] == ["cluster-aaa", "cluster-bbb"]
    assert len(transport.requests) == 2


def test_partial_without_next_fails_closed():
    page = json.loads(load("clusters-page1.json"))
    del page["pagination"]["next"]
    client, _ = make_client({f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))})
    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()


def test_unknown_pagination_field_fails_closed():
    page = json.loads(load("clusters.json"))
    page["pagination"]["continuationToken"] = "opaque"
    client, _ = make_client({f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))})
    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()


def test_missing_pagination_object_fails_closed():
    page = json.loads(load("clusters.json"))
    del page["pagination"]
    client, _ = make_client({f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))})
    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()


def test_cross_origin_next_url_is_refused_and_unauthenticated():
    page = json.loads(load("clusters-page1.json"))
    page["pagination"]["next"] = "https://evil.example/v3/clusters?limit=1"
    client, transport = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))}
    )
    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()
    assert all(r["url"].startswith(ORIGIN) for r in transport.requests)


def test_max_pages_limit_raises_incomplete():
    """A client with max_pages=1 raises IncompleteEnumeration."""
    import json

    ORIGIN_HERE = "https://valid.example.com"

    class _PaginatedTransport:
        def __init__(self):
            self.count = 0

        def request(self, method, url, headers, timeout):
            self.count += 1
            body = json.dumps(
                {
                    "data": [{"id": "c-1"}],
                    "pagination": {
                        "next": f"{ORIGIN_HERE}/v3/clusters?page={self.count + 1}"
                    },
                }
            )
            return 200, body

    client = RancherClient(
        ORIGIN_HERE,
        "token-abc",
        transport=_PaginatedTransport(),
        max_pages=1,
    )
    with pytest.raises(IncompleteEnumeration, match="did not terminate after 1 pages"):
        client.list_clusters()


# --- error categories -------------------------------------------------------


@pytest.mark.parametrize("status,category", [
    (401, ErrorCategory.AUTH),
    (403, ErrorCategory.AUTH),
    (500, ErrorCategory.TRANSPORT),
    (503, ErrorCategory.TRANSPORT),
])
def test_http_status_maps_to_fixed_enum(status, category):
    client, _ = make_client({f"{ORIGIN}/v3/clusters?limit=-1": (status, "denied")})
    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()
    assert excinfo.value.category is category


def test_redirect_is_refused_not_followed():
    client, transport = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (302, "")}
    )
    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()
    assert excinfo.value.category is ErrorCategory.TRANSPORT
    assert len(transport.requests) == 1


def test_malformed_json_fails_closed():
    client, _ = make_client({f"{ORIGIN}/v3/clusters?limit=-1": (200, "not-json{")})
    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()
    assert excinfo.value.category is ErrorCategory.MALFORMED


class ExplodingTransport:
    def request(self, method, url, headers, timeout):
        raise ConnectionError(f"boom contacting {url} with Bearer {TOKEN}")


def test_transport_exception_wrapped_and_token_scrubbed():
    client = RancherClient(base_url=ORIGIN, token=TOKEN, transport=ExplodingTransport())
    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()
    assert excinfo.value.category is ErrorCategory.TRANSPORT
    assert TOKEN not in str(excinfo.value)
    assert TOKEN not in repr(excinfo.value)


def test_error_bodies_are_not_reproduced_in_messages():
    secret_body = json.dumps({"message": "denied", "leak": TOKEN})
    client, _ = make_client({f"{ORIGIN}/v3/clusters?limit=-1": (401, secret_body)})
    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()
    assert TOKEN not in str(excinfo.value)


def test_transport_url_error_is_wrapped_cleanly():
    """URLError from transport is wrapped as TRANSPORT, not raw."""
    class _URLErrorTransport:
        def request(self, method, url, headers, timeout):
            raise urllib.error.URLError("name or service not known")

    client = RancherClient("https://valid.example.com", "token-abc", transport=_URLErrorTransport())
    with pytest.raises(RancherError) as exc:
        client.list_clusters()
    assert exc.value.category == ErrorCategory.TRANSPORT
    assert "transport failure" in str(exc.value)


def test_max_pages_limit_raises_incomplete():
    """A client with max_pages=1 raises IncompleteEnumeration."""
    import json

    ORIGIN_HERE = "https://valid.example.com"

    class _PaginatedTransport:
        def __init__(self):
            self.count = 0

        def request(self, method, url, headers, timeout):
            self.count += 1
            body = json.dumps(
                {
                    "data": [{"id": "c-1"}],
                    "pagination": {
                        "next": f"{ORIGIN_HERE}/v3/clusters?page={self.count + 1}"
                    },
                }
            )
            return 200, body

    client = RancherClient(
        ORIGIN_HERE,
        "token-abc",
        transport=_PaginatedTransport(),
        max_pages=1,
    )
    with pytest.raises(IncompleteEnumeration, match="did not terminate after 1 pages"):
        client.list_clusters()
