"""Prometheus metrics and skip/degraded-mode accounting (g004 V4, spec §4.2b).

Cardinality is bounded by construction: every label value is a fixed enum
member (rejecting arbitrary strings), and per-miner detail lives in
structured logs, never in metric labels. The exposition endpoint is bound
by the process (V6) to the compose-internal network only.

Degraded mode (spec D10/AC13): consecutive skipped cycles beyond
``max_consecutive_skips`` raise a loud flag — weights are never auto-zeroed.
"""

from __future__ import annotations

import collections
import enum
import time
from collections.abc import Callable, Sequence

from infrastructure_validation import (
    ValidationReason,
    ValidationStatus,
    ValidationVerdict,
)
from miner_scoring import SkipReason
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)
from rancher_client import ErrorCategory


class SuppressionReason(enum.Enum):
    """Fixed-enum reasons a reconciliation deletion was suppressed (§4.2a)."""

    RANCHER_DOWN = "rancher_down"
    PAGINATION_INCOMPLETE = "pagination_incomplete"
    METAGRAPH_FAILED = "metagraph_failed"
    BELOW_THRESHOLD = "below_threshold"
    RECHECK_MISMATCH = "recheck_mismatch"
    UNAUTHORIZED = "unauthorized_operator_action_required"


class ValidatorMetrics:
    """Registry + accounting for one validator process."""

    def __init__(
        self,
        max_consecutive_skips: int = 10,
        clock: Callable[[], float] = time.time,
        registry: CollectorRegistry | None = None,
    ) -> None:
        if (
            not isinstance(max_consecutive_skips, int)
            or max_consecutive_skips < 1
        ):
            raise ValueError(
                "max_consecutive_skips must be a positive integer"
            )
        self._max_skips = max_consecutive_skips
        self._clock = clock
        self.registry = (
            registry if registry is not None else CollectorRegistry()
        )

        self._rancher_errors = Counter(
            "kubetee_rancher_errors",
            "Rancher API errors by fixed category",
            ["category"],
            registry=self.registry,
        )
        self._set_weights = Counter(
            "kubetee_set_weights",
            "set_weights outcomes",
            ["result"],
            registry=self.registry,
        )
        self._skips = Counter(
            "kubetee_cycles_skipped",
            "Cycles that skipped set_weights, by fixed reason",
            ["reason"],
            registry=self.registry,
        )
        self._consecutive = Gauge(
            "kubetee_consecutive_skips",
            "Current consecutive skipped cycles",
            registry=self.registry,
        )
        self._degraded = Gauge(
            "kubetee_degraded_mode",
            "1 when consecutive skips exceeded the configured maximum",
            registry=self.registry,
        )
        self._last_success = Gauge(
            "kubetee_last_successful_scoring_timestamp",
            "Unix time of the last full successful scoring cycle",
            registry=self.registry,
        )
        self._discovered = Gauge(
            "kubetee_miners_discovered",
            "Miners discovered on the metagraph this cycle",
            registry=self.registry,
        )
        self._scoring = Gauge(
            "kubetee_miners_scoring",
            "Miners with score 1 this cycle",
            registry=self.registry,
        )
        self._validation_status = Gauge(
            "kubetee_validation_status",
            "Current miners by infrastructure validation status",
            ["status"],
            registry=self.registry,
        )
        self._validation_reason = Gauge(
            "kubetee_validation_reason",
            "Current miners by fixed infrastructure validation reason",
            ["reason"],
            registry=self.registry,
        )
        self._recon_deleted = Counter(
            "kubetee_reconciliation_deletions",
            "Reconciliation cluster deletions performed",
            registry=self.registry,
        )
        self._recon_suppressed = Counter(
            "kubetee_reconciliation_suppressed",
            "Reconciliation deletions suppressed, by fixed reason",
            ["reason"],
            registry=self.registry,
        )
        self._recon_conflicts = Counter(
            "kubetee_reconciliation_conflicts",
            "Reconciliation deletions that hit 404/409 (already absent/conflict)",
            registry=self.registry,
        )
        self._cycles_total = Counter(
            "kubetee_cycles_total",
            "Total validator cycles by outcome",
            ["outcome"],
            registry=self.registry,
        )

        # Scoring v2 per-miner dashboard metrics (cardinality bounded by the
        # <=256-UID metagraph; stale hotkeys are removed on metagraph exit).
        miner_labels = ["hotkey", "cluster_id"]
        self._miner_state = Gauge(
            "kubetee_miner_state",
            "Miner reliability state (0=probation, 1=earning)",
            miner_labels,
            registry=self.registry,
        )
        self._miner_probation = Gauge(
            "kubetee_miner_probation_cycles",
            "Consecutive healthy cycles accumulated in probation",
            miner_labels,
            registry=self.registry,
        )
        self._miner_tenure = Gauge(
            "kubetee_miner_tenure_factor",
            "Tenure multiplier (0 while probation; 1.0..1.0+bonus earning)",
            miner_labels,
            registry=self.registry,
        )
        self._miner_capacity = Gauge(
            "kubetee_miner_capacity_score",
            "Hardware capacity score (GPUs x class weight; debug: nodes)",
            miner_labels,
            registry=self.registry,
        )
        self._miner_score = Gauge(
            "kubetee_miner_score",
            "Final miner score this cycle (capacity x tenure; 0 if gated)",
            miner_labels,
            registry=self.registry,
        )
        self._miner_weight = Gauge(
            "kubetee_miner_weight",
            "On-chain weight assigned to the miner this cycle",
            miner_labels,
            registry=self.registry,
        )
        self._miner_gpus = Gauge(
            "kubetee_miner_gpu_count",
            "Total GPUs in the miner cluster inventory",
            miner_labels,
            registry=self.registry,
        )
        self._miner_nodes = Gauge(
            "kubetee_miner_node_count",
            "Nodes in the miner cluster inventory",
            miner_labels,
            registry=self.registry,
        )
        self._miner_gpu_class = Gauge(
            "kubetee_miner_gpu_class",
            "Info gauge: 1 for the miner's GPU class",
            miner_labels + ["gpu_class"],
            registry=self.registry,
        )
        self._miner_reason = Gauge(
            "kubetee_miner_validation_reason",
            "Info gauge: 1 for the miner's validation reason this cycle",
            miner_labels + ["reason"],
            registry=self.registry,
        )
        self._miner_transitions = Counter(
            "kubetee_miner_state_transitions",
            "Miner reliability state transitions",
            ["hotkey", "transition"],
            registry=self.registry,
        )
        self._earning_total = Gauge(
            "kubetee_scoring_earning_miners",
            "Miners currently in the EARNING state",
            registry=self.registry,
        )
        self._probation_total = Gauge(
            "kubetee_scoring_probation_miners",
            "Miners currently in probation",
            registry=self.registry,
        )
        self._capacity_total = Gauge(
            "kubetee_scoring_total_capacity",
            "Sum of capacity scores across earning miners",
            registry=self.registry,
        )
        self._miner_series: dict[str, tuple] = {}
        self._miner_target_usd = Gauge(
            "kubetee_miner_target_usd",
            "Per-window USD compensation target (0 while gated)",
            miner_labels,
            registry=self.registry,
        )
        self._miner_target_alpha = Gauge(
            "kubetee_miner_target_alpha",
            "Per-window Alpha target at live prices (0 while gated)",
            miner_labels,
            registry=self.registry,
        )
        self._price_tao_usd = Gauge(
            "kubetee_price_tao_usd",
            "TAO price in USD from the feed (0 when overridden)",
            registry=self.registry,
        )
        self._price_alpha_tao = Gauge(
            "kubetee_price_alpha_tao",
            "Subnet alpha price in TAO from the feed (0 when overridden)",
            registry=self.registry,
        )
        self._price_usd_per_alpha = Gauge(
            "kubetee_price_usd_per_alpha",
            "USD value of one alpha used for target conversion",
            registry=self.registry,
        )
        self._price_feed_age = Gauge(
            "kubetee_price_feed_age_seconds",
            "Age of the price quote when applied",
            registry=self.registry,
        )
        self._dynamic_share = Gauge(
            "kubetee_scoring_dynamic_miner_share",
            "Computed miner share of the weight vector this cycle",
            registry=self.registry,
        )
        self._bucket_alpha = Gauge(
            "kubetee_scoring_bucket_alpha",
            "Miner-bucket alpha per payout window used for the share",
            registry=self.registry,
        )

        self._consecutive_count = 0
        self._in_degraded = False
        # Touch enum-labelled series so exposition always carries the names.
        for category in ErrorCategory:
            self._rancher_errors.labels(category=category.value)
        for reason in SkipReason:
            self._skips.labels(reason=reason.value)
        for reason in SuppressionReason:
            self._recon_suppressed.labels(reason=reason.value)
        for status in ValidationStatus:
            self._validation_status.labels(status=status.value)
        for reason in ValidationReason:
            self._validation_reason.labels(reason=reason.value)
        for result in ("success", "failure"):
            self._set_weights.labels(result=result)
        for outcome in ("skip", "weights_set", "weights_rejected"):
            self._cycles_total.labels(outcome=outcome)

    # -- properties ----------------------------------------------------------

    @property
    def consecutive_skips(self) -> int:
        return self._consecutive_count

    @property
    def degraded(self) -> bool:
        return self._in_degraded

    @property
    def last_successful_scoring(self) -> float:
        # prometheus_client exposes gauge reads only through this value handle.
        # pylint: disable-next=protected-access
        return self._last_success._value.get()

    # -- recording (enum-validated) -------------------------------------------

    def record_rancher_error(self, category: ErrorCategory) -> None:
        if not isinstance(category, ErrorCategory):
            raise ValueError("category must be an ErrorCategory member")
        self._rancher_errors.labels(category=category.value).inc()

    def record_skip(self, reason: SkipReason) -> bool:
        """Count a skipped cycle. Returns True exactly when degraded mode is entered."""
        if not isinstance(reason, SkipReason):
            raise ValueError("reason must be a SkipReason member")
        self._skips.labels(reason=reason.value).inc()
        self._consecutive_count += 1
        self._consecutive.set(self._consecutive_count)
        if self._consecutive_count > self._max_skips and not self._in_degraded:
            self._in_degraded = True
            self._degraded.set(1)
            return True
        return False

    def record_successful_scoring(self) -> None:
        self._consecutive_count = 0
        self._consecutive.set(0)
        if self._in_degraded:
            self._in_degraded = False
        self._degraded.set(0)
        self._last_success.set(self._clock())

    def record_set_weights(self, success: bool) -> None:
        self._set_weights.labels(
            result="success" if success else "failure"
        ).inc()

    def record_scoring_result(self, discovered: int, scoring: int) -> None:
        self._discovered.set(discovered)
        self._scoring.set(scoring)

    def record_validation_results(
        self, verdicts: Sequence[ValidationVerdict]
    ) -> None:
        if not all(
            isinstance(verdict, ValidationVerdict)
            and isinstance(verdict.status, ValidationStatus)
            and isinstance(verdict.reason, ValidationReason)
            for verdict in verdicts
        ):
            raise ValueError(
                "verdicts must contain fixed-enum ValidationVerdict members"
            )
        statuses = collections.Counter(verdict.status for verdict in verdicts)
        reasons = collections.Counter(verdict.reason for verdict in verdicts)
        for status in ValidationStatus:
            self._validation_status.labels(status=status.value).set(
                statuses[status]
            )
        for reason in ValidationReason:
            self._validation_reason.labels(reason=reason.value).set(
                reasons[reason]
            )

    def record_reconciliation_deletion(self) -> None:
        self._recon_deleted.inc()

    def record_reconciliation_conflict(self) -> None:
        self._recon_conflicts.inc()

    def record_reconciliation_suppressed(
        self, reason: SuppressionReason
    ) -> None:
        if not isinstance(reason, SuppressionReason):
            raise ValueError("reason must be a SuppressionReason member")
        self._recon_suppressed.labels(reason=reason.value).inc()

    def record_cycle_outcome(self, outcome: str) -> None:
        if outcome not in ("skip", "weights_set", "weights_rejected"):
            raise ValueError(f"invalid cycle outcome: {outcome!r}")
        self._cycles_total.labels(outcome=outcome).inc()

    # -- exposition ------------------------------------------------------------

    def record_pricing(
        self, quote, dynamic_share: float, bucket: float
    ) -> None:
        """Publish the cycle's price conversion + computed share."""
        self._price_tao_usd.set(quote.tao_usd)
        self._price_alpha_tao.set(quote.alpha_tao)
        self._price_usd_per_alpha.set(quote.usd_per_alpha)
        self._price_feed_age.set(
            max(0.0, self._clock() - quote.fetched_at)
            if quote.fetched_at
            else 0.0
        )
        self._dynamic_share.set(dynamic_share)
        self._bucket_alpha.set(bucket)

    def record_miner_scoring(self, evidence: list[dict]) -> None:
        """Set the per-miner dashboard series from one cycle's evidence and
        drop series for hotkeys no longer present."""
        seen: dict[str, tuple] = {}
        earning = probation = 0
        capacity_sum = 0.0
        for entry in evidence:
            hotkey = entry["hotkey"]
            cluster_id = entry.get("cluster_id") or ""
            labels = (hotkey, cluster_id)
            previous = self._miner_series.get(hotkey)
            if previous is not None:
                prev_labels, prev_reason, prev_class = previous
                if prev_labels != labels:
                    # The hotkey moved to a different cluster: drop every
                    # series under the old (hotkey, cluster_id) pair so
                    # zero-valued ghosts don't linger on the dashboard.
                    for gauge in (
                        self._miner_state,
                        self._miner_probation,
                        self._miner_tenure,
                        self._miner_capacity,
                        self._miner_score,
                        self._miner_target_usd,
                        self._miner_target_alpha,
                        self._miner_weight,
                        self._miner_gpus,
                        self._miner_nodes,
                    ):
                        try:
                            gauge.remove(*prev_labels)
                        except KeyError:
                            pass
                if prev_reason != entry["reason"] or prev_labels != labels:
                    try:
                        self._miner_reason.remove(*prev_labels, prev_reason)
                    except KeyError:
                        pass
                if prev_class and prev_class != entry.get("gpu_class"):
                    try:
                        self._miner_gpu_class.remove(*prev_labels, prev_class)
                    except KeyError:
                        pass
            seen[hotkey] = (
                labels,
                entry["reason"],
                entry.get("gpu_class"),
            )
            is_earning = entry["state"] == "earning"
            earning += int(is_earning)
            probation += int(not is_earning)
            if is_earning:
                capacity_sum += entry["capacity"]
            self._miner_state.labels(*labels).set(int(is_earning))
            self._miner_probation.labels(*labels).set(
                entry["probation_cycles"]
            )
            self._miner_tenure.labels(*labels).set(entry["tenure_factor"])
            self._miner_capacity.labels(*labels).set(entry["capacity"])
            self._miner_score.labels(*labels).set(entry["score"])
            self._miner_target_usd.labels(*labels).set(
                entry.get("target_usd", 0.0)
            )
            self._miner_target_alpha.labels(*labels).set(
                entry.get("target_alpha", 0.0)
            )
            self._miner_weight.labels(*labels).set(entry["weight"])
            self._miner_gpus.labels(*labels).set(entry["gpu_count"])
            self._miner_nodes.labels(*labels).set(entry["node_count"])
            if entry.get("gpu_class"):
                self._miner_gpu_class.labels(*labels, entry["gpu_class"]).set(
                    1
                )
            self._miner_reason.labels(*labels, entry["reason"]).set(1)
            if entry.get("transitioned"):
                self._miner_transitions.labels(
                    hotkey, entry["transitioned"]
                ).inc()
        for hotkey, (labels, _reason, _class) in self._miner_series.items():
            if hotkey in seen:
                continue
            for gauge in (
                self._miner_state,
                self._miner_probation,
                self._miner_tenure,
                self._miner_capacity,
                self._miner_score,
                self._miner_target_usd,
                self._miner_target_alpha,
                self._miner_weight,
                self._miner_gpus,
                self._miner_nodes,
            ):
                try:
                    gauge.remove(*labels)
                except KeyError:
                    pass
        self._miner_series = seen
        self._earning_total.set(earning)
        self._probation_total.set(probation)
        self._capacity_total.set(capacity_sum)

    def exposition(self) -> bytes:
        return generate_latest(self.registry)
