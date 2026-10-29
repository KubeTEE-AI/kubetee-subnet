"""market_pricing: Lium feed parsing + dormant v1.3.1 market pricing.

v1.3.1 ships market pricing DORMANT (KUBETEE_MARKET_PRICING off): the
validator prices exactly like v1.3.0 and never contacts Lium. These
tests pin (a) the parser, (b) the SKU/floor rules, and (c) that OFF
really is v1.3.0-identical.
"""

import json

import pytest

import targon_payout_feed
from market_pricing import (
    MARKET_MARKUP_FRAC,
    MarketFeedError,
    _class_of_type,
    market_price,
    parse_market_response,
)
from targon_payout_feed import (
    DEFAULT_FLOOR_FRAC,
    DEFAULT_USD_CARD,
    TargonPayoutFeed,
    market_pricing_enabled,
)


class _Cfg:
    def __init__(self):
        self.usd_card_override = {}


def _feed(fetcher=None, floors=None):
    feed = TargonPayoutFeed(_Cfg(), per_card_fetcher=fetcher)
    feed.set_manual_floors(floors)
    return feed


def _frame(columns: dict[str, list], rows: list[tuple]):
    fields = [{"name": n} for n in columns]
    values = [list(r) for r in zip(*rows)] if rows else []
    return {
        "schema": {"fields": fields},
        "data": {"values": values},
    }


def _payload(frame) -> dict:
    return {"results": {"A": {"status": 200, "frames": [frame]}}}


# --- dormant-by-default ----------------------------------------------------


def test_market_pricing_disabled_by_default():
    """v1.3.1 default: flag off, weights byte-identical to v1.3.0."""
    assert market_pricing_enabled is False


def test_off_flag_yields_v130_pricing(monkeypatch):
    """Flag off -> effective_card() is the v1.3.0 clamp, no Lium traffic."""
    called = []
    monkeypatch.setattr(targon_payout_feed, "market_pricing_enabled", False)
    import market_pricing

    def _spy():
        called.append(1)
        raise MarketFeedError("must not be called")

    monkeypatch.setattr(market_pricing, "fetch_lium_per_card_usd", _spy)
    live = {"H200": 1.0, "H100": 5.0}
    effective, source = _feed(fetcher=lambda: live).effective_card()
    assert not called  # no Lium request at all
    assert effective["H200"] == pytest.approx(5.5 * DEFAULT_FLOOR_FRAC)
    assert effective["H100"] == pytest.approx(4.0)  # card cap holds
    assert source == "live"


# --- parser: Lium grafana response -> per-class -----------------------------


def test_parse_response_maps_types_and_takes_highest_sku():
    frame = _frame(
        ["type", "nodes", "median_rented", "median_all"],
        [
            ("NVIDIA B300 SXM6 AC", 40, 8.0, 7.75),
            ("NVIDIA B300 SXM6 PC", 21, 4.99, 4.99),
            ("NVIDIA H200", 43, 3.9, 3.75),
            ("NVIDIA H200 NVL", 6, 3.75, 3.75),
            ("NVIDIA B200", 18, 6.025, 6.05),
        ],
    )
    per_class = parse_market_response(_payload(frame))
    assert per_class["B300"] == pytest.approx(8.0)  # highest SKU
    assert per_class["H200"] == pytest.approx(3.9)
    assert per_class["B200"] == pytest.approx(6.025)


def test_parse_response_falls_back_to_all_nodes_median():
    """Type with no rented nodes uses the all-nodes median."""
    frame = _frame(
        ["type", "nodes", "median_rented", "median_all"],
        [
            ("NVIDIA B300 SXM6 PC", 21, None, 4.99),
            ("NVIDIA H200", 43, None, 3.75),
        ],
    )
    per_class = parse_market_response(_payload(frame))
    assert per_class["B300"] == pytest.approx(4.99)
    assert per_class["H200"] == pytest.approx(3.75)


def test_parse_response_rejects_empty_frames():
    with pytest.raises(MarketFeedError):
        parse_market_response(
            {"results": {"A": {"status": 200, "frames": []}}}
        )


def test_parse_response_rejects_bad_status():
    with pytest.raises(MarketFeedError):
        parse_market_response(
            {"results": {"A": {"status": 500, "frames": []}}}
        )


# --- SKU mapping -----------------------------------------------------------


def test_class_mapping_rules():
    assert _class_of_type("NVIDIA B300 SXM6 AC") == "B300"
    assert _class_of_type("NVIDIA B300 SXM6 PC") == "B300"
    assert _class_of_type("NVIDIA H200 NVL") == "H200"
    assert _class_of_type("NVIDIA B200") == "B200"
    # RTX PRO 6000 Blackwell maps; RTX A6000 (Ampere) must NOT map; RTX PRO
    # 5000 must NOT map; GeForce cards must NOT map.
    assert (
        _class_of_type("NVIDIA RTX PRO 6000 Blackwell Server Edition")
        == "RTX6000"
    )
    assert _class_of_type("NVIDIA RTX 6000 Ada Generation") == "RTX6000"
    assert _class_of_type("NVIDIA RTX A6000") is None
    assert _class_of_type("NVIDIA RTX PRO 5000 Blackwell") is None
    assert _class_of_type("NVIDIA GeForce RTX 5090") is None


def test_market_price_takes_highest_of_lium_and_targon():
    lium = {"H200": 3.9, "B300": 8.0}
    targon = {"H200": 3.5, "B300": 8.22}
    assert market_price("H200", lium, targon) == pytest.approx(
        3.9 * (1 + MARKET_MARKUP_FRAC)
    )
    assert market_price("B300", lium, targon) == pytest.approx(
        8.22 * (1 + MARKET_MARKUP_FRAC)
    )


def test_market_price_none_when_both_feeds_dark():
    assert market_price("H200", None, None) is None
    assert market_price("H200", {}, {}) is None


# --- market mode (KUBETEE_MARKET_PRICING=1) --------------------------------


def test_on_flag_pays_market_plus_10_percent(monkeypatch):
    """Flag on -> each class pays max(floor, 1.10 x highest(L, T))."""
    monkeypatch.setattr(targon_payout_feed, "market_pricing_enabled", True)
    import market_pricing as mp

    monkeypatch.setattr(
        mp,
        "fetch_lium_per_card_usd",
        lambda: {"H200": 3.9, "H100": 1.9, "B200": 6.025, "B300": 8.0},
    )
    live = {
        "H200": 3.5,
        "H100": 3.37,
        "B200": 6.5,
        "B300": 8.22,
        "RTX6000": 2.0,
    }
    # The real published card floors (fleet env, 2026-10-29)
    floors = {
        "H100": 3.0,
        "H200": 3.9525,
        "B200": 6.0,
        "B300": 9.495,
        "RTX6000": 1.875,
    }
    effective, source = _feed(
        fetcher=lambda: live, floors=floors
    ).effective_card()
    # H200: 1.10 x max(3.9, 3.5) = 4.29 (market wins over floor 3.9525)
    assert effective["H200"] == pytest.approx(4.29)
    # B300: 1.10 x max(8.0, 8.22) = 9.045 < floor 9.495 -> floor keeps
    assert effective["B300"] == pytest.approx(9.495)
    # H100: 1.10 x max(1.9, 3.37) = 3.707 > floor 3.0
    assert effective["H100"] == pytest.approx(3.707)
    # B200: 1.10 x max(6.025, 6.5) = 7.15 (market, uncapped: card is 8.0)
    assert effective["B200"] == pytest.approx(7.15)
    # RTX6000: 1.10 x max(-, 2.0) = 2.20 > floor 1.875
    assert effective["RTX6000"] == pytest.approx(2.2)
    assert source == "live"


def test_on_flag_no_card_cap_above_card_pays_market(monkeypatch):
    """Owner decision: no card ceiling — a market above the card pays
    market + 10% (v1.3.0 would have capped at the card)."""
    monkeypatch.setattr(targon_payout_feed, "market_pricing_enabled", True)
    import market_pricing as mp

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", lambda: {"H200": 6.0})
    live = {"H200": 3.5}
    effective, _ = _feed(fetcher=lambda: live).effective_card()
    # 1.10 x 6.0 = 6.6 > card 5.5: UNCAPPED pays 6.6
    assert effective["H200"] == pytest.approx(6.6)


def test_on_flag_floor_holds_when_market_below(monkeypatch):
    """Both feeds below the floor -> the class pays the floor."""
    monkeypatch.setattr(targon_payout_feed, "market_pricing_enabled", True)
    import market_pricing as mp

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", lambda: {"H200": 1.0})
    live = {"H200": 1.5}
    effective, _ = _feed(
        fetcher=lambda: live, floors={"H200": 3.95}
    ).effective_card()
    assert effective["H200"] == pytest.approx(3.95)


def test_on_flag_lium_down_falls_back_to_cache(monkeypatch, tmp_path):
    """Lium outage -> cached medians; still fail-soft per class."""
    monkeypatch.setattr(targon_payout_feed, "market_pricing_enabled", True)
    import market_pricing as mp

    monkeypatch.setenv("KUBETEE_LIUM_CACHE", str(tmp_path / "lium.json"))
    mp.save_lium_cache({"H200": 3.9})
    monkeypatch.setattr(
        mp,
        "fetch_lium_per_card_usd",
        lambda: (_ for _ in ()).throw(MarketFeedError("down")),
    )
    live = {"H200": 3.5}
    feed = _feed(fetcher=lambda: live)
    effective, source = feed.effective_card()
    assert effective["H200"] == pytest.approx(3.9 * (1 + MARKET_MARKUP_FRAC))
    assert feed.last_lium_source == "cache"
    assert source == "live"


def test_on_flag_class_absent_from_market_pays_floor(monkeypatch):
    """Neither feed covers a class (new GPU class) -> floor."""
    monkeypatch.setattr(targon_payout_feed, "market_pricing_enabled", True)
    import market_pricing as mp

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", lambda: {})
    live: dict[str, float] = {}
    feed = _feed(fetcher=lambda: live)
    effective, _ = feed.effective_card()
    # No manual floors -> 0.75 x card
    assert effective["B300"] == pytest.approx(10.0 * DEFAULT_FLOOR_FRAC)


def test_on_flag_uses_targon_only_when_lium_dark_for_class(monkeypatch):
    """Lium has the class dark but Targon covers it -> 1.10 x Targon."""
    monkeypatch.setattr(targon_payout_feed, "market_pricing_enabled", True)
    import market_pricing as mp

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", lambda: {})
    live = {"B300": 8.22}
    effective, _ = _feed(fetcher=lambda: live).effective_card()
    # 1.10 x 8.22 = 9.042 < floor 9.495 -> floor keeps... no wait: no manual
    # floors injected -> floor = 0.75 x 10.0 = 7.5; market 9.042 wins
    assert effective["B300"] == pytest.approx(8.22 * 1.10)


def test_on_flag_default_floors_match_v130_when_no_manual(monkeypatch):
    """No manual floors on the card -> market mode still floors at
    0.75 x card (v1.2.0/v1.3.0 floor semantics preserved)."""
    monkeypatch.setattr(targon_payout_feed, "market_pricing_enabled", True)
    import market_pricing as mp

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", lambda: {})
    live = {"H200": 1.0}
    effective, _ = _feed(fetcher=lambda: live).effective_card()
    assert effective["H200"] == pytest.approx(5.5 * DEFAULT_FLOOR_FRAC)
