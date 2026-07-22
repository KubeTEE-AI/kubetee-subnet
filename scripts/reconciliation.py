"""Guarded deregistration reconciliation (g004 V5, spec §4.2a).

The single Rancher mutation the validator may ever perform: removing a
cluster whose canonical binding labels match this validator's network/netuid
and whose ``kubetee.ai/hotkey`` points at a hotkey that has verifiably left the
metagraph. Every guard is mandatory and fail-closed:

- runs only on cycles whose metagraph read AND complete Rancher enumeration
  both succeeded; any skip freezes (never increments, never resets) the
  per-hotkey absence counters and is counted as a suppression
- absence must persist >= ``min_cycles`` consecutive successful cycles AND
  >= ``min_seconds`` wall-clock (both; plan-pinned 3 / 900)
- pre-delete recheck in the same cycle: one head-pinned metagraph read at
  least as recent as the cycle must still show the hotkey absent, and one
  final GET must re-validate the canonical cluster id, uuid, and binding
  labels; any mismatch or error aborts
- unlabeled clusters, ``internal`` clusters, and protected ids are
  structurally out of reach
- DELETE 404/409 is idempotent (conflict counter, no retry); an AUTH error
  fails closed as "unauthorized — operator action required", never a
  silent no-op
- state is in-memory only: a restart resets counters, which only defers
  deletion (the safe direction)

Evidence bundles carry identifiers and history — never label dumps, raw
payloads, or anything secret-bearing.
"""

from __future__ import annotations

import dataclasses
import time
import uuid as uuid_module
from collections.abc import Callable, Iterable

from infrastructure_validation import (
    BINDING_ID_LABEL,
    BINDING_STATUS_LABEL,
    COLDKEY_LABEL,
    ENROLLMENT_UID_ANNOTATION,
    GENERATION_LABEL,
    HOTKEY_LABEL,
    NETUID_LABEL,
    NETWORK_LABEL,
    ORIGIN_FP_PREFIX_LABEL,
    PROVIDER_ID_LABEL,
    has_canonical_binding_metadata,
)
from rancher_client import ErrorCategory, RancherError, validate_cluster_id
from validator_metrics import SuppressionReason, ValidatorMetrics

MINER_LABEL = HOTKEY_LABEL
PROTECTED_CLUSTER_IDS = frozenset({"local"})
_BINDING_IDENTITY_LABELS = (
    BINDING_ID_LABEL,
    HOTKEY_LABEL,
    COLDKEY_LABEL,
    PROVIDER_ID_LABEL,
    BINDING_STATUS_LABEL,
    GENERATION_LABEL,
    NETUID_LABEL,
    NETWORK_LABEL,
    ORIGIN_FP_PREFIX_LABEL,
)
_MAX_EVIDENCE_BLOCKS = 32


def _canonical_uuid(value: object) -> bool:
    """Accept only Rancher's canonical 36-character UUID representation."""
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(uuid_module.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _same_binding_identity(expected: dict, current: dict) -> bool:
    """Require every canonical binding field to survive the final GET."""
    if not (
        has_canonical_binding_metadata(expected)
        and has_canonical_binding_metadata(current)
    ):
        return False
    expected_labels = expected["labels"]
    current_labels = current["labels"]
    if any(
        current_labels.get(label) != expected_labels.get(label)
        for label in _BINDING_IDENTITY_LABELS
    ):
        return False
    return current["annotations"].get(ENROLLMENT_UID_ANNOTATION) == expected[
        "annotations"
    ].get(ENROLLMENT_UID_ANNOTATION)


@dataclasses.dataclass
class _Absence:
    cycles: int
    first_missing_at: float
    metagraph_blocks: list[int]


class ReconciliationEngine:
    """Per-process reconciliation state machine (spec §4.2a)."""

    def __init__(
        self,
        client,
        metrics: ValidatorMetrics,
        expected_netuid: int,
        expected_network: str,
        min_cycles: int = 3,
        min_seconds: float = 900.0,
        clock: Callable[[], float] = time.time,
        evidence_sink: Callable[[dict], None] | None = None,
        protected_ids: frozenset[str] = PROTECTED_CLUSTER_IDS,
    ) -> None:
        if min_cycles < 1:
            raise ValueError("min_cycles must be >= 1")
        if min_seconds < 0:
            raise ValueError("min_seconds must be >= 0")
        if (
            isinstance(expected_netuid, bool)
            or not isinstance(expected_netuid, int)
            or expected_netuid < 0
        ):
            raise ValueError("expected_netuid must be a non-negative integer")
        if not isinstance(expected_network, str) or not expected_network:
            raise ValueError("expected_network must be non-empty")
        self._client = client
        self._metrics = metrics
        self._expected_netuid = str(expected_netuid)
        self._expected_network = expected_network
        self._min_cycles = min_cycles
        self._min_seconds = min_seconds
        self._clock = clock
        self._sink = evidence_sink or (lambda event: None)
        self._protected = protected_ids
        self._absences: dict[str, _Absence] = {}
        self._last_metagraph_block: int | None = None

    # -- introspection ---------------------------------------------------------

    def absence_cycles(self, hotkey: str) -> int:
        record = self._absences.get(hotkey)
        return record.cycles if record else 0

    # -- cycle entry point -------------------------------------------------------

    def run_cycle(
        self,
        registered_hotkeys: set[str] | None,
        clusters: list[dict] | None,
        metagraph_block: int | None,
        refresh_registered: Callable[[int], set[str] | None],
    ) -> None:
        """Evaluate reconciliation for one validator cycle.

        ``registered_hotkeys is None`` marks a failed metagraph read;
        ``clusters is None`` marks a failed/incomplete Rancher enumeration.
        Either suppresses and freezes every counter. Blocks must advance on
        successful cycles; the final refresh receives the current block as a
        minimum freshness bound.
        """
        if registered_hotkeys is None:
            self._metrics.record_reconciliation_suppressed(
                SuppressionReason.METAGRAPH_FAILED
            )
            return
        if clusters is None:
            self._metrics.record_reconciliation_suppressed(
                SuppressionReason.RANCHER_DOWN
            )
            return
        if (
            isinstance(metagraph_block, bool)
            or not isinstance(metagraph_block, int)
            or metagraph_block < 0
            or (
                self._last_metagraph_block is not None
                and metagraph_block <= self._last_metagraph_block
            )
        ):
            self._metrics.record_reconciliation_suppressed(
                SuppressionReason.METAGRAPH_FAILED
            )
            return
        self._last_metagraph_block = metagraph_block

        candidates = self._candidates(clusters)
        seen_hotkeys = {hotkey for hotkey, _ in candidates}

        # Reappearance on-chain, or the labeled cluster vanished: clear state.
        for hotkey in list(self._absences):
            if hotkey in registered_hotkeys or hotkey not in seen_hotkeys:
                del self._absences[hotkey]

        now = self._clock()
        for hotkey, hotkey_clusters in candidates:
            if hotkey in registered_hotkeys:
                continue
            record = self._absences.get(hotkey)
            if record is None:
                record = _Absence(
                    cycles=0, first_missing_at=now, metagraph_blocks=[]
                )
                self._absences[hotkey] = record
            record.cycles += 1
            record.metagraph_blocks.append(metagraph_block)
            if len(record.metagraph_blocks) > _MAX_EVIDENCE_BLOCKS:
                del record.metagraph_blocks[:-_MAX_EVIDENCE_BLOCKS]

            elapsed = now - record.first_missing_at
            if record.cycles < self._min_cycles or elapsed < self._min_seconds:
                self._metrics.record_reconciliation_suppressed(
                    SuppressionReason.BELOW_THRESHOLD
                )
                continue
            self._attempt_delete(
                hotkey,
                hotkey_clusters,
                record,
                metagraph_block,
                refresh_registered,
            )

    # -- internals ------------------------------------------------------------------

    def _candidates(
        self, clusters: Iterable[dict]
    ) -> list[tuple[str, list[dict]]]:
        """Group deletable-in-principle clusters by labeled hotkey."""
        grouped: dict[str, list[dict]] = {}
        for cluster in clusters:
            if not isinstance(cluster, dict):
                continue
            labels = cluster.get("labels")
            hotkey = (
                labels.get(MINER_LABEL) if isinstance(labels, dict) else None
            )
            cluster_id = cluster.get("id")
            cluster_uuid = cluster.get("uuid")
            if not isinstance(labels, dict):
                continue
            if not has_canonical_binding_metadata(cluster):
                continue
            if (
                labels.get(BINDING_STATUS_LABEL) != "ENROLLED"
                or labels.get(NETUID_LABEL) != self._expected_netuid
                or labels.get(NETWORK_LABEL) != self._expected_network
            ):
                continue  # another trust domain: structurally out of reach
            if not isinstance(hotkey, str) or not hotkey:
                continue  # unlabeled: structurally out of reach
            try:
                validate_cluster_id(cluster_id)
            except ValueError:
                continue
            if not _canonical_uuid(cluster_uuid):
                continue
            if cluster.get("internal") or cluster_id in self._protected:
                continue  # management/protected: structurally out of reach
            grouped.setdefault(hotkey, []).append(cluster)
        return sorted(grouped.items())

    def _attempt_delete(
        self,
        hotkey: str,
        hotkey_clusters: list[dict],
        record: _Absence,
        metagraph_block: int,
        refresh_registered: Callable[[int], set[str] | None],
    ) -> None:
        # Pre-delete recheck 1: one final fresh metagraph read, same cycle.
        fresh = refresh_registered(metagraph_block)
        if fresh is None:
            self._metrics.record_reconciliation_suppressed(
                SuppressionReason.METAGRAPH_FAILED
            )
            return
        if hotkey in fresh:
            del self._absences[hotkey]  # re-registered: reset, never delete
            return

        handled = 0
        for cluster in hotkey_clusters:
            cluster_id = cluster.get("id")
            # Pre-delete recheck 2: final GET re-validating identity + label.
            try:
                current = self._client.get_cluster(cluster_id)
            except (RancherError, ValueError):
                self._metrics.record_reconciliation_suppressed(
                    SuppressionReason.RECHECK_MISMATCH
                )
                continue
            current_labels = current.get("labels")
            if (
                current.get("id") != cluster_id
                or current.get("uuid") != cluster.get("uuid")
                or not _canonical_uuid(current.get("uuid"))
                or not _same_binding_identity(cluster, current)
                or not isinstance(current_labels, dict)
                or current_labels.get(MINER_LABEL) != hotkey
                or current_labels.get(BINDING_STATUS_LABEL) != "ENROLLED"
                or current_labels.get(NETUID_LABEL) != self._expected_netuid
                or current_labels.get(NETWORK_LABEL) != self._expected_network
                or current.get("internal")
                or cluster_id in self._protected
            ):
                self._metrics.record_reconciliation_suppressed(
                    SuppressionReason.RECHECK_MISMATCH
                )
                continue

            correlation_id = str(uuid_module.uuid4())
            try:
                status = self._client.delete_cluster(cluster_id)
            except RancherError as error:
                if error.category is ErrorCategory.AUTH:
                    self._metrics.record_reconciliation_suppressed(
                        SuppressionReason.UNAUTHORIZED
                    )
                    self._sink(
                        {
                            "event": "reconciliation_unauthorized",
                            "hotkey": hotkey,
                            "cluster_id": cluster_id,
                            "detail": "operator action required",
                            "correlation_id": correlation_id,
                        }
                    )
                else:
                    self._metrics.record_reconciliation_suppressed(
                        SuppressionReason.RANCHER_DOWN
                    )
                continue

            if status in (404, 409):
                self._metrics.record_reconciliation_conflict()
                response_class = f"conflict-{status}"
            else:
                self._metrics.record_reconciliation_deletion()
                response_class = f"deleted-{status}"
            handled += 1
            self._sink(
                {
                    "event": "reconciliation_deletion",
                    "hotkey": hotkey,
                    "cluster_id": cluster_id,
                    "cluster_uuid": cluster.get("uuid"),
                    "absence_cycles": record.cycles,
                    "first_missing_at": record.first_missing_at,
                    "metagraph_blocks": list(record.metagraph_blocks),
                    "recheck": "identity+label+uuid verified; fresh metagraph absent",
                    "response_class": response_class,
                    "correlation_id": correlation_id,
                }
            )

        # Preserve threshold evidence while any candidate remains unresolved
        # so a later healthy cycle retries it immediately. The hotkey-level
        # window resolves only after every candidate reached a successful
        # deletion or idempotent 404/409 outcome.
        if handled == len(hotkey_clusters):
            self._absences.pop(hotkey, None)
