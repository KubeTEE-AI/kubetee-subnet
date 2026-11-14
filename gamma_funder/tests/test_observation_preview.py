"""No-spend observation boundary: synthetic local identity/chain only."""

from types import SimpleNamespace

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from fixtures import HK, REAL
from worker.chain import ChainError, GammaChain
from worker.observation import create_observation_application
from worker.protocol import GENESIS
from worker.service import preview_router
from test_management_service import certificate
from test_runtime import environment


class DisabledSnapshot:
    async def query(self, key, keys=None):
        name = getattr(key, "name", getattr(key, "_name", ""))
        if name == "SubnetGammaEnabled":
            return False
        if name == "GammaDeposits":
            assert keys == [90, HK]
            return None
        if name == "GammaEnabled":
            return True
        raise AssertionError(name)

    async def query_map(self, key, keys=None):
        assert key.name == "Services"
        return []

    async def read(self, name):
        return {"oracle": True, "blocks_since_last_feed": 1}


class DisabledClient:
    class _Substrate:
        async def block_hash(self, height):
            assert height in {0, 1000}, height
            return GENESIS if height == 0 else "0x" + "ab" * 32

    def __init__(self):
        self._substrate = self._Substrate()
        self.calls = 0
        self.closed = False

    async def finalized_block(self):
        self.calls += 1
        return 1000

    async def at(self, height):
        assert height == 1000
        return DisabledSnapshot()

    async def close(self):
        self.closed = True


async def chain_no_spend():
    chain = GammaChain(
        DisabledClient(),
        real_spender=REAL,
        delegate=None,
        service_url="https://llm.kubetee.ai/kubetee-service.json",
        spend_enabled=True,
    )

    async def genesis():
        return GENESIS

    chain.genesis = genesis
    with pytest.raises(ChainError, match="not enabled"):
        await chain.preflight()
    chain.spend_enabled = False
    assert await chain.preflight() is True
    return chain


@pytest.mark.asyncio
async def test_observation_app_has_only_authenticated_finalized_status(
    tmp_path,
):
    values = environment(tmp_path)
    values.update(
        {
            "KUBETEE_GAMMA_OBSERVE_ONLY": "true",
            "KUBETEE_GAMMA_PREVIEW_OBSERVATION_ONLY": "true",
            "KUBETEE_GAMMA_SPEND_ENABLED": "false",
            "KUBETEE_GAMMA_FINNEY_SPEND_APPROVED": "NOT_APPROVED",
            "KUBETEE_GAMMA_SUBTENSOR_ENDPOINT": "wss://entrypoint-finney.opentensor.ai:443",
            "KUBETEE_GAMMA_REAL_SPENDER_SS58": "5C7LYpP2ZH3tpKbvVvwiVe54AapxErdPBbvkYhe6y9ZBkqWt",
        }
    )
    from worker.runtime import Settings

    settings = Settings.from_environment(values)
    client = DisabledClient()

    async def connect():
        return client

    app = create_observation_application(settings, values, connect=connect)
    assert any(
        m.cls.__name__ == "DelegateProofMiddleware"
        for m in app.user_middleware
    )
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/internal/v1/reconcile" not in paths
    assert "/healthz" not in paths
    proof, fingerprint = certificate()
    service = app.state.preview_service
    service.certificate_fingerprint = fingerprint
    route_app = FastAPI()
    route_app.include_router(preview_router(service))
    # The existing socket tests exercise mTLS proof middleware. Here verify only
    # the route/service authorization body, never substitute it for TLS proof.
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=route_app),
            base_url="https://worker",
        ) as transport:
            denied = await transport.get("/preview/v1/status")
            forged = await transport.get(
                "/preview/v1/status",
                headers={"x-kubetee-worker-proof": proof[:-10] + "0000000000"},
            )
            assert not hasattr(service.chain, "execute_spend")
            assert service.chain.spend_enabled is False
            result = await transport.get(
                "/preview/v1/status", headers={"x-kubetee-worker-proof": proof}
            )
    assert denied.status_code == forged.status_code == 403
    assert result.status_code == 200
    body = result.json()
    assert body["finalized_height"] == 1000
    assert body["finalized_block_hash"] == "0x" + "ab" * 32
    assert body["genesis_hash"] == GENESIS
    assert body["deposit_row"] is None
    assert body["services"] == []
    assert body["sn90_enabled"] is False
    assert body["spend_submitted"] is False
    assert client.closed
    assert chain_not_spending(service.chain)


@pytest.mark.asyncio
async def test_observer_cannot_start_without_excluded_external_settings(
    tmp_path,
):
    from worker.runtime import ConfigurationError, Settings

    values = environment(tmp_path)
    values.update(
        {
            "KUBETEE_GAMMA_OBSERVE_ONLY": "true",
            "KUBETEE_GAMMA_PREVIEW_OBSERVATION_ONLY": "true",
            "KUBETEE_GAMMA_SPEND_ENABLED": "false",
            "KUBETEE_GAMMA_FINNEY_SPEND_APPROVED": "NOT_APPROVED",
            "KUBETEE_GAMMA_SUBTENSOR_ENDPOINT": "wss://entrypoint-finney.opentensor.ai:443",
            "KUBETEE_GAMMA_REAL_SPENDER_SS58": "5C7LYpP2ZH3tpKbvVvwiVe54AapxErdPBbvkYhe6y9ZBkqWt",
        }
    )
    values["KUBETEE_GAMMA_REDIS_URL"] = "rediss+sentinel://real-cluster"
    values["KUBETEE_GAMMA_TEST"] = "0"
    with pytest.raises(ConfigurationError, match="REDIS_URL"):
        create_observation_application(
            Settings.from_environment(values), values
        )


@pytest.mark.asyncio
async def test_preview_unavailable_is_retryable_not_internal_error(tmp_path):
    import httpx
    from fastapi import FastAPI
    from worker.observation import ObservationUnavailable
    from worker.service import WorkerService, preview_router

    proof, fingerprint = certificate()
    service = WorkerService(
        ObservationUnavailable(),
        object(),
        object(),
        certificate_fingerprint=fingerprint,
    )
    route_app = FastAPI()
    route_app.include_router(preview_router(service))
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=route_app),
        base_url="https://worker",
    )
    async with client:
        response = await client.get(
            "/preview/v1/status", headers={"x-kubetee-worker-proof": proof}
        )
    assert response.status_code == 503


class AdvancingClient(DisabledClient):
    def __init__(self):
        super().__init__()
        self.storage_heights = []

    async def finalized_block(self):
        self.calls += 1
        return 1000 + (self.calls > 1)

    async def at(self, height):
        self.storage_heights.append(height)
        if len(self.storage_heights) > 1:
            assert height == 1000, "latest head displaced the request snapshot"
        return DisabledSnapshot()


def preview_environment(tmp_path):
    values = environment(tmp_path)
    values.update(
        {
            "KUBETEE_GAMMA_OBSERVE_ONLY": "true",
            "KUBETEE_GAMMA_PREVIEW_OBSERVATION_ONLY": "true",
            "KUBETEE_GAMMA_SPEND_ENABLED": "false",
            "KUBETEE_GAMMA_FINNEY_SPEND_APPROVED": "NOT_APPROVED",
            "KUBETEE_GAMMA_SUBTENSOR_ENDPOINT": "wss://entrypoint-finney.opentensor.ai:443",
            "KUBETEE_GAMMA_REAL_SPENDER_SS58": "5C7LYpP2ZH3tpKbvVvwiVe54AapxErdPBbvkYhe6y9ZBkqWt",
        }
    )
    return values


@pytest.mark.asyncio
async def test_preview_all_finalized_reads_use_one_height(tmp_path):
    values = preview_environment(tmp_path)
    client = AdvancingClient()

    async def connect():
        return client

    from worker.runtime import Settings

    app = create_observation_application(
        Settings.from_environment(values), values, connect=connect
    )
    async with LifespanManager(app):
        # Start this request with a fresh client call. A later height must not
        # silently replace the height used by the deposit read.
        client.calls = 0
        response = await app.state.preview_service.preview_observation()
    assert response["finalized_height"] == 1000
    assert client.storage_heights == [1000, 1000, 1000]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ConnectionError("rpc closed"), TimeoutError()])
async def test_preview_rpc_failure_is_retryable_503(tmp_path, error):
    values = preview_environment(tmp_path)
    client = DisabledClient()

    async def connect():
        return client

    from worker.runtime import Settings

    app = create_observation_application(
        Settings.from_environment(values), values, connect=connect
    )
    proof, fingerprint = certificate()
    service = app.state.preview_service
    service.certificate_fingerprint = fingerprint
    route_app = FastAPI()
    route_app.include_router(preview_router(service))
    async with LifespanManager(app):

        async def unavailable(_hotkey):
            raise error

        service.chain.finalized_snapshot = unavailable
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=route_app),
            base_url="https://worker",
        ) as transport:
            response = await transport.get(
                "/preview/v1/status", headers={"x-kubetee-worker-proof": proof}
            )
    assert response.status_code == 503


def test_observer_rejects_false_observe_only_gate(tmp_path):
    from worker.runtime import ConfigurationError, Settings

    values = preview_environment(tmp_path)
    values["KUBETEE_GAMMA_OBSERVE_ONLY"] = "false"
    with pytest.raises(ConfigurationError, match="no-spend gates"):
        create_observation_application(
            Settings.from_environment(values), values
        )


def chain_not_spending(chain):
    return type(chain).__name__ == "ObservationUnavailable"
