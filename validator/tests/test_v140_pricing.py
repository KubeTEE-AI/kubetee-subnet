"""v1.4.0 semantics and overlap contracts (no external network writes)."""

from types import SimpleNamespace
from unittest.mock import patch
import urllib.request


import pytest

import urllib.request


class _S3HeadResponse:
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


from market_snapshot import (
    MARKET_VERSION,
    build_market_snapshot,
    chutes_for_epoch,
    fetch_market_snapshot,
    market_price,
    parse_market_snapshot,
    provider_rates,
    targon_fields,
    targon_rate,
)
from validator import Validator


def chutes(values, epoch=1):
    return {
        "per_class_usd": values,
        "bucket": epoch,
        "observation_window": "current_24h",
        "mode": "median_24h",
        "samples": {"B300": 123},
    }


def raw_rows():
    return {
        "B300": [{"unitRate": None, "maxPrice": 9.75, "targetPrice": 999}],
        "H200": [{"unitRate": 6.01045, "maxPrice": 10, "targetPrice": 999}],
    }


def snapshot(epoch=1, floors=None):
    return build_market_snapshot(
        epoch,
        floors if floors is not None else {"B300": 9.75, "H200": 4.0},
        raw_rows(),
        {"B300": 5, "H200": 3},
        chutes({"B300": 8, "H200": 7}, epoch),
    )


def test_targon_each_row_reads_hourly_else_its_own_maximum_only():
    rows = {
        "B300": [
            {"unitRate": None, "maxPrice": 9.75, "targetPrice": 999},
            {"unitRate": 6.01045, "maxPrice": 8, "targetPrice": 999},
            {"unitRate": 0, "maxPrice": 7, "targetPrice": 999},
        ],
        "H200": [{"unitRate": None, "maxPrice": 3.5, "targetPrice": 999}],
    }
    assert targon_fields(rows)["B300"] == {
        "unitRate": 6.01045,
        "maxPrice": 8,
    }
    assert targon_fields(rows)["H200"] == {"unitRate": None, "maxPrice": 3.5}
    assert targon_rate({"unitRate": 6.01045, "maxPrice": 9.75}) == 6.01045
    assert targon_rate({"unitRate": None, "maxPrice": 9.75}) == 9.75
    assert targon_rate({"unitRate": 5.0, "targetPrice": 999}) == 5.0
    with pytest.raises(ValueError):
        targon_rate({"targetPrice": 999})


def test_legacy_v13_reads_only_targon_maximum_not_hourly_or_target():
    from targon_payout_feed import _per_class_from_snapshot

    rows = [
        {
            "kind": "gpu",
            "key": "B300",
            "unitRate": 6.01045,
            "maxPrice": 9.75,
            "targetPrice": 999,
        },
        {
            "kind": "gpu",
            "key": "H200",
            "unitRate": 100,
            "maxPrice": None,
            "targetPrice": 999,
        },
    ]
    assert _per_class_from_snapshot(rows) == {"B300": 9.75}


def test_typed_raw_source_group_preserves_selected_raw_not_derived():
    from market_snapshot import targon_by_gpu

    rows = [
        {
            "kind": "gpu",
            "key": "B300",
            "unitRate": None,
            "maxPrice": 9.75,
            "targetPrice": 999,
        },
        {
            "kind": "gpu",
            "key": "B300 SXM",
            "unitRate": 6.01,
            "maxPrice": 7,
            "targetPrice": 999,
        },
    ]
    assert targon_rate(targon_fields(targon_by_gpu(rows))["B300"]) == 6.01
    assert targon_fields(targon_by_gpu(rows))["B300"] == {
        "unitRate": 6.01,
        "maxPrice": 7,
    }


def test_live_tdx_vm_hourly_wins_over_idle_sku_and_keeps_own_maximum():
    """API live rows: don't borrow an idle TDX-BM row's lower Maximum."""
    fields = targon_fields(
        {
            "B200": [
                {"unitRate": None, "maxPrice": 6.5},  # idle bare-metal
                {"unitRate": 6.0089, "maxPrice": 6.5},  # active TDX VM
            ],
            "H200": [
                {"unitRate": 3.291, "maxPrice": 4.5},  # active TDX VM
                {"unitRate": None, "maxPrice": 3.5},  # idle bare-metal
            ],
        }
    )
    assert fields["B200"] == {"unitRate": 6.0089, "maxPrice": 6.5}
    assert fields["H200"] == {"unitRate": 3.291, "maxPrice": 4.5}


def test_positive_targon_hourly_does_not_require_a_maximum():
    fields = targon_fields({"B300": [{"unitRate": 5, "maxPrice": None}]})
    assert fields["B300"] == {"unitRate": 5}
    normalized = targon_fields(fields)
    assert provider_rates({"providers": {"targon": normalized}}, "targon") == {
        "B300": 5
    }


def test_no_hourly_uses_tdx_vm_maximum_not_sev_or_bare_metal():
    fields = targon_fields(
        {
            "B300": [
                {"key": "TDX-BLACKWELL-NVIDIA-B300", "maxPrice": 99},
                {"key": "TDX-VM-NVIDIA-B300", "maxPrice": 9.75},
                {"key": "SEV-VM-NVIDIA-B300", "maxPrice": 55},
            ]
        }
    )
    assert fields["B300"] == {"unitRate": None, "maxPrice": 9.75}
    multiple = targon_fields(
        {"B300": [{"key": "TDX-VM-NVIDIA-B300", "maxPrice": 9.75}]}
    )
    assert multiple["B300"] == {"unitRate": None, "maxPrice": 9.75}


def test_full_snapshot_uses_tdx_vm_fallback_but_legacy_uses_same_row_max():
    rows = {
        "B300": [
            {"key": "TDX-BLACKWELL-NVIDIA-B300", "maxPrice": 99},
            {"key": "TDX-VM-NVIDIA-B300", "maxPrice": 9.75},
            {"key": "SEV-VM-Nvidia-B300", "maxPrice": 55},
        ]
    }
    market = build_market_snapshot(
        1, {"B300": 4}, rows, {}, chutes({"B300": 0}, 1), raw_targon=rows
    )
    assert provider_rates(market, "targon") == {"B300": 9.75}
    assert market_price("B300", market) == pytest.approx(10.725)
    from targon_payout_feed import _legacy_maximum_rows

    # Legacy is aggregated max across raw rows; no new hourly/markup field.
    assert _legacy_maximum_rows(rows)["B300"] == 99


def test_three_provider_max_plus_ten_then_floor_never_card_clamp():
    market = snapshot()
    assert market_price("B300", market) == pytest.approx(10.725)
    assert market_price("H200", market) == pytest.approx(7.7)
    market["providers"]["chutes"]["B300"]["maxPrice"] = 100
    # 12.66 or 10.00 card ceiling stays wholly out of this calculation.
    assert market_price("B300", market) == pytest.approx(110)
    market["providers"]["chutes"]["B300"]["maxPrice"] = 1
    market["providers"]["targon"]["B300"] = {
        "unitRate": 6.01045,
        "maxPrice": 9.75,
    }
    assert market_price("B300", market) == pytest.approx(9.75)
    assert market_price("B300", snapshot(floors={})) == pytest.approx(10.725)


def test_targon_fallback_participates_in_highest_of_three():
    assert market_price("B300", snapshot(floors={"B300": 1})) == pytest.approx(
        10.725
    )
    market = snapshot(floors={"B300": 1})
    market["providers"]["chutes"]["B300"]["maxPrice"] = 0
    market["providers"]["lium"]["B300"]["maxPrice"] = 0
    assert provider_rates(market, "lium")["B300"] == 0
    assert market_price("B300", market) == pytest.approx(10.725)
    market["providers"]["targon"]["B300"] = {
        "unitRate": 6.01045,
        "maxPrice": 9.75,
    }
    assert market_price("B300", market) == pytest.approx(6.611495)


def test_v3_only_and_current_chain_epoch_only_for_reader_payload():
    market = snapshot()
    assert parse_market_snapshot(market, 1) is not None
    assert parse_market_snapshot(market, 2) is None
    assert parse_market_snapshot({"version": 1, "epoch": 1}, 1) is None
    assert fetch_market_snapshot(0) is None
    with patch("hippius_store._get_public", return_value=market):
        assert fetch_market_snapshot(1) is not None
        assert fetch_market_snapshot(2) is None


def test_chutes_canonical_read_write_mask_and_stale_guards():
    market = snapshot()
    assert chutes_for_epoch(market["chutes_snapshot"], 1) is not None
    assert chutes_for_epoch(market["chutes_snapshot"], 1)["bucket"] == 1
    assert chutes_for_epoch(market["chutes_snapshot"], 2) is None
    # Explicit old Chutes retention is separate from the current market epoch.
    last = {**market["chutes_snapshot"], "stale": True}
    assert chutes_for_epoch(last, 2) is not None
    assert chutes_for_epoch(last, 2)["bucket"] == 1
    assert (
        parse_market_snapshot(
            {
                **market,
                "epoch": 2,
                "source_epochs": {"targon": 1, "lium": 1, "chutes": 1},
                "chutes_snapshot": last,
            },
            2,
        )
        is not None
    )
    assert (
        parse_market_snapshot(
            {
                **market,
                "epoch": 2,
                "source_epochs": {"targon": 1, "lium": 1, "chutes": 1},
            },
            2,
        )
        is None
    )


def test_no_external_prices_on_reader_only_shared_epoch_object():
    cfg = SimpleNamespace(
        network="test",
        endpoint=None,
        hotkey_seed=None,
        rancher_token="t",
        is_publisher=False,
        hippius_access_key="",
        hippius_secret_key="",
        taostats_api_key="t",
        usd_floor_override={},
        usd_card_override={},
    )
    with (
        patch("validator.ChainState") as chain,
        patch("validator.RancherClient"),
        patch("validator.PriceFeed"),
        patch("validator.TargonPayoutFeed"),
    ):
        chain.return_value.epoch_progress.return_value = (360, 360, 360)
        chain.return_value._subtensor.block = 360
        obj = Validator(cfg, dry_run=True)
    with (
        patch(
            "validator.fetch_market_snapshot", return_value=snapshot()
        ) as fetch,
        patch("validator.ChutesEarningsFeed") as chutes_api,
    ):
        shared = obj.market_for_epoch(1, 360, 360, 240.0)
        assert shared == obj.market_for_epoch(1, 361, 360, 240.0)
        assert fetch.call_count == 1
        assert chutes_api.call_count == 0
        assert obj.effective_market(shared)["H200"] == pytest.approx(7.7)
        assert obj.targon_chart(shared)["B300"] == 9.75
        assert obj.lium_chart(shared)["B300"] == 5
    obj.chain.epoch_progress.return_value = (360, 360, 360)
    with patch(
        "validator.fetch_market_snapshot", return_value=snapshot(2)
    ) as fetch:
        assert obj.shared_reader(1) is not None
        fetch.assert_called_once_with(1)


def _publisher(delegated=False):
    cfg = SimpleNamespace(
        network="test",
        endpoint=None,
        hotkey_seed=None,
        rancher_token="t",
        is_publisher=True,
        hippius_access_key="a",
        hippius_secret_key="b",
        taostats_api_key="t",
        usd_floor_override={"B300": 9.75},
        usd_card_override={"B300": 12.66},
        netuid=56,
    )
    with (
        patch("validator.ChainState") as chain,
        patch("validator.RancherClient"),
        patch("validator.PriceFeed"),
        patch("validator.TargonPayoutFeed"),
        patch("validator.HippiusStore"),
        patch.dict(
            "os.environ",
            {"KUBETEE_MARKET_PUBLISH_DELEGATED": str(delegated)},
            clear=False,
        ),
    ):
        chain.return_value.epoch_progress.return_value = (360, 360, 360)
        chain.return_value._subtensor.block = 360
        obj = Validator(cfg, dry_run=False)
    return obj


def test_delegated_candidate_reads_shared_epoch_but_never_writes():
    obj = _publisher(True)
    with (
        patch(
            "validator.fetch_market_snapshot", return_value=snapshot()
        ) as read,
        patch("validator.fetch_targon_snapshot_rows") as targon_api,
        patch("validator.fetch_lium_per_card_usd") as lium_api,
        patch("validator.ChutesEarningsFeed") as chutes_api,
    ):
        shared = obj.market_for_epoch(1, 360, 360, 240.0)
    assert {k: v for k, v in shared.items() if k != "taken_at"} == {
        k: v for k, v in snapshot().items() if k != "taken_at"
    }
    assert read.call_count == 1
    obj.hippius.put_json.assert_not_called()
    obj.targon.publish.assert_not_called()
    for api in (targon_api, lium_api, chutes_api):
        api.assert_not_called()


def test_delegated_candidate_skips_when_no_shared_epoch_exists():
    obj = _publisher(True)
    with (
        patch("validator.fetch_market_snapshot", return_value=None),
        patch("validator.fetch_targon_snapshot_rows") as targon_api,
        patch("validator.fetch_lium_per_card_usd") as lium_api,
        patch("validator.ChutesEarningsFeed") as chutes_api,
    ):
        with pytest.raises(
            RuntimeError, match="delegated reader has no shared"
        ):
            obj.market_for_epoch(2, 720, 360, 240.0)
    obj.hippius.put_json.assert_not_called()
    for api in (targon_api, lium_api, chutes_api):
        api.assert_not_called()


def test_non_delegated_publisher_without_s3_never_becomes_a_second_publisher():
    obj = _publisher()
    obj.hippius = None
    with (
        patch(
            "validator.fetch_targon_snapshot_rows",
            side_effect=AssertionError("S3-less publisher must not fetch"),
        ),
        pytest.raises(RuntimeError, match="no shared v3 market"),
    ):
        obj.market_for_epoch(1, 360, 360, 240.0)


def test_reader_does_not_publish_legacy_even_with_s3_credentials():
    obj = _publisher()
    obj.config.is_publisher = False
    obj._delegated = False
    with patch("validator.fetch_market_snapshot", return_value=snapshot()):
        assert obj.market_for_epoch(1, 360, 360, 240.0)["epoch"] == 1
    obj.hippius.put_json.assert_not_called()
    obj.targon.publish.assert_not_called()


def test_publisher_makes_one_epoch_frozen_read_then_publishes_v3_and_v1():
    obj = _publisher()
    obj.price_feed.last_tao_usd = 240.0
    obj.chain.spot_price.return_value = 0.01
    with (
        patch(
            "validator.fetch_targon_snapshot_rows", return_value=raw_rows()
        ) as targon,
        patch(
            "validator.fetch_lium_per_card_usd",
            return_value={"B300": 5, "H200": 3},
        ) as lium,
        patch.object(
            obj.chutes_feed,
            "snapshot",
            return_value=chutes({"B300": 8, "H200": 7}, 1),
        ),
        patch("validator.parse_price_card", return_value=None),
        patch("validator.build_price_card", return_value={"version": 1}),
        patch.object(
            obj.targon,
            "resolve_per_card_usd",
            return_value=({"B300": 6.01}, "live"),
        ),
        patch("hippius_store._get_public", return_value=None) as s3_read,
        patch.object(
            urllib.request, "urlopen", return_value=_S3HeadResponse()
        ),
        patch("validator.load_lium_cache", return_value=None),
        patch("validator.load_lium_cache_epoch", return_value=-1),
    ):
        first = obj.market_for_epoch(1, 360, 360, 240)
        obj.chain._subtensor.block = 361
        second = obj.market_for_epoch(1, 361, 360, 240)
        assert first == second
        assert targon.call_count == lium.call_count == 1
        assert s3_read.call_count == 1  # check current epoch publication
        assert first["source_epochs"] == {"targon": 1, "lium": 1, "chutes": 1}
        # Legacy refresh is independent of the frozen v3/API observations.
        assert [
            call.args[0] for call in obj.hippius.put_json.call_args_list
        ] == [
            "market.json",
            "price-card.json",
            "payout.json",
            "price-card.json",
            "payout.json",
        ]
        legacy_calls = [
            call.args[1]
            for call in obj.hippius.put_json.call_args_list
            if call.args[0] == "payout.json"
        ]
        assert [payload["epoch"] for payload in legacy_calls] == [360, 361]
        assert all(
            payload["per_card_usd"] == {"B300": 9.75, "H200": 10.0}
            for payload in legacy_calls
        )


def test_restart_inherits_raw_maximum_and_hourly_without_provider_api():
    obj = _publisher()
    obj.price_feed.last_tao_usd = 240.0
    obj.chain.spot_price.return_value = 0.01
    frozen = build_market_snapshot(
        1,
        {"B300": 9.75, "H200": 4.0},
        raw_rows(),
        {"B300": 5, "H200": 3},
        chutes({"B300": 8, "H200": 7}, 1),
        raw_targon=raw_rows(),
    )
    with (
        patch("validator.fetch_market_snapshot", return_value=frozen),
        patch(
            "validator.fetch_targon_snapshot_rows",
            side_effect=AssertionError("reader must not fetch Targon"),
        ),
        patch(
            "validator.fetch_lium_per_card_usd",
            side_effect=AssertionError("reader must not fetch Lium"),
        ),
        patch("validator.ChutesEarningsFeed") as chutes_api,
    ):
        shared = obj.market_for_epoch(1, 360, 360, 240.0)
        assert shared["targon_raw"] == raw_rows()
    published = {
        call.args[0]: call.args[1]
        for call in obj.hippius.put_json.call_args_list
    }
    assert published["payout.json"]["per_card_usd"] == {
        "B300": 9.75,
        "H200": 10.0,
    }
    assert "lium_per_card_usd" not in published["payout.json"]
    # A restart reads the existing v3; it must not double-write consensus.
    assert "market.json" not in published
    assert "targetPrice" in shared["targon_raw"]["B300"][0]
    chutes_api.assert_not_called()


def test_targon_total_outage_keeps_raw_sku_fallback_and_maximum():
    obj = _publisher()
    obj.price_feed.last_tao_usd = 240.0
    obj.chain.spot_price.return_value = 0.01
    obj._last_market = build_market_snapshot(
        1,
        {"B300": 9.75, "H200": 4.0},
        raw_rows(),
        {"B300": 5, "H200": 3},
        chutes({"B300": 8, "H200": 7}, 1),
        raw_targon=raw_rows(),
    )
    obj._market = obj._last_market
    obj._market_epoch = 1
    with (
        patch("validator.fetch_market_snapshot", return_value=None),
        patch(
            "validator.fetch_targon_snapshot_rows", side_effect=OSError("down")
        ),
        patch(
            "validator.load_lium_cache", return_value={"B300": 5, "H200": 3}
        ),
        patch("validator.load_lium_cache_epoch", return_value=1),
        patch(
            "validator.fetch_lium_per_card_usd", side_effect=OSError("down")
        ),
        patch.object(
            obj.chutes_feed,
            "snapshot",
            return_value={**chutes({"B300": 8, "H200": 7}, 1), "stale": True},
        ),
    ):
        shared = obj.market_for_epoch(2, 720, 360, 240.0)
    assert shared["source_epochs"] == {"targon": 1, "lium": 1, "chutes": 1}
    assert shared["targon_raw"] == raw_rows()
    assert shared["providers"]["targon"]["B300"] == {
        "unitRate": None,
        "maxPrice": 9.75,
    }
    assert obj._publisher_maximums() == {"B300": 9.75, "H200": 10.0}


def _retained(obj):
    return build_market_snapshot(
        1,
        {"B300": 9.75, "H200": 4.0},
        raw_rows(),
        {"B300": 5, "H200": 3},
        chutes({"B300": 8, "H200": 7}, 1),
        raw_targon=raw_rows(),
    )


def _outage():
    return (
        patch(
            "validator.fetch_targon_snapshot_rows", side_effect=OSError("down")
        ),
        patch(
            "validator.fetch_lium_per_card_usd", side_effect=OSError("down")
        ),
        patch("validator.load_lium_cache", return_value=None),
        patch("validator.load_lium_cache_epoch", return_value=-1),
    )


def test_all_sources_down_reuses_prior_chutes_in_memory():
    obj = _publisher()
    obj._last_market = previous = _retained(obj)
    obj.chutes_feed.last = previous["chutes_snapshot"]
    o1, o2, o3, o4 = _outage()
    with o1, o2, o3, o4, patch.object(obj, "shared_reader", return_value=None):
        shared = obj._publisher_market(2, 720, 360, 240.0)
    assert shared["source_epochs"] == {"targon": 1, "lium": 1, "chutes": 1}
    assert shared["chutes_snapshot"] == {
        **previous["chutes_snapshot"],
        "stale": True,
    }


def test_all_sources_down_restarted_publisher_recovers_chutes_lium_targon():
    obj = _publisher()
    reads = []
    previous = _retained(obj)

    def reader(epoch):
        reads.append(epoch)
        return previous if epoch == 1 else None

    with patch.object(obj, "shared_reader", side_effect=reader):
        o1, o2, o3, o4 = _outage()
        with (
            o1,
            o2,
            o3,
            o4,
            patch.object(
                obj.chutes_feed,
                "_get",
                side_effect=OSError("all sources down"),
            ),
        ):
            shared = obj._publisher_market(2, 720, 360, 240.0)
    assert reads == [1]
    assert shared["chutes_snapshot"] == {
        **previous["chutes_snapshot"],
        "stale": True,
    }
    assert shared["source_epochs"] == {"targon": 1, "lium": 1, "chutes": 1}
    assert obj._publisher_maximums() == {"B300": 9.75, "H200": 10.0}


def test_legacy_v1_card_written_unchanged_until_legacy_cutoff():
    obj = _publisher()
    obj.price_feed.last_tao_usd = 240.0
    obj.chain.spot_price.return_value = 0.01
    obj._publisher_targon_raw = raw_rows()
    card = {
        "version": 1,
        "usd_per_gpu_hour": {"B300": 12.66},
        "floors": {"B300": 9.75},
        "pricing": {"targon": True, "lium": False},
    }
    with (
        patch("validator.build_price_card", return_value=card),
        patch(
            "validator.parse_price_card",
            return_value=(
                card["usd_per_gpu_hour"],
                card["floors"],
                card["pricing"],
            ),
        ),
        patch.object(
            obj.targon, "card", return_value=card["usd_per_gpu_hour"]
        ),
        patch.object(
            obj.targon,
            "resolve_per_card_usd",
            return_value=({"B300": 6.01}, "live"),
        ),
    ):
        obj._publish_legacy(obj._publisher_floors())
    written = {
        call.args[0]: call.args[1]
        for call in obj.hippius.put_json.call_args_list
    }
    payload = written["price-card.json"]
    assert payload["usd_per_gpu_hour"]["B300"] == 12.66
    assert payload["floors"]["B300"] == 9.75
    assert payload["pricing"] == {"targon": True, "lium": False}
    assert "market_price" not in payload
    payout = written["payout.json"]
    assert payout["epoch"] == 360  # legacy v1: block, not a pricing epoch
    # v1.3.x reads Maximum only: not PAYOUT/h, and not v1.4.0's +10%.
    assert payout["per_card_usd"] == {"B300": 9.75, "H200": 10.0}


def test_reader_and_delegate_ignore_legacy_refresh_failures_and_never_write():
    for delegated in (False, True):
        obj = _publisher(delegated=delegated)
        obj.config.is_publisher = not delegated
        with (
            patch("validator.fetch_market_snapshot", return_value=snapshot()),
            patch.object(
                obj, "_publish_legacy", side_effect=OSError("S3 down")
            ),
        ):
            assert obj.market_for_epoch(1, 360, 360, 240)["epoch"] == 1
        obj.hippius.put_json.assert_not_called()
        obj.targon.publish.assert_not_called()


def test_cached_legacy_refresh_error_does_not_block_v3_scoring():
    obj = _publisher()
    frozen = snapshot()
    obj._market = frozen
    obj._market_epoch = 1
    with patch.object(obj, "_publish_legacy", side_effect=OSError("S3 down")):
        assert obj.market_for_epoch(1, 361, 360, 240) is frozen


def test_publish_payout_retries_each_block_and_preserves_tao_fallback():
    obj = _publisher()
    obj.price_feed.last_tao_usd = 221.5
    obj.chain.spot_price.return_value = 0.017
    obj._publisher_maximums = lambda: {"B300": 9.75}
    obj._publish_legacy({"B300": 9.75})
    for epoch, payload in (
        (360, {"tao_usd": 221.5, "alpha_to_tao": 0.017}),
        (366, {"tao_usd": 221.5, "alpha_to_tao": 0.017}),
    ):
        obj._epoch = lambda epoch=epoch: epoch
        obj._publish_legacy({"B300": 9.75})
        assert (
            obj.hippius.put_json.call_args_list[-1].args[1]["tao_usd"]
            == payload["tao_usd"]
        )


def test_floor_override_from_publisher_is_only_floor_not_a_ceiling():
    obj = _publisher()
    market = snapshot(floors={"B300": 20})
    assert obj.effective_market(market)["B300"] == 20
