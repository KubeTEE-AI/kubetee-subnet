"""Validator wiring stays publisher-only and uses already resolved TAO/USDT."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from validator import Validator


def test_publisher_has_feed_and_reader_does_not():
    for publisher, present in ((True, True), (False, False)):
        cfg = SimpleNamespace(
            network="test",
            endpoint=None,
            hotkey_seed=None,
            rancher_token="r",
            is_publisher=publisher,
            hippius_access_key="a",
            hippius_secret_key="b",
            taostats_api_key="t",
        )
        with (
            patch("validator.ChainState"),
            patch("validator.RancherClient"),
            patch("validator.PriceFeed"),
            patch("validator.TargonPayoutFeed"),
            patch("validator.HippiusStore"),
        ):
            obj = Validator(cfg, dry_run=True)
        assert (obj.chutes_feed is not None) is present


def test_snapshot_is_synchronous_with_block_tempo_and_tao():
    collector = MagicMock()
    collector.snapshot.return_value = {
        "per_class_usd": {"H200": 1.2},
        "stale": False,
    }
    with patch(
        "validator.ChutesEarningsFeed", return_value=collector
    ) as factory:
        cfg = SimpleNamespace(
            network="test",
            endpoint=None,
            hotkey_seed=None,
            rancher_token="r",
            is_publisher=True,
            hippius_access_key="a",
            hippius_secret_key="b",
            taostats_api_key="t",
        )
        with (
            patch("validator.ChainState"),
            patch("validator.RancherClient"),
            patch("validator.PriceFeed"),
            patch("validator.TargonPayoutFeed"),
            patch("validator.HippiusStore"),
        ):
            obj = Validator(cfg, dry_run=True)
    factory.assert_called_once_with("t")
    assert (
        obj._chutes_snapshot(360, 360, 222.5)
        == collector.snapshot.return_value
    )
    collector.snapshot.assert_called_once_with(360, 360, 222.5)
