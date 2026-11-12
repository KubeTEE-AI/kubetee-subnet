"""Remote-attested startup: KBS resources before every network authorization."""
import os
import ssl

import uvicorn

from .runtime import (
    MTLSProofProtocol,
    Settings,
    certificate_material,
    create_application,
    materialize_kbs_identity,
    verify_worker_start,
)


async def bootstrap(fetch=certificate_material, *, scratch_directory=None):
    # Match the Deployment's emptyDir and KBS repository namespace exactly.
    # No Kubernetes Secret or guest-pinned /secrets path enters this identity.
    await materialize_kbs_identity(os.environ, fetch)
    # materialize_kbs_identity already fetched and pinned the fourth
    # clientAuth leaf; no second secret-resource name or duplicate fetch.
    ca, cert, key = (os.environ[name] for name in (
        "KUBETEE_GAMMA_PROJECTOR_PEM",
        "KUBETEE_GAMMA_CLIENT_PEM",
        "KUBETEE_GAMMA_CLIENT_KEY",
    ))
    settings = Settings.from_environment(os.environ)
    # Inbound serving and outbound clientAuth are distinct certificate roles.
    settings.outbound_tls_files()
    with open(ca, "rb") as ca_file, open(cert, "rb") as cert_file:
        # KBS-specific DER validation is applied to leaves in bootstrap/runtime,
        # not to the approved east-west CA supplied alongside them.
        verify_worker_start(settings, ca_file.read(), cert_file.read())
    return ca, cert, key


def main(fetch=certificate_material):
    import asyncio
    ca, cert, key = asyncio.run(bootstrap(fetch))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    context.load_verify_locations(cafile=ca)
    context.verify_mode = ssl.CERT_REQUIRED
    uvicorn.run(create_application(), host="0.0.0.0", port=8443,
        http="worker.runtime:MTLSProofProtocol", ssl_certfile=cert,
        ssl_keyfile=key, ssl_cert_reqs=ssl.CERT_REQUIRED, ssl_ca_certs=ca)


if __name__ == "__main__":
    main()
