"""Process wiring for the isolated, attested worker.

Spend is off by default. Finney requires BOTH KUBETEE_GAMMA_SPEND_ENABLED=1
and KUBETEE_GAMMA_FINNEY_SPEND_APPROVED=1; test-only settings never enable
production funding. Tests inject transports, never these approval switches.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI
from pydantic import ValidationError

from .chain import GammaChain
from .management import Management
from .protocol import GENESIS, internal_router, ss58_address
from .reconciler import Reconciler
from .service import WorkerService


class ConfigurationError(RuntimeError):
    pass


class MainnetSpendNotApproved(ConfigurationError):
    pass


def flag(env, name: str) -> bool:
    return env.get(name, "0").strip().lower() in {"1", "true"}


async def certificate_material(name: str) -> bytes:
    """Read only the two dedicated in-guest KBS resources, with no fallback."""
    url = "http://127.0.0.1:8006/cdh/resource/" + name
    async with httpx.AsyncClient(timeout=10) as client:
        for attempt in range(30):
            if attempt:
                await asyncio.sleep(2)
            try:
                response = await client.get(url)
                if response.status_code == 200 and response.content:
                    return response.content
            except httpx.HTTPError:
                continue
    raise ConfigurationError("attested KBS resource unavailable")


def load_proxy_keypair(raw: bytes, expected: str):
    """Ephemeral SR25519 GammaSpend delegate, never the service real key."""
    import bittensor as bt
    from bittensor_core import Keypair

    text = raw.decode().strip()
    try:
        if text.startswith("0x"):
            signer = Keypair.create_from_seed(bytes.fromhex(text[2:]), crypto_type=bt.CRYPTO_SR25519)
        elif len(text) == 64:
            signer = Keypair.create_from_seed(bytes.fromhex(text), crypto_type=bt.CRYPTO_SR25519)
        else:
            signer = Keypair.create_from_mnemonic(text, crypto_type=bt.CRYPTO_SR25519)
    except (ValueError, TypeError) as exc:
        raise ConfigurationError("GammaSpend delegate material rejected") from exc
    if signer.ss58_address != expected:
        raise ConfigurationError("GammaSpend delegate is not the configured proxy address")
    return signer


@dataclass(frozen=True)
class Settings:
    real_spender: str
    gateway_fingerprint: str
    management_url: str
    certificate_files: tuple[str, str, str]
    network: str
    fee_cap: str
    models: tuple[str, ...]
    mcp_servers: tuple[str, ...] | None
    worker_fingerprint: str
    gateway_client_fingerprint: str
    spender: Any
    signer: Any
    test: bool
    spend_enabled: bool

    @classmethod
    def from_environment(cls, env) -> "Settings":
        if not flag(env, "KUBETEE_GAMMA_WORKER"):
            raise ConfigurationError("KUBETEE_GAMMA_WORKER=1 is required; no enabled-by-default worker")
        if env.get("KUBETEE_GAMMA_NETWORK", "finney") != "finney":
            raise ConfigurationError("only exact Finney network is accepted")
        real = env.get("KUBETEE_GAMMA_REAL_SPENDER_SS58", "")
        ss58_address(real)
        fingerprint = env.get("KUBETEE_GAMMA_GATEWAY_CERT_SHA256", "")
        if len(fingerprint) != 64 or not all(c in "0123456789abcdef" for c in fingerprint):
            raise ConfigurationError("exact gateway TLS leaf certificate SHA256 is required")
        worker_fingerprint = env.get("KUBETEE_GAMMA_WORKER_CERT_SHA256", "")
        if len(worker_fingerprint) != 64 or not all(c in "0123456789abcdef" for c in worker_fingerprint):
            raise ConfigurationError("exact worker TLS leaf certificate SHA256 is required")
        client_fingerprint = env.get("KUBETEE_GAMMA_GATEWAY_CLIENT_CERT_SHA256", "")
        if len(client_fingerprint) != 64 or not all(c in "0123456789abcdef" for c in client_fingerprint):
            raise ConfigurationError("exact gateway client TLS leaf fingerprint required")
        if client_fingerprint in {fingerprint, worker_fingerprint}:
            raise ConfigurationError("gateway client, server and worker must be separate TLS identities")
        models = tuple(filter(None, env.get("KUBETEE_GAMMA_MODELS", "").split(",")))
        if not models or len(set(models)) != len(models):
            raise ConfigurationError("one or more explicit restricted Gamma models required")
        mcp = tuple(filter(None, env.get("KUBETEE_GAMMA_MCP_SERVERS", "").split(","))) or None
        url = env.get("KUBETEE_GAMMA_MANAGEMENT_BASE_URL", "")
        parsed_url = urlsplit(url)
        try:
            port = parsed_url.port or 443
        except ValueError as exc:
            raise ConfigurationError("invalid cluster-internal gateway HTTPS port") from exc
        if (url != "https://litellm-gateway-mtls.litellm.svc.cluster.local:8443"
                or parsed_url.scheme != "https"
                or parsed_url.hostname != "litellm-gateway-mtls.litellm.svc.cluster.local"
                or parsed_url.username or parsed_url.password or parsed_url.query
                or parsed_url.fragment or parsed_url.path.rstrip("/") or port != 8443):
            raise ConfigurationError("exact private Gamma gateway mTLS HTTPS ClusterIP origin required")
        test = flag(env, "KUBETEE_GAMMA_TEST")
        spend = flag(env, "KUBETEE_GAMMA_SPEND_ENABLED")
        if spend and not test and env.get("KUBETEE_GAMMA_FINNEY_SPEND_APPROVED", "") != "yes, approved by operator":
            raise MainnetSpendNotApproved("Finney spend requires separate explicit operator approval")
        if not test and any(flag(env, name) for name in ("KUBETEE_GAMMA_INJECT", "KUBETEE_GAMMA_MOCK")):
            raise ConfigurationError("mock capabilities forbidden outside synthetic tests")
        fee = env.get("KUBETEE_GAMMA_MAX_FEE_TAO", "")
        try:
            if not fee or Decimal(fee) <= 0:
                raise ConfigurationError("positive bounded GammaSpend fee cap required")
        except InvalidOperation as exc:
            raise ConfigurationError("invalid bounded fee cap") from exc
        delegate = env.get("KUBETEE_GAMMA_PROXY_DELEGATE_SS58", "")
        if spend:
            ss58_address(delegate)
        else:
            delegate = ""
        for name in ("KUBETEE_GAMMA_KBS_CA", "KUBETEE_GAMMA_KBS_CERT", "KUBETEE_GAMMA_KBS_KEY", "KUBETEE_GAMMA_KBS_PROXY_SEED"):
            if not env.get(name) or not env[name].startswith("default/"):
                raise ConfigurationError("in-guest KBS resource paths must be inside default/")
            if not env.get(name):
                raise ConfigurationError("in-guest KBS CA/certificate/key resource paths required")
        if any(variable not in env for variable in ("KUBETEE_GAMMA_PROJECTOR_PEM", "KUBETEE_GAMMA_CLIENT_PEM", "KUBETEE_GAMMA_CLIENT_KEY")):
            raise ConfigurationError("KUBETEE_GAMMA_PROJECTOR_PEM and worker KBS certificate resources missing: attested startup required")
        import os.path
        if any(not os.path.isfile(env[name]) for name in ("KUBETEE_GAMMA_PROJECTOR_PEM", "KUBETEE_GAMMA_CLIENT_PEM", "KUBETEE_GAMMA_CLIENT_KEY")):
            raise ConfigurationError("KUBETEE_GAMMA_PROJECTOR_PEM and worker KBS certificate resources missing: attested startup required")
        material = (env["KUBETEE_GAMMA_PROJECTOR_PEM"], env["KUBETEE_GAMMA_CLIENT_PEM"], env["KUBETEE_GAMMA_CLIENT_KEY"])
        return cls(real, fingerprint, url, material, env["KUBETEE_GAMMA_NETWORK"],
                   fee, models, mcp, worker_fingerprint, client_fingerprint,
                   delegate, None, test, spend)


from cryptography import x509
from cryptography.hazmat.primitives import serialization


import socket
import ssl


def pinned_gateway_certificate(settings: Settings) -> bytes:
    ca, cert, key = settings.certificate_files
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca)
    context.load_cert_chain(cert, key)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    address = urlsplit(settings.management_url)
    with socket.create_connection((address.hostname, address.port or 443), 10) as raw:
        with context.wrap_socket(raw, server_hostname=address.hostname) as tls:
            der = tls.getpeercert(True)
    if hashlib.sha256(der).hexdigest() != settings.gateway_fingerprint:
        raise ConfigurationError("gateway TLS certificate does not match measured leaf")
    return der


def verify_worker_start(settings: Settings, ca_chain: bytes, certificate: bytes) -> bytes:
    """No unverified filesystem secret can select an alternate identity."""
    ca = x509.load_pem_x509_certificate(ca_chain)
    leaf = x509.load_pem_x509_certificate(certificate)
    if not ca_chain.startswith(b"-----BEGIN CERTIFICATE-----"):
        raise ConfigurationError("unrecognized KBS certificate material")
    leaf_der = leaf.public_bytes(serialization.Encoding.DER)
    if hashlib.sha256(leaf_der).hexdigest() != settings.worker_fingerprint:
        raise ConfigurationError("KBS worker certificate fingerprint mismatch")
    return leaf_der


async def materialize_kbs_identity(env=os.environ, fetch=certificate_material):
    """CDH/Guest scratch only; filesystem mounts cannot inject an identity."""
    from pathlib import Path
    resources = ((env["KUBETEE_GAMMA_KBS_CA"], "ca.pem", 0o644),
                 (env["KUBETEE_GAMMA_KBS_CERT"], "tls.crt", 0o600),
                 (env["KUBETEE_GAMMA_KBS_KEY"], "tls.key", 0o600))
    target = Path(env.get("KUBETEE_GAMMA_PROJECTOR_PEM", "/run/gamma-kbs/ca.pem")).parent
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    for resource, name, mode in resources:
        data = await fetch(resource)
        if not data:
            raise ConfigurationError("empty KBS certificate material")
        with open(target / name, "wb") as material:
            material.write(data)
        os.chmod(target / name, mode)
    ca_data = (target / "ca.pem").read_bytes()
    cert_data = (target / "tls.crt").read_bytes()
    # Match the exact KBS client identity, not a caller/env-supplied alternative.
    leaf = x509.load_pem_x509_certificate(cert_data)
    if hashlib.sha256(leaf.public_bytes(serialization.Encoding.DER)).hexdigest() != env["KUBETEE_GAMMA_WORKER_CERT_SHA256"]:
        raise ConfigurationError("KBS worker certificate fingerprint mismatch")
    env["KUBETEE_GAMMA_PROJECTOR_PEM"] = str(target / "ca.pem")
    env["KUBETEE_GAMMA_CLIENT_PEM"] = str(target / "tls.crt")
    env["KUBETEE_GAMMA_CLIENT_KEY"] = str(target / "tls.key")


def scoped_http_client(settings: Settings, gateway_der: bytes | None = None) -> httpx.AsyncClient:
    ca, certificate, key = settings.certificate_files
    import ssl
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca)
    context.load_cert_chain(certificate, key)
    if gateway_der is None:
        raise ConfigurationError("verified gateway TLS leaf required for worker authentication")
    if hashlib.sha256(gateway_der).hexdigest() != settings.gateway_fingerprint:
        raise ConfigurationError("mTLS gateway certificate is not the operator-approved leaf")
    # No caller-provided peer-DER header is needed. The socket carries identity;
    # the gateway protocol inserts it after verifying its allowed client leaf.
    headers = {"user-agent": "gamma-reconciler-type22"}
    # Service port 8443 is translated to gateway listener 4001 by Kubernetes,
    # not by a client-side URL rewrite. SNI and mTLS retain the ClusterIP name.
    # The gateway rejects any externally supplied proof header. Only the socket's
    # peer certificate is accepted; this header is not a substitute identity.
    return httpx.AsyncClient(verify=context, timeout=httpx.Timeout(30, connect=10),
                             base_url=settings.management_url, headers=headers)


class DelegateProofMiddleware:
    """Loopback proof only after the gateway's TLS leaf matched its fingerprint."""
    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        # Direct headers remain untrusted. Derive proof ONLY from TLS client
        # certificate validated by uvicorn's required mTLS SSLContext.
        scope["headers"] = [(name, value) for name, value in scope["headers"]
                            if name not in {b"x-kubetee-worker-proof", b"x-kubetee-worker-cert-der"}]
        transport = scope.get("extensions", {}).get("transport")
        if transport is None:
            raise TypeError("mTLSProofProtocol required: no trusted TLS transport")
        tls = transport.get_extra_info("ssl_object")
        if tls is None:
            raise RuntimeError("verified transport has no mTLS TLS object")
        peer_certificate = tls.getpeercert(True)
        if peer_certificate is None:
            from fastapi.responses import JSONResponse
            response = JSONResponse({"detail": {"status": "ineligible", "reason": "worker TLS required"}}, status_code=403)
            await response(scope, receive, send)
            return
        import base64
        der = peer_certificate
        if not isinstance(der, bytes) or not der:
            raise RuntimeError("mTLS peer certificate required from verified transport")
        if hashlib.sha256(der).hexdigest() != self.fingerprint:
            from fastapi.responses import JSONResponse
            response = JSONResponse({"detail": {"status": "ineligible", "reason": "wrong worker certificate"}}, status_code=403)
            await response(scope, receive, send)
            return
        headers = list(scope["headers"])
        proof = __import__("base64").b64encode(peer_certificate)
        headers.append((b"x-kubetee-worker-proof", proof))
        await self.app({**scope, "headers": headers}, receive, send)

    def __init__(self, app, fingerprint: str):
        self.app, self.fingerprint = app, fingerprint


from uvicorn.protocols.http import h11_impl


class MTLSProofCycle(h11_impl.RequestResponseCycle):
    """Expose only the server's socket to ASGI, never a caller-provided proof."""
    async def run_asgi(self, app):
        self.scope.setdefault("extensions", {})["transport"] = self.transport
        return await super().run_asgi(app)


class MTLSProofProtocol(h11_impl.H11Protocol):
    def __init__(self, *args, **kwargs):
        # Uvicorn 1.x resolves its request cycle through this module global
        # rather than a protocol attribute. Worker has one dedicated server.
        h11_impl.RequestResponseCycle = MTLSProofCycle
        super().__init__(*args, **kwargs)



def create_application(env=os.environ, *, connect=None, create_store=None, create_chain=None, fetch=certificate_material, gateway_der=None, management_transport=None):
    """No host database, raw API-key trust, or master-token transport exists."""
    settings = Settings.from_environment(env)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(DelegateProofMiddleware, fingerprint=settings.gateway_client_fingerprint)
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        client = management = chain = store = redis_connection = None
        try:
            if connect is None:
                import bittensor as bt
                client = await bt.Subtensor(settings.network)
            else:
                client = await connect(settings)
            store = await create_store(settings) if create_store is not None else None
            if not settings.test and store is None:
                url = env.get("KUBETEE_GAMMA_REDIS_URL", "")
                if urlsplit(url).scheme not in {"redis", "rediss", "redis+sentinel", "rediss+sentinel"} or not urlsplit(url).hostname:
                    raise ConfigurationError("production Redis fencing client required")
                from .config import redis_production_settings
                from redis.asyncio import Redis, Sentinel
                try:
                    parsed = redis_production_settings(url)
                    if "url" in parsed:
                        store = Redis.from_url(**parsed)
                    else:
                        nodes = parsed.pop("sentinel_nodes")
                        service_name = parsed.pop("service_name")
                        sentinel_kwargs = parsed.pop("sentinel_kwargs")
                        discovery = Sentinel(nodes, sentinel_kwargs=sentinel_kwargs,
                                             socket_connect_timeout=5.0, socket_timeout=5.0)
                        store = discovery.master_for(service_name, **parsed)
                except ValueError as error:
                    raise ConfigurationError("invalid production Redis URI configuration") from error
            if store is not None and not hasattr(store, "acquire"):
                from .lease import RedisHotkeyLease
                redis_connection = store
                store = RedisHotkeyLease(store, f"pod:{os.environ.get('HOSTNAME', 'worker')}")
            if not settings.spend_enabled and settings.spender:
                raise ConfigurationError("proxy delegate set while spend is disabled")
            signer = load_proxy_keypair(await fetch(env["KUBETEE_GAMMA_KBS_PROXY_SEED"]), settings.spender) if settings.spender else None
            peer_der = gateway_der
            if peer_der is None:
                from cryptography import x509
                peer_der = pinned_gateway_certificate(settings)
            chain = (create_chain(settings, client, signer) if create_chain else GammaChain(
                client, real_spender=settings.real_spender, delegate=settings.spender or settings.real_spender,
                max_fee=settings.fee_cap, genesis_hash=GENESIS,
            ))
            await chain.preflight()
            management = scoped_http_client(settings, peer_der)
            if management_transport is not None:
                # Synthetic channel mirrors the measured mTLS contract; master
                # credentials cannot enter either transport in production.
                await management.aclose()
                management = httpx.AsyncClient(transport=management_transport, base_url=settings.management_url)
            credential = env.get("KUBETEE_GAMMA_MANAGEMENT_CREDENTIAL", "")
            if not settings.test and credential != "mTLS:gamma-reconciler-type22":
                raise ConfigurationError("only the narrow mTLS Gamma worker identity is accepted")
            native = Management(management, settings.management_url, credential or "mTLS:gamma-reconciler-type22",
                                models=list(settings.models), mcp_servers=list(settings.mcp_servers) if settings.mcp_servers else None)
            reconciler = Reconciler(chain, native, store, signer=signer)
            if not settings.test and management_transport is None:
                if not await native.ready():
                    raise ConfigurationError("private gateway readiness failed over pinned mTLS")
            service = WorkerService(chain, chain.finalized_snapshot, reconciler,
                                    certificate_fingerprint=settings.gateway_client_fingerprint, ready=True)
            app.include_router(internal_router(service))
            if signer is None:
                # No GammaSpend signature is submitted. Capped reminders remain
                # blocked, not falsely converted into successful credit.
                async def observation_only():
                    while True:
                        await asyncio.sleep(6)
                task = asyncio.create_task(observation_only())
            else:
                async def reminder_loop():
                    while True:
                        try:
                            height = await client.finalized_block()
                            for hotkey in list(reconciler.follow):
                                if height % 12 == 0:
                                    await reconciler.reconcile(hotkey)
                                await asyncio.sleep(6)
                        except Exception:
                            await asyncio.sleep(12)
                task = asyncio.create_task(reminder_loop())
            try:
                yield
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            if store is not None:
                for hotkey in list(store.tokens):
                    await store.release(hotkey)
            if management is not None:
                await management.aclose()
            if redis_connection is not None:
                close = getattr(redis_connection, "aclose", None)
                if close is not None:
                    await close()
            if client is not None:
                close = getattr(client, "close", None)
                if close is not None:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
    app.router.lifespan_context = lifespan
    return app
