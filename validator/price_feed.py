"""Compensation price feed — TAO/USD then on-chain alpha->TAO.

The alpha->TAO rate is read directly from the chain's metagraph (`mg.price`)
to avoid Taostats delay. TAO/USD (the chain doesn't know USD) is:

  1. Taostats live (`api.taostats.io`, needs ``TAOSTATS_API_KEY``)
  2. CoinGecko public simple/price (no API key)
  3. Last good in-process / disk cache
  4. Caller then tries S3 payout.json

A 429 / outage must not skip the cycle when any of those succeed.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from config import Config

_TAO_USD_URL = "https://api.taostats.io/api/price/latest/v1?asset=tao"
_COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd"

_USER_AGENT = "kubetee-validator/0.1"

CACHE_PATH = os.environ.get(
    "KUBETEE_TAO_USD_CACHE",
    os.path.expanduser("~/.kubetee/tao_usd_cache.json"),
)

log = logging.getLogger("validator")


class PriceFeedError(RuntimeError):
    """The compensation price could not be obtained; skip the cycle."""


def _get_json(url: str, api_key: str = "", label: str = "taostats") -> object:
    headers = {
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
    }
    if api_key:
        headers["Authorization"] = api_key
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.URLError as exc:
        raise PriceFeedError(f"{label} GET {url}: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise PriceFeedError(f"{label} GET {url}: invalid JSON") from exc


def _tao_usd_from_coingecko() -> float:
    """Public CoinGecko simple/price — no API key.

    https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd
    """
    payload = _get_json(_COINGECKO_URL, label="coingecko")
    if not isinstance(payload, dict):
        raise PriceFeedError("coingecko: unexpected payload")
    coin = payload.get("bittensor")
    if not isinstance(coin, dict):
        raise PriceFeedError("coingecko: missing bittensor")
    value = coin.get("usd")
    if not isinstance(value, (int, float)) or float(value) <= 0:
        raise PriceFeedError("coingecko: no usable usd price")
    return float(value)


def _extract_first(payload: object, keys: tuple[str, ...]) -> float | None:
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


def _load_tao_usd_cache() -> float | None:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    value = payload.get("tao_usd") if isinstance(payload, dict) else None
    if isinstance(value, (int, float)) and float(value) > 0:
        return float(value)
    return None


def _save_tao_usd_cache(tao_usd: float) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as handle:
            json.dump({"tao_usd": tao_usd}, handle)
    except OSError:
        pass


class PriceFeed:
    def __init__(self, config: Config, chain_state=None) -> None:
        self._api_key = config.taostats_api_key
        self._netuid = config.netuid
        self._chain_state = chain_state
        self._last_tao_usd = _load_tao_usd_cache()

    @property
    def last_tao_usd(self) -> float | None:
        """Last good TAO/USD (live, disk, or seeded from payout.json)."""
        return self._last_tao_usd

    def seed_tao_usd(self, tao_usd: float) -> None:
        """Remember a TAO/USD from payout.json / a prior cycle (no disk write)."""
        if tao_usd > 0:
            self._last_tao_usd = float(tao_usd)

    def seed_from_published(self, published: object) -> None:
        value = self.tao_usd_from_published(published)
        if value is not None:
            self.seed_tao_usd(value)

    def _remember(self, value: float) -> float:
        self._last_tao_usd = value
        _save_tao_usd_cache(value)
        return value

    def tao_usd(self) -> float:
        """TAO/USD: Taostats → CoinGecko (no key) → last cached value.

        The chain doesn't know USD. CoinGecko's public simple/price needs no
        API key and unblocks a cold start during a Taostats 429.
        """
        try:
            payload = _get_json(_TAO_USD_URL, self._api_key)
            value = _extract_first(payload, ("price", "usd", "rate"))
            if value is None or value <= 0:
                raise PriceFeedError("no usable TAO/USD in Taostats response")
            return self._remember(value)
        except PriceFeedError as taostats_exc:
            log.warning("%s", taostats_exc)
        try:
            value = _tao_usd_from_coingecko()
            log.warning(
                "taostats TAO/USD unavailable — using CoinGecko %.4f", value
            )
            return self._remember(value)
        except PriceFeedError as cg_exc:
            log.warning("%s", cg_exc)
        if self._last_tao_usd and self._last_tao_usd > 0:
            log.warning(
                "taostats and CoinGecko unavailable — using cached %.4f",
                self._last_tao_usd,
            )
            return self._last_tao_usd
        raise PriceFeedError(
            "no usable TAO/USD from Taostats, CoinGecko, or cache"
        )

    def alpha_to_tao(self) -> float:
        """Alpha->TAO rate, read directly from the chain's metagraph (no delay).

        Falls back to Taostats pool API if the chain read fails.
        """
        # Primary: cached metagraph spot price (zero delay, no second client)
        if self._chain_state is not None:
            try:
                price = self._chain_state.spot_price()
                if not price:
                    self._chain_state.metagraph(self._netuid)
                    price = self._chain_state.spot_price()
                if price and price > 0:
                    return price
            except Exception:
                pass  # fall through to Taostats

        # Fallback: Taostats pool API (may have delay)
        url = (
            "https://api.taostats.io/api/dtao/pool/latest/v1"
            f"?netuid={self._netuid}"
        )
        payload = _get_json(url, self._api_key)
        value = _extract_first(payload, ("price",))
        if value is None or value <= 0:
            alpha = _extract_first(payload, ("alpha_in_pool",))
            tao = _extract_first(payload, ("tao_in_pool",))
            if alpha and tao:
                value = alpha / max(tao, 1e-18)
        if not value or value <= 0:
            raise PriceFeedError("no usable alpha->TAO from chain or Taostats")
        return value

    def usd_per_alpha(self) -> float:
        """USD value of one alpha token."""
        return self.tao_usd() * self.alpha_to_tao()

    def usd_per_alpha_from_published(self, published: dict) -> float | None:
        """Fallback: derive usd_per_alpha from a published payout.json snapshot.

        Returns None if the snapshot doesn't carry the price fields or they
        are invalid. The caller (validator.py) uses this when the live Taostats
        feed is down, so a reader validator can keep scoring off the owner's
        last-known prices rather than skipping the cycle indefinitely.
        """
        if not isinstance(published, dict):
            return None
        tao_usd = published.get("tao_usd")
        alpha_to_tao = published.get("alpha_to_tao")
        if not isinstance(tao_usd, (int, float)) or tao_usd <= 0:
            return None
        if not isinstance(alpha_to_tao, (int, float)) or alpha_to_tao <= 0:
            return None
        return float(tao_usd) * float(alpha_to_tao)

    def tao_usd_from_published(self, published: dict) -> float | None:
        """Fallback: TAO/USD from a published payout.json snapshot."""
        if not isinstance(published, dict):
            return None
        tao_usd = published.get("tao_usd")
        if not isinstance(tao_usd, (int, float)) or tao_usd <= 0:
            return None
        return float(tao_usd)
