"""market_pricing: Lium feed parsing + the card-switched market rule.

v1.3.3: the market + 10% rule is selected by the published price card's
`pricing.lium` switch (injected per-cycle via set_pricing_flags), not an
env var — readers upgrading across versions never edit their .env. These
tests pin (a) the parser, (b) the SKU/floor rules, (c) that switches-off
really is v1.3.0-identical, and (d) the card-driven activation.
"""

import json

import pytest

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
)


class _Cfg:
    def __init__(self):
        self.usd_card_override = {}


def _feed(fetcher=None, floors=None, pricing=None):
    feed = TargonPayoutFeed(_Cfg(), per_card_fetcher=fetcher)
    feed.set_manual_floors(floors)
    feed.set_pricing_flags(pricing)
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


# --- dormant by default ------------------------------------------------------


def test_defaults_are_targon_on_lium_off():
    """Fresh feed: the v1.3.0 clamp, no Lium traffic, until the card
    injects switches."""
    feed = _feed()
    assert feed.pricing_flags() == {"targon": True, "lium": False}


def test_switches_off_yields_v130_pricing(monkeypatch):
    """Card switches default -> effective_card() is the v1.3.0 clamp,
    no Lium traffic."""
    called = []
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


def test_targon_switch_off_pays_flat_card(monkeypatch):
    """pricing.targon=false: no feed pull-down — pay the card exactly."""
    import market_pricing as mp

    called = []

    def _spy():
        called.append(1)
        return {"H200": 0.01}

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", _spy)
    live = {"H200": 1.0, "H100": 5.0}
    effective, source = _feed(
        fetcher=lambda: live, pricing={"targon": False, "lium": False}
    ).effective_card()
    assert not called
    assert effective == {
        k: pytest.approx(v) for k, v in DEFAULT_USD_CARD.items()
    }
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


# --- market mode (card's pricing.lium switch on) -----------------------------


def test_lium_switch_on_pays_market_plus_10_percent(monkeypatch):
    """Switch on -> each class pays max(floor, 1.10 x highest(L, T))."""
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
        fetcher=lambda: live,
        floors=floors,
        pricing={"targon": True, "lium": True},
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


def test_lium_switch_on_no_card_cap_above_card_pays_market(monkeypatch):
    """Owner decision: no card ceiling — a market above the card pays
    market + 10% (v1.3.0 would have capped at the card)."""
    import market_pricing as mp

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", lambda: {"H200": 6.0})
    live = {"H200": 3.5}
    effective, _ = _feed(
        fetcher=lambda: live, pricing={"targon": True, "lium": True}
    ).effective_card()
    # 1.10 x 6.0 = 6.6 > card 5.5: UNCAPPED pays 6.6
    assert effective["H200"] == pytest.approx(6.6)


def test_lium_switch_on_floor_holds_when_market_below(monkeypatch):
    """Both feeds below the floor -> the class pays the floor."""
    import market_pricing as mp

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", lambda: {"H200": 1.0})
    live = {"H200": 1.5}
    effective, _ = _feed(
        fetcher=lambda: live,
        floors={"H200": 3.95},
        pricing={"targon": True, "lium": True},
    ).effective_card()
    assert effective["H200"] == pytest.approx(3.95)


def test_lium_switch_on_lium_down_falls_back_to_cache(monkeypatch, tmp_path):
    """Lium outage -> cached medians; still fail-soft per class."""
    import market_pricing as mp

    monkeypatch.setenv("KUBETEE_LIUM_CACHE", str(tmp_path / "lium.json"))
    mp.save_lium_cache({"H200": 3.9})
    monkeypatch.setattr(
        mp,
        "fetch_lium_per_card_usd",
        lambda: (_ for _ in ()).throw(MarketFeedError("down")),
    )
    live = {"H200": 3.5}
    feed = _feed(fetcher=lambda: live, pricing={"targon": True, "lium": True})
    effective, source = feed.effective_card()
    assert effective["H200"] == pytest.approx(3.9 * (1 + MARKET_MARKUP_FRAC))
    assert feed.last_lium_source == "cache"
    assert source == "live"


def test_lium_switch_on_class_absent_from_market_pays_floor(monkeypatch):
    """Neither feed covers a class (new GPU class) -> floor."""
    import market_pricing as mp

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", lambda: {})
    live: dict[str, float] = {}
    feed = _feed(fetcher=lambda: live, pricing={"targon": True, "lium": True})
    effective, _ = feed.effective_card()
    # No manual floors -> 0.75 x card
    assert effective["B300"] == pytest.approx(10.0 * DEFAULT_FLOOR_FRAC)


def test_lium_switch_on_uses_targon_only_when_lium_dark_for_class(
    monkeypatch,
):
    """Lium has the class dark but Targon covers it -> 1.10 x Targon."""
    import market_pricing as mp

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", lambda: {})
    live = {"B300": 8.22}
    effective, _ = _feed(
        fetcher=lambda: live, pricing={"targon": True, "lium": True}
    ).effective_card()
    # No manual floors injected -> floor = 0.75 x 10.0 = 7.5; market 9.042 wins
    assert effective["B300"] == pytest.approx(8.22 * 1.10)


def test_lium_switch_on_default_floors_match_v130_when_no_manual(monkeypatch):
    """No manual floors on the card -> market mode still floors at
    0.75 x card (v1.2.0/v1.3.0 floor semantics preserved)."""
    import market_pricing as mp

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", lambda: {})
    live = {"H200": 1.0}
    effective, _ = _feed(
        fetcher=lambda: live, pricing={"targon": True, "lium": True}
    ).effective_card()
    assert effective["H200"] == pytest.approx(5.5 * DEFAULT_FLOOR_FRAC)


# --- v1.3.2 display-only Lium snapshot --------------------------------------


def test_lium_snapshot_display_only_switches_off(monkeypatch):
    """Switch off: lium_snapshot() fetches for DISPLAY, never touches
    effective_card() — weights stay byte-identical to v1.3.0."""
    import market_pricing as mp

    monkeypatch.setattr(
        mp,
        "fetch_lium_per_card_usd",
        lambda: {"H200": 3.9, "B200": 6.025},
    )
    feed = _feed(fetcher=lambda: {"H200": 1.0})
    snap = feed.lium_snapshot()
    assert snap == {"H200": 3.9, "B200": 6.025}
    # pricing unchanged: floor 0.75 x 5.5 = 4.125 lifts live 1.0
    effective, _ = feed.effective_card()
    assert effective["H200"] == pytest.approx(4.125)


def test_lium_snapshot_reuses_market_fetch_when_switch_on(monkeypatch):
    """Switch on: lium_snapshot() returns the same medians the pricing
    path fetched (no second Lium request)."""
    import market_pricing as mp

    calls = []

    def _fetch():
        calls.append(1)
        return {"H200": 3.9}

    monkeypatch.setattr(mp, "fetch_lium_per_card_usd", _fetch)
    feed = _feed(
        fetcher=lambda: {"H200": 3.5},
        pricing={"targon": True, "lium": True},
    )
    feed.effective_card()  # pricing fetch #1
    snap = feed.lium_snapshot()
    assert snap == {"H200": 3.9}
    assert len(calls) == 1  # display reused the pricing fetch


def test_lium_snapshot_fail_soft_off(monkeypatch):
    """Lium down + no cache -> empty dict (page shows 'Lium feed off')."""
    import market_pricing as mp

    monkeypatch.setenv("KUBETEE_LIUM_CACHE", "/nonexistent/lium.json")
    monkeypatch.setattr(
        mp,
        "fetch_lium_per_card_usd",
        lambda: (_ for _ in ()).throw(MarketFeedError("down")),
    )
    feed = _feed(fetcher=lambda: {})
    assert feed.lium_snapshot() == {}


def test_dashboard_renders_lium_panel():
    import dashboard as _dashboard

    snapshot = {
        "epoch": 1,
        "block": 1,
        "tempo": 360,
        "hours_per_epoch": 1.2,
        "usd_per_alpha": 4.2,
        "card": {"H200": 5.5},
        "floors": {"H200": 4.125},
        "effective_card": {"H200": 4.125},
        "targon_payout": {"H200": 3.5},
        "lium_payout": {"H200": 3.9},
        "lium_pricing": False,
        "targon_pricing": True,
        "miners": [],
        "fleet_gpus": {"H200": 8},
        "miner_usd": 0.0,
        "owner_usd": 0.0,
        "total_pool_usd": 0.0,
        "published_at": 1793000000.0,
    }
    html_out = _dashboard.build_html(snapshot)
    assert "Lium market" in html_out
    assert "median of rented nodes" in html_out
    assert "display only" in html_out
    assert "$3.90" in html_out
    assert "live — clamps pay toward SN4" in html_out
    blob = _dashboard.build_dashboard_json(snapshot)
    assert blob["lium_payout"] == {"H200": 3.9}
    assert blob["lium_pricing"] is False
    assert blob["targon_pricing"] is True
