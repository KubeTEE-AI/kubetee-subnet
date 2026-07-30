"""Hippius (SN75) S3 store hand-rolledSigV4-signed GET/PUT for the kubetee-validator bucket.

The subnet-owner publisher PUTs `payout.json` and `price-card.json`; every
other validator GETs them anonymously. The load-bearing rules:

- Bucket/key are pinned in code, never configurable, so two validators can
  never be pointed at different data.
- Every PUT must send `x-amz-acl: public-read`, *signed*. An S3 PUT replaces
  the object's ACL along with its bytes, so omitting the canned ACL silently
  re-privatises the object and cuts off every reader; SigV4 rejects an
  unsigned `x-amz-*` header, so it must be folded into the canonical request.
- The payload is deliberately unsigned (public aggregate data): the S3 write
  credential is the access control, TLS is the channel, and the card envelope
  is the bound.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import urllib.error
import urllib.request

DEFAULT_BUCKET = "kubetee-validator"
DEFAULT_PAYOUT_KEY = "payout.json"
DEFAULT_CARD_KEY = "price-card.json"

_REGION = "auto"
_SERVICE = "s3"
_HOST = "s3.hippius.com"
_USER_AGENT = "kubetee-validator/0.1"


class HippiusError(RuntimeError):
    """A Hippius GET/PUT failed."""


def object_url(key: str) -> str:
    return f"https://{_HOST}/{DEFAULT_BUCKET}/{key}"


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _signature_key(secret: str, date: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date)
    k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode(), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def _hmac_hex(key: bytes, message: str) -> str:
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()


class HippiusStore:
    def __init__(self, access_key: str, secret_key: str) -> None:
        self._access_key = access_key
        self._secret_key = secret_key

    # -- anonymous read ----------------------------------------------------

    def get_json(self, key: str) -> dict:
        """GET an object anonymously (readers carry no credentials)."""
        return _get_public(key)

    # -- publisher write ---------------------------------------------------

    def put_json(self, key: str, payload: dict) -> None:
        """PUT a JSON object with a signed x-amz-acl: public-read."""
        self._put(key, json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(), "application/json")

    def put_raw(self, key: str, data: bytes | str, content_type: str = "text/html; charset=utf-8") -> None:
        """PUT raw bytes/text (e.g. index.html) with the signed public-read ACL."""
        self._put(key, data.encode() if isinstance(data, str) else data, content_type)

    def _put(self, key: str, body: bytes, content_type: str = "application/json") -> None:
        """SigV4-signed raw object PUT with a public-read ACL."""
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        body_sha256 = hashlib.sha256(body).hexdigest()
        headers = {
            "content-type": content_type,
            "host": _HOST,
            "x-amz-acl": "public-read",
            "x-amz-content-sha256": body_sha256,
            "x-amz-date": amz_date,
        }
        canonical_uri = f"/{DEFAULT_BUCKET}/{key}"
        canonical_headers = "".join(
            f"{k}:{headers[k]}\n" for k in sorted(headers)
        )
        signed_headers = ";".join(sorted(headers))
        canonical_request = "\n".join(
            [
                "PUT",
                canonical_uri,
                "",  # canonical query string
                canonical_headers,
                signed_headers,
                body_sha256,
            ]
        )
        credential_scope = f"{date_stamp}/{_REGION}/{_SERVICE}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signing_key = _signature_key(
            self._secret_key, date_stamp, _REGION, _SERVICE
        )
        signature = _hmac_hex(signing_key, string_to_sign)
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self._access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        request = urllib.request.Request(
            object_url(key),
            data=body,
            method="PUT",
            headers={
                **headers,
                "Authorization": authorization,
                "User-Agent": _USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            raise HippiusError(
                f"PUT {key}: HTTP {exc.code} {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise HippiusError(f"PUT {key}: {exc}") from exc


def _get_public(key: str) -> dict:
    request = urllib.request.Request(
        object_url(key),
        method="GET",
        headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise HippiusError(f"GET {key}: HTTP {exc.code} {exc.reason}") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HippiusError(f"GET {key}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HippiusError(f"GET {key}: unexpected payload")
    return payload
