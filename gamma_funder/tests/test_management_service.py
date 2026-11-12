import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).parents[1]))
from fixtures import HK, NativeStore, SyntheticChain
from worker.management import Management, exact_money
from worker.protocol import GENESIS, internal_router
from worker.reconciler import Reconciler
from worker.service import WorkerService


def certificate():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "synthetic measured caller")]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(minutes=1))
        .sign(key, hashes.SHA256())
    )
    der = cert.public_bytes(serialization.Encoding.DER)
    return base64.b64encode(der).decode(), hashlib.sha256(der).hexdigest()


@pytest.mark.asyncio
async def test_separate_worker_reserves_credits_and_never_returns_raw_key():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(1_000_000_000)
    native = Management(
        store, "https://native.invalid", "synthetic scoped credential"
    )
    reconciler = Reconciler(chain, native, None, signer=object())
    proof, fingerprint = certificate()
    service = WorkerService(
        chain,
        lambda hk: chain.finalized_snapshot(hk),
        reconciler,
        certificate_fingerprint=fingerprint,
    )
    with pytest.raises(HTTPException):
        await service.authenticate("invalid")
    with pytest.raises(HTTPException):
        await service.authenticate(certificate()[0])
    await service.authenticate(proof)
    application = FastAPI()
    application.include_router(internal_router(service))
    transport = ASGITransport(app=application)
    body = {
        "network": "finney",
        "genesis_hash": GENESIS,
        "netuid": 90,
        "hotkey_ss58": HK,
        "action": "claim",
        "verified_challenge_digest": "a" * 64,
    }
    async with AsyncClient(
        transport=transport, base_url="http://worker.invalid"
    ) as http:
        root = await http.get("/internal/v1/ready")
        assert root.status_code == 403
        result = await http.post(
            "/internal/v1/reconcile",
            json=body,
            headers={"x-kubetee-worker-proof": proof},
        )
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["status"] == "funded"
    assert exact_money(payload["max_budget"]) == 1_000_000_000
    assert store.credits == 1 and len(chain.submitted) == 1
    assert (
        store.row["key_alias"]
        == store.row["metadata"]["gamma"]["observation_coldkey"]
        + "-"
        + store.row["metadata"]["gamma_hotkey"].lower()
    )
    assert "api_key" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_internal_pending_reason_projects_to_public_gateway_schema():
    import importlib.util
    from fastapi import FastAPI
    from worker.reconciler import Reconciler
    from worker.service import WorkerService
    from fixtures import NativeStore, SyntheticChain

    import os

    overlay = Path(
        os.environ.get(
            "KUBETEE_GAMMA_GATEWAY_OVERLAY",
            Path.home()
            / ".config/superpowers/worktrees/litellm/gamma-mtls-release/tools/kubetee-litellm-overlay/kubetee_gamma_claim.py",
        )
    )
    if not overlay.is_file():
        pytest.skip(
            "set KUBETEE_GAMMA_GATEWAY_OVERLAY for the cross-repository boundary test"
        )
    spec = importlib.util.spec_from_file_location(
        "gamma_pending_boundary", overlay
    )
    claim = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = claim
    spec.loader.exec_module(claim)
    chain, store = SyntheticChain(), NativeStore()
    native = Management(
        store, "https://native.invalid", "synthetic credential"
    )
    reconciler = Reconciler(chain, native, None, signer=object())
    proof, fingerprint = certificate()
    service = WorkerService(
        chain,
        chain.finalized_snapshot,
        reconciler,
        certificate_fingerprint=fingerprint,
    )
    app = FastAPI()
    app.include_router(internal_router(service))
    # Use real worker ASGI and signature verification. Raw-key issuance must
    # use the gateway's narrow in-process client, never an external HTTP API.
    sys.path.insert(0, str(overlay.parent))
    import kubetee_gamma_management as native_management
    from kubetee_gamma_private_mtls import InProcessIssueClient

    fixture_path = str(
        Path(overlay).parent.parent.parent
        / "tests/test_litellm/tools/kubetee-litellm-overlay/test_kubetee_gamma_management.py"
    )
    fixture_spec = importlib.util.spec_from_file_location(
        "gamma_native_fixture", fixture_path
    )
    if fixture_spec is None or fixture_spec.loader is None:
        raise ImportError("matching gateway fixture loader unavailable")
    native_fixture = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(native_fixture)
    management = native_management.GammaManagement(
        proxy=native_fixture.SyntheticStore(),
        certificate_fingerprint="ab" * 32,
        proxy_ip="127.0.0.1",
        models=["selected-model"],
    )
    native_issue = InProcessIssueClient(management)

    async def authentic_worker(*args, **kwargs):
        return "native-grant:0000000000000000"

    native_issue.issue = authentic_worker
    with pytest.raises(TypeError):
        InProcessIssueClient(object())
    worker = claim.KubeTEEGammaClaimHandler(
        claim.PrivateWorkerResponse(
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="https://worker.invalid",
            ),
            native_issue,
            {"x-kubetee-worker-proof": proof},
        ),
        authority=claim.MemoryAuthority(),
    )
    public = FastAPI()
    worker.register(public)
    chain.signer = object()
    from bittensor_wallet import Keypair as SigningKeypair
    from bittensor_core import Keypair

    real_signer = SigningKeypair.create_from_mnemonic(
        SigningKeypair.generate_mnemonic()
    )
    chain.HK = real_signer.ss58_address

    def verify_signer(message, signature, hotkey):
        assert hotkey == real_signer.ss58_address
        return bool(
            Keypair(ss58_address=hotkey).verify(
                message.encode(), bytes.fromhex(signature)
            )
        )

    claim._verify = verify_signer
    async with AsyncClient(
        transport=ASGITransport(app=public), base_url="https://public.invalid"
    ) as http:
        result = await http.post(
            "/v1/gamma/challenge",
            json={
                "hotkey_ss58": real_signer.ss58_address,
                "action": "claim",
                "netuid": 90,
            },
        )
        assert result.status_code == 200
        challenge = result.json()
        signed = await http.post(
            "/v1/gamma/key/claim",
            json={
                "challenge_id": challenge["challenge_id"],
                "signature": real_signer.sign(
                    challenge["message"].encode()
                ).hex(),
            },
        )
        assert signed.status_code == 202, signed.text
        assert signed.json()["reason"] == "spend_final_credit_pending"

    request = {
        "hotkey_ss58": HK,
        "action": "claim",
        "verified_challenge_digest": "0" * 64,
    }
    result = await worker.worker.claim(request)
    assert (
        result[0] == 202
        and result[1]["reason"] == "spend_final_credit_pending"
    )
    projected = claim._typed_response(*result)
    assert projected.status_code == 202
    assert json.loads(projected.body)["status"] == "pending"
