"""Release wiring tests use fake transports/secrets, never a Finney connection."""
from __future__ import annotations

import base64
import hashlib
import re
import asyncio
from pathlib import Path

import httpx
import pytest

from worker.management import Management
from worker.protocol import GENESIS
from worker.runtime import (
    MainnetSpendNotApproved, ConfigurationError, Settings, create_application, load_proxy_keypair, scoped_http_client,
    DelegateProofMiddleware,
)
from worker.service import WorkerService
from fixtures import HK, REAL


def provider(tmp_path: Path):
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "litellm-gateway-mtls.litellm.svc.cluster.local")])
    now = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)
    cert = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(
        x509.random_serial_number()).not_valid_before(now).not_valid_after(now + timedelta(hours=1)).add_extension(
        x509.SubjectAlternativeName([x509.DNSName("litellm-gateway-mtls.litellm.svc.cluster.local")]), critical=False).sign(key, hashes.SHA256())
    (tmp_path / "projector.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "worker.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "worker.key").write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    import hashlib
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest(), cert.public_bytes(serialization.Encoding.DER)


def environment(tmp_path: Path) -> dict[str, str]:
    fingerprint, _ = provider(tmp_path)
    return {
        "KUBETEE_GAMMA_WORKER": "1",
        "KUBETEE_GAMMA_TEST": "1",
        "KUBETEE_GAMMA_SPEND_ENABLED": "0",
        "KUBETEE_GAMMA_NETWORK": "finney",
        "KUBETEE_GAMMA_REAL_SPENDER_SS58": REAL,
        "KUBETEE_GAMMA_MAX_FEE_TAO": "0.001",
        "KUBETEE_GAMMA_GATEWAY_CERT_SHA256": fingerprint,
        "KUBETEE_GAMMA_WORKER_CERT_SHA256": fingerprint,
        # Synthetic-only distinct caller; the dedicated mTLS integration test
        # uses actual separate leaves instead of colliding these identities.
        "KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256": "a" * 64,
        "KUBETEE_GAMMA_PROXY_DELEGATE_SS58": "",
        "KUBETEE_GAMMA_MODELS": "z-ai/glm-5.3",
        "KUBETEE_GAMMA_MANAGEMENT_BASE_URL": "https://litellm-gateway-mtls.litellm.svc.cluster.local:8443",
        "KUBETEE_GAMMA_KBS_CA": "default/eastwest-ca/ca.pem",
        "KUBETEE_GAMMA_KBS_CERT": "default/gamma-spend-proxy/tls.crt",
        "KUBETEE_GAMMA_KBS_KEY": "default/gamma-spend-proxy/tls.key",
        "KUBETEE_GAMMA_KBS_PROXY_SEED": "default/gamma-spend-proxy/seed",
        "KUBETEE_GAMMA_PROJECTOR_PEM": str(tmp_path / "projector.pem"),
        "KUBETEE_GAMMA_CLIENT_PEM": str(tmp_path / "worker.pem"),
        "KUBETEE_GAMMA_CLIENT_KEY": str(tmp_path / "worker.key"),
    }


def test_scoped_client_maps_service_onto_private_listener(monkeypatch):
    # Production simply connects Service:8443; K8s maps to gateway pod :4001.
    # A mocked transport validates TLS URL/path, auth construction and
    # the helper without pretending the caller needs to rewrite the URL port.
    observed = []
    async def request(self, method, url, **kwargs):
        observed.append(str(url))
        return httpx.Response(200, json={"ready": True}, request=httpx.Request("GET", str(url)))
    monkeypatch.setattr(httpx.AsyncClient, "request", request)
    client = Management(httpx.AsyncClient(verify=True),
                        "https://litellm-gateway-mtls.litellm.svc.cluster.local:8443",
                        "mTLS:gamma-reconciler-type22")
    assert asyncio.run(client.ready())
    assert observed == [
        "https://litellm-gateway-mtls.litellm.svc.cluster.local:8443/internal/v1/ready"]


async def success(*args, **kwargs):
    return httpx.Response(200, json={"ready": True}, request=httpx.Request("GET", "http://cdh.invalid"))


def test_worker_requires_explicit_distinct_gateway_client_fingerprint(tmp_path):
    values = environment(tmp_path)
    values["KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256"] = "a" * 64
    settings = Settings.from_environment(values)
    assert settings.gateway_client_fingerprint == "a" * 64
    assert settings.worker_fingerprint != settings.gateway_client_fingerprint
    missing_client = environment(tmp_path)
    missing_client.pop("KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256")
    with pytest.raises(ConfigurationError, match="client TLS leaf"):
        Settings.from_environment(missing_client)
    server, server_der = provider(tmp_path)
    settings = Settings.from_environment(dict(values,
        KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256="b" * 64,
        KUBETEE_GAMMA_GATEWAY_CERT_SHA256=hashlib.sha256(server_der).hexdigest(),
        KUBETEE_GAMMA_WORKER_CERT_SHA256=server))
    assert settings.worker_fingerprint == server
    service = scoped_http_client(settings, server_der)
    assert "x-kubetee-worker-proof" not in service.headers
    asyncio.run(service.aclose())


def test_management_url_must_be_exact_cluster_https_origin(tmp_path):
    values = dict(environment(tmp_path), KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256="a" * 64)
    with pytest.raises(ConfigurationError, match="HTTPS"):
        Settings.from_environment(dict(values,
            KUBETEE_GAMMA_MANAGEMENT_BASE_URL="http://litellm-gateway-mtls.litellm.svc.cluster.local:8443"))
    with pytest.raises(ConfigurationError, match="HTTPS"):
        Settings.from_environment(dict(environment(tmp_path),
            KUBETEE_GAMMA_MANAGEMENT_BASE_URL="https://litellm-gateway-mtls.litellm.svc.cluster.local:8443:4001"))


@pytest.mark.asyncio
async def test_three_distinct_leaf_mtls_round_trip(tmp_path):
    import ssl
    import socket
    import uvicorn
    import json
    from fastapi import FastAPI
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    def identity(cn, usage=None, san=None, ca=None, ca_key=None):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        builder = (x509.CertificateBuilder().subject_name(name)
            .issuer_name(ca.subject if ca is not None else name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.BasicConstraints(ca=ca is None, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False))
        if ca is None: ca_key = key
        builder = builder.add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        builder = builder.add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=usage is not None,
            key_cert_sign=ca is None,
            crl_sign=ca is None, content_commitment=False, data_encipherment=False,
            key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        if usage is not None:
            builder = builder.add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
        # The authority and subject identifiers above distinguish the CA chain;
        # no CSR/client extension is silently inherited from another leaf.
        if san is not None:
            builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
        return builder.sign(ca_key, hashes.SHA256()), key
    ca_cert, ca_key = identity("gamma-only-roundtrip-ca")
    gateway_server, gateway_server_key = identity("gateway-server", ExtendedKeyUsageOID.SERVER_AUTH,
        "litellm-gateway-mtls.litellm.svc.cluster.local", ca_cert, ca_key)
    gateway_client, gateway_client_key = identity("gateway-client", ExtendedKeyUsageOID.CLIENT_AUTH, None, ca_cert, ca_key)
    worker_server, worker_server_key = identity("worker-server", ExtendedKeyUsageOID.SERVER_AUTH,
        "gamma-funder.kubetee-ops.svc.cluster.local", ca_cert, ca_key)
    wrong_client, wrong_client_key = identity("wrong-client", ExtendedKeyUsageOID.CLIENT_AUTH, None, ca_cert, ca_key)
    def write(name, cert, key=None):
        (tmp_path / (name + ".crt")).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        if key is not None:
            (tmp_path / (name + ".key")).write_bytes(key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    for name, cert, key in (("ca", ca_cert, None), ("gw-server", gateway_server, gateway_server_key),
                            ("gw-client", gateway_client, gateway_client_key),
                            ("worker-server", worker_server, worker_server_key),
                            ("wrong-client", wrong_client, wrong_client_key)):
        write(name, cert, key)
    gateway_der = gateway_server.public_bytes(serialization.Encoding.DER)
    worker_der = worker_server.public_bytes(serialization.Encoding.DER)
    values = environment(tmp_path)
    values.update(KUBETEE_GAMMA_GATEWAY_CERT_SHA256=hashlib.sha256(gateway_der).hexdigest(),
        KUBETEE_GAMMA_WORKER_CERT_SHA256=hashlib.sha256(worker_der).hexdigest(),
        KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256=hashlib.sha256(gateway_client.public_bytes(serialization.Encoding.DER)).hexdigest())
    class Candidate:
        real_spender = REAL
        async def preflight(self): pass
        async def finalized_snapshot(self, hotkey): return None
    app = create_application(values, connect=connect_synthetic,
        create_store=lease_synthetic, create_chain=lambda *a: Candidate(), gateway_der=gateway_der)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0)); listener.listen()
    write("tls", worker_server, worker_server_key)
    settings = Settings.from_environment(values)
    ca_data = (tmp_path / "ca.crt").read_bytes()
    from worker.runtime import verify_worker_start
    verify_worker_start(settings, ca_data, (tmp_path / "tls.crt").read_bytes())
    import contextlib
    server = uvicorn.Server(uvicorn.Config(app, http="worker.runtime:MTLSProofProtocol",
        timeout_keep_alive=1, ssl_certfile=str(tmp_path / "tls.crt"),
        ssl_keyfile=str(tmp_path / "tls.key"),
        ssl_ca_certs=str(tmp_path / "ca.crt"), ssl_cert_reqs=ssl.CERT_REQUIRED, log_level="error"))
    server.capture_signals = lambda: contextlib.nullcontext()
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        await asyncio.sleep(.15)
        async def request(name):
            context = ssl.create_default_context(cafile=str(tmp_path / "ca.crt"))
            context.load_cert_chain(str(tmp_path / (name + ".crt")), str(tmp_path / (name + ".key")))
            reader, writer = await asyncio.open_connection("127.0.0.1", listener.getsockname()[1],
                ssl=context, server_hostname="gamma-funder.kubetee-ops.svc.cluster.local")
            writer.write(b"GET /internal/v1/ready HTTP/1.1\r\nHost: internal\r\nConnection: close\r\n\r\n")
            await writer.drain()
            headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            length = int(re.search(br"content-length: (\d+)", headers, re.I).group(1))
            body = await asyncio.wait_for(reader.readexactly(length), 5)
            writer.close(); await writer.wait_closed()
            return headers, body
        headers, body = await request("gw-client")
        assert headers.startswith(b"HTTP/1.1 200 OK"), headers
        assert json.loads(body) == {"ready": True}
        service = app.router.lifespan_context
        assert hashlib.sha256(worker_der).hexdigest() == settings.worker_fingerprint
        assert hashlib.sha256(worker_der).hexdigest() != settings.gateway_client_fingerprint
        assert hashlib.sha256(gateway_der).hexdigest() != settings.gateway_client_fingerprint
        # Any other approved-CA client—including this worker presenting its
        # serverAuth leaf—is rejected at the gateway-client identity boundary.
        # A client-purpose mismatch may terminate the TLS handshake before an
        # HTTP response can be sent; it must not be converted into a 200.
        for caller in ("gw-server", "wrong-client"):
            try:
                headers, _ = await request(caller)
            except (ssl.SSLError, ConnectionError, asyncio.IncompleteReadError):
                continue
            assert headers.startswith(b"HTTP/1.1 403 Forbidden"), headers
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=5)
        listener.close()


async def test_factory_production_defaults_fail_closed(tmp_path):
    issued = []
    app = create_application(
        environment(tmp_path),
        connect=lambda settings: pytest.fail("Finney must not connect for a production-default factory test"),
        create_store=lambda settings: pytest.fail("No Redis connection allowed"),
        create_chain=lambda settings, client, signer: pytest.fail("missing realtime accounting certificate"),
    )
    assert app is not None


def test_mainnet_spend_has_two_explicit_switches(tmp_path):
    value = environment(tmp_path)
    value.pop("KUBETEE_GAMMA_TEST")
    assert Settings.from_environment(value).signer is None
    value["KUBETEE_GAMMA_SPEND_ENABLED"] = "1"
    value["KUBETEE_GAMMA_PROXY_DELEGATE_SS58"] = HK
    with pytest.raises(MainnetSpendNotApproved):
        Settings.from_environment(value)
    value["KUBETEE_GAMMA_FINNEY_SPEND_APPROVED"] = "yes, approved by operator"
    assert Settings.from_environment(value).spender == HK


def test_management_client_has_no_general_master_credential():
    management = Management(httpx.AsyncClient(), "https://worker.invalid", "restricted-synthetic")
    assert management.models is None and management.mcp_servers is None


def test_certificate_source_redacts_error_paths(tmp_path, monkeypatch):
    for name in ("projector.pem", "worker.pem", "worker.key"):
        (tmp_path / name).write_text("synthetic material")
    values = environment(tmp_path)
    values["KUBETEE_GAMMA_PROJECTOR_PEM"] = str(tmp_path / "absent.pem")
    with pytest.raises(RuntimeError, match="KUBETEE_GAMMA_PROJECTOR_PEM") as error:
        Settings.from_environment(values)
    assert str(tmp_path) not in str(error.value)
    assert "KUBETEE_GAMMA_PROJECTOR_PEM" in str(error.value)
    with pytest.raises(RuntimeError, match="KUBETEE_GAMMA_PROJECTOR_PEM"):
        Settings.from_environment(dict(values, KUBETEE_GAMMA_PROJECTOR_PEM=str(tmp_path / "absent.pem")))
    no_source = dict(values)
    no_source.pop("KUBETEE_GAMMA_PROJECTOR_PEM")
    with pytest.raises(RuntimeError, match="KUBETEE_GAMMA_PROJECTOR_PEM") as error:
        Settings.from_environment(no_source)
    assert str(tmp_path) not in str(error.value)
    values["KUBETEE_GAMMA_PROJECTOR_PEM"] = str(tmp_path / "projector.pem")
    settings = Settings.from_environment(values)
    assert settings.signer is None
    _, der = provider(tmp_path)
    with pytest.raises(RuntimeError, match="operator-approved"):
        bad = b"another-certificate"
        scoped_http_client(settings, bad)
    match, good = provider(tmp_path)
    matching = Settings.from_environment(dict(values, KUBETEE_GAMMA_GATEWAY_CERT_SHA256=match))
    service = scoped_http_client(matching, good)
    assert isinstance(service, httpx.AsyncClient)
    assert "authorization" not in service.headers
    assert "x-kubetee-worker-proof" not in service.headers
    assert service.headers["user-agent"] == "gamma-reconciler-type22"
    asyncio.run(service.aclose())


@pytest.mark.asyncio
async def test_runtime_factory_starts_authenticates_and_cleans_up(tmp_path):
    from worker.service import WorkerService
    fingerprint, der = provider(tmp_path)
    values = environment(tmp_path)
    values["KUBETEE_GAMMA_GATEWAY_CERT_SHA256"] = fingerprint
    class Candidate:
        real_spender = REAL
        client = None
        preflight_calls = 0
        finalized_snapshot_calls = 0
        async def preflight(self): self.preflight_calls += 1
        async def finalized_snapshot(self, hotkey): self.finalized_snapshot_calls += 1; return 1, "0x"+"1"*64, None
    candidate = Candidate()
    app = create_application(values, connect=connect_synthetic,
        create_store=lease_synthetic, create_chain=lambda *a: candidate, gateway_der=der)
    from asgi_lifespan import LifespanManager
    async with LifespanManager(app) as manager:
        assert candidate.preflight_calls == 1
        response = httpx.Response(403)
        forwarded = []
        asyncio.get_running_loop()  # Validate active test loop only; mocks stay local.
        from starlette.responses import JSONResponse
        async def record(scope, receive, send):
            forwarded.append(dict(scope["headers"]))
            await ok_endpoint(scope, receive, send)
        middleware = DelegateProofMiddleware(record, fingerprint)
        called = []
        async def send(message): called.append(message)
        async def receive(): return {"type": "http.request"}
        class Transport:
            def get_extra_info(self, name):
                assert name == "ssl_object"
                return type("TLS", (), {"getpeercert": lambda _self, binary: der})()
        untrusted = {"type": "http", "method": "GET", "scheme": "https", "path": "/internal/v1/ready",
                     "query_string": b"", "headers": [(b"x-kubetee-worker-proof", base64.b64encode(der))], "extensions": {}}
        with pytest.raises(TypeError, match="mTLSProofProtocol"):
            await middleware(untrusted, receive, send)
        real = {**untrusted, "extensions": {"transport": Transport()}}
        await DelegateProofMiddleware(ok_endpoint, hashlib.sha256(b"other").hexdigest())(real, receive, send)
        assert called[0]["status"] == 403
        called.clear()
        await middleware(real, receive, send)
        assert called[0]["status"] == 200
        assert candidate.finalized_snapshot_calls == 0
        spoofed = {**real, "headers": [(b"x-kubetee-worker-proof", base64.b64encode(b"forged"))]}
        await middleware(spoofed, receive, send)
        proof = forwarded[-1][b"x-kubetee-worker-proof"]
        import json as json_module
        assert hashlib.sha256(base64.b64decode(proof)).hexdigest() == fingerprint
        class NoTLS:
            def get_extra_info(self, name): return None
        with pytest.raises(RuntimeError, match="verified transport"):
            await middleware({**untrusted, "extensions": {"transport": NoTLS()}}, receive, send)


@pytest.mark.asyncio
async def test_mtls_production_ready_route_authenticates_socket(tmp_path):
    import json
    import ssl
    import socket
    import uvicorn
    from fastapi import FastAPI
    from worker.protocol import internal_router
    fingerprint, _ = provider(tmp_path)
    class Candidate:
        real_spender = REAL
    service = WorkerService(Candidate(), lambda hotkey: None, object(), certificate_fingerprint=fingerprint, ready=True)
    app = FastAPI()
    app.include_router(internal_router(service))
    app.add_middleware(DelegateProofMiddleware, fingerprint=fingerprint)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    server = uvicorn.Server(uvicorn.Config(app,
        http="worker.runtime:MTLSProofProtocol", timeout_keep_alive=1,
        ssl_certfile=str(tmp_path / "worker.pem"), ssl_keyfile=str(tmp_path / "worker.key"),
        ssl_cert_reqs=ssl.CERT_REQUIRED, ssl_ca_certs=str(tmp_path / "projector.pem"), log_level="error"))
    server.capture_signals = lambda: __import__('contextlib').nullcontext()
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        await asyncio.sleep(.15)
        context = ssl.create_default_context(cafile=str(tmp_path / "projector.pem"))
        context.load_cert_chain(str(tmp_path / "worker.pem"), str(tmp_path / "worker.key"))
        reader, writer = await asyncio.open_connection("127.0.0.1", listener.getsockname()[1], ssl=context,
            server_hostname="litellm-gateway-mtls.litellm.svc.cluster.local")
        writer.write(b"GET /internal/v1/ready HTTP/1.1\r\nHost: internal\r\nConnection: close\r\nX-Kubetee-Worker-Proof: forged\r\n\r\n")
        await writer.drain()
        headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
        assert headers.startswith(b"HTTP/1.1 200 OK"), headers
        length = int(re.search(br"content-length: (\d+)", headers, re.I).group(1))
        assert json.loads(await asyncio.wait_for(reader.readexactly(length), timeout=5)) == {"ready": True}
        writer.close()
        await writer.wait_closed()
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=5)
        listener.close()


@pytest.mark.asyncio
async def test_disabled_spend_skips_proxy_seed_and_disabled_balance_preflight(tmp_path):
    """Readiness observes registration/oracle, never a delegate fee balance."""
    from worker.chain import GammaChain
    from fixtures import NativeStore
    fetched = []
    created = []
    env = environment(tmp_path)
    fingerprint, der = provider(tmp_path)
    env["KUBETEE_GAMMA_GATEWAY_CERT_SHA256"] = fingerprint
    async def fetch(resource):
        fetched.append(resource)
        return b"synthetic"
    class Candidate:
        real_spender = REAL
        delegate = REAL
        async def preflight(self): pass
        async def finalized_snapshot(self, hotkey): return None
    app = create_application(env, connect=connect_synthetic,
        create_store=lease_synthetic,
        create_chain=lambda *args: created.append(args) or Candidate(),
        gateway_der=der, fetch=fetch)
    from asgi_lifespan import LifespanManager
    async with LifespanManager(app):
        assert fetched == []
        assert created[0][2] is None

    class Storage:
        class SubtensorModule:
            GammaEnabled = "gamma"
            SubnetGammaEnabled = "net90"
            Services = "services"
        class System:
            Account = "account"
        class Proxy:
            Proxies = "proxy"
    class Snapshot:
        def __init__(self): self.queries = []
        async def query(self, key, *args):
            self.queries.append(key); return True if key != "services" else None
        async def query_map(self, key, *args):
            self.queries.append(key); return iter([(None, {"url": "https://llm.kubetee.ai", "spender": REAL})])
        async def read(self, name): return {"oracle": "present", "blocks_since_last_feed": 0}
    class Client:
        def __init__(self):
            self._substrate = self
            self.snapshot = Snapshot()
        async def finalized_block(self): return 1
        async def block_hash(self, height): return "0x" + hashlib.sha256(str(height).encode()).hexdigest() if height else GENESIS
        async def at(self, height): return self.snapshot
    chain = GammaChain(Client(), real_spender=REAL, delegate=REAL, genesis_hash=GENESIS)
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
async def test_enabled_spend_fetches_only_configured_seed_resource(tmp_path, monkeypatch):
    env = environment(tmp_path)
    env.update(KUBETEE_GAMMA_SPEND_ENABLED="1", KUBETEE_GAMMA_PROXY_DELEGATE_SS58=HK)
    fetched = []
    created = []
    signer = object()
    fingerprint, der = provider(tmp_path)
    env["KUBETEE_GAMMA_GATEWAY_CERT_SHA256"] = fingerprint
    async def fetch(resource):
        fetched.append(resource)
        return b"synthetic delegate"
    monkeypatch.setattr("worker.runtime.load_proxy_keypair", lambda raw, expected: (
        (raw, expected) == (b"synthetic delegate", HK) and signer))
    class Candidate:
        real_spender = REAL
        async def preflight(self): pass
        async def finalized_snapshot(self, hotkey): return None
    from fixtures import NativeStore
    app = create_application(env, connect=connect_synthetic, create_store=lease_synthetic,
        create_chain=lambda *args: created.append(args) or Candidate(), gateway_der=der, fetch=fetch)
    from asgi_lifespan import LifespanManager
    async with LifespanManager(app):
        assert fetched == ["default/gamma-spend-proxy/seed"]
        assert created[0][2] is signer


@pytest.mark.asyncio
async def test_startup_materializes_current_kbs_paths_in_guest_scratch(tmp_path, monkeypatch):
    env = environment(tmp_path)
    for key, value in env.items(): monkeypatch.setenv(key, value)
    monkeypatch.setenv("KUBETEE_GAMMA_PROJECTOR_PEM", str(tmp_path / "run" / "ca.pem"))
    monkeypatch.setenv("KUBETEE_GAMMA_CLIENT_PEM", str(tmp_path / "run" / "tls.crt"))
    monkeypatch.setenv("KUBETEE_GAMMA_CLIENT_KEY", str(tmp_path / "run" / "tls.key"))
    requested = []
    async def fetch(resource):
        requested.append(resource)
        if resource.endswith("tls.key"): return (tmp_path / "worker.key").read_bytes()
        return (tmp_path / "worker.pem").read_bytes()
    from worker.start import bootstrap
    ca, cert, key = await bootstrap(fetch)
    assert (ca, cert, key) == tuple(str(tmp_path / "run" / name) for name in ("ca.pem", "tls.crt", "tls.key"))
    assert requested == ["default/eastwest-ca/ca.pem", "default/gamma-spend-proxy/tls.crt",
                         "default/gamma-spend-proxy/tls.key"]
    assert "default/gamma-spend-proxy/seed" not in requested


async def connect_synthetic(settings):
    class Client:
        closed = False
        async def close(self): self.closed = True
    return Client()


async def lease_synthetic(settings):
    class Lease:  # Test adapter already implements the production lease API.
        tokens = {}
        async def acquire(self, hotkey): return False
        async def release(self, hotkey): pass
    return Lease()


async def ok_endpoint(scope, receive, send):
    from starlette.responses import JSONResponse
    await JSONResponse({"ready": False})(scope, receive, send)
