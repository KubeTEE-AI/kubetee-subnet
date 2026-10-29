"""price_feed + targon clamp: hard-fail vs fail-soft, envelope bounds."""

import pytest

from price_feed import PriceFeedError
from targon_payout_feed import (
    DEFAULT_FLOOR_FRAC,
    DEFAULT_USD_CARD,
    TargonFeedError,
    TargonPayoutFeed,
    _per_class_from_snapshot,
)
from price_card import (
    FLOOR_ENVELOPE_MAX_FRAC,
    FLOOR_ENVELOPE_MIN_FRAC,
    clamp_to_envelope,
    parse_price_card,
    resolve_card,
)


class _Cfg:
    def __init__(self):
        self.usd_card_override = {}
        # PriceFeed fields
        self.taostats_api_key = "test-key"
        self.netuid = 90


def _feed(fetcher=None, floors=None):
    feed = TargonPayoutFeed(_Cfg(), per_card_fetcher=fetcher)
    feed.set_manual_floors(floors)
    return feed


# --- snapshot parsing (tRPC compute[] rows) -------------------------------


def test_snapshot_takes_unit_rate_and_falls_back_to_max_price():
    """unitRate (highest live $/card) wins; null unitRate -> maxPrice."""
    compute = [
        {
            "key": "TDX-VM-NVIDIA-H200",
            "kind": "gpu",
            "unitRate": 3.0,
            "maxPrice": 4.5,
        },
        {
            "key": "SEV-VM-NVIDIA-B300",
            "kind": "gpu",
            "unitRate": 6.09,
            "maxPrice": 9.75,
        },
        # B200 has no supply: unitRate null -> maxPrice
        {
            "key": "TDX-BLACKWELL-NVIDIA-B200",
            "kind": "gpu",
            "unitRate": None,
            "maxPrice": 6.5,
        },
        # CPU rows are skipped even though they carry rates
        {"key": "SEV-VM-CPU", "kind": "cpu", "unitRate": 0.1, "maxPrice": 0.2},
        # targetPrice must never be read: absent here on purpose
    ]
    per_class = _per_class_from_snapshot(compute)
    assert per_class["H200"] == pytest.approx(3.0)
    assert per_class["B300"] == pytest.approx(6.09)
    assert per_class["B200"] == pytest.approx(6.5)
    assert "RTX6000" not in per_class or per_class["RTX6000"] > 0
    assert all(
        k in ("H100", "H200", "B200", "B300", "RTX6000") for k in per_class
    )


def test_snapshot_collapses_class_variants_to_highest():
    """Multiple compute types of one GPU class -> highest rate."""
    compute = [
        {
            "key": "TDX-VM-NVIDIA-B300",
            "kind": "gpu",
            "unitRate": 8.23,
            "maxPrice": 9.75,
        },
        {
            "key": "SEV-VM-NVIDIA-B300",
            "kind": "gpu",
            "unitRate": 6.09,
            "maxPrice": 9.75,
        },
        {
            "key": "TDX-BLACKWELL-NVIDIA-B300",
            "kind": "gpu",
            "unitRate": None,
            "maxPrice": 6.5,
        },
    ]
    per_class = _per_class_from_snapshot(compute)
    assert per_class == {"B300": pytest.approx(8.23)}


def test_snapshot_never_reads_target_price():
    """A row with only targetPrice (no unitRate/maxPrice) yields nothing."""
    compute = [
        {
            "key": "TDX-VM-NVIDIA-H200",
            "kind": "gpu",
            "unitRate": None,
            "maxPrice": None,
            "targetPrice": 2.9,
        },
    ]
    assert _per_class_from_snapshot(compute) == {}


# --- manual floors (v1.3.0: replace KUBETEE_TARGON_PRICE_FLOOR_FRAC) --------


def test_default_floor_matches_v120_when_no_manual_floors():
    """No floors on the card -> 0.75 x card per class (v1.2.0 parity)."""
    live = {"H200": 1.0, "H100": 5.0}  # H200 way below floor, H100 above card
    effective, source = _feed(fetcher=lambda: live).effective_card()
    # H200 floor = 5.50 * 0.75 = 4.125 (live 1.0 lifted to floor)
    assert effective["H200"] == pytest.approx(5.5 * DEFAULT_FLOOR_FRAC)
    # H100 capped at card (live 5.0 pulled down to 4.0)
    assert effective["H100"] == pytest.approx(4.0)
    # classes not in live fall back to card
    assert effective["B200"] == pytest.approx(8.0)
    assert source == "live"


def test_manual_floor_pins_class_above_default():
    """A card-set floor replaces 0.75 x card for that class."""
    live = {"H200": 3.0}
    effective, _ = _feed(
        fetcher=lambda: live, floors={"H200": 3.95}
    ).effective_card()
    assert effective["H200"] == pytest.approx(3.95)  # lifted to manual floor


def test_manual_floor_below_live_is_inert():
    """Live above the manual floor passes (capped at the card)."""
    live = {"H200": 5.0}
    effective, _ = _feed(
        fetcher=lambda: live, floors={"H200": 2.0}
    ).effective_card()
    assert effective["H200"] == pytest.approx(5.0)


def test_manual_floor_capped_at_card_price():
    """A floor above the class' card price cannot push pay above the card."""
    live = {"H200": 1.0}
    effective, _ = _feed(
        fetcher=lambda: live, floors={"H200": 99.0}
    ).effective_card()
    assert effective["H200"] == pytest.approx(5.5)  # the card


def test_floored_class_in_card_without_override_uses_default_frac():
    """A class missing from the floors dict keeps the 0.75 x card floor."""
    live = {"B300": 1.0}
    effective, _ = _feed(
        fetcher=lambda: live, floors={"H200": 3.95}
    ).effective_card()
    assert effective["B300"] == pytest.approx(10.0 * DEFAULT_FLOOR_FRAC)


# --- price card parse/clamp (card + floors pair) ---------------------------


def test_clamp_to_envelope_bounds():
    published = {"H100": 100.0, "H200": 0.01}
    effective = clamp_to_envelope(published)
    assert effective["H100"] == pytest.approx(4.0 * 1.25)  # capped at 1.25x
    assert effective["H200"] == pytest.approx(5.5 * 0.8)  # floored at 0.8x
    # omitted class falls back to compiled-in default
    assert effective["B200"] == pytest.approx(8.0)


def test_parse_price_card_extracts_floors_and_envelopes_them():
    floors = {"H200": 3.95, "B300": 9.5}
    parsed = parse_price_card(
        {
            "usd_per_gpu_hour": {"H100": 3.0, "H200": 3.5},
            "floors": floors,
            "version": 1,
        }
    )
    assert parsed is not None
    card, got_floors = parsed
    assert card == {"H100": 3.0, "H200": 3.5}
    assert got_floors is not None
    assert got_floors["H200"] == pytest.approx(3.95)
    assert got_floors["B300"] == pytest.approx(9.5)


def test_parse_price_card_floor_envelope():
    """Floors are clamped to [0.5x, 1.25x] of the compiled default."""
    parsed = parse_price_card(
        {
            "usd_per_gpu_hour": {"H100": 3.0},
            "floors": {"H100": 0.01, "H200": 999.0, "B200": 6.0},
            "version": 1,
        }
    )
    assert parsed is not None
    floors = parsed[1]
    assert floors is not None
    assert floors["H100"] == pytest.approx(4.0 * FLOOR_ENVELOPE_MIN_FRAC)
    assert floors["H200"] == pytest.approx(5.5 * FLOOR_ENVELOPE_MAX_FRAC)
    assert floors["B200"] == pytest.approx(6.0)


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
    assert ok is not None
    assert ok[0] == {"H100": 3.0, "H200": 3.5}
    assert ok[1] is None  # v1.2.0-shaped card: no floors


def test_parse_price_card_drops_invalid_floors_individually():
    """Unknown class / non-positive floors drop; the card stays valid."""
    parsed = parse_price_card(
        {
            "usd_per_gpu_hour": {"H100": 3.0},
            "floors": {"DOGE": 1.0, "H100": 0, "H200": 3.95},
            "version": 1,
        }
    )
    assert parsed is not None
    floors = parsed[1]
    assert floors is not None
    assert floors == {"H200": pytest.approx(3.95)}


def test_resolve_card_without_floors_keeps_cache_floors():
    """A floor-less published card (v1.2.0 writer) keeps previous floors
    on a v1.3.0 reader that already held them? No — the design says a
    floor-less card maps to the 0.75x default. But mid-run cache fallback
    (unreadable card) keeps the previous pair. Test the cache path."""

    def fetch_none():
        raise RuntimeError("store down")

    card, floors, source = resolve_card(
        fetch_none, fallback=({"H100": 3.3}, {"H100": 2.5})
    )
    assert source == "cache"
    assert card == {"H100": 3.3}
    assert floors == {"H100": 2.5}


def test_resolve_card_published_without_floors_returns_none_floors():
    """v1.2.0-shaped published card (no floors field) -> floors None
    -> feed falls back to 0.75 x card (v1.2.0 parity)."""

    def fetch_legacy():
        return {"usd_per_gpu_hour": {"H100": 4.0}, "version": 1}

    card, floors, source = resolve_card(fetch_legacy)
    assert source == "published"
    assert card["H100"] == pytest.approx(4.0)
    assert floors is None


def test_pricefeederror_is_runtimeerror():
    assert issubclass(PriceFeedError, RuntimeError)


# --- S3 fallback: PriceFeed.usd_per_alpha_from_published ---------------------


def test_published_fallback_extracts_usd_per_alpha():
    from price_feed import PriceFeed

    feed = PriceFeed(_Cfg())
    published = {"tao_usd": 200.0, "alpha_to_tao": 0.0035}
    assert feed.usd_per_alpha_from_published(published) == pytest.approx(0.7)


def test_published_fallback_returns_none_on_missing_fields():
    from price_feed import PriceFeed

    feed = PriceFeed(_Cfg())
    assert feed.usd_per_alpha_from_published({}) is None
    assert feed.usd_per_alpha_from_published({"tao_usd": 200.0}) is None
    assert feed.usd_per_alpha_from_published({"alpha_to_tao": 0.0035}) is None
    assert feed.usd_per_alpha_from_published("not a dict") is None


def test_published_fallback_returns_none_on_zero_or_negative():
    from price_feed import PriceFeed

    feed = PriceFeed(_Cfg())
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


def test_tao_usd_caches_live_and_reuses_on_429(tmp_path, monkeypatch):
    from price_feed import PriceFeed

    monkeypatch.setattr("price_feed.CACHE_PATH", str(tmp_path / "tao.json"))
    feed = PriceFeed(_Cfg())
    monkeypatch.setattr(
        "price_feed._get_json", lambda url, key="": {"price": 228.5}
    )
    assert feed.tao_usd() == pytest.approx(228.5)
    assert feed.last_tao_usd == pytest.approx(228.5)

    def boom(url, key="", label="taostats"):
        raise PriceFeedError("taostats GET …: HTTP Error 429")

    monkeypatch.setattr("price_feed._get_json", boom)
    monkeypatch.setattr(
        "price_feed._tao_usd_from_coingecko",
        lambda: (_ for _ in ()).throw(PriceFeedError("coingecko down")),
    )
    assert feed.tao_usd() == pytest.approx(228.5)


def test_tao_usd_coingecko_fallback(tmp_path, monkeypatch):
    from price_feed import PriceFeed

    monkeypatch.setattr("price_feed.CACHE_PATH", str(tmp_path / "none.json"))
    feed = PriceFeed(_Cfg())

    def boom(url, key="", label="taostats"):
        raise PriceFeedError("429")

    monkeypatch.setattr("price_feed._get_json", boom)
    monkeypatch.setattr("price_feed._tao_usd_from_coingecko", lambda: 231.47)
    assert feed.tao_usd() == pytest.approx(231.47)
    assert feed.last_tao_usd == pytest.approx(231.47)


def test_tao_usd_from_coingecko_payload(monkeypatch):
    from price_feed import _tao_usd_from_coingecko

    monkeypatch.setattr(
        "price_feed._get_json",
        lambda url, api_key="", label="coingecko": {
            "bittensor": {"usd": 231.47}
        },
    )
    assert _tao_usd_from_coingecko() == pytest.approx(231.47)


def test_tao_usd_loads_disk_cache(tmp_path, monkeypatch):
    from price_feed import PriceFeed, _save_tao_usd_cache

    cache = tmp_path / "tao.json"
    monkeypatch.setattr("price_feed.CACHE_PATH", str(cache))
    _save_tao_usd_cache(201.31)
    feed = PriceFeed(_Cfg())
    assert feed.last_tao_usd == pytest.approx(201.31)

    def boom(url, key="", label="taostats"):
        raise PriceFeedError("429")

    monkeypatch.setattr("price_feed._get_json", boom)
    monkeypatch.setattr(
        "price_feed._tao_usd_from_coingecko",
        lambda: (_ for _ in ()).throw(PriceFeedError("coingecko down")),
    )
    assert feed.tao_usd() == pytest.approx(201.31)


def test_tao_usd_raises_without_cache(tmp_path, monkeypatch):
    from price_feed import PriceFeed

    monkeypatch.setattr("price_feed.CACHE_PATH", str(tmp_path / "none.json"))
    feed = PriceFeed(_Cfg())

    def boom(url, key="", label="taostats"):
        raise PriceFeedError("429")

    monkeypatch.setattr("price_feed._get_json", boom)
    monkeypatch.setattr(
        "price_feed._tao_usd_from_coingecko",
        lambda: (_ for _ in ()).throw(PriceFeedError("coingecko down")),
    )
    with pytest.raises(PriceFeedError):
        feed.tao_usd()


def test_seed_from_published_fills_cache():
    from price_feed import PriceFeed

    feed = PriceFeed(_Cfg())
    feed.seed_from_published({"tao_usd": 210.0, "alpha_to_tao": 0.04})
    assert feed.last_tao_usd == pytest.approx(210.0)


def test_published_fallback_tao_usd():
    from price_feed import PriceFeed

    feed = PriceFeed(_Cfg())
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


def test_alpha_to_tao_uses_cached_metagraph_spot_price():
    """Reuse ChainState.spot_price — do not open a second Subtensor."""
    from price_feed import PriceFeed

    class _Chain:
        def __init__(self):
            self.reads = 0

        def spot_price(self):
            self.reads += 1
            return 0.0125

        def metagraph(self, netuid):
            raise AssertionError("cached spot price should skip a refetch")

    chain = _Chain()
    feed = PriceFeed(_Cfg(), chain_state=chain)
    assert feed.alpha_to_tao() == pytest.approx(0.0125)
    assert chain.reads == 1


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
