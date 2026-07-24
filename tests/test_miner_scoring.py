"""Metagraph identity and binary-score weight decision tests.

Infrastructure evidence is evaluated in ``infrastructure_validation``. This
module tests complete metagraph identity, miner discovery, and the S/N weight
formula with explicit zeros.
"""

from __future__ import annotations

import math
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from miner_scoring import (
    CycleConfig,
    SkipCycle,
    SkipReason,
    WeightsDecision,
    decide_cycle,
    validate_share,
)

OWNER = "5OwnerHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEabcd"
ALICE = "5AliceHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEabcd"
BOB = "5BobHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEab"
CAROL = "5CarolHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEabcd"

CONFIG = CycleConfig(
    owner_hotkey=OWNER, validator_hotkey=ALICE, miner_share=0.10
)


def neurons(*pairs):
    return [
        {"uid": uid, "hotkey": hotkey, "coldkey": f"cold:{hotkey}"}
        for uid, hotkey in pairs
    ]


# --- share validation (fail-fast config, D12/AC1) ---------------------------


@pytest.mark.parametrize(
    "bad", [-0.1, 1.0001, float("nan"), float("inf"), "0.1", None]
)
def test_invalid_share_rejected(bad):
    with pytest.raises(ValueError):
        validate_share(bad)


@pytest.mark.parametrize("ok", [0.0, 0.1, 0.5, 1.0])
def test_valid_share_accepted(ok):
    assert validate_share(ok) == ok


def test_config_rejects_identical_own_hotkeys():
    with pytest.raises(ValueError):
        CycleConfig(
            owner_hotkey=OWNER, validator_hotkey=OWNER, miner_share=0.1
        )


def test_config_rejects_blank_hotkeys():
    with pytest.raises(ValueError):
        CycleConfig(owner_hotkey=" ", validator_hotkey=ALICE, miner_share=0.1)


# --- identity resolution / discovery (D9, step 1) ---------------------------


def test_owner_missing_from_metagraph_skips():
    outcome = decide_cycle(neurons((1, ALICE), (2, BOB)), {BOB: 1}, CONFIG)
    assert isinstance(outcome, SkipCycle)
    assert outcome.reason is SkipReason.OWNER_UNRESOLVED


def test_validator_missing_from_metagraph_skips():
    outcome = decide_cycle(neurons((0, OWNER), (2, BOB)), {BOB: 1}, CONFIG)
    assert isinstance(outcome, SkipCycle)
    assert outcome.reason is SkipReason.IDENTITY_VIOLATION


def test_duplicate_hotkey_in_metagraph_skips():
    outcome = decide_cycle(
        neurons((0, OWNER), (1, ALICE), (2, BOB), (3, BOB)), {BOB: 1}, CONFIG
    )
    assert isinstance(outcome, SkipCycle)
    assert outcome.reason is SkipReason.IDENTITY_VIOLATION


def test_empty_metagraph_skips():
    outcome = decide_cycle([], {}, CONFIG)
    assert isinstance(outcome, SkipCycle)
    assert outcome.reason is SkipReason.OWNER_UNRESOLVED


def test_no_miners_yields_owner_only_weights():
    outcome = decide_cycle(neurons((0, OWNER), (1, ALICE)), {}, CONFIG)
    assert isinstance(outcome, WeightsDecision)
    assert outcome.weights == {0: 1.0, 1: 0.0}


# --- weights (step 4, AC1) ---------------------------------------------------


def base_neurons():
    return neurons((0, OWNER), (1, ALICE), (2, BOB))


def test_healthy_miner_gets_share_owner_gets_rest():
    outcome = decide_cycle(base_neurons(), {BOB: 1}, CONFIG)
    assert isinstance(outcome, WeightsDecision)
    assert outcome.weights == {
        0: pytest.approx(0.9),
        2: pytest.approx(0.1),
        1: 0.0,
    }


def test_zero_scoring_miner_gets_explicit_zero():
    outcome = decide_cycle(base_neurons(), {BOB: 0}, CONFIG)
    assert outcome.weights == {0: 1.0, 2: 0.0, 1: 0.0}


def test_share_splits_across_scoring_miners():
    ns = neurons((0, OWNER), (1, ALICE), (2, BOB), (3, CAROL))
    outcome = decide_cycle(ns, {BOB: 1, CAROL: 1}, CONFIG)
    assert outcome.weights[2] == pytest.approx(0.05)
    assert outcome.weights[3] == pytest.approx(0.05)
    assert outcome.weights[0] == pytest.approx(0.9)


def test_only_scoring_miners_split_the_share():
    ns = neurons((0, OWNER), (1, ALICE), (2, BOB), (3, CAROL))
    outcome = decide_cycle(ns, {BOB: 1, CAROL: 0}, CONFIG)
    assert outcome.weights == {
        0: pytest.approx(0.9),
        2: pytest.approx(0.1),
        3: 0.0,
        1: 0.0,
    }


def test_weights_always_sum_to_one():
    ns = neurons(
        (0, OWNER),
        (1, ALICE),
        (2, BOB),
        (3, CAROL),
        (4, "5DaveFAKE" + "x" * 39),
    )
    for scores in ({}, {BOB: 1}, {BOB: 1, CAROL: 1}, {BOB: 0, CAROL: 0}):
        outcome = decide_cycle(ns, scores, CONFIG)
        assert isinstance(outcome, WeightsDecision)
        assert math.isclose(sum(outcome.weights.values()), 1.0)
        assert set(outcome.weights) == {n["uid"] for n in ns}


def test_degenerate_share_zero_reproduces_owner_only_behavior():
    config = CycleConfig(
        owner_hotkey=OWNER, validator_hotkey=ALICE, miner_share=0.0
    )
    outcome = decide_cycle(base_neurons(), {BOB: 1}, config)
    assert outcome.weights == {0: 1.0, 2: 0.0, 1: 0.0}


def test_missing_score_treated_as_zero():
    outcome = decide_cycle(base_neurons(), {}, CONFIG)
    assert outcome.weights == {0: 1.0, 2: 0.0, 1: 0.0}


def test_missing_coldkey_skips_cycle_as_identity_violation():
    snapshot = base_neurons()
    del snapshot[2]["coldkey"]

    outcome = decide_cycle(snapshot, {}, CONFIG)

    assert outcome == SkipCycle(
        SkipReason.IDENTITY_VIOLATION,
        "neuron missing uid, hotkey, or coldkey",
    )


def test_shared_coldkey_is_allowed_for_multiple_hotkeys():
    snapshot = base_neurons()
    snapshot[2]["coldkey"] = snapshot[1]["coldkey"]

    outcome = decide_cycle(snapshot, {}, CONFIG)

    assert isinstance(outcome, WeightsDecision)


def test_malformed_neuron_skips_instead_of_crashing():
    config = CycleConfig(
        owner_hotkey="5OWNER", validator_hotkey="5VALIDATOR", miner_share=0.1
    )
    snapshot = [
        {"uid": 0, "hotkey": "5OWNER", "coldkey": "5OWNER-COLD"},
        {"uid": 1, "hotkey": "5VALIDATOR", "coldkey": "5VALIDATOR-COLD"},
        {"uid": 2, "coldkey": "5MINER-COLD"},
    ]
    result = decide_cycle(snapshot, {}, config)
    assert isinstance(result, SkipCycle)
    assert result.reason == SkipReason.IDENTITY_VIOLATION


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("uid", True),
        ("uid", -1),
        ("uid", "2"),
        ("hotkey", {"not": "scalar"}),
        ("coldkey", 123),
    ],
)
def test_malformed_neuron_scalar_shapes_skip_cycle(field, value):
    snapshot = base_neurons()
    snapshot[2][field] = value

    outcome = decide_cycle(snapshot, {}, CONFIG)

    assert isinstance(outcome, SkipCycle)
    assert outcome.reason is SkipReason.IDENTITY_VIOLATION


def test_duplicate_uid_in_metagraph_skips_cycle():
    snapshot = base_neurons()
    snapshot[2]["uid"] = snapshot[1]["uid"]

    outcome = decide_cycle(snapshot, {}, CONFIG)

    assert isinstance(outcome, SkipCycle)
    assert outcome.reason is SkipReason.IDENTITY_VIOLATION


def test_share_splits_proportionally_to_float_scores():
    """Scoring v2: a miner with 2x the score earns 2x the weight."""
    ns = neurons((0, OWNER), (1, ALICE), (2, BOB), (3, CAROL))
    outcome = decide_cycle(ns, {BOB: 16.0, CAROL: 8.0}, CONFIG)
    assert outcome.weights[2] == pytest.approx(0.1 * 2 / 3)
    assert outcome.weights[3] == pytest.approx(0.1 * 1 / 3)
    assert outcome.weights[0] == pytest.approx(0.9)


def test_zero_and_nonfinite_scores_are_excluded():
    ns = neurons((0, OWNER), (1, ALICE), (2, BOB), (3, CAROL))
    outcome = decide_cycle(ns, {BOB: 8.0, CAROL: float("nan")}, CONFIG)
    assert outcome.weights[3] == 0.0
    assert outcome.weights[2] == pytest.approx(0.1)
