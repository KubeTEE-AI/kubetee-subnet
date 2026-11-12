"""Measured TEE container entrypoint; CDH/KBS identity before any bind."""

import asyncio
import os

from .runtime import create_application, materialize_kbs_identity


async def serve():
    import uvicorn

    await materialize_kbs_identity()
    application = create_application()
    config = uvicorn.Config(
        application,
        host="0.0.0.0",
        port=8443,
        http="worker.runtime:MTLSProofProtocol",
        log_level="info",
        ssl_certfile=os.environ["KUBETEE_GAMMA_CLIENT_PEM"],
        ssl_keyfile=os.environ["KUBETEE_GAMMA_CLIENT_KEY"],
        ssl_ca_certs=os.environ["KUBETEE_GAMMA_PROJECTOR_PEM"],
        ssl_cert_reqs=__import__("ssl").CERT_REQUIRED,
    )
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    asyncio.run(serve())
