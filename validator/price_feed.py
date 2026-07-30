"""Compensation price feed (Taostats) — HARD dependency.

Fetches TAO/USD and the SN90 alpha->TAO rate each cycle. A failure raises
PriceFeedError; the caller skips the cycle and previous on-chain weights
persist. The validator never guesses a price.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from config import Config

_TAO_USD_URL = "https://api.taostats.io/api/price/latest/v1?asset=tao"
_SUBNET_PRICE_URL = (
    "https://api.taostats.io/api/dtao/pool/latest/v1?netuid={netuid}"
)

_USER_AGENT = "kubetee-validator/0.1"


class PriceFeedError(RuntimeError):
    """The compensation price could not be obtained; skip the cycle."""


def _get_json(url: str, api_key: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
            "Authorization": api_key,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.URLError as exc:
        raise PriceFeedError(f"taostats GET {url}: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise PriceFeedError(f"taostats GET {url}: invalid JSON") from exc


def _extract_first(payload: object, keys: tuple[str, ...]) -> float | None:
    """Best-effort numeric extraction from a nested Taostats payload."""
    if isinstance(payload, dict):
        for key in keys:
            if key in payload:
                value = payload[key]
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, dict):
                    nested = _extract_first(value, ("price", "usd", "rate"))
                    if nested is not None:
                        return nested
                if isinstance(value, str):
                    try:
                        return float(value)
                    except ValueError:
                        pass
        for value in payload.values():
            nested = _extract_first(value, keys)
            if nested is not None:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = _extract_first(item, keys)
            if nested is not None:
                return nested
    return None


class PriceFeed:
    def __init__(self, config: Config) -> None:
        self._api_key = config.taostats_api_key
        self._netuid = config.netuid

    def tao_usd(self) -> float:
        payload = _get_json(_TAO_USD_URL, self._api_key)
        value = _extract_first(payload, ("price", "usd", "rate"))
        if value is None or value <= 0:
            raise PriceFeedError("no usable TAO/USD in Taostats response")
        return value

    def alpha_to_tao(self) -> float:
        """Alpha per 1 TAO for this subnet (alpha/TAO rate)."""
        url = _SUBNET_PRICE_URL.format(netuid=self._netuid)
        payload = _get_json(url, self._api_key)
        value = _extract_first(payload, ("price",))
        if value is None or value <= 0:
            # Fallback to the pool ratio: alpha_in_pool / tao_in_pool (rao).
            alpha = _extract_first(payload, ("alpha_in_pool",))
            tao = _extract_first(payload, ("tao_in_pool",))
            if alpha and tao:
                value = alpha / max(tao, 1e-18)
        if not value or value <= 0:
            raise PriceFeedError("no usable alpha->TAO in Taostats response")
        return value

    def usd_per_alpha(self) -> float:
        """USD value of one alpha token."""
        return self.tao_usd() * self.alpha_to_tao()
