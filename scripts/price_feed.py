"""Taostats price feed for scoring v3 (USD-priced weights).

One authenticated feed supplies both conversion legs:

- TAO/USD:        GET /api/price/latest/v1
- alpha->TAO:     GET /api/dtao/pool/latest/v1?netuid=<netuid>

Auth follows the rbmk data-pipeline pattern: ``Authorization: tao-<key>``
(the ``tao-`` prefix is added when missing). The key is never logged.

Fail-closed contract: any transport, parsing, or value problem raises
``PriceFeedError`` — the validator then skips the cycle
(``SkipReason.PRICE_UNAVAILABLE``) and the previous on-chain weights persist.
The validator never guesses a price.
"""

from __future__ import annotations

import dataclasses
import json
import math
import time
import urllib.request
from collections.abc import Callable

DEFAULT_BASE_URL = "https://api.taostats.io"
_DEFAULT_TIMEOUT_SECONDS = 10.0


class PriceFeedError(RuntimeError):
    """The feed could not produce a trustworthy quote (fail-closed)."""


@dataclasses.dataclass(frozen=True)
class PriceQuote:
    """One live conversion snapshot."""

    tao_usd: float
    alpha_tao: float
    usd_per_alpha: float
    fetched_at: float


def _default_opener(url: str, headers: dict, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(  # noqa: S310 - fixed https origin
        request, timeout=timeout
    ) as response:
        return response.read()


def _positive_price(payload: object, what: str) -> float:
    try:
        rows = payload["data"]  # type: ignore[index]
        value = float(str(rows[0]["price"]))
    except (TypeError, KeyError, IndexError, ValueError) as error:
        raise PriceFeedError(f"{what}: malformed payload") from error
    if not math.isfinite(value) or value <= 0:
        raise PriceFeedError(f"{what}: non-positive or non-finite price")
    return value


def check_divergence(
    feed_alpha_tao: float,
    chain_alpha_tao: float | None,
    max_frac: float,
) -> bool:
    """True when the feed price diverges from a usable on-chain reference by
    more than ``max_frac`` (relative to the chain price). A missing or
    non-positive chain reference cannot veto the feed."""
    if chain_alpha_tao is None or not isinstance(
        chain_alpha_tao, (int, float)
    ):
        return False
    if not math.isfinite(chain_alpha_tao) or chain_alpha_tao <= 0:
        return False
    return abs(feed_alpha_tao - chain_alpha_tao) / chain_alpha_tao > max_frac


class TaostatsPriceFeed:
    """Minimal, injectable Taostats client (two GETs per fetch)."""

    def __init__(
        self,
        api_key: str,
        netuid: int,
        opener: Callable[[str, dict, float], bytes] | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        key = (api_key or "").strip()
        if not key:
            raise ValueError("taostats api key must be non-empty")
        if not key.startswith("tao-"):
            key = "tao-" + key
        self._headers = {
            "Authorization": key,
            "Accept": "application/json",
        }
        self._netuid = netuid
        self._opener = opener or _default_opener
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._clock = clock

    def fetch(self) -> PriceQuote:
        tao_usd = _positive_price(
            self._get("/api/price/latest/v1"), "tao price"
        )
        alpha_tao = _positive_price(
            self._get(f"/api/dtao/pool/latest/v1?netuid={self._netuid}"),
            "alpha pool price",
        )
        return PriceQuote(
            tao_usd=tao_usd,
            alpha_tao=alpha_tao,
            usd_per_alpha=tao_usd * alpha_tao,
            fetched_at=self._clock(),
        )

    def _get(self, path: str) -> object:
        url = self._base_url + path
        try:
            raw = self._opener(url, dict(self._headers), self._timeout)
        # Any transport-layer surprise is a feed failure by contract.
        except Exception as error:  # pylint: disable=broad-exception-caught
            raise PriceFeedError(f"feed transport failed: {path}") from error
        try:
            return json.loads(raw)
        except ValueError as error:
            raise PriceFeedError(f"feed returned non-JSON: {path}") from error
