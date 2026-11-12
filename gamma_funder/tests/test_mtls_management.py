"""Measured request construction never downgrades to legacy management auth."""
import httpx
import pytest

from worker.management import Management
from worker.protocol import GENESIS


@pytest.mark.asyncio
async def test_mtls_management_preserves_cluster_tls_and_socket_proof():
    requests = []
    transport = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json={
            "exists": False, "row": None,
        })
    ), base_url="https://litellm-gateway-mtls.litellm.svc.cluster.local:8443",
        headers={"user-agent": "gamma-reconciler-type22"})
    mgmt = Management(transport,
        "https://litellm-gateway-mtls.litellm.svc.cluster.local:8443",
        "mTLS:gamma-reconciler-type22", models=["z-ai/glm-5.3"])
    await mgmt.call("GET", "/internal/v1/gamma/key",
        params={"network": "finney", "genesis_hash": GENESIS, "netuid": 90, "hotkey_ss58": "wallet"},
        headers={"x-kubetee-worker-proof": "caller-supplied-invalid-header"})
    assert requests[0].url.scheme == "https"
    assert requests[0].url.host == "litellm-gateway-mtls.litellm.svc.cluster.local"
    assert requests[0].url.port == 8443
    assert requests[0].url.path == "/internal/v1/gamma/key"
    assert dict(requests[0].url.params) == {"network": "finney", "genesis_hash": GENESIS,
                                           "netuid": "90", "hotkey_ss58": "wallet"}
    assert "x-kubetee-worker-proof" not in requests[0].headers
    # Production removes caller-supplied proof: the gateway derives it from TLS.
    assert "authorization" not in requests[0].headers
    await transport.aclose()


async def test_mtls_management_rejects_unpinned_localhost():
    with pytest.raises(ValueError, match="cannot be rebound"):
        Management(httpx.AsyncClient(), "http://localhost:9000", "mTLS:gamma-reconciler-type22")
    with pytest.raises(ValueError, match="cannot be rebound"):
        Management(httpx.AsyncClient(), "https://litellm-gateway-mtls.litellm.svc.cluster.local:8443:4001",
                   "mTLS:gamma-reconciler-type22")
