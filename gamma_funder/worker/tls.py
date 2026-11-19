"""Per-response mTLS peer evidence; mirrored in the gateway overlay image.

Both independently built source packages carry the same small adapter. No
common unmeasured Python package is shared by their containers. This adapter
pins a real HTTPX response's TLS socket before the caller parses its body.
"""

from __future__ import annotations

import hashlib
import hmac

import httpx


class PeerCertificateError(RuntimeError):
    """Configured mTLS peer evidence is absent or unexpected."""


class PinningAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport,
        *,
        hostname: str,
        fingerprint: str,
    ):
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError(
                "operator-approved SHA256 leaf fingerprint required"
            )
        if any(c not in "0123456789abcdef" for c in fingerprint):
            raise ValueError("fingerprint must be lowercase hex")
        self.transport = transport
        self.extensions = {"sni_hostname": hostname}
        self.fingerprint = fingerprint

    async def handle_async_request(
        self, request: httpx.Request
    ) -> httpx.Response:
        # Preserve request-specific extensions but make SNI non-overridable.
        request.extensions.update(self.extensions)
        if request.url.scheme != "https":
            raise PeerCertificateError("pinned mTLS requires an HTTPS request")
        response = await self.transport.handle_async_request(request)
        try:
            stream = response.extensions.get("network_stream")
            if stream is None:
                raise PeerCertificateError("no verified TLS network stream")
            tls = stream.get_extra_info("ssl_object")
            der = (
                tls.getpeercert(binary_form=True) if tls is not None else None
            )
            if not isinstance(der, bytes) or not hmac.compare_digest(
                hashlib.sha256(der).hexdigest(),
                self.fingerprint,
            ):
                raise PeerCertificateError("pinned mTLS server leaf mismatch")
            # Validation belongs before AsyncClient reads/parses the response body.
            return response
        except BaseException:
            await response.aclose()
            raise

    async def aclose(self) -> None:
        await self.transport.aclose()
