"""Release wiring tests: synthetic local identities, never a Finney connection."""

import asyncio
import base64
import contextlib
import hashlib
import json
import re
import socket
import ssl
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from asgi_lifespan import LifespanManager

from certificates import issue_certificates
from fixtures import HK, REAL
from worker.management import Management
from worker.protocol import GENESIS, internal_router
from worker.runtime import (
    ConfigurationError,
    DelegateProofMiddleware,
    MainnetSpendNotApproved,
    Settings,
    create_application,
    scoped_http_client,
    verify_worker_start,
)
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding


def gateway_der(settings):
    root = Path(settings.certificate_files[0]).parent
    return x509.load_pem_x509_certificate(
        (root / "gateway-server.crt").read_bytes()
    ).public_bytes(Encoding.DER)


from worker.service import WorkerService


def provider(tmp_path: Path):
    """Return the gateway server's exact pin and its already-issued DER."""
    return issue_certificates(tmp_path)["gateway-server"]


def environment(tmp_path: Path) -> dict[str, str]:
    leaves = issue_certificates(tmp_path, fourth_client=True)
    return {
        "KUBETEE_GAMMA_WORKER": "1",
        "KUBETEE_GAMMA_TEST": "1",
        "KUBETEE_GAMMA_SPEND_ENABLED": "0",
        "KUBETEE_GAMMA_NETWORK": "finney",
        "KUBETEE_GAMMA_REAL_SPENDER_SS58": REAL,
        "KUBETEE_GAMMA_MAX_FEE_TAO": "0.001",
        "KUBETEE_GAMMA_GATEWAY_CERT_SHA256": leaves["gateway-server"][0],
        "KUBETEE_GAMMA_WORKER_CERT_SHA256": leaves["worker-server"][0],
        "KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256": leaves["gateway-client"][
            0
        ],
        "KUBETEE_GAMMA_WORKER_CLIENT_CERT_SHA256": leaves["worker-client"][0],
        "KUBETEE_GAMMA_WORKER_CLIENT_PEM": str(tmp_path / "worker-client.crt"),
        "KUBETEE_GAMMA_WORKER_CLIENT_KEY": str(tmp_path / "worker-client.key"),
        "KUBETEE_GAMMA_PROXY_DELEGATE_SS58": "",
        "KUBETEE_GAMMA_MODELS": "z-ai/glm-5.3",
        "KUBETEE_GAMMA_MANAGEMENT_BASE_URL": "https://litellm-gateway-mtls.litellm.svc.cluster.local:8443",
        "KUBETEE_GAMMA_KBS_CA": "default/eastwest-ca/ca.pem",
        "KUBETEE_GAMMA_KBS_CERT": "default/gamma-worker-server/tls.crt",
        "KUBETEE_GAMMA_KBS_GATEWAY_SERVER_CERT": "default/gamma-gateway-private/tls.crt",
        "KUBETEE_GAMMA_KBS_KEY": "default/gamma-spend-proxy/tls.key",
        "KUBETEE_GAMMA_KBS_PROXY_SEED": "default/gamma-spend-proxy/seed",
        "KUBETEE_GAMMA_KBS_CLIENT_CERT": "default/gamma-worker-client/tls.crt",
        "KUBETEE_GAMMA_KBS_CLIENT_KEY": "default/gamma-worker-client/tls.key",
        "KUBETEE_GAMMA_PROJECTOR_PEM": str(tmp_path / "projector.crt"),
        "KUBETEE_GAMMA_CLIENT_PEM": str(tmp_path / "worker.pem"),
        "KUBETEE_GAMMA_CLIENT_KEY": str(tmp_path / "worker.key"),
    }


class Candidate:
    real_spender = REAL
    max_backfill = 12
    preflight_calls = 0
    finalized_snapshot_calls = 0

    async def preflight(self):
        self.preflight_calls += 1

    def __init__(self):
        self.client = self
        self.finalized_snapshot_calls = 0

    async def finalized_snapshot(self, hotkey):
        self.finalized_snapshot_calls += 1
        return 1, "0x" + "1" * 64, None

    async def events(self, height):
        return "0x" + "1" * 64, []

    async def finalized_block(self):
        return 1

    async def blocks(self, *, finalized=False):
        assert finalized is True
        await asyncio.sleep(3600)
        return
        yield


def test_scoped_client_maps_service_onto_private_listener(monkeypatch):
    observed = []

    async def request(self, method, url, **kwargs):
        observed.append(str(url))
        return httpx.Response(
            200, json={"ready": True}, request=httpx.Request("GET", str(url))
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", request)
    client = Management(
        httpx.AsyncClient(verify=True),
        "https://litellm-gateway-mtls.litellm.svc.cluster.local:8443",
        "mTLS:gamma-reconciler-type22",
    )
    assert asyncio.run(client.ready())
    assert observed == [
        "https://litellm-gateway-mtls.litellm.svc.cluster.local:8443/internal/v1/ready"
    ]


def test_outbound_client_auth_is_required_and_not_an_inbound_server_identity(
    tmp_path,
):
    settings = Settings.from_environment(environment(tmp_path))
    assert (
        len(
            {
                settings.gateway_fingerprint,
                settings.worker_fingerprint,
                settings.gateway_client_fingerprint,
                settings.gateway_client_fingerprint,
                environment(tmp_path)[
                    "KUBETEE_GAMMA_WORKER_CLIENT_CERT_SHA256"
                ],
            }
        )
        == 4
    )
    # All four DER pins are distinct; the outbound filename cannot determine role.
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding

    leaf = x509.load_pem_x509_certificate(
        (tmp_path / settings.outbound_tls_files()[0]).read_bytes()
    )
    pin = hashlib.sha256(leaf.public_bytes(Encoding.DER)).hexdigest()
    assert (
        len(
            {
                settings.gateway_fingerprint,
                settings.worker_fingerprint,
                settings.gateway_client_fingerprint,
                pin,
            }
        )
        == 4
    )
    absent = environment(tmp_path)
    absent.pop("KUBETEE_GAMMA_WORKER_CLIENT_PEM")
    with pytest.raises(
        ConfigurationError, match="dedicated KBS worker client"
    ):
        Settings.from_environment(absent)
    wrong_pin = environment(tmp_path)
    wrong_pin["KUBETEE_GAMMA_WORKER_CLIENT_CERT_SHA256"] = "b" * 64
    with pytest.raises(ConfigurationError, match="fingerprint mismatch"):
        Settings.from_environment(wrong_pin)
    wrong_role = environment(tmp_path)
    wrong_role["KUBETEE_GAMMA_WORKER_CLIENT_PEM"] = str(
        tmp_path / "worker.pem"
    )
    wrong_role["KUBETEE_GAMMA_WORKER_CLIENT_KEY"] = str(
        tmp_path / "worker.key"
    )
    wrong_role["KUBETEE_GAMMA_WORKER_CLIENT_CERT_SHA256"] = wrong_role[
        "KUBETEE_GAMMA_WORKER_CERT_SHA256"
    ]
    with pytest.raises(ConfigurationError, match="lacks clientAuth"):
        Settings.from_environment(wrong_role)
    foreign = environment(tmp_path)
    foreign["KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256"] = foreign[
        "KUBETEE_GAMMA_WORKER_CLIENT_CERT_SHA256"
    ]
    with pytest.raises(ConfigurationError, match="distinct"):
        Settings.from_environment(foreign)


def test_management_url_must_be_exact_cluster_https_origin(tmp_path):
    values = environment(tmp_path)
    with pytest.raises(ConfigurationError, match="HTTPS"):
        Settings.from_environment(
            dict(
                values,
                KUBETEE_GAMMA_MANAGEMENT_BASE_URL="http://litellm-gateway-mtls.litellm.svc.cluster.local:8443",
            )
        )
    with pytest.raises(ConfigurationError, match="HTTPS"):
        Settings.from_environment(
            dict(
                values,
                KUBETEE_GAMMA_MANAGEMENT_BASE_URL="https://litellm-gateway-mtls.litellm.svc.cluster.local:8443:4001",
            )
        )


async def request_tls(listener: socket.socket, root: Path, client_role: str):
    context = ssl.create_default_context(cafile=str(root / "projector.crt"))
    context.load_cert_chain(
        str(root / (client_role + ".crt")), str(root / (client_role + ".key"))
    )
    reader, writer = await asyncio.open_connection(
        "127.0.0.1",
        listener.getsockname()[1],
        ssl=context,
        server_hostname="gamma-funder.kubetee-ops.svc.cluster.local",
    )
    writer.write(
        b"GET /internal/v1/ready HTTP/1.1\r\nHost: internal\r\nConnection: close\r\n\r\n"
    )
    await writer.drain()
    headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
    body = await asyncio.wait_for(
        reader.readexactly(
            int(re.search(rb"content-length: (\d+)", headers, re.I).group(1))
        ),
        5,
    )
    writer.close()
    await writer.wait_closed()
    return headers, body


@pytest.mark.asyncio
async def test_four_directional_leaf_mtls_round_trip(tmp_path):
    values = environment(tmp_path)
    settings = Settings.from_environment(values)
    der = gateway_der(Settings.from_environment(environment(tmp_path)))
    app = synthetic_lifecycle(
        values,
        tmp_path=tmp_path,
        connect=connect_synthetic,
        create_store=lease_synthetic,
        create_chain=lambda *args: Candidate(),
        gateway_der=der,
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    verify_worker_start(
        settings,
        (tmp_path / "projector.crt").read_bytes(),
        (tmp_path / "worker.pem").read_bytes(),
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            http="worker.runtime:MTLSProofProtocol",
            timeout_keep_alive=1,
            ssl_certfile=str(tmp_path / "worker.pem"),
            ssl_keyfile=str(tmp_path / "worker.key"),
            ssl_ca_certs=str(tmp_path / "projector.crt"),
            ssl_cert_reqs=ssl.CERT_REQUIRED,
            log_level="error",
        )
    )
    server.capture_signals = lambda: contextlib.nullcontext()
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        await asyncio.sleep(0.15)
        headers, body = await request_tls(listener, tmp_path, "gateway-client")
        assert headers.startswith(b"HTTP/1.1 200 OK")
        assert json.loads(body) == {"ready": True}
        for role in ("worker-client", "worker-server"):
            try:
                headers, _ = await request_tls(listener, tmp_path, role)
            except (
                ssl.SSLError,
                ConnectionError,
                asyncio.IncompleteReadError,
            ):
                continue
            assert headers.startswith(b"HTTP/1.1 403 Forbidden")
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        listener.close()
    # The outbound socket's actual client identity is the fourth clientAuth leaf.
    from cryptography import x509

    leaf = x509.load_pem_x509_certificate(
        (tmp_path / settings.outbound_tls_files()[0]).read_bytes()
    )
    assert (
        hashlib.sha256(
            leaf.public_bytes(
                __import__(
                    "cryptography.hazmat.primitives.serialization",
                    fromlist=["Encoding"],
                ).Encoding.DER
            )
        ).hexdigest()
        == values["KUBETEE_GAMMA_WORKER_CLIENT_CERT_SHA256"]
    )


def test_factory_production_defaults_fail_closed(tmp_path):
    app = create_application(
        environment(tmp_path),
        connect=lambda settings: pytest.fail("Finney must not connect"),
        create_store=lambda settings: pytest.fail(
            "No Redis connection allowed"
        ),
        create_chain=lambda *args: pytest.fail(
            "missing realtime accounting certificate"
        ),
    )
    assert app is not None


def test_mainnet_spend_has_two_explicit_switches(tmp_path):
    value = environment(tmp_path)
    value.pop("KUBETEE_GAMMA_TEST")
    assert Settings.from_environment(value).signer is None
    value.update(
        KUBETEE_GAMMA_SPEND_ENABLED="1", KUBETEE_GAMMA_PROXY_DELEGATE_SS58=HK
    )
    with pytest.raises(MainnetSpendNotApproved):
        Settings.from_environment(value)
    value["KUBETEE_GAMMA_FINNEY_SPEND_APPROVED"] = "yes, approved by operator"
    assert Settings.from_environment(value).spender == HK


def test_management_client_has_no_general_master_credential():
    management = Management(
        httpx.AsyncClient(), "https://worker.invalid", "restricted-synthetic"
    )
    assert management.models is None and management.mcp_servers is None


def test_certificate_source_redacts_error_paths(tmp_path):
    values = environment(tmp_path)
    values["KUBETEE_GAMMA_PROJECTOR_PEM"] = str(tmp_path / "absent.crt")
    with pytest.raises(
        RuntimeError, match="KUBETEE_GAMMA_PROJECTOR_PEM"
    ) as error:
        Settings.from_environment(values)
    assert str(tmp_path) not in str(error.value)
    with pytest.raises(RuntimeError, match="KUBETEE_GAMMA_PROJECTOR_PEM"):
        Settings.from_environment(
            dict(
                values,
                KUBETEE_GAMMA_PROJECTOR_PEM=str(tmp_path / "absent.crt"),
            )
        )
    missing = environment(tmp_path)
    missing.pop("KUBETEE_GAMMA_PROJECTOR_PEM")
    with pytest.raises(
        RuntimeError, match="KUBETEE_GAMMA_PROJECTOR_PEM"
    ) as error:
        Settings.from_environment(missing)
    assert str(tmp_path) not in str(error.value)
    settings = Settings.from_environment(environment(tmp_path))
    der = gateway_der(Settings.from_environment(environment(tmp_path)))
    with pytest.raises(RuntimeError, match="operator-approved"):
        scoped_http_client(settings, b"wrong-cert")
    service = scoped_http_client(settings, der)
    assert "authorization" not in service.headers
    assert "x-kubetee-worker-proof" not in service.headers
    assert service.headers["user-agent"] == "gamma-reconciler-type22"
    asyncio.run(service.aclose())


@pytest.mark.asyncio
async def test_runtime_factory_starts_authenticates_and_cleans_up(tmp_path):
    values = environment(tmp_path)
    fingerprint = values["KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256"]
    bridge = issue_certificates(tmp_path)["gateway-client"][1]
    der = gateway_der(Settings.from_environment(environment(tmp_path)))
    candidate = Candidate()
    app = synthetic_lifecycle(
        values,
        tmp_path=tmp_path,
        connect=connect_synthetic,
        create_store=lease_synthetic,
        create_chain=lambda *args: candidate,
        gateway_der=der,
    )
    async with LifespanManager(app):
        assert candidate.preflight_calls == 1
        forwarded, called = [], []

        async def record(scope, receive, send):
            forwarded.append(dict(scope["headers"]))
            await ok_endpoint(scope, receive, send)

        middleware = DelegateProofMiddleware(record, fingerprint)

        async def send(message):
            called.append(message)

        async def receive():
            return {"type": "http.request"}

        class Transport:
            def get_extra_info(self, name):
                assert name == "ssl_object"
                return type(
                    "TLS", (), {"getpeercert": lambda self, binary: bridge}
                )()

        headers = [(b"x-kubetee-worker-proof", base64.b64encode(b"forged"))]
        scope = {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/internal/v1/ready",
            "query_string": b"",
            "headers": headers,
            "extensions": {"transport": Transport()},
        }
        await middleware(scope, receive, send)
        assert called[0]["status"] == 200
        assert (
            base64.b64decode(forwarded[-1][b"x-kubetee-worker-proof"])
            == bridge
        )
        with pytest.raises(TypeError, match="mTLSProofProtocol"):
            await middleware({**scope, "extensions": {}}, receive, send)
        denied = []

        async def denied_send(message):
            denied.append(message)

        await DelegateProofMiddleware(
            ok_endpoint, hashlib.sha256(b"other").hexdigest()
        )(scope, receive, denied_send)
        assert denied[0]["status"] == 403
        assert candidate.finalized_snapshot_calls == 0


@pytest.mark.asyncio
async def test_mtls_production_ready_route_authenticates_socket(tmp_path):
    values = environment(tmp_path)
    fingerprint = values["KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256"]
    service = WorkerService(
        Candidate(),
        lambda hotkey: None,
        object(),
        certificate_fingerprint=fingerprint,
        ready=True,
    )
    app = FastAPI()
    app.include_router(internal_router(service))
    app.add_middleware(DelegateProofMiddleware, fingerprint=fingerprint)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            http="worker.runtime:MTLSProofProtocol",
            timeout_keep_alive=1,
            ssl_certfile=str(tmp_path / "worker.pem"),
            ssl_keyfile=str(tmp_path / "worker.key"),
            ssl_cert_reqs=ssl.CERT_REQUIRED,
            ssl_ca_certs=str(tmp_path / "projector.crt"),
            log_level="error",
        )
    )
    server.capture_signals = lambda: contextlib.nullcontext()
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        await asyncio.sleep(0.15)
        headers, body = await request_tls(listener, tmp_path, "gateway-client")
        assert headers.startswith(b"HTTP/1.1 200 OK")
        assert json.loads(body) == {"ready": True}
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        listener.close()


@pytest.mark.asyncio
async def test_disabled_spend_skips_proxy_seed_and_disabled_balance_preflight(
    tmp_path,
):
    from worker.chain import GammaChain

    fetched, created = [], []

    async def fetch(resource):
        fetched.append(resource)
        return b"synthetic"

    env = environment(tmp_path)
    der = gateway_der(Settings.from_environment(environment(tmp_path)))
    app = synthetic_lifecycle(
        env,
        tmp_path=tmp_path,
        connect=connect_synthetic,
        create_store=lease_synthetic,
        create_chain=lambda *args: created.append(args) or Candidate(),
        gateway_der=der,
        fetch=fetch,
    )
    async with LifespanManager(app):
        assert fetched == []
        assert created[0][2] is None

    class Storage:
        class SubtensorModule:
            GammaEnabled, SubnetGammaEnabled, Services = (
                "gamma",
                "net90",
                "services",
            )

        class System:
            Account = "account"

        class Proxy:
            Proxies = "proxy"

    class Snapshot:
        def __init__(self):
            self.queries = []

        async def query(self, key, *args):
            self.queries.append(key)
            return True if key != "services" else None

        async def query_map(self, key, *args):
            self.queries.append(key)
            return iter(
                [(None, {"url": "https://llm.kubetee.ai", "spender": REAL})]
            )

        async def read(self, name):
            return {"oracle": "present", "blocks_since_last_feed": 0}

    class Client:
        def __init__(self):
            self._substrate, self.snapshot = self, Snapshot()

        async def finalized_block(self):
            return 1

        async def block_hash(self, height):
            return (
                "0x" + hashlib.sha256(str(height).encode()).hexdigest()
                if height
                else GENESIS
            )

        async def at(self, height):
            return self.snapshot

    chain = GammaChain(
        Client(), real_spender=REAL, delegate=REAL, genesis_hash=GENESIS
    )
    import bittensor as bt

    original = bt.storage
    bt.storage = Storage
    try:
        await chain.preflight()
        assert "account" not in chain.client.snapshot.queries
        assert "proxy" not in chain.client.snapshot.queries
    finally:
        bt.storage = original


@pytest.mark.asyncio
async def test_enabled_spend_fetches_only_configured_seed_resource(
    tmp_path, monkeypatch
):
    env = environment(tmp_path)
    env.update(
        KUBETEE_GAMMA_SPEND_ENABLED="1", KUBETEE_GAMMA_PROXY_DELEGATE_SS58=HK
    )
    fetched, created, signer = [], [], object()

    async def fetch(resource):
        fetched.append(resource)
        return b"synthetic delegate"

    monkeypatch.setattr(
        "worker.runtime.load_proxy_keypair",
        lambda raw, expected: (raw, expected) == (b"synthetic delegate", HK)
        and signer,
    )
    der = gateway_der(Settings.from_environment(environment(tmp_path)))
    app = synthetic_lifecycle(
        env,
        tmp_path=tmp_path,
        connect=connect_synthetic,
        create_store=lease_synthetic,
        create_chain=lambda *args: created.append(args) or Candidate(),
        gateway_der=der,
        fetch=fetch,
    )
    async with LifespanManager(app):
        assert fetched == [env["KUBETEE_GAMMA_KBS_PROXY_SEED"]]
        assert created[0][2] is signer


@pytest.mark.asyncio
async def test_startup_materializes_current_kbs_paths_in_guest_scratch(
    tmp_path, monkeypatch
):
    # Use a stable one-call directory; no other fixture aliases exist here.
    tmp_path = tmp_path / "bootstrap"
    tmp_path.mkdir()
    env = environment(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv(
        "KUBETEE_GAMMA_PROJECTOR_PEM", str(tmp_path / "run" / "ca.pem")
    )
    monkeypatch.setenv(
        "KUBETEE_GAMMA_CLIENT_PEM", str(tmp_path / "run" / "tls.crt")
    )
    monkeypatch.setenv(
        "KUBETEE_GAMMA_CLIENT_KEY", str(tmp_path / "run" / "tls.key")
    )
    requested = []
    material = {
        "default/eastwest-ca/ca.pem": (
            tmp_path / "projector.crt"
        ).read_bytes(),
        env["KUBETEE_GAMMA_KBS_CERT"]: (tmp_path / "worker.pem").read_bytes(),
        env["KUBETEE_GAMMA_KBS_KEY"]: (tmp_path / "worker.key").read_bytes(),
        env["KUBETEE_GAMMA_KBS_CLIENT_CERT"]: (
            tmp_path / "worker-client.crt"
        ).read_bytes(),
        env["KUBETEE_GAMMA_KBS_CLIENT_KEY"]: (
            tmp_path / "worker-client.key"
        ).read_bytes(),
    }

    async def fetch(resource):
        requested.append(resource)
        return material[resource]

    from worker.start import bootstrap

    ca, cert, key = await bootstrap(fetch, scratch_directory=tmp_path / "run")
    assert (ca, cert, key) == tuple(
        str(tmp_path / "run" / name)
        for name in ("ca.pem", "tls.crt", "tls.key")
    )
    # Only its CA/server leaf and outbound client leaf belong in bootstrap.
    # The gateway server leaf is fetched in create_application; client
    # materialization is
    # independently pinned by materialize_kbs_identity using the fourth leaf.
    assert requested == [
        "default/eastwest-ca/ca.pem",
        env["KUBETEE_GAMMA_KBS_CERT"],
        env["KUBETEE_GAMMA_KBS_KEY"],
        env["KUBETEE_GAMMA_KBS_CLIENT_CERT"],
        env["KUBETEE_GAMMA_KBS_CLIENT_KEY"],
    ]
    assert env["KUBETEE_GAMMA_KBS_PROXY_SEED"] not in requested
    assert __import__("os").environ["KUBETEE_GAMMA_WORKER_CLIENT_PEM"] == str(
        tmp_path / "run" / "client.crt"
    )
    assert (tmp_path / "run" / "client.crt").read_bytes() == (
        tmp_path / "worker-client.crt"
    ).read_bytes()
    assert (tmp_path / "run" / "client.key").stat().st_mode & 0o777 == 0o600


from worker.runtime import materialize_kbs_identity


def synthetic_lifecycle(values, *, tmp_path, **kwargs):
    async def request(request):
        if (request.method, request.url.path) == ("GET", "/internal/v1/ready"):
            return httpx.Response(200, json={"ready": True})
        if (request.method, request.url.path) == (
            "GET",
            "/internal/v1/gamma/keys",
        ):
            return httpx.Response(200, json={"keys": []})
        raise AssertionError(
            f"unexpected synthetic gateway request {request.url}"
        )

    kwargs.setdefault("management_transport", httpx.MockTransport(request))
    return create_application(values, **kwargs)


async def connect_synthetic(settings):
    class Client:
        closed = False

        async def close(self):
            self.closed = True

    return Client()


async def lease_synthetic(settings):
    class Lease:
        tokens = {}

        async def acquire(self, hotkey):
            return False

        async def release(self, hotkey):
            pass

    return Lease()


async def ok_endpoint(scope, receive, send):
    from starlette.responses import JSONResponse

    await JSONResponse({"ready": False})(scope, receive, send)
