"""Scoring v2 state machine, tenure, capacity, and persistence (TDD).

Spec: kubetee/docs/superpowers/specs/2026-07-24-scoring-v2-design.md.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from infrastructure_validation import ValidationProfile
from scoring_state import (
    DEFAULT_GPU_WEIGHTS,
    MinerState,
    ScoringConfig,
    ScoringStateEngine,
    capacity_score,
    parse_gpu_weights,
)

HOT = "5MinerHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE"
DAY = 86400.0


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def make_engine(
    tmp_path=None,
    probation_cycles=3,
    tenure_bonus=0.2,
    tenure_days=7.0,
    clock=None,
):
    config = ScoringConfig(
        probation_cycles=probation_cycles,
        tenure_bonus=tenure_bonus,
        tenure_days=tenure_days,
        gpu_weights=dict(DEFAULT_GPU_WEIGHTS),
    )
    state_file = (tmp_path / "state.json") if tmp_path is not None else None
    clock = clock or FakeClock()
    engine = ScoringStateEngine(config, state_file=state_file, clock=clock)
    engine.load(bootstrap_earning=set())
    return engine, clock


# -- state machine -----------------------------------------------------------


def test_new_miner_starts_in_probation_and_scores_zero_factor():
    engine, _ = make_engine()
    result = engine.observe(HOT, healthy=True)
    assert result.state is MinerState.PROBATION
    assert result.tenure_factor == 0.0


def test_probation_promotes_after_n_consecutive_healthy_cycles():
    engine, _ = make_engine(probation_cycles=3)
    states = [engine.observe(HOT, healthy=True).state for _ in range(4)]
    assert states[:3] == [MinerState.PROBATION] * 3
    assert states[3] is MinerState.EARNING


def test_failed_cycle_resets_probation_counter():
    engine, _ = make_engine(probation_cycles=3)
    engine.observe(HOT, healthy=True)
    engine.observe(HOT, healthy=True)
    engine.observe(HOT, healthy=False)  # reset
    states = [engine.observe(HOT, healthy=True).state for _ in range(4)]
    assert states[3] is MinerState.EARNING
    assert states[2] is MinerState.PROBATION


def test_earning_miner_falls_to_probation_on_failure():
    engine, _ = make_engine(probation_cycles=1)
    engine.observe(HOT, healthy=True)
    assert engine.observe(HOT, healthy=True).state is MinerState.EARNING
    assert engine.observe(HOT, healthy=False).state is MinerState.PROBATION


def test_probation_zero_means_immediate_earning():
    engine, _ = make_engine(probation_cycles=0)
    assert engine.observe(HOT, healthy=True).state is MinerState.EARNING


def test_drop_missing_removes_state():
    engine, _ = make_engine(probation_cycles=0)
    engine.observe(HOT, healthy=True)
    engine.drop_missing(set())  # hotkey left the metagraph
    # re-observed as a NEW miner -> probation again (with gate > 0)
    engine2, _ = make_engine(probation_cycles=1)
    engine2.observe(HOT, healthy=True)
    assert engine2.observe(HOT, healthy=True).state is MinerState.EARNING
    assert HOT not in engine.snapshot()


# -- tenure ------------------------------------------------------------------


def test_tenure_ramps_linearly_and_caps():
    clock = FakeClock()
    engine, _ = make_engine(probation_cycles=0, clock=clock)
    first = engine.observe(HOT, healthy=True)
    assert first.tenure_factor == pytest.approx(1.0)
    clock.advance(3.5 * DAY)
    assert engine.observe(HOT, healthy=True).tenure_factor == pytest.approx(
        1.1
    )
    clock.advance(10 * DAY)  # beyond 7d cap
    assert engine.observe(HOT, healthy=True).tenure_factor == pytest.approx(
        1.2
    )


def test_tenure_resets_after_probation():
    clock = FakeClock()
    engine, _ = make_engine(probation_cycles=1, clock=clock)
    engine.observe(HOT, healthy=True)
    engine.observe(HOT, healthy=True)  # EARNING
    clock.advance(7 * DAY)
    assert engine.observe(HOT, healthy=True).tenure_factor == pytest.approx(
        1.2
    )
    engine.observe(HOT, healthy=False)  # fall
    engine.observe(HOT, healthy=True)  # probation k=1 -> promote next
    promoted = engine.observe(HOT, healthy=True)
    assert promoted.state is MinerState.EARNING
    assert promoted.tenure_factor == pytest.approx(1.0)


# -- capacity ----------------------------------------------------------------


def _gpu_node(count="8", product="NVIDIA-H100-80GB-HBM3"):
    return {
        "capacity": {"nvidia.com/gpu": count},
        "labels": {"nvidia.com/gpu.product": product},
        "state": "active",
        "transitioning": "no",
    }


def test_capacity_production_gpus_times_class_weight():
    nodes = [_gpu_node(), _gpu_node()]  # 16 x H100
    assert capacity_score(
        nodes, ValidationProfile.PRODUCTION, DEFAULT_GPU_WEIGHTS
    ) == pytest.approx(16.0)
    b200 = [_gpu_node(product="NVIDIA-B200")]
    assert capacity_score(
        b200, ValidationProfile.PRODUCTION, DEFAULT_GPU_WEIGHTS
    ) == pytest.approx(8 * 2.17)


def test_capacity_debug_is_node_count():
    nodes = [{"state": "active", "transitioning": "no"}] * 3
    assert capacity_score(
        nodes, ValidationProfile.DEBUG, DEFAULT_GPU_WEIGHTS
    ) == pytest.approx(3.0)


def test_capacity_malformed_nodes_fail_closed_zero():
    assert (
        capacity_score(
            [{"capacity": {}, "labels": {}}],
            ValidationProfile.PRODUCTION,
            DEFAULT_GPU_WEIGHTS,
        )
        == 0.0
    )
    assert capacity_score(None, ValidationProfile.PRODUCTION, {}) == 0.0


def test_parse_gpu_weights_roundtrip_and_failfast():
    assert parse_gpu_weights("H100=1.0,B200=2.17") == {
        "H100": 1.0,
        "B200": 2.17,
    }
    with pytest.raises(ValueError):
        parse_gpu_weights("H100=abc")
    with pytest.raises(ValueError):
        parse_gpu_weights("H100")


# -- persistence -------------------------------------------------------------


def test_state_survives_reload(tmp_path):
    clock = FakeClock()
    engine, _ = make_engine(tmp_path, probation_cycles=2, clock=clock)
    engine.observe(HOT, healthy=True)
    engine.save()

    fresh = ScoringStateEngine(
        ScoringConfig(2, 0.2, 7.0, dict(DEFAULT_GPU_WEIGHTS)),
        state_file=tmp_path / "state.json",
        clock=clock,
    )
    fresh.load(bootstrap_earning=set())
    # one more healthy cycle completes the gate (k was 1)
    assert fresh.observe(HOT, healthy=True).state is MinerState.PROBATION
    assert fresh.observe(HOT, healthy=True).state is MinerState.EARNING


def test_missing_state_file_bootstraps_earning_set(tmp_path):
    engine = ScoringStateEngine(
        ScoringConfig(60, 0.2, 7.0, dict(DEFAULT_GPU_WEIGHTS)),
        state_file=tmp_path / "absent.json",
        clock=FakeClock(),
    )
    engine.load(bootstrap_earning={HOT})
    assert engine.observe(HOT, healthy=True).state is MinerState.EARNING
    assert engine.observe("5Other", healthy=True).state is MinerState.PROBATION


def test_corrupt_state_file_bootstraps(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    engine = ScoringStateEngine(
        ScoringConfig(60, 0.2, 7.0, dict(DEFAULT_GPU_WEIGHTS)),
        state_file=path,
        clock=FakeClock(),
    )
    engine.load(bootstrap_earning={HOT})
    assert engine.observe(HOT, healthy=True).state is MinerState.EARNING


def test_save_is_atomic_json(tmp_path):
    engine, _ = make_engine(tmp_path, probation_cycles=0)
    engine.observe(HOT, healthy=True)
    engine.save()
    data = json.loads((tmp_path / "state.json").read_text())
    assert HOT in data["miners"]
    assert not list(tmp_path.glob("*.tmp"))


# -- USD targets (scoring v3) -------------------------------------------------


USD_CARD = {"H100": 2.00, "H200": 2.34, "B200": 4.34, "B300": 5.34}


def test_usd_target_production_sums_gpus_times_card():
    from scoring_state import usd_target_per_hour

    nodes = [_gpu_node(), _gpu_node(product="NVIDIA-B200")]  # 8xH100 + 8xB200
    assert usd_target_per_hour(
        nodes, ValidationProfile.PRODUCTION, USD_CARD
    ) == pytest.approx(8 * 2.00 + 8 * 4.34)


def test_usd_target_debug_is_node_count_times_h100():
    from scoring_state import usd_target_per_hour

    nodes = [{"state": "active"}] * 3
    assert usd_target_per_hour(
        nodes, ValidationProfile.DEBUG, USD_CARD
    ) == pytest.approx(3 * 2.00)


def test_usd_target_fails_closed_on_unknown_class_or_bad_nodes():
    from scoring_state import usd_target_per_hour

    unknown = [_gpu_node(product="NVIDIA-A100-SXM4")]
    assert (
        usd_target_per_hour(unknown, ValidationProfile.PRODUCTION, USD_CARD)
        == 0.0
    )
    assert (
        usd_target_per_hour(None, ValidationProfile.PRODUCTION, USD_CARD)
        == 0.0
    )
