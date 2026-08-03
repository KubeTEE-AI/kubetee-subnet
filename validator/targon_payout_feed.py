"""Targon (SN4) supply-side payout feed — FAIL-SOFT.

Reads live per-card USD per GPU class from stats.targon.com/api/miners and
clamps the committed GPU price card DOWNWARD only (never above the card),
floored at `floor_frac x card` so a single Targon node cannot drag a class
down. Degrades live -> last known (cached on disk) -> card, and never skips a
cycle. Off by default; enabling it is a real pay change.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from config import Config

_TARGON_MINERS_URL = "https://stats.targon.com/api/miners"
_USER_AGENT = "kubetee-validator/0.1"

DEFAULT_USD_CARD: dict[str, float] = {
    "H100": 3.00,
    "H200": 3.50,
    "B200": 6.50,
    "B300": 8.00,
    "RTX6000": 2.25,
}

CACHE_PATH = os.environ.get(
    "KUBETEE_TARGON_CACHE",
    os.path.expanduser("~/.kubetee/targon_payout_cache.json"),
)


class TargonFeedError(RuntimeError):
    """A faithful Targon snapshot could not be produced (never skips cycle)."""


def _gpu_class_of(compute_type: str) -> str | None:
    text = compute_type.upper()
    for klass in DEFAULT_USD_CARD:
        if klass in text:
            return klass
    return None


def fetch_live_per_card_usd() -> dict[str, float]:
    """Live $/card/hour per GPU class (total payout / total cards)."""
    request = urllib.request.Request(
        _TARGON_MINERS_URL,
        headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())

    miners = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(miners, list):
        raise TargonFeedError("targon api/miners: unexpected payload")

    payout_by_class: dict[str, float] = {}
    cards_by_class: dict[str, float] = {}
    for miner in miners:
        if not isinstance(miner, dict):
            continue
        klass = _gpu_class_of(str(miner.get("compute_type", "")))
        if klass is None:
            continue
        try:
            payout = float(miner.get("payout", 0) or 0)
            cards = float(miner.get("cards", 0) or 0)
        except (TypeError, ValueError):
            continue
        if cards <= 0 or payout <= 0:
            continue
        payout_by_class[klass] = payout_by_class.get(klass, 0.0) + payout
        cards_by_class[klass] = cards_by_class.get(klass, 0.0) + cards

    per_card: dict[str, float] = {}
    for klass, total in payout_by_class.items():
        cards = cards_by_class.get(klass, 0.0)
        if cards > 0:
            per_card[klass] = total / cards
    if not per_card:
        raise TargonFeedError("targon api/miners: no usable per-card data")
    return per_card


def _load_cache() -> dict[str, float] | None:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    per_card = payload.get("per_card_usd")
    if not isinstance(per_card, dict):
        return None
    return {
        str(k).upper(): float(v)
        for k, v in per_card.items()
        if isinstance(v, (int, float)) and float(v) > 0
    } or None


def _save_cache(per_card: dict[str, float]) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as handle:
            json.dump({"per_card_usd": per_card}, handle)
    except OSError:
        pass  # cache is best-effort; never block the cycle


class TargonPayoutFeed:
    def __init__(
        self,
        config: Config,
        per_card_fetcher=fetch_live_per_card_usd,
    ) -> None:
        self._enabled = config.targon_payout_enabled
        self._floor_frac = config.targon_floor_frac
        self._card = dict(DEFAULT_USD_CARD)
        self._card.update(config.usd_card_override)
        self._fetcher = per_card_fetcher

    def card(self) -> dict[str, float]:
        """The committed card (compiled-in default + operator override)."""
        return dict(self._card)

    def resolve_per_card_usd(self) -> tuple[dict[str, float], str]:
        """The per-card USD per class, plus the source that supplied it.

        Degrades live -> cache -> published (S3) -> card. Never raises (fail-soft).
        """
        if not self._enabled:
            return self.card(), "card"

        try:
            per_card = self._fetcher()
            _save_cache(per_card)
            return per_card, "live"
        except Exception:  # noqa: BLE001 - fail-soft to cache
            cached = _load_cache()
            if cached:
                return cached, "cache"
        # 3rd tier: the owner's last published Targon snapshot (S3).
        # Fresher than the compiled default for readers with no disk cache.
        try:
            from hippius_store import fetch_published_payout  # noqa: PLC0415

            published = fetch_published_payout()
            if isinstance(published, dict):
                per_card_pub = published.get("per_card_usd")
                if isinstance(per_card_pub, dict):
                    per_card = {
                        str(k).upper(): float(v)
                        for k, v in per_card_pub.items()
                        if isinstance(v, (int, float)) and float(v) > 0
                    }
                    if per_card:
                        return per_card, "published"
        except Exception:  # noqa: BLE001 - fail-soft to card
            pass
        return self.card(), "card"

    def effective_card(self) -> tuple[dict[str, float], str]:
        """Card clamped to [floor_frac x card, card] per class, and source."""
        resolved, source = self.resolve_per_card_usd()
        effective: dict[str, float] = {}
        for klass, card_price in self.card().items():
            floor = card_price * self._floor_frac
            live = resolved.get(klass, card_price)
            clamped = min(card_price, max(floor, live))
            effective[klass] = clamped
        return effective, source
