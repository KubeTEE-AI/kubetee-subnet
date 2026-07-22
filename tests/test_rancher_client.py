"""g004 V2: contained Rancher v3 client (TDD, red first).

Covers spec AC4 (containment: fixed https origin, redirects refused,
endpoint allowlist of scoring GETs plus exactly one DELETE, method+URL of
every emittable request asserted) and AC5 at the client layer (the token
never appears in errors or repr), plus exhaustive fail-closed pagination
per tests/fixtures/rancher/contract.json.
"""

# Transport fakes preserve keyword-compatible protocol signatures, and one
# boundary test intentionally calls the private raw-request guard.
# pylint: disable=unused-argument,protected-access,unnecessary-lambda

from __future__ import annotations

import json
import pathlib
import sys
import urllib.error

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

import rancher_client
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


def make_client(
    routes: dict[str, tuple[int, str]],
) -> tuple[RancherClient, FakeTransport]:
    transport = FakeTransport(routes)
    client = RancherClient(base_url=ORIGIN, token=TOKEN, transport=transport)
    return client, transport


# --- construction / containment -------------------------------------------


def test_rejects_non_https_origin():
    with pytest.raises(ValueError):
        RancherClient(base_url="http://rancher.example", token=TOKEN)


@pytest.mark.parametrize(
    "url",
    [
        "https://rancher.example/v3",
        "https://rancher.example?scope=all",
        "https://rancher.example#fragment",
        "https://user:embedded-secret@rancher.example",
    ],
)
def test_rejects_non_origin_or_credential_bearing_url(url):
    with pytest.raises(ValueError) as excinfo:
        RancherClient(base_url=url, token=TOKEN)
    assert "embedded-secret" not in str(excinfo.value)


def test_rejects_empty_token():
    with pytest.raises(ValueError):
        RancherClient(base_url=ORIGIN, token="  ")


def test_repr_and_str_never_contain_token():
    client, _ = make_client({})
    assert TOKEN not in repr(client)
    assert TOKEN not in str(client)


def test_custom_ca_is_scoped_to_the_rancher_transport(monkeypatch):
    observed: list[str | None] = []

    def fake_context(*, cafile=None):
        observed.append(cafile)
        return object()

    monkeypatch.setattr(
        rancher_client.ssl, "create_default_context", fake_context
    )
    monkeypatch.setattr(
        rancher_client.urllib.request,
        "HTTPSHandler",
        lambda *, context: object(),
    )
    monkeypatch.setattr(
        rancher_client.urllib.request,
        "build_opener",
        lambda *handlers: object(),
    )

    RancherClient(
        base_url=ORIGIN,
        token=TOKEN,
        ca_file="/run/secrets/rancher-ca.crt",
    )

    assert observed == ["/run/secrets/rancher-ca.crt"]


def test_every_request_is_get_except_the_single_delete():
    routes = {
        f"{ORIGIN}/v3/clusters?limit=-1": (200, load("clusters.json")),
        f"{ORIGIN}/v3/clusters/cluster-aaa": (
            200,
            json.dumps(json.loads(load("clusters.json"))["data"][0]),
        ),
        f"{ORIGIN}/v3/nodes?clusterId=cluster-aaa&limit=-1": (
            200,
            load("nodes.json"),
        ),
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


@pytest.mark.parametrize("status", [0, 500, 503])
def test_delete_transport_status_is_an_error_not_a_success(status):
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters/cluster-bbb": (status, "unavailable")}
    )

    with pytest.raises(RancherError) as excinfo:
        client.delete_cluster("cluster-bbb")

    assert excinfo.value.category is ErrorCategory.TRANSPORT


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
    for bad in (
        "",
        "a/b",
        "x?y",
        "c m",
        "../local",
        " cluster-aaa ",
        None,
        123,
        [],
    ):
        with pytest.raises(ValueError):
            client.get_cluster(bad)
        with pytest.raises(ValueError):
            client.delete_cluster(bad)


# --- pagination -------------------------------------------------------------


def test_pagination_followed_to_exhaustion():
    routes = {
        f"{ORIGIN}/v3/clusters?limit=-1": (200, load("clusters-page1.json")),
        f"{ORIGIN}/v3/clusters?limit=1&marker=cluster-bbb": (
            200,
            load("clusters-page2.json"),
        ),
    }
    client, transport = make_client(routes)
    clusters = client.list_clusters()
    assert [c["id"] for c in clusters] == ["cluster-aaa", "cluster-bbb"]
    assert len(transport.requests) == 2


def test_partial_without_next_fails_closed():
    page = json.loads(load("clusters-page1.json"))
    del page["pagination"]["next"]
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))}
    )
    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()


def test_unknown_pagination_field_fails_closed():
    page = json.loads(load("clusters.json"))
    hostile_field = "attacker-controlled-pagination-field"
    page["pagination"][hostile_field] = "opaque"
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))}
    )
    with pytest.raises(IncompleteEnumeration) as excinfo:
        client.list_clusters()

    assert hostile_field not in str(excinfo.value)


@pytest.mark.parametrize(
    ("resource", "field", "wrong_value"),
    [
        ("clusters", "type", "not-a-collection"),
        ("clusters", "resourceType", "node"),
        ("nodes", "type", "not-a-collection"),
        ("nodes", "resourceType", "cluster"),
    ],
)
def test_collection_envelope_must_match_the_allowlisted_resource(
    resource, field, wrong_value
):
    if resource == "clusters":
        page = json.loads(load("clusters.json"))
        first_url = f"{ORIGIN}/v3/clusters?limit=-1"
    else:
        page = json.loads(load("nodes.json"))
        first_url = f"{ORIGIN}/v3/nodes?clusterId=cluster-aaa&limit=-1"
    page[field] = wrong_value
    client, _ = make_client({first_url: (200, json.dumps(page))})

    with pytest.raises(RancherError) as excinfo:
        if resource == "clusters":
            client.list_clusters()
        else:
            client.list_nodes("cluster-aaa")

    assert excinfo.value.category is ErrorCategory.MALFORMED


@pytest.mark.parametrize(
    ("resource", "wrong_type"),
    [("clusters", "node"), ("nodes", "cluster")],
)
def test_collection_item_type_must_match_the_allowlisted_resource(
    resource, wrong_type
):
    if resource == "clusters":
        page = json.loads(load("clusters.json"))
        first_url = f"{ORIGIN}/v3/clusters?limit=-1"
    else:
        page = json.loads(load("nodes.json"))
        first_url = f"{ORIGIN}/v3/nodes?clusterId=cluster-aaa&limit=-1"
    page["data"][0]["type"] = wrong_type
    client, _ = make_client({first_url: (200, json.dumps(page))})

    with pytest.raises(RancherError) as excinfo:
        if resource == "clusters":
            client.list_clusters()
        else:
            client.list_nodes("cluster-aaa")

    assert excinfo.value.category is ErrorCategory.MALFORMED


def test_missing_pagination_object_fails_closed():
    page = json.loads(load("clusters.json"))
    del page["pagination"]
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))}
    )
    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()


@pytest.mark.parametrize(
    ("field", "value"),
    [("next", 0), ("next", [])],
)
def test_malformed_terminal_pagination_fails_closed(field, value):
    page = json.loads(load("clusters.json"))
    page["pagination"][field] = value
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))}
    )

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


def test_repeated_next_url_is_refused_before_an_extra_request():
    first_url = f"{ORIGIN}/v3/clusters?limit=-1"
    page = json.loads(load("clusters-page1.json"))
    page["pagination"]["next"] = first_url
    client, transport = make_client({first_url: (200, json.dumps(page))})

    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()

    assert len(transport.requests) == 1


def test_same_origin_next_url_cannot_escape_the_allowlisted_resource():
    page = json.loads(load("clusters-page1.json"))
    page["pagination"]["next"] = f"{ORIGIN}/v3/secrets?limit=1"
    client, transport = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))}
    )

    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()

    assert [request["url"] for request in transport.requests] == [
        f"{ORIGIN}/v3/clusters?limit=-1"
    ]


def test_node_pagination_cannot_drop_the_cluster_filter():
    page = json.loads(load("nodes.json"))
    page["pagination"].update(
        {
            "partial": True,
            "total": 2,
            "next": f"{ORIGIN}/v3/nodes?limit=1&marker=node-next",
        }
    )
    client, transport = make_client(
        {
            f"{ORIGIN}/v3/nodes?clusterId=cluster-aaa&limit=-1": (
                200,
                json.dumps(page),
            )
        }
    )

    with pytest.raises(IncompleteEnumeration):
        client.list_nodes("cluster-aaa")

    assert len(transport.requests) == 1


def test_cluster_pagination_cannot_add_a_narrowing_filter():
    page = json.loads(load("clusters-page1.json"))
    page["pagination"][
        "next"
    ] = f"{ORIGIN}/v3/clusters?limit=1&marker=cluster-bbb&name=one-cluster"
    client, transport = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))}
    )

    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()

    assert len(transport.requests) == 1


def test_non_object_collection_item_is_malformed_not_silently_dropped():
    page = json.loads(load("clusters.json"))
    page["data"].append("not-an-object")
    page["pagination"]["total"] += 1
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))}
    )

    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()

    assert excinfo.value.category is ErrorCategory.MALFORMED


@pytest.mark.parametrize(
    ("resource", "bad_id"),
    [
        ("clusters", "../local"),
        ("clusters", "Cluster-AAA"),
        ("nodes", "node-without-cluster-prefix"),
        ("nodes", "cluster-aaa:../node"),
    ],
)
def test_collection_item_ids_must_be_canonical(resource, bad_id):
    if resource == "clusters":
        page = json.loads(load("clusters.json"))
        first_url = f"{ORIGIN}/v3/clusters?limit=-1"
    else:
        page = json.loads(load("nodes.json"))
        first_url = f"{ORIGIN}/v3/nodes?clusterId=cluster-aaa&limit=-1"
    page["data"][0]["id"] = bad_id
    client, _ = make_client({first_url: (200, json.dumps(page))})

    with pytest.raises(RancherError) as excinfo:
        if resource == "clusters":
            client.list_clusters()
        else:
            client.list_nodes("cluster-aaa")

    assert excinfo.value.category is ErrorCategory.MALFORMED


def test_duplicate_collection_ids_are_incomplete():
    page = json.loads(load("clusters.json"))
    page["data"][1]["id"] = page["data"][0]["id"]
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))}
    )

    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()


def test_final_page_count_mismatch_is_incomplete_even_without_partial_flag():
    page = json.loads(load("clusters.json"))
    page["data"].pop()
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, json.dumps(page))}
    )

    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()


def test_max_pages_limit_raises_incomplete():
    """A client with max_pages=1 raises IncompleteEnumeration."""
    origin_here = "https://valid.example.com"

    class _PaginatedTransport:
        def __init__(self):
            self.count = 0

        def request(self, method, url, headers, timeout):
            self.count += 1
            body = json.dumps(
                {
                    "type": "collection",
                    "resourceType": "cluster",
                    "data": [{"id": "c-1", "type": "cluster"}],
                    "pagination": {
                        "total": 2,
                        "partial": True,
                        "next": f"{origin_here}/v3/clusters?page={self.count + 1}",
                    },
                }
            )
            return 200, body

    client = RancherClient(
        origin_here,
        "token-abc",
        transport=_PaginatedTransport(),
        max_pages=1,
    )
    with pytest.raises(
        IncompleteEnumeration, match="did not terminate after 1 pages"
    ):
        client.list_clusters()


def test_multipage_collection_has_a_cumulative_byte_budget():
    first = load("clusters-page1.json")
    second = load("clusters-page2.json")
    routes = {
        f"{ORIGIN}/v3/clusters?limit=-1": (200, first),
        f"{ORIGIN}/v3/clusters?limit=1&marker=cluster-bbb": (200, second),
    }
    transport = FakeTransport(routes)
    client = RancherClient(
        base_url=ORIGIN,
        token=TOKEN,
        transport=transport,
        max_collection_bytes=len(first.encode("utf-8"))
        + len(second.encode("utf-8"))
        - 1,
    )

    with pytest.raises(IncompleteEnumeration, match="byte budget"):
        client.list_clusters()

    assert len(transport.requests) == 2


def test_multipage_collection_has_a_whole_enumeration_deadline():
    class _Clock:
        def __init__(self):
            self.now = 0.0

        def __call__(self):
            return self.now

    class _AdvancingTransport(FakeTransport):
        def request(self, method, url, headers, timeout):
            result = super().request(method, url, headers, timeout)
            clock.now += 0.6
            return result

    clock = _Clock()
    transport = _AdvancingTransport(
        {
            f"{ORIGIN}/v3/clusters?limit=-1": (
                200,
                load("clusters-page1.json"),
            ),
            f"{ORIGIN}/v3/clusters?limit=1&marker=cluster-bbb": (
                200,
                load("clusters-page2.json"),
            ),
        }
    )
    client = RancherClient(
        base_url=ORIGIN,
        token=TOKEN,
        transport=transport,
        collection_timeout=1.0,
        monotonic=clock,
    )

    with pytest.raises(IncompleteEnumeration, match="deadline"):
        client.list_clusters()

    assert len(transport.requests) == 2


# --- error categories -------------------------------------------------------


@pytest.mark.parametrize(
    "status,category",
    [
        (401, ErrorCategory.AUTH),
        (403, ErrorCategory.AUTH),
        (500, ErrorCategory.TRANSPORT),
        (503, ErrorCategory.TRANSPORT),
    ],
)
def test_http_status_maps_to_fixed_enum(status, category):
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (status, "denied")}
    )
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
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (200, "not-json{")}
    )
    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()
    assert excinfo.value.category is ErrorCategory.MALFORMED


@pytest.mark.parametrize(
    ("body", "hostile_marker"),
    [
        (
            '{"type":"collection","resourceType":"cluster","data":[],'
            '"pagination":{"total":0},'
            '"pagination":{"total":0,"attacker-pagination":"secret"}}',
            "attacker-pagination",
        ),
        (
            '{"type":"collection","resourceType":"cluster","data":['
            '{"id":"cluster-aaa","type":"cluster","labels":{'
            '"kubetee.ai/hotkey":"first",'
            '"kubetee.ai/hotkey":"attacker-hotkey"}}],'
            '"pagination":{"total":1}}',
            "attacker-hotkey",
        ),
    ],
)
def test_duplicate_json_keys_fail_closed_without_reflection(
    body, hostile_marker
):
    client, _ = make_client({f"{ORIGIN}/v3/clusters?limit=-1": (200, body)})

    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()

    assert excinfo.value.category is ErrorCategory.MALFORMED
    assert hostile_marker not in str(excinfo.value)


def test_non_utf8_response_fails_closed_without_reflection():
    body = (
        b'{"type":"collection","resourceType":"cluster","data":[],'
        b'"unused":"\xff","pagination":{"total":0}}'
    )

    class _Response:
        status = 200

        def __init__(self):
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return body

    class _Opener:
        def open(self, _request, timeout):
            return _Response()

    transport = object.__new__(rancher_client.UrllibTransport)
    transport._opener = _Opener()
    transport._max_response_bytes = 1024
    client = RancherClient(base_url=ORIGIN, token=TOKEN, transport=transport)

    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()

    assert excinfo.value.category is ErrorCategory.MALFORMED
    assert repr(body) not in str(excinfo.value)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_json_constants_fail_closed_without_reflection(constant):
    body = (
        '{"type":"collection","resourceType":"cluster","data":[],'
        f'"unused":{constant},"pagination":{{"total":0}}}}'
    )
    client, _ = make_client({f"{ORIGIN}/v3/clusters?limit=-1": (200, body)})

    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()

    assert excinfo.value.category is ErrorCategory.MALFORMED
    assert constant not in str(excinfo.value)


class ExplodingTransport:
    def request(self, method, url, headers, timeout):
        raise ConnectionError(f"boom contacting {url} with Bearer {TOKEN}")


def test_transport_exception_wrapped_and_token_scrubbed():
    client = RancherClient(
        base_url=ORIGIN, token=TOKEN, transport=ExplodingTransport()
    )
    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()
    assert excinfo.value.category is ErrorCategory.TRANSPORT
    assert TOKEN not in str(excinfo.value)
    assert TOKEN not in repr(excinfo.value)


def test_transport_exception_message_does_not_reflect_remote_text():
    hostile_marker = "REMOTE-ATTACKER-CONTROLLED-MARKER"

    class _HostileTransport:
        def request(self, method, url, headers, timeout):
            raise ConnectionError(hostile_marker)

    client = RancherClient(
        base_url=ORIGIN, token=TOKEN, transport=_HostileTransport()
    )

    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()

    assert hostile_marker not in str(excinfo.value)


def test_non_origin_refusal_does_not_reflect_supplied_host():
    hostile_host = "attacker-controlled.example"
    client, _ = make_client({})

    with pytest.raises(IncompleteEnumeration) as excinfo:
        client._raw("GET", f"https://{hostile_host}/v3/clusters")

    assert hostile_host not in str(excinfo.value)


def test_error_bodies_are_not_reproduced_in_messages():
    secret_body = json.dumps({"message": "denied", "leak": TOKEN})
    client, _ = make_client(
        {f"{ORIGIN}/v3/clusters?limit=-1": (401, secret_body)}
    )
    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()
    assert TOKEN not in str(excinfo.value)


def test_oversized_response_body_fails_before_json_parsing():
    client = RancherClient(
        base_url=ORIGIN,
        token=TOKEN,
        transport=FakeTransport(
            {f"{ORIGIN}/v3/clusters?limit=-1": (200, "x" * 65)}
        ),
        max_response_bytes=64,
    )

    with pytest.raises(RancherError) as excinfo:
        client.list_clusters()

    assert excinfo.value.category is ErrorCategory.TRANSPORT


def test_collection_total_over_item_ceiling_is_incomplete():
    client = RancherClient(
        base_url=ORIGIN,
        token=TOKEN,
        transport=FakeTransport(
            {f"{ORIGIN}/v3/clusters?limit=-1": (200, load("clusters.json"))}
        ),
        max_collection_items=1,
    )

    with pytest.raises(IncompleteEnumeration):
        client.list_clusters()


def test_transport_url_error_is_wrapped_cleanly():
    """URLError from transport is wrapped as TRANSPORT, not raw."""

    class _URLErrorTransport:
        def request(self, method, url, headers, timeout):
            raise urllib.error.URLError("name or service not known")

    client = RancherClient(
        "https://valid.example.com",
        "token-abc",
        transport=_URLErrorTransport(),
    )
    with pytest.raises(RancherError) as exc:
        client.list_clusters()
    assert exc.value.category == ErrorCategory.TRANSPORT
    assert "transport failure" in str(exc.value)
