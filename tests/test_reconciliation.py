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

from infrastructure_validation import (
    BINDING_ID_LABEL,
    BINDING_STATUS_LABEL,
    COLDKEY_LABEL,
    ENROLLMENT_UID_ANNOTATION,
    GENERATION_LABEL,
    NETUID_LABEL,
    NETWORK_LABEL,
    ORIGIN_FP_PREFIX_LABEL,
    PROVIDER_ID_LABEL,
)
from rancher_client import ErrorCategory, RancherError
from reconciliation import ReconciliationEngine
from validator_metrics import ValidatorMetrics

GONE = "5GoneMinerHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEabcd"
BOB = "5BobHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEab"
LABEL = "kubetee.ai/hotkey"
NETUID = 1
NETWORK = "finney"
BLOCK = 100
UUID_ONE = "00000000-0000-4000-8000-000000000001"
UUID_TWO = "00000000-0000-4000-8000-000000000002"
UUID_OTHER = "00000000-0000-4000-8000-000000000099"


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


def cluster(cid: str, hotkey: str | None = GONE, uuid: str = UUID_ONE) -> dict:
    labels = (
        {
            LABEL: hotkey,
            BINDING_ID_LABEL: f"binding-{cid}",
            COLDKEY_LABEL: "5CanonicalColdkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKE",
            PROVIDER_ID_LABEL: UUID_TWO,
            BINDING_STATUS_LABEL: "ENROLLED",
            GENERATION_LABEL: "1",
            NETUID_LABEL: str(NETUID),
            NETWORK_LABEL: NETWORK,
            ORIGIN_FP_PREFIX_LABEL: "a" * 63,
        }
        if hotkey is not None
        else {}
    )
    return {
        "id": cid,
        "uuid": uuid,
        "state": "active",
        "transitioning": "no",
        "labels": labels,
        "annotations": (
            {ENROLLMENT_UID_ANNOTATION: "99"} if hotkey is not None else {}
        ),
        "internal": False,
    }


def make_engine(min_cycles: int = 3, min_seconds: float = 900.0):
    client = FakeClient()
    metrics = ValidatorMetrics(max_consecutive_skips=10, clock=lambda: 0.0)
    clock = FakeClock()
    logs: list[dict] = []
    engine = ReconciliationEngine(
        client=client,
        metrics=metrics,
        expected_netuid=NETUID,
        expected_network=NETWORK,
        min_cycles=min_cycles,
        min_seconds=min_seconds,
        clock=clock,
        evidence_sink=logs.append,
    )
    return engine, client, metrics, clock, logs


def run_until_threshold(
    engine,
    clock,
    clusters,
    registered,
    cycles: int,
    step_seconds: float = 400.0,
    refresh=lambda _minimum_block: set(),
    start_block: int = BLOCK,
):
    outcome = None
    for offset in range(cycles):
        outcome = engine.run_cycle(
            registered_hotkeys=registered,
            clusters=clusters,
            metagraph_block=start_block + offset,
            refresh_registered=refresh,
        )
        clock.advance(step_seconds)
    return outcome


# --- suppression + freeze -----------------------------------------------------


def test_metagraph_failure_never_deletes_and_freezes_counter():
    engine, client, metrics, clock, _ = make_engine()
    clusters = [cluster("c-gone")]
    run_until_threshold(engine, clock, clusters, {BOB}, 2)
    engine.run_cycle(
        registered_hotkeys=None,
        clusters=clusters,
        metagraph_block=None,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == []
    assert engine.absence_cycles(GONE) == 2  # frozen, not incremented or reset
    text = metrics.exposition().decode()
    assert 'reason="metagraph_failed"' in text


def test_missing_metagraph_block_never_starts_an_absence_window():
    engine, client, metrics, _, _ = make_engine(
        min_cycles=1,
        min_seconds=0,
    )
    candidate = cluster("c-gone")
    client.clusters["c-gone"] = candidate

    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=[candidate],
        metagraph_block=None,
        refresh_registered=lambda _minimum_block: set(),
    )

    assert client.deleted == []
    assert engine.absence_cycles(GONE) == 0
    assert 'reason="metagraph_failed"' in metrics.exposition().decode()


def test_repeated_metagraph_block_freezes_absence_window():
    engine, client, metrics, _, _ = make_engine(
        min_cycles=2,
        min_seconds=0,
    )
    candidate = cluster("c-gone")
    client.clusters["c-gone"] = candidate
    for _ in range(2):
        engine.run_cycle(
            registered_hotkeys={BOB},
            clusters=[candidate],
            metagraph_block=BLOCK,
            refresh_registered=lambda _minimum_block: set(),
        )

    assert client.deleted == []
    assert engine.absence_cycles(GONE) == 1
    assert 'reason="metagraph_failed"' in metrics.exposition().decode()


def test_rancher_outage_never_deletes_and_freezes_counter():
    engine, client, _metrics, clock, _ = make_engine()
    clusters = [cluster("c-gone")]
    run_until_threshold(engine, clock, clusters, {BOB}, 2)
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=None,
        metagraph_block=BLOCK,
        refresh_registered=lambda _minimum_block: set(),
    )
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
    run_until_threshold(
        engine,
        clock,
        clusters,
        {BOB},
        3,
        step_seconds=100,
        refresh=lambda _minimum_block: set(),
    )
    assert client.deleted == []


def test_boundary_899_vs_900_seconds():
    engine, client, _, clock, _ = make_engine(min_cycles=2, min_seconds=900)
    clusters = [cluster("c-gone")]
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK,
        refresh_registered=lambda _minimum_block: set(),
    )
    clock.advance(899)
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == []  # 899s < 900s
    clock.advance(1)
    client.clusters["c-gone"] = cluster("c-gone")
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 2,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == ["c-gone"]  # 900s reached


def test_reappearance_resets_counter():
    engine, client, _, clock, _ = make_engine()
    clusters = [cluster("c-gone")]
    run_until_threshold(engine, clock, clusters, {BOB}, 2)
    engine.run_cycle(
        registered_hotkeys={BOB, GONE},
        clusters=clusters,
        metagraph_block=BLOCK + 2,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert engine.absence_cycles(GONE) == 0
    run_until_threshold(
        engine,
        clock,
        clusters,
        {BOB},
        2,
        step_seconds=1000,
        start_block=BLOCK + 3,
    )
    assert (
        client.deleted == []
    )  # counter restarted; threshold not yet met again


# --- pre-delete recheck --------------------------------------------------------


def ready_engine():
    """Engine one healthy cycle away from deletion of c-gone."""
    engine, client, metrics, clock, logs = make_engine(
        min_cycles=2, min_seconds=100
    )
    clusters = [cluster("c-gone")]
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK,
        refresh_registered=lambda _minimum_block: set(),
    )
    clock.advance(200)
    client.clusters["c-gone"] = cluster("c-gone")
    return engine, client, metrics, clock, logs, clusters


def test_refresh_shows_reappearance_aborts_and_resets():
    engine, client, _, _clock, _, clusters = ready_engine()
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: {GONE},
    )
    assert client.deleted == []
    assert engine.absence_cycles(GONE) == 0


def test_refresh_failure_suppresses_no_delete():
    engine, client, metrics, _clock, _, clusters = ready_engine()
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: None,
    )
    assert client.deleted == []
    assert 'reason="metagraph_failed"' in metrics.exposition().decode()


def test_final_refresh_is_required_at_the_cycle_block_or_newer():
    engine, _, _, _, _, clusters = ready_engine()
    minimum_blocks = []

    def refresh(minimum_block):
        minimum_blocks.append(minimum_block)
        return {GONE}

    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=refresh,
    )

    assert minimum_blocks == [BLOCK + 1]


def test_label_changed_midcycle_aborts():
    engine, client, metrics, _, _, clusters = ready_engine()
    client.clusters["c-gone"] = cluster("c-gone", hotkey=BOB)  # relabeled
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == []
    assert 'reason="recheck_mismatch"' in metrics.exposition().decode()


def test_malformed_labels_during_recheck_abort():
    engine, client, metrics, _, _, clusters = ready_engine()
    current = cluster("c-gone")
    current["labels"] = "not-a-mapping"
    client.clusters["c-gone"] = current

    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )

    assert client.deleted == []
    assert 'reason="recheck_mismatch"' in metrics.exposition().decode()


@pytest.mark.parametrize(
    ("label", "value"),
    [(NETUID_LABEL, "2"), (NETWORK_LABEL, "test")],
)
def test_reconciliation_scope_changed_midcycle_aborts(label, value):
    engine, client, metrics, _, _, clusters = ready_engine()
    current = cluster("c-gone")
    current["labels"][label] = value
    client.clusters["c-gone"] = current

    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )

    assert client.deleted == []
    assert 'reason="recheck_mismatch"' in metrics.exposition().decode()


def test_binding_generation_changed_midcycle_aborts():
    engine, client, metrics, _, _, clusters = ready_engine()
    current = cluster("c-gone")
    current["labels"][GENERATION_LABEL] = "2"
    client.clusters["c-gone"] = current

    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )

    assert client.deleted == []
    assert 'reason="recheck_mismatch"' in metrics.exposition().decode()


def test_uuid_changed_midcycle_aborts():
    engine, client, _, _, _, clusters = ready_engine()
    client.clusters["c-gone"] = cluster("c-gone", uuid=UUID_OTHER)
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == []


def test_recheck_get_error_aborts():
    engine, client, _, _, _, clusters = ready_engine()
    client.get_errors["c-gone"] = RancherError(ErrorCategory.TRANSPORT, "down")
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == []
    assert engine.absence_cycles(GONE) == 2

    # The threshold evidence survives the transient GET failure, so the next
    # healthy cycle retries immediately instead of restarting the window.
    del client.get_errors["c-gone"]
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 2,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == ["c-gone"]
    assert engine.absence_cycles(GONE) == 0


# --- protected / unlabeled targets ---------------------------------------------


def test_unlabeled_and_internal_clusters_never_considered():
    engine, client, _, clock, _ = make_engine(min_cycles=1, min_seconds=0)
    mgmt = cluster("local", hotkey=None)
    internal = cluster("c-int", hotkey=GONE)
    internal["internal"] = True
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=[mgmt, internal],
        metagraph_block=BLOCK,
        refresh_registered=lambda _minimum_block: set(),
    )
    clock.advance(10)
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=[mgmt, internal],
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == []


def test_retired_miner_hotkey_label_is_not_a_reconciliation_candidate():
    engine, client, _, clock, _ = make_engine(min_cycles=1, min_seconds=0)
    legacy = cluster("c-legacy", hotkey=None)
    retired_label = "kubetee.ai/" + "miner-hotkey"
    legacy["labels"] = {retired_label: GONE}
    for offset in range(2):
        engine.run_cycle(
            registered_hotkeys={BOB},
            clusters=[legacy],
            metagraph_block=BLOCK + offset,
            refresh_registered=lambda _minimum_block: set(),
        )
        clock.advance(10)
    assert client.deleted == []


@pytest.mark.parametrize(
    ("label", "value"),
    [(NETUID_LABEL, "2"), (NETWORK_LABEL, "test")],
)
def test_cluster_outside_reconciliation_scope_is_never_deleted(label, value):
    engine, client, _, _, _ = make_engine(min_cycles=1, min_seconds=0)
    outside = cluster("c-outside")
    outside["labels"][label] = value
    client.clusters["c-outside"] = outside

    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=[outside],
        metagraph_block=BLOCK,
        refresh_registered=lambda _minimum_block: set(),
    )

    assert client.deleted == []


def test_non_enrolled_binding_is_never_a_reconciliation_candidate():
    engine, client, _, _, _ = make_engine(min_cycles=1, min_seconds=0)
    pending = cluster("c-pending")
    pending["labels"][BINDING_STATUS_LABEL] = "PENDING"
    client.clusters["c-pending"] = pending

    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=[pending],
        metagraph_block=BLOCK,
        refresh_registered=lambda _minimum_block: set(),
    )

    assert client.deleted == []


def test_malformed_labels_are_not_reconciliation_candidates():
    engine, client, _, clock, _ = make_engine(min_cycles=1, min_seconds=0)
    malformed = cluster("c-malformed", hotkey=None)
    malformed["labels"] = "not-a-mapping"
    for offset in range(2):
        engine.run_cycle(
            registered_hotkeys={BOB},
            clusters=[malformed],
            metagraph_block=BLOCK + offset,
            refresh_registered=lambda _minimum_block: set(),
        )
        clock.advance(10)
    assert client.deleted == []


def test_incomplete_canonical_binding_is_never_deleted():
    engine, client, _, _, _ = make_engine(min_cycles=1, min_seconds=0)
    malformed = cluster("c-incomplete")
    del malformed["labels"][BINDING_ID_LABEL]
    client.clusters[malformed["id"]] = malformed

    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=[malformed],
        metagraph_block=BLOCK,
        refresh_registered=lambda _minimum_block: set(),
    )

    assert client.deleted == []


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_uuid",
        "malformed_uuid",
        "uppercase_uuid",
        "invalid_id",
        "unsafe_id",
        "invalid_hotkey",
    ],
)
def test_malformed_candidate_identity_is_never_deleted(mutation):
    engine, client, _, _, _ = make_engine(min_cycles=1, min_seconds=0)
    malformed = cluster("c-malformed")
    if mutation == "missing_uuid":
        malformed.pop("uuid")
    elif mutation == "malformed_uuid":
        malformed["uuid"] = "not-a-rancher-uuid"
    elif mutation == "uppercase_uuid":
        malformed["uuid"] = "abcdefab-cdef-4abc-8def-abcdefabcdef".upper()
    elif mutation == "invalid_id":
        malformed["id"] = 123
    elif mutation == "unsafe_id":
        malformed["id"] = "../local"
    else:
        malformed["labels"][LABEL] = {"not": "scalar"}
    client.clusters[malformed["id"]] = malformed

    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=[malformed],
        metagraph_block=BLOCK,
        refresh_registered=lambda _minimum_block: set(),
    )

    assert client.deleted == []


def test_protected_id_never_deleted_even_if_labeled():
    engine, client, _, clock, _ = make_engine(min_cycles=1, min_seconds=0)
    trap = cluster("local", hotkey=GONE)
    for offset in range(3):
        engine.run_cycle(
            registered_hotkeys={BOB},
            clusters=[trap],
            metagraph_block=BLOCK + offset,
            refresh_registered=lambda _minimum_block: set(),
        )
        clock.advance(10)
    assert client.deleted == []


# --- deletion outcomes -----------------------------------------------------------


def test_successful_delete_counts_and_logs_evidence_bundle():
    engine, client, metrics, _clock, logs, clusters = ready_engine()
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == ["c-gone"]
    assert (
        "kubetee_reconciliation_deletions_total 1.0"
        in metrics.exposition().decode()
    )
    bundle = [e for e in logs if e.get("event") == "reconciliation_deletion"][
        -1
    ]
    for field in (
        "hotkey",
        "cluster_id",
        "cluster_uuid",
        "absence_cycles",
        "first_missing_at",
        "metagraph_blocks",
        "recheck",
        "response_class",
        "correlation_id",
    ):
        assert field in bundle, field
    assert engine.absence_cycles(GONE) == 0  # record cleared


@pytest.mark.parametrize("status", [404, 409])
def test_conflict_statuses_are_idempotent_not_retried(status):
    engine, client, metrics, _, _, clusters = ready_engine()
    client.delete_results["c-gone"] = status
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == ["c-gone"]
    assert (
        "kubetee_reconciliation_conflicts_total 1.0"
        in metrics.exposition().decode()
    )
    assert engine.absence_cycles(GONE) == 0  # resolved, no aggressive retry


def test_unauthorized_delete_fails_closed_with_operator_signal():
    engine, client, metrics, _, logs, clusters = ready_engine()
    client.delete_results["c-gone"] = RancherError(
        ErrorCategory.AUTH, "denied"
    )
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    text = metrics.exposition().decode()
    assert 'reason="unauthorized_operator_action_required"' in text
    assert any(e.get("event") == "reconciliation_unauthorized" for e in logs)
    assert engine.absence_cycles(GONE) == 2


def test_failed_delete_retains_absence_window_for_retry():
    engine, client, metrics, _, _, clusters = ready_engine()
    client.delete_results["c-gone"] = RancherError(
        ErrorCategory.TRANSPORT, "temporary outage"
    )
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert engine.absence_cycles(GONE) == 2
    assert 'reason="rancher_down"' in metrics.exposition().decode()

    client.delete_results["c-gone"] = 204
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 2,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == ["c-gone", "c-gone"]
    assert engine.absence_cycles(GONE) == 0


def test_retained_absence_evidence_has_bounded_block_history():
    engine, client, _, _, logs = make_engine(min_cycles=1, min_seconds=0)
    candidate = cluster("c-gone")
    client.clusters["c-gone"] = candidate
    client.get_errors["c-gone"] = RancherError(
        ErrorCategory.TRANSPORT, "persistent outage"
    )

    for offset in range(40):
        engine.run_cycle(
            registered_hotkeys={BOB},
            clusters=[candidate],
            metagraph_block=BLOCK + offset,
            refresh_registered=lambda _minimum_block: set(),
        )
    assert engine.absence_cycles(GONE) == 40

    del client.get_errors["c-gone"]
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=[candidate],
        metagraph_block=BLOCK + 40,
        refresh_registered=lambda _minimum_block: set(),
    )

    bundle = [e for e in logs if e.get("event") == "reconciliation_deletion"][
        -1
    ]
    assert bundle["absence_cycles"] == 41
    assert bundle["metagraph_blocks"] == list(range(BLOCK + 9, BLOCK + 41))


def test_duplicate_hotkey_record_waits_for_every_candidate():
    (
        engine,
        client,
        _,
        clock,
        _,
    ) = make_engine(min_cycles=2, min_seconds=100)
    first = cluster("c-one", uuid=UUID_ONE)
    second = cluster("c-two", uuid=UUID_TWO)
    clusters = [first, second]
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK,
        refresh_registered=lambda _minimum_block: set(),
    )
    clock.advance(200)
    client.clusters["c-one"] = first
    client.clusters["c-two"] = second
    client.get_errors["c-two"] = RancherError(
        ErrorCategory.TRANSPORT, "second cluster unavailable"
    )

    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == ["c-one"]
    assert engine.absence_cycles(GONE) == 2

    # A complete next enumeration contains only the unresolved candidate.
    del client.get_errors["c-two"]
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=[second],
        metagraph_block=BLOCK + 2,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert client.deleted == ["c-one", "c-two"]
    assert engine.absence_cycles(GONE) == 0


def test_duplicate_labeled_clusters_each_handled():
    engine, client, _, clock, logs = make_engine(min_cycles=2, min_seconds=100)
    clusters = [
        cluster("c-one", uuid=UUID_ONE),
        cluster("c-two", uuid=UUID_TWO),
    ]
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK,
        refresh_registered=lambda _minimum_block: set(),
    )
    clock.advance(200)
    client.clusters["c-one"] = cluster("c-one", uuid=UUID_ONE)
    client.clusters["c-two"] = cluster("c-two", uuid=UUID_TWO)
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    assert sorted(client.deleted) == ["c-one", "c-two"]
    deletions = [
        e for e in logs if e.get("event") == "reconciliation_deletion"
    ]
    assert {d["cluster_id"] for d in deletions} == {"c-one", "c-two"}


def test_evidence_bundle_never_contains_raw_labels_dump_or_state_payload():
    engine, _client, _, _clock, logs, clusters = ready_engine()
    engine.run_cycle(
        registered_hotkeys={BOB},
        clusters=clusters,
        metagraph_block=BLOCK + 1,
        refresh_registered=lambda _minimum_block: set(),
    )
    bundle = [e for e in logs if e.get("event") == "reconciliation_deletion"][
        -1
    ]
    assert "labels" not in bundle
    assert "state" not in bundle


def test_miner_prefixed_hotkey_cluster_is_scored_but_never_auto_deleted():
    """Deliberate posture: the validator accepts kubetee.ai/miner-hotkey as a
    scoring alias (infrastructure_validation.canonicalize_kubetee_keys), but the
    guarded deletion path extracts the hotkey via the RAW kubetee.ai/hotkey key.
    A cluster labeled only with the miner- alias therefore yields no hotkey for
    reconciliation and is never a deletion candidate — hand-provisioned staging
    clusters stay immune to the reaper even though they score."""
    engine, client, _, clock, _ = make_engine(min_cycles=1, min_seconds=0)
    aliased = cluster("c-aliased")
    aliased["labels"]["kubetee.ai/miner-hotkey"] = aliased["labels"].pop(LABEL)
    client.clusters["c-aliased"] = aliased

    for offset in range(3):
        engine.run_cycle(
            registered_hotkeys={BOB},  # GONE is absent from the metagraph
            clusters=[aliased],
            metagraph_block=BLOCK + offset,
            refresh_registered=lambda _minimum_block: set(),
        )
        clock.advance(1000)

    assert client.deleted == []
