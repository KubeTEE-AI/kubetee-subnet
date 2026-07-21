"""Prometheus metrics and skip/degraded-mode accounting (g004 V4, spec §4.2b).

Cardinality is bounded by construction: every label value is a fixed enum
member (rejecting arbitrary strings), and per-miner detail lives in
structured logs, never in metric labels. The exposition endpoint is bound
by the process (V6) to the compose-internal network only.

Degraded mode (spec D10/AC13): consecutive skipped cycles beyond
``max_consecutive_skips`` raise a loud flag — weights are never auto-zeroed.
"""

from __future__ import annotations

import enum
import time
from collections.abc import Callable

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
        if not isinstance(max_consecutive_skips, int) or max_consecutive_skips < 1:
            raise ValueError("max_consecutive_skips must be a positive integer")
        self._max_skips = max_consecutive_skips
        self._clock = clock
        self.registry = registry if registry is not None else CollectorRegistry()

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

        self._consecutive_count = 0
        self._in_degraded = False
        # Touch enum-labelled series so exposition always carries the names.
        for category in ErrorCategory:
            self._rancher_errors.labels(category=category.value)
        for reason in SkipReason:
            self._skips.labels(reason=reason.value)
        for reason in SuppressionReason:
            self._recon_suppressed.labels(reason=reason.value)
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
        self._set_weights.labels(result="success" if success else "failure").inc()

    def record_scoring_result(self, discovered: int, scoring: int) -> None:
        self._discovered.set(discovered)
        self._scoring.set(scoring)

    def record_reconciliation_deletion(self) -> None:
        self._recon_deleted.inc()

    def record_reconciliation_conflict(self) -> None:
        self._recon_conflicts.inc()

    def record_reconciliation_suppressed(self, reason: SuppressionReason) -> None:
        if not isinstance(reason, SuppressionReason):
            raise ValueError("reason must be a SuppressionReason member")
        self._recon_suppressed.labels(reason=reason.value).inc()

    def record_cycle_outcome(self, outcome: str) -> None:
        if outcome not in ("skip", "weights_set", "weights_rejected"):
            raise ValueError(f"invalid cycle outcome: {outcome!r}")
        self._cycles_total.labels(outcome=outcome).inc()

    # -- exposition ------------------------------------------------------------

    def exposition(self) -> bytes:
        return generate_latest(self.registry)
