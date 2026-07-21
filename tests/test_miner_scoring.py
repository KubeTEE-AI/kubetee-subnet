"""g004 V3: discovery + scoring + weights engine (TDD, red first).

Pure-logic tests for spec §4.2 steps 1/3/4: own-identity validation,
metagraph-driven miner discovery (D9), the binary fail-closed node-active
score (D4), and the S/N weight formula with explicit zeros (AC1, AC3).
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
    score_miner,
    validate_share,
)

OWNER = "5OwnerHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEabcd"
ALICE = "5AliceHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEabcd"
BOB = "5BobHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEab"
CAROL = "5CarolHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEabcd"

CONFIG = CycleConfig(owner_hotkey=OWNER, validator_hotkey=ALICE, miner_share=0.10)


def neurons(*pairs):
    return [{"uid": uid, "hotkey": hotkey} for uid, hotkey in pairs]


def cluster(cid, hotkey=None, state="active", transitioning="no", extra_labels=None):
    labels = dict(extra_labels or {})
    if hotkey is not None:
        labels["kubetee.ai/miner-hotkey"] = hotkey
    return {"id": cid, "state": state, "transitioning": transitioning, "labels": labels}


def node(state="active", transitioning="no"):
    doc = {"id": "node-x", "transitioning": transitioning}
    if state is not None:
        doc["state"] = state
    return doc


# --- share validation (fail-fast config, D12/AC1) ---------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.0001, float("nan"), float("inf"), "0.1", None])
def test_invalid_share_rejected(bad):
    with pytest.raises(ValueError):
        validate_share(bad)


@pytest.mark.parametrize("ok", [0.0, 0.1, 0.5, 1.0])
def test_valid_share_accepted(ok):
    assert validate_share(ok) == ok


def test_config_rejects_identical_own_hotkeys():
    with pytest.raises(ValueError):
        CycleConfig(owner_hotkey=OWNER, validator_hotkey=OWNER, miner_share=0.1)


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


# --- binary score (D4, step 3) ----------------------------------------------


def test_healthy_single_cluster_scores_one():
    clusters = [cluster("c1", BOB)]
    assert score_miner(BOB, clusters, {"c1": [node()]}) == 1


@pytest.mark.parametrize(
    "clusters,nodes_by_cluster",
    [
        ([], {}),                                                  # no cluster
        ([cluster("c1", BOB), cluster("c2", BOB)],
         {"c1": [node()], "c2": [node()]}),                        # ambiguous
        ([cluster("c1", BOB, state="provisioning")], {"c1": [node()]}),
        ([cluster("c1", BOB, state=None)], {"c1": [node()]}),      # missing state
        ([cluster("c1", BOB, transitioning="yes")], {"c1": [node()]}),
        ([cluster("c1", BOB)], {"c1": []}),                        # empty node list
        ([cluster("c1", BOB)], {"c1": [node(state="cordoned")]}),
        ([cluster("c1", BOB)], {"c1": [node(state=None)]}),        # node missing state
        ([cluster("c1", BOB)], {"c1": [node(transitioning="yes")]}),
        ([cluster("c1", BOB)], {}),                                # nodes unavailable
    ],
)
def test_fail_closed_scores_zero(clusters, nodes_by_cluster):
    assert score_miner(BOB, clusters, nodes_by_cluster) == 0


def test_one_active_node_among_inactive_is_enough():
    clusters = [cluster("c1", BOB)]
    nodes = {"c1": [node(state="cordoned"), node()]}
    assert score_miner(BOB, clusters, nodes) == 1


def test_unlabeled_and_other_clusters_ignored():
    clusters = [cluster("mgmt"), cluster("c1", BOB), cluster("c2", CAROL)]
    assert score_miner(BOB, clusters, {"c1": [node()]}) == 1


# --- weights (step 4, AC1) ---------------------------------------------------


def base_neurons():
    return neurons((0, OWNER), (1, ALICE), (2, BOB))


def test_healthy_miner_gets_share_owner_gets_rest():
    outcome = decide_cycle(base_neurons(), {BOB: 1}, CONFIG)
    assert isinstance(outcome, WeightsDecision)
    assert outcome.weights == {0: pytest.approx(0.9), 2: pytest.approx(0.1), 1: 0.0}


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
        0: pytest.approx(0.9), 2: pytest.approx(0.1), 3: 0.0, 1: 0.0,
    }


def test_weights_always_sum_to_one():
    ns = neurons((0, OWNER), (1, ALICE), (2, BOB), (3, CAROL), (4, "5DaveFAKE" + "x" * 39))
    for scores in ({}, {BOB: 1}, {BOB: 1, CAROL: 1}, {BOB: 0, CAROL: 0}):
        outcome = decide_cycle(ns, scores, CONFIG)
        assert isinstance(outcome, WeightsDecision)
        assert math.isclose(sum(outcome.weights.values()), 1.0)
        assert set(outcome.weights) == {n["uid"] for n in ns}


def test_degenerate_share_zero_reproduces_owner_only_behavior():
    config = CycleConfig(owner_hotkey=OWNER, validator_hotkey=ALICE, miner_share=0.0)
    outcome = decide_cycle(base_neurons(), {BOB: 1}, config)
    assert outcome.weights == {0: 1.0, 2: 0.0, 1: 0.0}


def test_missing_score_treated_as_zero():
    outcome = decide_cycle(base_neurons(), {}, CONFIG)
    assert outcome.weights == {0: 1.0, 2: 0.0, 1: 0.0}


def test_malformed_neuron_skips_instead_of_crashing():
    config = CycleConfig(owner_hotkey="5OWNER", validator_hotkey="5VALIDATOR", miner_share=0.1)
    neurons = [{"uid": 0, "hotkey": "5OWNER"}, {"uid": 1, "hotkey": "5VALIDATOR"}, {"uid": 2}]  # missing hotkey
    result = decide_cycle(neurons, {}, config)
    assert isinstance(result, SkipCycle)
    assert result.reason == SkipReason.IDENTITY_VIOLATION
