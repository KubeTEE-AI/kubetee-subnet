"""The GPU price card: the consensus parameter every validator prices with.

The subnet-owner card is published to `price-card.json` and read by all. It is
NEVER trusted as-is: `clamp_to_envelope` holds every class inside
`[0.8x, 1.25x]` of the *compiled-in* `DEFAULT_USD_CARD` (imported from
`targon_payout_feed`, the trust root), so a hostile published object can
retune pay but cannot zero or mint it. The envelope is anchored to the
compiled-in default, NOT to an operator override. A class the published card
omits falls back to the compiled-in price (the designed fallback in the
feed), not the local override, so two honest validators stay identical.
"""

from __future__ import annotations

import json
import time

from targon_payout_feed import DEFAULT_USD_CARD

CARD_ENVELOPE_MIN_FRAC = 0.8
CARD_ENVELOPE_MAX_FRAC = 1.25

_CARD_VERSION = 1


class CardUnavailableError(RuntimeError):
    """No price card could be resolved at startup; refuse to start."""


def build_price_card(epoch: int, usd_per_gpu_hour: dict[str, float]) -> dict:
    """The exact published price-card.json shape."""
    return {
        "epoch": epoch,
        "published_at": time.time(),
        "usd_per_gpu_hour": {
            str(k).upper(): float(v) for k, v in usd_per_gpu_hour.items()
        },
        "version": _CARD_VERSION,
    }


def parse_price_card(payload: object) -> dict[str, float] | None:
    """Strictly validate a published card; return its {class: usd} or None."""
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != _CARD_VERSION:
        return None
    card = payload.get("usd_per_gpu_hour")
    if not isinstance(card, dict):
        return None
    out: dict[str, float] = {}
    for key, value in card.items():
        klass = str(key).upper()
        if klass not in DEFAULT_USD_CARD:
            return None  # unknown class => reject whole card
        if not isinstance(value, (int, float)) or float(value) <= 0:
            return None
        out[klass] = float(value)
    if not out:
        return None
    return out


def clamp_to_envelope(published: dict[str, float]) -> dict[str, float]:
    """Clamp each published class to [0.8x, 1.25x] of the compiled-in card.

    Classes in the published card are clamped; classes omitted fall back to
    the compiled-in price, keeping every honest validator identical.
    """
    effective: dict[str, float] = {}
    for klass, default in DEFAULT_USD_CARD.items():
        lo = default * CARD_ENVELOPE_MIN_FRAC
        hi = default * CARD_ENVELOPE_MAX_FRAC
        proposed = published.get(klass, default)
        effective[klass] = min(hi, max(lo, float(proposed)))
    return effective


def resolve_card(
    published_fetcher, fallback: dict[str, float] | None = None
) -> tuple[dict[str, float], str]:
    """Resolve the working card: published object validated+envelope-clamped.

    Returns (card, source). On any fetch/parse failure uses `fallback` (the
    last resolved card from a previous epoch) or, at startup, the compiled-in
    default. The caller refuses to START (CardUnavailableError) when a fresh
    validator has nothing at all; mid-run it keeps the previous card.
    """
    published = None
    if published_fetcher is not None:
        try:
            published = parse_price_card(published_fetcher())
        except Exception:  # noqa: BLE001 - any fetch failure is a fallback
            published = None
    if published is not None:
        return clamp_to_envelope(published), "published"
    if fallback:
        return dict(fallback), "cache"
    # Fresh validator, nothing cached, published object unavailable: fall back
    # to the trust root but signal it loudly so the caller can refuse to
    # start. Mid-run the caller passes its previous card as `fallback`.
    return dict(DEFAULT_USD_CARD), "default"


def require_card(card_source: str, is_first_cycle: bool) -> None:
    """Refuse to start a fresh validator off the compiled-in trust root only.

    A validator that has never held a published card AND cannot reach the
    published object must not silently price a live fleet off a long-stale
    compiled anchor; the owner may have retuned the card long ago. Mid-run,
    the caller passes its previous card (source "cache"), which is fine.
    """
    if is_first_cycle and card_source == "default":
        raise CardUnavailableError(
            "no price card: could not read the published price-card.json and "
            "no cached card on disk; refusing to start off the compiled-in "
            "default"
        )
