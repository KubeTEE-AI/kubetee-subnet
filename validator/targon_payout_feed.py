"""Targon (SN4) supply-side payout feed — FAIL-SOFT.

Reads live per-card USD per GPU class from Targon's snapshot API
(`stats.targon.com/api/trpc/statistics.getSnapshot` — the same endpoint
the stats site's /targets page consumes) and clamps the committed GPU
price card DOWNWARD only (never above the card). Per class, the live
value is the highest miner $/card Targon lists for it
(`compute[].unitRate`); a class with NO supplied capacity (`unitRate`
null — e.g. B200 today) resolves to Targon's published MAXIMUM payout
(`compute[].maxPrice`) instead of having no price at all. The Targon
"target price" (`targetPrice`) is deliberately never read.

Each class is floored at its manually-committed per-GPU floor (set by
the subnet owner on the published price card; see `set_manual_floors`),
so a single Targon node cannot drag a class below it. Classes without a
manual floor fall back to 0.75 x card — exactly the v1.2.0 floor, so
the transition changes nothing until the owner retunes the floors.
Always on. Degrades live -> last known (cached on disk) -> published
(S3) -> card, and never skips a cycle.

v1.3.1: the Lium "market + 10%" rule layers on top of the Targon
resolution: when the card's `pricing.lium` switch is on, effective_card()
prices each class at max(floor, 1.10 x highest(Lium median, Targon live))
with no card cap. v1.3.3 moved the switch from the KUBETEE_MARKET_PRICING
env var (which readers never edit when upgrading) onto the published
price card itself; the default (lium off) keeps this module
byte-identical to v1.3.0.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from config import Config

# v1.3.1: dormant Lium market pricing (see market_pricing.py). v1.3.3:
# the activation switch lives on the published price card
# (`pricing.lium`), set per-cycle via set_pricing_flags — no env var.

# The /api/miners REST endpoint is retired: it only listed classes with
# supplied capacity, so B200/RTX6000 had no live price at all. The snapshot
# API carries every class incl. maxPrice; it answers plain urllib GETs.
_TARGON_SNAPSHOT_URL = (
    "https://stats.targon.com/api/trpc/statistics.getSnapshot"
)
_USER_AGENT = "kubetee-validator/0.1"

DEFAULT_USD_CARD: dict[str, float] = {
    "H100": 4.00,
    "H200": 5.50,
    "B200": 8.00,
    "B300": 10.00,
    "RTX6000": 2.50,
}

# Per-class floor as a fraction of the card, used ONLY when the price card
# carries no manual floor for a class. This is exactly the v1.2.0 floor
# (KUBETEE_TARGON_PRICE_FLOOR_FRAC=0.75), so a v1.3.0 validator and a
# v1.2.0 validator agree on the floor until the owner retunes the
# published card's floors.
DEFAULT_FLOOR_FRAC = 0.75

# v1.3.1: Lium market pricing ("market + 10%") ships DORMANT. v1.3.3 moved
# the activation switch onto the published price card (`pricing.lium`), set
# per-cycle by validator.py from the card every validator reads each epoch
# (owner decision 2026-10-29: readers upgrading across versions never edit
# their .env, so an env flag could never be flipped fleet-wide). Until the
# owner flips the card's switch this is dead code: no Lium request is made
# and pricing is byte-identical to v1.3.0.
DEFAULT_PRICING: dict[str, bool] = {"targon": True, "lium": False}

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


def _per_class_from_snapshot(compute: list) -> dict[str, float]:
    """Per-class live $/card/hr from the snapshot's compute[] rows.

    `unitRate` is the highest live miner $/card in that class (the same
    statistic the /api/miners reader used); when it is null (no supplied
    capacity — B200 today), fall back to that class' `maxPrice` (the
    Targon network MAXIMUM payout) so every GPU class resolves to a live
    number. `targetPrice` is deliberately never read. CPU rows are
    skipped; multiple rows of one class collapse to the highest rate.
    """
    per_class: dict[str, float] = {}
    for row in compute:
        if not isinstance(row, dict):
            continue
        if str(row.get("kind", "gpu")) != "gpu":
            continue
        klass = _gpu_class_of(str(row.get("key", "")))
        if klass is None:
            continue
        rate = row.get("unitRate")
        if rate is None:
            rate = row.get("maxPrice")
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            continue
        if rate <= 0:
            continue
        prev = per_class.get(klass)
        if prev is None or rate > prev:
            per_class[klass] = rate
    return per_class


def fetch_live_per_card_usd() -> dict[str, float]:
    """Live $/card/hour per GPU class from the Targon snapshot API."""
    request = urllib.request.Request(
        _TARGON_SNAPSHOT_URL,
        headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())

    # tRPC/superjson response envelope: result.data.json (with plain-dict
    # fallbacks so a subtle envelope change degrades loudly, not silently).
    result = payload.get("result") if isinstance(payload, dict) else None
    data = (
        result.get("data") if isinstance(result, dict) else None
    ) or payload
    snapshot = (data.get("json") if isinstance(data, dict) else None) or data
    if not isinstance(snapshot, dict):
        raise TargonFeedError("targon snapshot api: unexpected payload")
    compute = snapshot.get("compute")
    if not isinstance(compute, list):
        raise TargonFeedError("targon snapshot api: no compute rows")

    per_class = _per_class_from_snapshot(compute)
    if not per_class:
        raise TargonFeedError("targon snapshot api: no usable per-class data")
    return per_class


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
        self._card = dict(DEFAULT_USD_CARD)
        self._card.update(config.usd_card_override)
        # Per-class manual floors from the price card. None until the
        # resolved card supplies them; validator.py injects the card's
        # floors each cycle so the feed always prices against the card
        # the subnet actually committed this epoch.
        self._manual_floors: dict[str, float] | None = None
        self._pricing_flags: dict[str, bool] = dict(DEFAULT_PRICING)
        self._fetcher = per_card_fetcher
        # v1.3.1 market-pricing diagnostics: "live" | "cache" | "off"
        self.last_lium_source = "off"

    def set_pricing_flags(self, pricing: dict[str, bool] | None) -> None:
        """Inject the resolved price card's pricing switches (v1.3.3).

        validator.py calls this each cycle right after resolving the card,
        so the mode follows the published object — flip once in S3 and
        every v1.3.3+ validator adopts it on its next epoch read. None
        resets to the defaults (targon on, lium off).
        """
        if pricing:
            self._pricing_flags = {
                str(k).lower(): bool(v) for k, v in pricing.items()
            }
        else:
            self._pricing_flags = dict(DEFAULT_PRICING)

    def pricing_flags(self) -> dict[str, bool]:
        """The active pricing switches (card-injected or defaults)."""
        return dict(self._pricing_flags)

    def lium_snapshot(self) -> dict[str, float]:
        """DISPLAY-ONLY Lium market medians (v1.3.2): one request per
        cycle for the dashboard, zero pricing impact.

        Fetches live, degrading to the on-disk cache; never raises
        (fail-soft — an empty dict means "Lium feed off" on the page).
        When the card's lium switch is on this returns the same medians
        the pricing path already fetched (no double request).
        """
        if self._pricing_flags.get("lium"):
            return dict(getattr(self, "_lium_used", {}) or {})
        from market_pricing import (  # noqa: PLC0415 - lazy: display only
            fetch_lium_per_card_usd,
            load_lium_cache,
            save_lium_cache,
        )

        try:
            per_card = fetch_lium_per_card_usd()
            save_lium_cache(per_card)
            return per_card
        except Exception:  # noqa: BLE001 - display only, fail-soft
            cached = load_lium_cache()
            return dict(cached) if cached else {}

    def card(self) -> dict[str, float]:
        """The committed card (compiled-in default + operator override)."""
        return dict(self._card)

    def set_manual_floors(self, floors: dict[str, float] | None) -> None:
        """Inject the resolved price card's manual per-class floors."""
        self._manual_floors = (
            {
                str(k).upper(): float(v)
                for k, v in floors.items()
                if float(v) > 0
            }
            if floors
            else None
        )

    def floor_for(self, klass: str, card_price: float) -> float:
        """The floor for one class: the card's manual floor if set, else
        the v1.2.0-compatible default (0.75 x card)."""
        manual = (self._manual_floors or {}).get(klass)
        if manual is not None and manual > 0:
            return min(manual, card_price)
        return card_price * DEFAULT_FLOOR_FRAC

    def resolve_per_card_usd(self) -> tuple[dict[str, float], str]:
        """The per-card USD per class, plus the source that supplied it.

        Degrades live -> cache -> published (S3) -> card. Never raises
        (fail-soft).
        """
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
        """Card clamped to [manual floor, card] per class, and source.

        v1.3.3: when the published card's `pricing.lium` switch is on,
        each class instead prices at
        ``max(floor, 1.10 x highest(Lium median, Targon live))`` with NO
        card cap (owner decision 2026-10-29). With the switch off
        (default) this is byte-identical to v1.3.0.

        The `targon` switch (default on) gates the supply-side clamp
        itself: off = pay the flat card, no feed pull-down.
        """
        resolved, source = self.resolve_per_card_usd()
        if self._pricing_flags.get("lium"):
            return self._market_effective_card(resolved), source
        if not self._pricing_flags.get("targon", True):
            # Targon clamp off: pay the flat card (floors still hold via
            # min(card, ...) trivially — the card IS the price).
            return self.card(), source
        effective: dict[str, float] = {}
        for klass, card_price in self.card().items():
            floor = self.floor_for(klass, card_price)
            live = resolved.get(klass, card_price)
            clamped = min(card_price, max(floor, live))
            effective[klass] = clamped
        return effective, source

    def _market_effective_card(
        self, targon: dict[str, float]
    ) -> dict[str, float]:
        """max(floor, 1.10 x highest(Lium, Targon)) per class — uncapped.

        The static floor still holds when both feeds price a class below
        it (or neither feed covers the class). This path only runs when
        the card's `pricing.lium` switch is on; it never caps at the card.
        """
        lium: dict[str, float] | None = None
        lium_source = "off"
        from market_pricing import (  # noqa: PLC0415 - lazy: dormant path only
            fetch_lium_per_card_usd,
            load_lium_cache,
            market_price,
            save_lium_cache,
        )

        try:
            lium = fetch_lium_per_card_usd()
            save_lium_cache(lium)
            lium_source = "live"
        except Exception:  # noqa: BLE001 - fail-soft to cache
            lium = load_lium_cache()
            if lium:
                lium_source = "cache"
        self.last_lium_source = lium_source
        self._lium_used = dict(lium or {})
        effective: dict[str, float] = {}
        for klass, card_price in self.card().items():
            floor = self.floor_for(klass, card_price)
            market = market_price(klass, lium, targon)
            if market is None:
                effective[klass] = floor
                continue
            effective[klass] = max(floor, market)
        return effective
