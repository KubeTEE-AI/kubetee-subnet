"""Real socket test for the worker mTLS identity boundary."""
import asyncio
import contextlib
import json
import socket
import ssl

import pytest
import uvicorn

from worker.runtime import MTLSProofProtocol, internal_router
from fixtures import HK, NativeStore, SyntheticChain
from test_runtime import provider
from worker.reconciler import Reconciler
from worker.service import WorkerService, ss58_address


@pytest.mark.asyncio
async def test_mtls_reconcile_accepts_and_authenticates_transport(tmp_path):
    fingerprint, _ = provider(tmp_path)
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(1_000_000_000)
    reconciler = Reconciler(chain, store, store, signer=object())
    service = WorkerService(chain, chain.finalized_snapshot, reconciler,
        certificate_fingerprint=fingerprint, ready=True)
    from fastapi import FastAPI
    application = FastAPI()
    application.include_router(internal_router(service))
    from worker.runtime import DelegateProofMiddleware
    application.add_middleware(DelegateProofMiddleware, fingerprint=fingerprint)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    configuration = uvicorn.Config(application,
        http="worker.runtime:MTLSProofProtocol", timeout_keep_alive=1,
        ssl_certfile=str(tmp_path / "worker.pem"), ssl_keyfile=str(tmp_path / "worker.key"),
        ssl_cert_reqs=ssl.CERT_REQUIRED, ssl_ca_certs=str(tmp_path / "projector.pem"), log_level="error")
    server = uvicorn.Server(configuration)
    server.capture_signals = lambda: contextlib.nullcontext()
    task = asyncio.create_task(server.serve(sockets=[listener]))
    await asyncio.sleep(.1)
    context = ssl.create_default_context(cafile=str(tmp_path / "projector.pem"))
    context.load_cert_chain(str(tmp_path / "worker.pem"), str(tmp_path / "worker.key"))
    try:
        # No wallet is committed on this side; the socket proves both strict
        # mTLS identity and eventual successful chain-driven budget allocation.
        async def request(injected=False):
            reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", listener.getsockname()[1], ssl=context, server_hostname="litellm-gateway-mtls.litellm.svc.cluster.local"), 5)
            body = json.dumps({"action": "claim", "hotkey_ss58": HK, "verified_challenge_digest": "0"*64}).encode()
            forged = b"X-Kubetee-Worker-Proof: YmFk\r\n" if injected else b""
            writer.write(b"POST /internal/v1/reconcile HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode()+b"\r\nConnection:close\r\n" + forged + b"\r\n"+body)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), 5)
            writer.close(); await writer.wait_closed()
            return response
        from worker.protocol import GENESIS as Snapshot
        response = await request(True)
        assert response.startswith(b"HTTP/1.1 200 OK"), response
        assert b"\"status\":\"funded\"" in response, response
        assert store.row["max_budget"] == "1.0"
        assert store.row["key_alias"] == store.row["metadata"]["gamma"]["observation_coldkey"]
        # Even with a forged proof header, both previously untrusted force-deny
        # identities remain impossible when the server DER is different.
        chain, store = SyntheticChain(), NativeStore()
        chain.mint(1_000_000_000)
        service.certificate_fingerprint = "0"*64
        service.reconciler = Reconciler(chain, store, store, signer=object())
        response = await request(True)
        assert response.startswith(b"HTTP/1.1 403 Forbidden"), response
        assert store.row is None and not chain.submitted
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        listener.close()
