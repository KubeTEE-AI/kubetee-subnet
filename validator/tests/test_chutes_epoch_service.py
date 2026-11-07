"""Exact one-attempt-per-epoch behavior of the synchronous publisher feed."""

import json
from pathlib import Path
import httpx
import pytest
import chutes_earnings_feed as feed


@pytest.fixture
def fixtures():
    directory = Path(__file__).parent / "fixtures" / "chutes-reference"
    return {
        name: json.loads((directory / f"{name}.json").read_text())
        for name in ("nodes", "stats", "catalog", "rewards")
    }


def test_four_bound_reads_and_raw_key_only_to_rewards(fixtures):
    calls = []

    def handler(request):
        calls.append(request)
        path = str(request.url.path)
        key = (
            "rewards"
            if "taostats" in str(request.url)
            else (
                "nodes"
                if path == "/nodes/"
                else "stats" if "/miner/stats" in path else "catalog"
            )
        )
        return httpx.Response(200, json=fixtures[key])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = feed.ChutesEarningsFeed("test-key", client=client)
    result = collector.snapshot(360, 360, 221.74)
    assert {call.url.path for call in calls} == {
        "/nodes/",
        "/miner/stats",
        "/chutes/",
        "/api/metagraph/latest/v1",
    }
    assert result["bucket"] == 1 and result["stale"] is False
    for call in calls:
        if "taostats" in str(call.url):
            assert call.headers["Authorization"] == "test-key"
        else:
            assert "authorization" not in call.headers


class InlineExecutor:
    """Join all mock requests inside snapshot; concurrency is tested above."""

    def submit(self, function, *arguments):
        from concurrent.futures import Future

        future = Future()
        future.set_result(function(*arguments))
        return future


def test_epoch_guard_blocks_repeated_success_failure_and_no_price(fixtures):
    calls = []
    failed = False

    def handler(request):
        calls.append(request)
        if not failed:
            return httpx.Response(503, text="upstream")
        key = (
            "nodes"
            if "nodes" in str(request.url)
            else (
                "stats"
                if "miner/stats" in str(request.url)
                else "catalog" if "chutes/" in str(request.url) else "rewards"
            )
        )
        return httpx.Response(200, json=fixtures[key])

    collector = feed.ChutesEarningsFeed(
        "test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    collector.executor = InlineExecutor()
    assert collector.snapshot(100, 360, 221.74) is None
    assert collector.snapshot(359, 360, 221.74) is None
    failed = True
    exact = len(calls)
    first = collector.snapshot(360, 360, 221.74)
    assert first and first["bucket"] == 1
    assert collector.snapshot(400, 360, 221.74)["stale"] is False
    assert collector.snapshot(0, 360, 221.74) == first
    assert len(calls) == exact + 4
    second = collector.snapshot(720, 360, 221.74)
    assert collector.snapshot(900, 360, 221.74) == second
    assert len(calls) == exact + 8
    calls.clear()
    blocked = feed.ChutesEarningsFeed(
        "test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert blocked.snapshot(400, 0, 221.74) is None
    assert blocked.snapshot(360, 360, 0) is None
    assert not calls


def test_failure_is_unavailable_then_next_epoch_recovers_and_public_payload_is_small(
    fixtures,
):
    calls = []

    def handler(request):
        # Mock failure by epoch, not count: request completion order is
        # intentionally nondeterministic under the four-worker concurrency.
        calls.append(request)
        key = (
            "rewards"
            if "taostats" in str(request.url)
            else (
                "nodes"
                if "/nodes/" in str(request.url)
                else (
                    "stats"
                    if "/miner/stats" in str(request.url)
                    else "catalog"
                )
            )
        )
        return httpx.Response(200, json=fixtures[key])

    collector = feed.ChutesEarningsFeed(
        "test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    def fail_first(request):
        if collector.attempted == 1:
            return httpx.Response(503, text="upstream")
        return handler(request)

    collector.client = httpx.Client(transport=httpx.MockTransport(fail_first))
    collector.executor = InlineExecutor()
    assert collector.snapshot(360, 360, 221.74) is None
    recovered = collector.snapshot(720, 360, 221.74)
    assert recovered["stale"] is False and recovered["bucket"] == 2
    assert recovered["per_class_usd"]["B300"] > 0
    assert set(recovered) == {
        "per_class_usd",
        "samples",
        "mode",
        "bucket",
        "observed_at",
        "tao_usd",
        "observation_window",
        "stale",
    }
    assert "rows" not in recovered and "hotkey" not in str(recovered)


def test_tao_reward_scale_boundaries_and_invalid():
    assert (
        feed.get_emission({"daily_total_rewards_as_tao": 1_000_000})
        == 1_000_000
    )
    assert feed.get_emission(
        {"daily_total_rewards_as_tao": 1_000_001}
    ) == pytest.approx(0.001000001)
    assert feed.get_emission({"daily_total_rewards_as_tao": 0.5}) == 0.5
    assert feed.get_emission({"daily_total_rewards_as_tao": float("nan")}) == 0
    assert feed.get_emission({"daily_mining_alpha_as_tao": 0}) == 0
    assert feed.get_emission({"emission": 0.01}) == 0.01
