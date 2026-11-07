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


def make_publisher(chutes_feed=None, published=None):
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
        patch("validator.ChutesEarningsFeed", return_value=chutes_feed),
        patch("validator.fetch_published_dashboard", return_value=published),
    ):
        return Validator(cfg, dry_run=True)


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


def test_cold_start_and_failures_keep_published_chutes_values():
    """A publisher restart must not erase last-good values if Chutes fails."""
    published = {
        "per_class_usd": {"B300": 6.44},
        "samples": {"B300": 3},
        "stale": False,
        "observed_at": "2026-11-07T00:00:00Z",
    }

    collector = MagicMock()
    collector.last = None
    collector.snapshot.side_effect = lambda *args: dict(
        collector.last or {}, stale=True
    )
    failed_published = {"chutes_earnings": dict(published, stale=True)}
    obj = make_publisher(chutes_feed=collector, published=failed_published)
    assert collector.last == published
    result = obj._chutes_snapshot(360, 360, 222.56)
    assert result["per_class_usd"] == {"B300": 6.44}
    assert result["samples"] == {"B300": 3}
    assert result["stale"] is True


def test_invalid_published_chutes_does_not_shadow_the_dry_run_card():
    obj = make_publisher()
    assert obj.chutes_feed is None
    assert obj._last_chutes_snapshot is None
