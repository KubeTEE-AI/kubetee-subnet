"""The GPU price card: the consensus parameter every validator prices with.

The subnet-owner card is published to `price-card.json` and read by all. It is
NEVER trusted as-is: `clamp_to_envelope` holds every class inside
`[0.8x, 1.25x]` of the *compiled-in* `DEFAULT_USD_CARD` (imported from
`targon_payout_feed`, the trust root), so a hostile published object can
retune pay but cannot zero or mint it. The envelope is anchored to the
compiled-in default, NOT to an operator override. A class the published card
omits falls back to the compiled-in price (the designed fallback in the
feed), not the local override, so two honest validators stay identical.

The card also carries the **pricing switches** (v1.3.3): the flat fields
`targon_pricing` (default `true`) and `lium_pricing` (default `false`)
move the per-epoch pricing MODE onto the consensus object itself,
replacing the v1.3.1 `KUBETEE_MARKET_PRICING` env flag (readers
upgrading across versions never edit their `.env`, so an env flag could
never be flipped fleet-wide). Defaults reproduce v1.3.0 pricing exactly;
the owner flips them by editing the published card
(`scripts/set_pricing_flags.py`) and every v1.3.3+ validator adopts the
new mode on its next epoch read. A card that omits them (any pre-v1.3.3
writer) parses to the defaults, so old and new validators agree in both
directions — until the owner flips a switch, which is a deliberate act
gated on every weight-setting validator running v1.3.3+.

The card also carries **manual per-class floors** (`floors`): the USD values
below which the live Targon payout can never pull a class. They replace the
old global `floor_frac x card` (v1.2.0, `KUBETEE_TARGON_PRICE_FLOOR_FRAC`).

Transition safety (v1.2.0 <-> v1.3.0): the card keeps `version: 1` and the
`floors` field is optional. A v1.2.0 validator ignores the unknown field and
keeps its own `0.75 x card` floor; a v1.3.0 validator reading a card WITHOUT
floors falls back to `0.75 x card` per class (the same numbers) — so the
two versions agree in both directions as long as the owner publishes floors
equal to `0.75 x card` (the publisher's default when no floor override is
set). Retuning floors away from `0.75 x card` is a deliberate owner act and
must wait until every weight-setting validator runs v1.3.0.

A published floor is trusted only inside `[0.5x, 1.25x]` of the compiled-in
default for that class, so a hostile card cannot free a class from its floor
entirely nor set the floor above the envelope ceiling. A floor is
additionally capped at the class' own card price when consumed (see
`TargonPayoutFeed.floor_for`), so a floor can pin a class at the card but
never push effective pay above it.
"""

from __future__ import annotations

import time

from targon_payout_feed import DEFAULT_PRICING, DEFAULT_USD_CARD

CARD_ENVELOPE_MIN_FRAC = 0.8
CARD_ENVELOPE_MAX_FRAC = 1.25

# A published manual floor is trusted only inside this band of the
# compiled-in default for that class.
FLOOR_ENVELOPE_MIN_FRAC = 0.5
FLOOR_ENVELOPE_MAX_FRAC = 1.25

_CARD_VERSION = 1


class CardUnavailableError(RuntimeError):
    """No price card could be resolved at startup; refuse to start."""


def build_price_card(
    epoch: int,
    usd_per_gpu_hour: dict[str, float],
    floors: dict[str, float] | None = None,
    pricing: dict[str, bool] | None = None,
) -> dict:
    """The exact published price-card.json shape (v1.3.0 adds `floors`,
    v1.3.3 adds the `targon_pricing`/`lium_pricing` switches).

    `floors` is optional and omitted when empty, so older readers and newer
    ones both accept the object (version stays 1; each side's parser skips
    unknown fields). The pricing switches (`targon_pricing` default true,
    `lium_pricing` default false) are written as FLAT fields; a reader that
    predates v1.3.3 ignores them and keeps its compiled-in behavior.
    """
    card: dict = {
        "epoch": epoch,
        "published_at": time.time(),
        "usd_per_gpu_hour": {
            str(k).upper(): float(v) for k, v in usd_per_gpu_hour.items()
        },
        "version": _CARD_VERSION,
    }
    if floors:
        card["floors"] = {str(k).upper(): float(v) for k, v in floors.items()}
    switches = dict(DEFAULT_PRICING)
    if pricing:
        for key, value in pricing.items():
            name = str(key).lower()
            if name in switches and isinstance(value, bool):
                switches[name] = value
    card.update({f"{name}_pricing": value for name, value in switches.items()})
    return card


def _floors_from_payload(payload: dict) -> dict[str, float] | None:
    """Extract + envelope-clamp the manual floors, or None if absent/invalid.

    Invalid floors (unknown class, non-positive, out-of-band) are dropped
    individually; a floor-less payload returns None so consumers fall back
    to `0.75 x card` per class — exactly the v1.2.0 floor.
    """
    raw = payload.get("floors")
    if not isinstance(raw, dict) or not raw:
        return None
    floors: dict[str, float] = {}
    for key, value in raw.items():
        klass = str(key).upper()
        default = DEFAULT_USD_CARD.get(klass)
        if default is None:
            continue  # unknown class: drop that floor, keep the card
        if not isinstance(value, (int, float)) or float(value) <= 0:
            continue
        lo = default * FLOOR_ENVELOPE_MIN_FRAC
        hi = default * FLOOR_ENVELOPE_MAX_FRAC
        floors[klass] = min(hi, max(lo, float(value)))
    return floors or None


def _pricing_from_payload(payload: dict) -> dict[str, bool]:
    """Extract the `targon_pricing`/`lium_pricing` switches, or the
    defaults if absent/invalid.

    Non-boolean values drop to the default for that switch; a payload
    without either field parses to the defaults (targon on, lium off) —
    exactly what every pre-v1.3.3 card means.
    """
    pricing = dict(DEFAULT_PRICING)
    for name, default in DEFAULT_PRICING.items():
        raw = payload.get(f"{name}_pricing")
        if isinstance(raw, bool):
            pricing[name] = raw
    return pricing


def parse_price_card(
    payload: object,
) -> tuple[dict[str, float], dict[str, float] | None, dict[str, bool]] | None:
    """Validate a published card; return ({class: usd}, {class: floor},
    {switch: on/off}).

    Returns None if the payload is not a valid v1 card. The floors half is
    None when the card carries no floors (pre-v1.3.0 shape) — consumers then
    default to `0.75 x card` per class, which is exactly what v1.2.0 does,
    keeping the two versions in sync during the transition. The pricing
    half defaults to (targon on, lium off) when the card carries no
    `pricing` object (pre-v1.3.3 shape).
    """
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
    return out, _floors_from_payload(payload), _pricing_from_payload(payload)


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
    published_fetcher,
    fallback: (
        tuple[
            dict[str, float],
            dict[str, float] | None,
            dict[str, bool],
        ]
        | None
    ) = None,
) -> tuple[dict[str, float], dict[str, float] | None, dict[str, bool], str]:
    """Resolve the working (card, floors, pricing) triple from the
    published object.

    The card half is validated + envelope-clamped; the floors half is
    extracted + floor-envelope-clamped (or None when the card predates
    v1.3.0, mapping to the v1.2.0-equivalent `0.75 x card` default in the
    feed); the pricing half defaults to (targon on, lium off) when the card
    predates v1.3.3. Returns (card, floors, pricing, source). On any
    fetch/parse failure uses `fallback` (the previous epoch's triple) or,
    at startup, the compiled-in default with no floors and default
    pricing. The caller refuses to START
    (CardUnavailableError) when a fresh validator has nothing at all;
    mid-run it keeps the previous card.
    """
    published = None
    if published_fetcher is not None:
        try:
            published = parse_price_card(published_fetcher())
        except Exception:  # noqa: BLE001 - any fetch failure is a fallback
            published = None
    if published is not None:
        card, floors, pricing = published
        return clamp_to_envelope(card), floors, pricing, "published"
    if fallback is not None and fallback[0]:
        return (
            dict(fallback[0]),
            (dict(fallback[1]) if fallback[1] else None),
            dict(fallback[2]),
            "cache",
        )
    # Fresh validator, nothing cached, published object unavailable: fall
    # back to the trust root but signal it loudly so the caller can refuse
    # to start. Mid-run the caller passes its previous card as `fallback`.
    return (
        dict(DEFAULT_USD_CARD),
        None,
        dict(DEFAULT_PRICING),
        "default",
    )


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
