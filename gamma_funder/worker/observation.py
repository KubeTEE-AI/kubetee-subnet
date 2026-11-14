"""Measured, authenticated observation-only app; no settlement components.

There is no Redis client, native gateway client, delegate signer, spending,
reconciliation listener or key-discovery path. Public Finney RPC is an
unattested read transport. It never receives a wallet or an extrinsic.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import bittensor as bt
from fastapi import FastAPI

from .chain import ChainError, GammaChain, PendingReceipt
from .protocol import GENESIS
from .service import WorkerService, preview_router

RPC_ENDPOINT = "wss://entrypoint-finney.opentensor.ai:443"
# Public, synthetic, unowned observation value. It is not a funded coldkey and
# there is never a signer or delegate seed for it in this application.
OBSERVATION_SPENDER = "5C7LYpP2ZH3tpKbvVvwiVe54AapxErdPBbvkYhe6y9ZBkqWt"


class ObservationChain:
    """Public finalized reader only; deliberately not a spend-capable subclass."""

    def __init__(self, client, genesis):
        self.client = client
        self.genesis_hash = genesis.lower()
        self.service_observation = {}
        self.spend_enabled = False
        self.reader = GammaChain(
            client, real_spender=OBSERVATION_SPENDER, delegate=None,
            genesis_hash=genesis, spend_enabled=False,
        )

    async def preflight(self):
        await self.reader.preflight()
        self.service_observation = self.reader.service_observation

    async def finalized_snapshot(self, hotkey):
        return await self.reader.finalized_snapshot(hotkey)


class ObservationUnavailable:
    spend_enabled = False
    preview_pending = True
    async def preflight(self):
        raise PendingReceipt("attested observation is not ready")


def create_observation_application(settings, env, *, connect=None):
    """Build only a client-authenticated finalized-storage reader."""
    from .runtime import ConfigurationError, DelegateProofMiddleware

    if (
        not settings.preview_observation
        or env.get("KUBETEE_GAMMA_OBSERVE_ONLY") != "true"
        or settings.spend_enabled
        or env.get("KUBETEE_GAMMA_FINNEY_SPEND_APPROVED") != "NOT_APPROVED"
        or env.get("KUBETEE_GAMMA_PROXY_DELEGATE_SS58")
        or settings.spender
    ):
        raise ConfigurationError("observer requires explicit no-spend gates")
    if env.get("KUBETEE_GAMMA_SUBTENSOR_ENDPOINT") != RPC_ENDPOINT:
        raise ConfigurationError("reviewed official Finney read RPC required")
    if settings.real_spender != OBSERVATION_SPENDER:
        raise ConfigurationError("synthetic non-wallet observer identity required")
    if env.get("KUBETEE_GAMMA_KBS_PROXY_SEED") != "default/gamma-spend-proxy/seed":
        raise ConfigurationError("fixed unused signer resource path required")
    if settings.test and connect is None:
        raise ConfigurationError("synthetic mode is forbidden in the real preview")
    for name in (
        "KUBETEE_GAMMA_REDIS_URL", "KUBETEE_GAMMA_MANAGEMENT_CREDENTIAL",
        "KUBETEE_GAMMA_INJECT", "KUBETEE_GAMMA_MOCK",
        "KUBETEE_GAMMA_GATEWAY_CLIENT_PEM", "KUBETEE_GAMMA_GATEWAY_CLIENT_KEY",
    ):
        if env.get(name):
            raise ConfigurationError(f"observer excludes {name}")

    service = WorkerService(
        chain=ObservationUnavailable(), fresh_checkpoint=object(),
        reconciler=object(),
        certificate_fingerprint=settings.gateway_client_fingerprint,
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        DelegateProofMiddleware,
        fingerprint=settings.gateway_client_fingerprint,
    )
    app.include_router(preview_router(service))

    @asynccontextmanager
    async def lifespan(_application):
        client = None
        try:
            client = await (
                connect() if connect is not None
                else bt.Client(RPC_ENDPOINT).connect()
            )
            chain = ObservationChain(
                client, genesis=GENESIS,
            )
            await asyncio.wait_for(chain.preflight(), timeout=20)
            service.chain = chain
            yield
        finally:
            service.chain = ObservationUnavailable()
            if client is not None:
                result = client.close()
                if asyncio.iscoroutine(result):
                    await result

    app.state.preview_service = service
    app.router.lifespan_context = lifespan
    return app
