"""g004 V5: guarded deregistration reconciliation (TDD, red first).

One test per spec §4.2a guard and AC12 race: suppression on metagraph
failure / Rancher outage / incomplete enumeration (with counter freeze),
consecutive-cycle AND wall-clock thresholds (boundaries 2/3 and 899/900),
reset on reappearance, pre-delete recheck aborts, protected clusters,
idempotent 404/409, unauthorized fail-closed, per-cluster duplicate
handling, and the evidence bundle.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from rancher_client import ErrorCategory, RancherError
from reconciliation import ReconciliationEngine
from validator_metrics import ValidatorMetrics

GONE = "5GoneMinerHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEabcd"
BOB = "5BobHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEab"
LABEL = "kubetee.ai/hotkey"


class FakeClock:
    def __init__(self, now: float = 0.0):
        self.now = now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


class FakeClient:
    """Stands in for RancherClient: get_cluster + delete_cluster only."""

    def __init__(self):
        self.clusters: dict[str, dict] = {}
        self.delete_results: dict[str, object] = {}
        self.deleted: list[str] = []
        self.get_errors: dict[str, Exception] = {}

    def get_cluster(self, cluster_id: str) -> dict:
        if cluster_id in self.get_errors:
            raise self.get_errors[cluster_id]
        return self.clusters[cluster_id]

    def delete_cluster(self, cluster_id: str) -> int:
        self.deleted.append(cluster_id)
        result = self.delete_results.get(cluster_id, 200)
        if isinstance(result, Exception):
            raise result
        return result


def cluster(cid: str, hotkey: str | None = GONE, uuid: str = "u-1") -> dict:
    labels = {LABEL: hotkey} if hotkey is not None else {}
    return {"id": cid, "uuid": uuid, "state": "active",
            "transitioning": "no", "labels": labels, "internal": False}


def make_engine(min_cycles: int = 3, min_seconds: float = 900.0):
    client = FakeClient()
    metrics = ValidatorMetrics(max_consecutive_skips=10, clock=lambda: 0.0)
    clock = FakeClock()
    logs: list[dict] = []
    engine = ReconciliationEngine(
        client=client,
        metrics=metrics,
        min_cycles=min_cycles,
        min_seconds=min_seconds,
        clock=clock,
        evidence_sink=logs.append,
    )
    return engine, client, metrics, clock, logs


def run_until_threshold(engine, clock, clusters, registered, cycles: int,
                        step_seconds: float = 400.0,
                        refresh=lambda: set()):
    outcome = None
    for _ in range(cycles):
        outcome = engine.run_cycle(
            registered_hotkeys=registered,
            clusters=clusters,
            metagraph_block="0xabc",
            refresh_registered=refresh,
        )
        clock.advance(step_seconds)
    return outcome


# --- suppression + freeze -----------------------------------------------------


def test_metagraph_failure_never_deletes_and_freezes_counter():
    engine, client, metrics, clock, _ = make_engine()
    clusters = [cluster("c-gone")]
    run_until_threshold(engine, clock, clusters, {BOB}, 2)
    engine.run_cycle(registered_hotkeys=None, clusters=clusters,
                     metagraph_block=None, refresh_registered=lambda: set())
    assert client.deleted == []
    assert engine.absence_cycles(GONE) == 2  # frozen, not incremented or reset
    text = metrics.exposition().decode()
    assert 'reason="metagraph_failed"' in text


def test_rancher_outage_never_deletes_and_freezes_counter():
    engine, client, metrics, clock, _ = make_engine()
    clusters = [cluster("c-gone")]
    run_until_threshold(engine, clock, clusters, {BOB}, 2)
    engine.run_cycle(registered_hotkeys={BOB}, clusters=None,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    assert client.deleted == []
    assert engine.absence_cycles(GONE) == 2


def test_below_cycle_threshold_suppresses():
    engine, client, metrics, clock, _ = make_engine(min_cycles=3)
    clusters = [cluster("c-gone")]
    run_until_threshold(engine, clock, clusters, {BOB}, 2, step_seconds=1000)
    assert client.deleted == []
    assert 'reason="below_threshold"' in metrics.exposition().decode()


def test_wall_clock_not_met_suppresses_even_with_cycles():
    engine, client, _, clock, _ = make_engine(min_cycles=3, min_seconds=900)
    clusters = [cluster("c-gone")]
    # 3 cycles but only 2 x 100s elapsed since first sighting
    run_until_threshold(engine, clock, clusters, {BOB}, 3, step_seconds=100,
                        refresh=lambda: set())
    assert client.deleted == []


def test_boundary_899_vs_900_seconds():
    engine, client, _, clock, _ = make_engine(min_cycles=2, min_seconds=900)
    clusters = [cluster("c-gone")]
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    clock.advance(899)
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    assert client.deleted == []  # 899s < 900s
    clock.advance(1)
    client.clusters["c-gone"] = cluster("c-gone")
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    assert client.deleted == ["c-gone"]  # 900s reached


def test_reappearance_resets_counter():
    engine, client, _, clock, _ = make_engine()
    clusters = [cluster("c-gone")]
    run_until_threshold(engine, clock, clusters, {BOB}, 2)
    engine.run_cycle(registered_hotkeys={BOB, GONE}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    assert engine.absence_cycles(GONE) == 0
    run_until_threshold(engine, clock, clusters, {BOB}, 2, step_seconds=1000)
    assert client.deleted == []  # counter restarted; threshold not yet met again


# --- pre-delete recheck --------------------------------------------------------


def ready_engine():
    """Engine one healthy cycle away from deletion of c-gone."""
    engine, client, metrics, clock, logs = make_engine(min_cycles=2, min_seconds=100)
    clusters = [cluster("c-gone")]
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    clock.advance(200)
    client.clusters["c-gone"] = cluster("c-gone")
    return engine, client, metrics, clock, logs, clusters


def test_refresh_shows_reappearance_aborts_and_resets():
    engine, client, _, clock, _, clusters = ready_engine()
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc",
                     refresh_registered=lambda: {GONE})
    assert client.deleted == []
    assert engine.absence_cycles(GONE) == 0


def test_refresh_failure_suppresses_no_delete():
    engine, client, metrics, clock, _, clusters = ready_engine()
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc",
                     refresh_registered=lambda: None)
    assert client.deleted == []
    assert 'reason="metagraph_failed"' in metrics.exposition().decode()


def test_label_changed_midcycle_aborts():
    engine, client, metrics, _, _, clusters = ready_engine()
    client.clusters["c-gone"] = cluster("c-gone", hotkey=BOB)  # relabeled
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    assert client.deleted == []
    assert 'reason="recheck_mismatch"' in metrics.exposition().decode()


def test_uuid_changed_midcycle_aborts():
    engine, client, _, _, _, clusters = ready_engine()
    client.clusters["c-gone"] = cluster("c-gone", uuid="u-DIFFERENT")
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    assert client.deleted == []


def test_recheck_get_error_aborts():
    engine, client, _, _, _, clusters = ready_engine()
    client.get_errors["c-gone"] = RancherError(ErrorCategory.TRANSPORT, "down")
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    assert client.deleted == []


# --- protected / unlabeled targets ---------------------------------------------


def test_unlabeled_and_internal_clusters_never_considered():
    engine, client, _, clock, _ = make_engine(min_cycles=1, min_seconds=0)
    mgmt = cluster("local", hotkey=None)
    internal = cluster("c-int", hotkey=GONE)
    internal["internal"] = True
    engine.run_cycle(registered_hotkeys={BOB}, clusters=[mgmt, internal],
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    clock.advance(10)
    engine.run_cycle(registered_hotkeys={BOB}, clusters=[mgmt, internal],
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    assert client.deleted == []


def test_retired_miner_hotkey_label_is_not_a_reconciliation_candidate():
    engine, client, _, clock, _ = make_engine(min_cycles=1, min_seconds=0)
    legacy = cluster("c-legacy", hotkey=None)
    retired_label = "kubetee.ai/" + "miner-hotkey"
    legacy["labels"] = {retired_label: GONE}
    for _ in range(2):
        engine.run_cycle(
            registered_hotkeys={BOB},
            clusters=[legacy],
            metagraph_block="0xabc",
            refresh_registered=lambda: set(),
        )
        clock.advance(10)
    assert client.deleted == []


def test_protected_id_never_deleted_even_if_labeled():
    engine, client, _, clock, _ = make_engine(min_cycles=1, min_seconds=0)
    trap = cluster("local", hotkey=GONE)
    for _ in range(3):
        engine.run_cycle(registered_hotkeys={BOB}, clusters=[trap],
                         metagraph_block="0xabc", refresh_registered=lambda: set())
        clock.advance(10)
    assert client.deleted == []


# --- deletion outcomes -----------------------------------------------------------


def test_successful_delete_counts_and_logs_evidence_bundle():
    engine, client, metrics, clock, logs, clusters = ready_engine()
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xdef", refresh_registered=lambda: set())
    assert client.deleted == ["c-gone"]
    assert "kubetee_reconciliation_deletions_total 1.0" in metrics.exposition().decode()
    bundle = [e for e in logs if e.get("event") == "reconciliation_deletion"][-1]
    for field in ("hotkey", "cluster_id", "cluster_uuid", "absence_cycles",
                  "first_missing_at", "metagraph_blocks", "recheck",
                  "response_class", "correlation_id"):
        assert field in bundle, field
    assert engine.absence_cycles(GONE) == 0  # record cleared


@pytest.mark.parametrize("status", [404, 409])
def test_conflict_statuses_are_idempotent_not_retried(status):
    engine, client, metrics, _, _, clusters = ready_engine()
    client.delete_results["c-gone"] = status
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    assert client.deleted == ["c-gone"]
    assert "kubetee_reconciliation_conflicts_total 1.0" in metrics.exposition().decode()
    assert engine.absence_cycles(GONE) == 0  # resolved, no aggressive retry


def test_unauthorized_delete_fails_closed_with_operator_signal():
    engine, client, metrics, _, logs, clusters = ready_engine()
    client.delete_results["c-gone"] = RancherError(ErrorCategory.AUTH, "denied")
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    text = metrics.exposition().decode()
    assert 'reason="unauthorized_operator_action_required"' in text
    assert any(e.get("event") == "reconciliation_unauthorized" for e in logs)


def test_duplicate_labeled_clusters_each_handled():
    engine, client, _, clock, logs = make_engine(min_cycles=2, min_seconds=100)
    clusters = [cluster("c-one", uuid="u-1"), cluster("c-two", uuid="u-2")]
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    clock.advance(200)
    client.clusters["c-one"] = cluster("c-one", uuid="u-1")
    client.clusters["c-two"] = cluster("c-two", uuid="u-2")
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    assert sorted(client.deleted) == ["c-one", "c-two"]
    deletions = [e for e in logs if e.get("event") == "reconciliation_deletion"]
    assert {d["cluster_id"] for d in deletions} == {"c-one", "c-two"}


def test_evidence_bundle_never_contains_raw_labels_dump_or_state_payload():
    engine, client, _, clock, logs, clusters = ready_engine()
    engine.run_cycle(registered_hotkeys={BOB}, clusters=clusters,
                     metagraph_block="0xabc", refresh_registered=lambda: set())
    bundle = [e for e in logs if e.get("event") == "reconciliation_deletion"][-1]
    assert "labels" not in bundle
    assert "state" not in bundle
