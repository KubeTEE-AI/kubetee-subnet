"""price_feed + targon clamp: hard-fail vs fail-soft, envelope bounds."""

import pytest

from price_feed import PriceFeedError
from targon_payout_feed import (
    DEFAULT_USD_CARD,
    TargonFeedError,
    TargonPayoutFeed,
    _per_card_from_miners,
)
from price_card import clamp_to_envelope, parse_price_card


class _Cfg:
    def __init__(self, floor=0.75):
        self.targon_floor_frac = floor
        self.usd_card_override = {}
        # PriceFeed fields
        self.taostats_api_key = "test-key"
        self.netuid = 90


def _feed(floor=0.75, fetcher=None):
    return TargonPayoutFeed(_Cfg(floor), per_card_fetcher=fetcher)


def test_targon_live_uses_highest_per_card_not_average():
    """Each GPU class takes the max miner $/card, not the card-weighted mean."""
    miners = [
        {"compute_type": "H200", "payout": 20.0, "cards": 8},  # $2.50/card
        {"compute_type": "H200", "payout": 36.0, "cards": 8},  # $4.50/card
        {"compute_type": "B200", "payout": 40.0, "cards": 8},  # $5.00/card
        {"compute_type": "B200", "payout": 64.0, "cards": 8},  # $8.00/card
        {"compute_type": "skip-me", "payout": 99.0, "cards": 1},
        {"compute_type": "H100", "payout": 0, "cards": 8},
    ]
    per_card = _per_card_from_miners(miners)
    assert per_card["H200"] == pytest.approx(4.50)
    assert per_card["B200"] == pytest.approx(8.00)
    assert "H100" not in per_card


def test_targon_live_clamps_downward_and_floors():
    live = {"H200": 1.0, "H100": 5.0}  # H200 way below, H100 above card
    effective, source = _feed(floor=0.75, fetcher=lambda: live).effective_card()
    # H200 floor = 5.50*0.75 = 4.125 (live 1.0 is lifted to floor)
    assert effective["H200"] == pytest.approx(4.125)
    # H100 capped at card (live 5.0 pulled down to 4.0)
    assert effective["H100"] == pytest.approx(4.0)
    # classes not in live fall back to card
    assert effective["B200"] == pytest.approx(8.0)
    assert source == "live"


def test_targon_live_failure_falls_back_to_card(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "targon_payout_feed.CACHE_PATH", str(tmp_path / "none.json")
    )
    # Simulate no published payout on S3 (4th tier) so we fall through to card.
    monkeypatch.setattr("hippius_store.fetch_published_payout", lambda: None)

    def boom():
        raise TargonFeedError("no data")

    effective, source = _feed(fetcher=boom).effective_card()
    assert source == "card"
    assert effective == DEFAULT_USD_CARD


def test_clamp_to_envelope_bounds():
    published = {"H100": 100.0, "H200": 0.01}
    effective = clamp_to_envelope(published)
    assert effective["H100"] == pytest.approx(4.0 * 1.25)  # capped at 1.25x
    assert effective["H200"] == pytest.approx(5.5 * 0.8)  # floored at 0.8x
    # omitted class falls back to compiled-in default
    assert effective["B200"] == pytest.approx(8.0)


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


# --- S3 fallback: PriceFeed.usd_per_alpha_from_published ---------------------


def test_published_fallback_extracts_usd_per_alpha():
    from price_feed import PriceFeed

    cfg = _Cfg()
    feed = PriceFeed(cfg)
    published = {"tao_usd": 200.0, "alpha_to_tao": 0.0035}
    assert feed.usd_per_alpha_from_published(published) == pytest.approx(0.7)


def test_published_fallback_returns_none_on_missing_fields():
    from price_feed import PriceFeed

    cfg = _Cfg()
    feed = PriceFeed(cfg)
    assert feed.usd_per_alpha_from_published({}) is None
    assert feed.usd_per_alpha_from_published({"tao_usd": 200.0}) is None
    assert feed.usd_per_alpha_from_published({"alpha_to_tao": 0.0035}) is None
    assert feed.usd_per_alpha_from_published("not a dict") is None


def test_published_fallback_returns_none_on_zero_or_negative():
    from price_feed import PriceFeed

    cfg = _Cfg()
    feed = PriceFeed(cfg)
    assert (
        feed.usd_per_alpha_from_published(
            {"tao_usd": 0, "alpha_to_tao": 0.0035}
        )
        is None
    )
    assert (
        feed.usd_per_alpha_from_published(
            {"tao_usd": 200.0, "alpha_to_tao": -1}
        )
        is None
    )


def test_published_fallback_tao_usd():
    from price_feed import PriceFeed

    cfg = _Cfg()
    feed = PriceFeed(cfg)
    assert feed.tao_usd_from_published({"tao_usd": 215.5}) == pytest.approx(
        215.5
    )
    assert feed.tao_usd_from_published({}) is None
    assert feed.tao_usd_from_published({"tao_usd": -1}) is None


# --- Targon 4th tier: published payout.json --------------------------------


def test_targon_falls_back_to_published_payout(tmp_path, monkeypatch):
    """When live fails + no local cache, fall back to published payout.json."""
    monkeypatch.setattr(
        "targon_payout_feed.CACHE_PATH", str(tmp_path / "none.json")
    )
    monkeypatch.setattr(
        "hippius_store.fetch_published_payout",
        lambda: {"per_card_usd": {"H100": 2.9, "H200": 3.4}},
    )

    def boom():
        raise TargonFeedError("no data")

    feed = _feed(fetcher=boom)
    resolved, source = feed.resolve_per_card_usd()
    assert source == "published"
    assert resolved == {"H100": 2.9, "H200": 3.4}


def test_targon_published_fallback_skips_invalid_entries(
    tmp_path, monkeypatch
):
    """Invalid (zero/negative) entries in the published snapshot are dropped."""
    monkeypatch.setattr(
        "targon_payout_feed.CACHE_PATH", str(tmp_path / "none.json")
    )
    monkeypatch.setattr(
        "hippius_store.fetch_published_payout",
        lambda: {
            "per_card_usd": {"H100": 2.9, "H200": 0, "B200": -1, "B300": 7.5}
        },
    )

    def boom():
        raise TargonFeedError("no data")

    feed = _feed(fetcher=boom)
    resolved, source = feed.resolve_per_card_usd()
    assert source == "published"
    assert resolved == {"H100": 2.9, "B300": 7.5}


def test_targon_published_failure_falls_to_card(tmp_path, monkeypatch):
    """When live + cache + published all fail, fall back to the compiled card."""
    monkeypatch.setattr(
        "targon_payout_feed.CACHE_PATH", str(tmp_path / "none.json")
    )
    monkeypatch.setattr("hippius_store.fetch_published_payout", lambda: None)

    def boom():
        raise TargonFeedError("no data")

    feed = _feed(fetcher=boom)
    resolved, source = feed.resolve_per_card_usd()
    assert source == "card"
    assert resolved == DEFAULT_USD_CARD
