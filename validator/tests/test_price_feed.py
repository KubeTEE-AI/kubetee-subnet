"""price_feed + targon clamp: hard-fail vs fail-soft, envelope bounds."""

import pytest

from price_feed import PriceFeedError
from targon_payout_feed import (
    DEFAULT_USD_CARD,
    TargonFeedError,
    TargonPayoutFeed,
)
from price_card import clamp_to_envelope, parse_price_card


class _Cfg:
    def __init__(self, enabled=False, floor=0.75):
        self.targon_payout_enabled = enabled
        self.targon_floor_frac = floor
        self.usd_card_override = {}


def _feed(enabled=True, floor=0.75, fetcher=None):
    return TargonPayoutFeed(_Cfg(enabled, floor), per_card_fetcher=fetcher)


def test_targon_disabled_uses_card():
    effective, source = _feed(
        enabled=False, fetcher=lambda: {"H100": 1.0}
    ).effective_card()
    assert effective == DEFAULT_USD_CARD
    assert source == "card"


def test_targon_live_clamps_downward_and_floors():
    live = {"H200": 1.0, "H100": 4.0}  # H200 way below, H100 above card
    effective, source = _feed(
        enabled=True, floor=0.75, fetcher=lambda: live
    ).effective_card()
    # H200 floor = 3.5*0.75 = 2.625 (live 1.0 is lifted to floor)
    assert effective["H200"] == pytest.approx(2.625)
    # H100 capped at card (live 4.0 pulled down to 3.0)
    assert effective["H100"] == pytest.approx(3.0)
    # classes not in live fall back to card
    assert effective["B200"] == pytest.approx(6.5)
    assert source == "live"


def test_targon_live_failure_falls_back_to_card(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "targon_payout_feed.CACHE_PATH", str(tmp_path / "none.json")
    )

    def boom():
        raise TargonFeedError("no data")

    effective, source = _feed(enabled=True, fetcher=boom).effective_card()
    assert source == "card"
    assert effective == DEFAULT_USD_CARD


def test_clamp_to_envelope_bounds():
    published = {"H100": 100.0, "H200": 0.01}
    effective = clamp_to_envelope(published)
    assert effective["H100"] == pytest.approx(3.0 * 1.25)  # capped at 1.25x
    assert effective["H200"] == pytest.approx(3.5 * 0.8)  # floored at 0.8x
    # omitted class falls back to compiled-in default
    assert effective["B200"] == pytest.approx(6.5)


def test_parse_price_card_rejects_unknown_class_and_bad_values():
    assert (
        parse_price_card({"usd_per_gpu_hour": {"DOGE": 1.0}, "version": 1})
        is None
    )
    assert (
        parse_price_card({"usd_per_gpu_hour": {"H100": 0}, "version": 1})
        is None
    )
    assert (
        parse_price_card({"usd_per_gpu_hour": {"H100": 1.0}, "version": 2})
        is None
    )
    ok = parse_price_card(
        {"usd_per_gpu_hour": {"H100": 3.0, "H200": 3.5}, "version": 1}
    )
    assert ok == {"H100": 3.0, "H200": 3.5}


def test_pricefeederror_is_runtimeerror():
    assert issubclass(PriceFeedError, RuntimeError)
