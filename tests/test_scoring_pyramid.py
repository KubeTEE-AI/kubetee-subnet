"""Expensive in-memory scoring-pyramid simulations (scoring v2).

Long-horizon, multi-miner, whole-loop scenarios sitting between the unit
suite and the compose UAT: thousands of simulated 60s cycles driven through
the real ScoringStateEngine (and, for the marathon, the real BasicValidator
cycle) with simulated clocks — no chain, no Rancher, no sleeping.
"""

from __future__ import annotations

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
)

CYCLE_SECONDS = 60.0
DAY = 86400.0


class SimClock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def tick(self, seconds: float = CYCLE_SECONDS) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def sim_engine(clock, probation_cycles=60, state_file=None):
    engine = ScoringStateEngine(
        ScoringConfig(
            probation_cycles=probation_cycles,
            tenure_bonus=0.2,
            tenure_days=7.0,
            gpu_weights=dict(DEFAULT_GPU_WEIGHTS),
        ),
        state_file=state_file,
        clock=clock,
    )
    engine.load(bootstrap_earning=set())
    return engine


def run_cycles(engine, clock, plan, cycles):
    """Run `cycles` cycles; plan maps hotkey -> health fn(cycle_index)."""
    last = {}
    for index in range(cycles):
        for hotkey, health in plan.items():
            last[hotkey] = engine.observe(hotkey, healthy=health(index))
        clock.tick()
    return last


# -- 7-day tenure marathon ----------------------------------------------------


def test_tenure_ramp_is_monotonic_over_a_simulated_week():
    """10,140 simulated cycles: 60 probation + 7 days of earning. Tenure
    must rise monotonically 1.0 -> 1.2 and cap exactly."""
    clock = SimClock()
    engine = sim_engine(clock)
    factors = []
    for _ in range(60 + 7 * 24 * 60):
        result = engine.observe("hot-a", healthy=True)
        if result.state is MinerState.EARNING:
            factors.append(result.tenure_factor)
        clock.tick()
    assert factors[0] == pytest.approx(1.0, abs=1e-6)
    assert factors[-1] == pytest.approx(1.2, abs=1e-4)
    assert all(b >= a for a, b in zip(factors, factors[1:]))
    # halfway through the ramp: ~1.1
    midpoint = factors[len(factors) // 2]
    assert 1.08 < midpoint < 1.12


def test_veteran_out_earns_newcomer_until_ramp_parity():
    """A miner earning for 7 simulated days holds a 1.2x score advantage
    over an identical newcomer, decaying to parity a week later."""
    clock = SimClock()
    engine = sim_engine(clock, probation_cycles=0)
    # veteran earns alone for 7 days
    for _ in range(7 * 24 * 60):
        engine.observe("veteran", healthy=True)
        clock.tick()
    vet = engine.observe("veteran", healthy=True)
    new = engine.observe("newcomer", healthy=True)
    assert vet.tenure_factor == pytest.approx(1.2, abs=1e-4)
    assert new.tenure_factor == pytest.approx(1.0, abs=1e-6)
    # a week later they are equal
    for _ in range(7 * 24 * 60):
        vet = engine.observe("veteran", healthy=True)
        new = engine.observe("newcomer", healthy=True)
        clock.tick()
    assert new.tenure_factor == pytest.approx(vet.tenure_factor, abs=1e-4)


# -- flapping and churn --------------------------------------------------------


def test_flapping_miner_never_earns_across_two_simulated_days():
    """A cluster failing every 30th cycle can never clear a 60-cycle gate."""
    clock = SimClock()
    engine = sim_engine(clock, probation_cycles=60)
    plan = {"flappy": lambda i: i % 30 != 29}
    last = run_cycles(engine, clock, plan, cycles=2 * 24 * 60)
    assert last["flappy"].state is MinerState.PROBATION


def test_one_blip_costs_tenure_and_a_full_probation():
    clock = SimClock()
    engine = sim_engine(clock, probation_cycles=60)
    for _ in range(61):
        engine.observe("hot-a", healthy=True)
        clock.tick()
    for _ in range(3 * 24 * 60):  # 3 days earning
        engine.observe("hot-a", healthy=True)
        clock.tick()
    before = engine.observe("hot-a", healthy=True)
    assert before.state is MinerState.EARNING
    assert before.tenure_factor > 1.05
    engine.observe("hot-a", healthy=False)  # the blip
    gated = [engine.observe("hot-a", healthy=True) for _ in range(60)]
    assert all(r.state is MinerState.PROBATION for r in gated)
    recovered = engine.observe("hot-a", healthy=True)
    assert recovered.state is MinerState.EARNING
    assert recovered.tenure_factor == pytest.approx(1.0, abs=1e-6)


# -- fleet-scale capacity/weights ---------------------------------------------


def _fleet_nodes(gpu_class: str, node_count: int):
    return [
        {
            "capacity": {"nvidia.com/gpu": "8"},
            "labels": {"nvidia.com/gpu.product": f"NVIDIA-{gpu_class}"},
            "state": "active",
            "transitioning": "no",
        }
        for _ in range(node_count)
    ]


def test_fifty_miner_fleet_capacity_and_split_invariants():
    """50 miners with mixed GPU classes: proportional shares sum to the
    miner share; every class weight ratio is preserved."""
    from miner_scoring import CycleConfig, WeightsDecision, decide_cycle

    classes = ["H100", "H200", "B200", "B300"]
    clock = SimClock()
    engine = sim_engine(clock, probation_cycles=0)
    neurons = [
        {"uid": 0, "hotkey": "owner", "coldkey": "owner-ck"},
        {"uid": 1, "hotkey": "validator", "coldkey": "validator-ck"},
    ]
    scores = {}
    capacities = {}
    for index in range(50):
        hotkey = f"miner-{index:02d}"
        neurons.append(
            {"uid": index + 2, "hotkey": hotkey, "coldkey": f"{hotkey}-ck"}
        )
        gpu_class = classes[index % 4]
        nodes = _fleet_nodes(gpu_class, node_count=1 + index % 3)
        capacity = capacity_score(
            nodes, ValidationProfile.PRODUCTION, DEFAULT_GPU_WEIGHTS
        )
        result = engine.observe(hotkey, healthy=True)
        assert result.state is MinerState.EARNING
        capacities[hotkey] = capacity
        scores[hotkey] = capacity * result.tenure_factor

    decision = decide_cycle(
        neurons,
        scores,
        CycleConfig(
            owner_hotkey="owner",
            validator_hotkey="validator",
            miner_share=0.1,
        ),
    )
    assert isinstance(decision, WeightsDecision)
    total = sum(decision.weights.values())
    assert total == pytest.approx(1.0, abs=1e-9)
    miner_total = sum(
        weight for uid, weight in decision.weights.items() if uid >= 2
    )
    assert miner_total == pytest.approx(0.1, abs=1e-9)
    # class-weight ratios survive the split: same node count, B300 vs H100
    h100 = next(
        h for h, c in capacities.items() if c == 8 * 1.0
    )  # 1 node H100
    b300 = next(h for h, c in capacities.items() if c == 8 * 2.67)
    uid_of = {n["hotkey"]: n["uid"] for n in neurons}
    ratio = decision.weights[uid_of[b300]] / decision.weights[uid_of[h100]]
    assert ratio == pytest.approx(2.67, rel=1e-6)


# -- restart / persistence equivalence ----------------------------------------


def test_restart_mid_simulation_is_trajectory_equivalent(tmp_path):
    """Persisting + reloading halfway through a 4-day simulation produces
    exactly the same states and tenure factors as an uninterrupted run."""
    plan = {
        "steady": lambda i: True,
        "flappy": lambda i: i % 97 != 96,
        "late": lambda i: i > 1000,
    }
    cycles = 4 * 24 * 60
    half = cycles // 2

    clock_a = SimClock()
    uninterrupted = sim_engine(clock_a, probation_cycles=60)
    final_a = run_cycles(uninterrupted, clock_a, plan, cycles)

    clock_b = SimClock()
    first = sim_engine(
        clock_b, probation_cycles=60, state_file=tmp_path / "s.json"
    )
    run_cycles(first, clock_b, plan, half)
    first.save()
    second = ScoringStateEngine(
        ScoringConfig(60, 0.2, 7.0, dict(DEFAULT_GPU_WEIGHTS)),
        state_file=tmp_path / "s.json",
        clock=clock_b,
    )
    second.load(bootstrap_earning=set())
    final_b = {}
    for index in range(half, cycles):
        for hotkey, health in plan.items():
            final_b[hotkey] = second.observe(hotkey, healthy=health(index))
        clock_b.tick()

    for hotkey in plan:
        assert final_b[hotkey].state is final_a[hotkey].state, hotkey
        assert final_b[hotkey].tenure_factor == pytest.approx(
            final_a[hotkey].tenure_factor, abs=1e-9
        ), hotkey


def test_state_loss_with_chain_bootstrap_preserves_earning(tmp_path):
    """Losing the state file never zeroes working miners: the chain
    bootstrap seeds them EARNING (tenure ramp restarts)."""
    clock = SimClock()
    engine = ScoringStateEngine(
        ScoringConfig(60, 0.2, 7.0, dict(DEFAULT_GPU_WEIGHTS)),
        state_file=tmp_path / "lost.json",
        clock=clock,
    )
    engine.load(bootstrap_earning={"steady", "veteran"})
    for hotkey in ("steady", "veteran"):
        assert engine.observe(hotkey, healthy=True).state is MinerState.EARNING
    assert (
        engine.observe("newcomer", healthy=True).state is MinerState.PROBATION
    )


# -- whole-validator marathon --------------------------------------------------


def test_validator_marathon_probation_then_proportional_weights():
    """Real BasicValidator loop for 80 cycles (debug profile, 2-cycle gate):
    gate first, then stable proportional weights, state consistent."""
    import test_basic_validator as tb

    config = tb.ValidatorConfig.from_env(
        tb.make_env(KUBETEE_PROBATION_CYCLES="2")
    )
    clusters, nodes = tb.active_bob_cluster()
    validator, subtensor, *_ = tb.build_validator(
        config=config,
        rancher=tb.FakeRancher(clusters=clusters, nodes_by_cluster=nodes),
    )
    for _ in range(80):
        assert validator.run_cycle() == "weights_set"
    weights = [c["weights"] for c in subtensor.set_weights_calls]
    assert weights[0] == [1.0, 0.0, 0.0]
    assert weights[1] == [1.0, 0.0, 0.0]
    for vector in weights[2:]:
        assert vector == pytest.approx([0.9, 0.0, 0.1])


# -- USD-priced weights marathon (scoring v3) ---------------------------------


def test_price_swing_marathon_usd_income_constant():
    """Whole-validator marathon across a token price swing: the miner's USD
    target stays constant while its weight halves when alpha price doubles."""
    import test_basic_validator as tb

    clusters, nodes = tb.active_bob_cluster()

    def run_with_price(usd_per_alpha):
        config = tb.ValidatorConfig.from_env(
            tb.make_env(KUBETEE_USD_PER_ALPHA_OVERRIDE=str(usd_per_alpha))
        )
        validator, subtensor, _, _, metrics, _ = tb.build_validator(
            config=config,
            rancher=tb.FakeRancher(clusters=clusters, nodes_by_cluster=nodes),
        )
        for _ in range(20):
            assert validator.run_cycle() == "weights_set"
        weight = subtensor.set_weights_calls[-1]["weights"][2]
        text = metrics.exposition().decode()
        target_usd = next(
            float(line.rsplit(" ", 1)[1])
            for line in text.splitlines()
            if line.startswith("kubetee_miner_target_usd{")
        )
        return weight, target_usd

    weight_1, usd_1 = run_with_price(1.0)
    weight_2, usd_2 = run_with_price(2.0)
    assert usd_1 == pytest.approx(usd_2)  # USD income target constant
    assert weight_2 == pytest.approx(weight_1 / 2)  # weight halves


# -- single chain clock marathon ----------------------------------------------


def test_epoch_clock_marathon_exactly_one_cycle_per_epoch():
    """500 loop ticks over tempo=100 epochs: the validator submits weights
    exactly once per distinct epoch it observes — never twice in an epoch,
    never skipping an observed epoch."""
    import test_basic_validator as tb

    config = tb.ValidatorConfig.from_env(
        tb.make_env(KUBETEE_TEMPO_BLOCKS="100")
    )
    clusters, nodes = tb.active_bob_cluster()
    sleep, sleep_calls = tb.stop_after(500)
    validator, subtensor, *_ = tb.build_validator(
        config=config,
        rancher=tb.FakeRancher(clusters=clusters, nodes_by_cluster=nodes),
        sleep=sleep,
    )
    observed_epochs = set()
    original_due = validator._epoch_due

    def tracking_due():
        due = original_due()
        if validator._last_cycled_epoch is not None:
            observed_epochs.add(validator._last_cycled_epoch)
        return due

    validator._epoch_due = tracking_due
    with pytest.raises(tb._StopLoop):
        validator.run_forever()

    assert len(sleep_calls) == 500
    assert len(subtensor.set_weights_calls) == len(observed_epochs)
    assert len(observed_epochs) >= 5  # the run genuinely crossed epochs
