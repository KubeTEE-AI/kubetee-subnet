"""Attested worker TLS bootstrap; selected only by a dedicated preview command."""
import asyncio
import ssl

import uvicorn

from .observation import create_observation_application
from .runtime import Settings
from .start import bootstrap


def main():
    import os

    ca, certificate, key = asyncio.run(bootstrap())
    settings = Settings.from_environment(os.environ)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    context.load_verify_locations(cafile=ca)
    context.verify_mode = ssl.CERT_REQUIRED
    uvicorn.run(
        create_observation_application(settings, os.environ),
        host="0.0.0.0", port=8443,
        http="worker.runtime:MTLSProofProtocol",
        ssl_certfile=certificate, ssl_keyfile=key,
        ssl_cert_reqs=ssl.CERT_REQUIRED, ssl_ca_certs=ca,
    )


if __name__ == "__main__":
    main()
