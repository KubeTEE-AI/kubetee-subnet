"""minimize_scoring: USD-denominated split, owner recycle, weights sum 1.0."""

import pytest

from miner_scoring import MinerInput, compute_weights, usd_target_per_hour

CARD = {"H100": 3.0, "H200": 3.5, "B200": 6.5, "B300": 8.0}


def test_usd_target_per_hour():
    assert usd_target_per_hour("H200", 1, CARD) == 3.5 * 8
    assert usd_target_per_hour("h200", 2, CARD) == 3.5 * 8 * 2
    assert usd_target_per_hour(None, 1, CARD) == 0.0
    assert usd_target_per_hour("H100", 0, CARD) == 0.0
    assert usd_target_per_hour("UNKNOWN", 1, CARD) == 0.0


def _sum(weights):
    return round(sum(weights.values()), 9)


def test_one_ready_miner_owner_remainder():
    miners = [
        MinerInput(0, "owner-hk", ready=False, gpu_class=None, gpu_workers=0),
        MinerInput(1, "miner-hk", ready=True, gpu_class="H200", gpu_workers=1),
    ]
    # miner earns 3.5*8 = 28 USD/hr; budget 100 USD/hr -> owner remainder 72
    scores = compute_weights(
        miners,
        CARD,
        usd_per_alpha=1.0,
        window_hours=1.0,
        owner_uid=0,
        emission_usd_per_epoch=100.0,
    )
    assert scores.weights[1] == pytest.approx(28.0 / 100.0)
    assert scores.weights[0] == pytest.approx(72.0 / 100.0)
    assert _sum(scores.weights) == pytest.approx(1.0)


def test_two_miners_split_proportionally_owner_zero_budget():
    miners = [
        MinerInput(0, "owner-hk", ready=False, gpu_class=None, gpu_workers=0),
        MinerInput(1, "a", ready=True, gpu_class="H100", gpu_workers=1),  # 24
        MinerInput(2, "b", ready=True, gpu_class="H200", gpu_workers=1),  # 28
    ]
    scores = compute_weights(
        miners,
        CARD,
        usd_per_alpha=1.0,
        window_hours=1.0,
        owner_uid=0,
        emission_usd_per_epoch=0.0,
    )
    # budget 0 -> owner remainder 0 -> miners split the pot proportionally
    assert scores.weights[1] == pytest.approx(24.0 / 52.0)
    assert scores.weights[2] == pytest.approx(28.0 / 52.0)
    assert scores.weights.get(0, 0.0) == 0.0
    assert _sum(scores.weights) == pytest.approx(1.0)


def test_not_ready_miner_earns_nothing():
    miners = [
        MinerInput(0, "owner-hk", ready=False, gpu_class=None, gpu_workers=0),
        MinerInput(1, "down", ready=False, gpu_class="H200", gpu_workers=1),
        MinerInput(2, "up", ready=True, gpu_class="H100", gpu_workers=1),
    ]
    scores = compute_weights(
        miners,
        CARD,
        usd_per_alpha=1.0,
        window_hours=1.0,
        owner_uid=0,
        emission_usd_per_epoch=24.0,
    )
    assert 1 not in scores.weights or scores.weights[1] == 0.0
    assert scores.weights[2] == pytest.approx(1.0)


def test_nothing_ready_recycles_to_owner():
    miners = [
        MinerInput(0, "owner-hk", ready=False, gpu_class=None, gpu_workers=0),
        MinerInput(1, "down", ready=False, gpu_class="B200", gpu_workers=1),
    ]
    scores = compute_weights(
        miners,
        CARD,
        usd_per_alpha=1.0,
        window_hours=1.0,
        owner_uid=0,
        emission_usd_per_epoch=1000.0,
    )
    assert scores.weights[0] == pytest.approx(1.0)
    assert _sum(scores.weights) == pytest.approx(1.0)


def test_tenure_scales_earnings():
    miners = [
        MinerInput(0, "owner-hk", ready=False, gpu_class=None, gpu_workers=0),
        MinerInput(
            1,
            "probation",
            ready=True,
            gpu_class="H200",
            gpu_workers=1,
            tenure=0.5,
        ),
    ]
    scores = compute_weights(
        miners,
        CARD,
        usd_per_alpha=1.0,
        window_hours=1.0,
        owner_uid=0,
        emission_usd_per_epoch=28.0,
    )
    assert scores.weights[1] == pytest.approx(0.5)


def test_usd_per_alpha_validated():
    with pytest.raises(ValueError):
        compute_weights(
            [],
            CARD,
            usd_per_alpha=0.0,
            window_hours=1.0,
            owner_uid=0,
            emission_usd_per_epoch=100.0,
        )
