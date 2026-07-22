"""g004 V4: Prometheus metrics + skip accounting / degraded mode (TDD).

Spec §4.2b + AC11 (fixed-enum labels, bounded cardinality, secret-free
exposition) and AC13 logic (KUBETEE_MAX_CONSECUTIVE_SKIPS boundary 10/11,
no auto-zero — degraded mode is a flag, never a weight change).
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from infrastructure_validation import (
    ValidationReason,
    ValidationStatus,
    ValidationVerdict,
)
from miner_scoring import SkipReason
from rancher_client import ErrorCategory
from validator_metrics import (
    SuppressionReason,
    ValidatorMetrics,
)


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_metrics(max_skips: int = 10) -> tuple[ValidatorMetrics, FakeClock]:
    clock = FakeClock()
    return (
        ValidatorMetrics(max_consecutive_skips=max_skips, clock=clock),
        clock,
    )


# --- exposition hygiene (AC11) ----------------------------------------------


def test_exposition_contains_expected_metric_names():
    metrics, _ = make_metrics()
    text = metrics.exposition().decode()
    for name in (
        "kubetee_rancher_errors_total",
        "kubetee_set_weights_total",
        "kubetee_cycles_skipped_total",
        "kubetee_consecutive_skips",
        "kubetee_degraded_mode",
        "kubetee_last_successful_scoring_timestamp",
        "kubetee_miners_discovered",
        "kubetee_miners_scoring",
        "kubetee_reconciliation_deletions_total",
        "kubetee_reconciliation_suppressed_total",
        "kubetee_reconciliation_conflicts_total",
        "kubetee_validation_status",
        "kubetee_validation_reason",
    ):
        assert name in text, name


def test_labels_are_fixed_enums_only():
    metrics, _ = make_metrics()
    with pytest.raises((ValueError, KeyError, TypeError)):
        metrics.record_rancher_error(
            "token-abc12:leak"
        )  # not an ErrorCategory
    with pytest.raises((ValueError, KeyError, TypeError)):
        metrics.record_skip("arbitrary string")  # not a SkipReason
    with pytest.raises((ValueError, KeyError, TypeError)):
        metrics.record_validation_results(["arbitrary string"])
    with pytest.raises((ValueError, KeyError, TypeError)):
        metrics.record_validation_results(
            [ValidationVerdict("eligible", ValidationReason.ELIGIBLE)]
        )


def test_exposition_never_contains_free_text():
    metrics, _ = make_metrics()
    metrics.record_rancher_error(ErrorCategory.TRANSPORT)
    metrics.record_skip(SkipReason.RANCHER_UNAVAILABLE)
    metrics.record_reconciliation_suppressed(SuppressionReason.RANCHER_DOWN)
    text = metrics.exposition().decode()
    assert "token-" not in text
    assert "Bearer" not in text


def test_scoring_gauges_are_aggregate_not_per_hotkey():
    metrics, _ = make_metrics()
    metrics.record_scoring_result(discovered=3, scoring=2)
    text = metrics.exposition().decode()
    assert "kubetee_miners_discovered 3.0" in text
    assert "kubetee_miners_scoring 2.0" in text
    assert "hotkey" not in text  # bounded cardinality: no per-miner labels


def test_validation_metrics_are_bounded_aggregates():
    metrics, _ = make_metrics()
    metrics.record_validation_results(
        [
            ValidationVerdict(
                ValidationStatus.ELIGIBLE,
                ValidationReason.ELIGIBLE,
                "c-secret-identifier",
            ),
            ValidationVerdict(
                ValidationStatus.SUSPENDED,
                ValidationReason.CLUSTER_MISSING,
            ),
            ValidationVerdict(
                ValidationStatus.SUSPENDED,
                ValidationReason.CLUSTER_MISSING,
            ),
        ]
    )
    text = metrics.exposition().decode()

    assert 'kubetee_validation_status{status="eligible"} 1.0' in text
    assert 'kubetee_validation_status{status="suspended"} 2.0' in text
    assert 'kubetee_validation_reason{reason="cluster_missing"} 2.0' in text
    assert 'kubetee_validation_reason{reason="eligible"} 1.0' in text
    assert "c-secret-identifier" not in text


def test_validation_metrics_replace_previous_cycle_values():
    metrics, _ = make_metrics()
    metrics.record_validation_results(
        [
            ValidationVerdict(
                ValidationStatus.SUSPENDED,
                ValidationReason.CLUSTER_MISSING,
            )
        ]
    )
    metrics.record_validation_results(
        [
            ValidationVerdict(
                ValidationStatus.ELIGIBLE,
                ValidationReason.ELIGIBLE,
                "c-miner",
            )
        ]
    )
    text = metrics.exposition().decode()

    assert 'kubetee_validation_status{status="eligible"} 1.0' in text
    assert 'kubetee_validation_status{status="suspended"} 0.0' in text
    assert 'kubetee_validation_reason{reason="cluster_missing"} 0.0' in text


# --- skip accounting / degraded mode (AC13 boundaries) ----------------------


def test_consecutive_skips_counted_and_reset_on_success():
    metrics, clock = make_metrics()
    metrics.record_skip(SkipReason.RANCHER_UNAVAILABLE)
    metrics.record_skip(SkipReason.RANCHER_UNAVAILABLE)
    assert metrics.consecutive_skips == 2
    metrics.record_successful_scoring()
    assert metrics.consecutive_skips == 0
    assert metrics.last_successful_scoring == clock.now


def test_degraded_mode_boundary_at_max_plus_one():
    metrics, _ = make_metrics(max_skips=10)
    for _ in range(10):
        metrics.record_skip(SkipReason.RANCHER_UNAVAILABLE)
    assert metrics.degraded is False  # 10 == max: not yet beyond
    metrics.record_skip(SkipReason.RANCHER_UNAVAILABLE)
    assert metrics.degraded is True  # 11 > max
    assert "kubetee_degraded_mode 1.0" in metrics.exposition().decode()


def test_degraded_mode_clears_on_recovery():
    metrics, _ = make_metrics(max_skips=2)
    for _ in range(3):
        metrics.record_skip(SkipReason.RANCHER_UNAVAILABLE)
    assert metrics.degraded is True
    metrics.record_successful_scoring()
    assert metrics.degraded is False
    assert "kubetee_degraded_mode 0.0" in metrics.exposition().decode()


def test_degraded_transitions_reported_once_for_logging():
    metrics, _ = make_metrics(max_skips=1)
    assert metrics.record_skip(SkipReason.RANCHER_UNAVAILABLE) is False
    assert (
        metrics.record_skip(SkipReason.RANCHER_UNAVAILABLE) is True
    )  # entered
    assert (
        metrics.record_skip(SkipReason.RANCHER_UNAVAILABLE) is False
    )  # already in


def test_max_skips_validated_fail_fast():
    with pytest.raises(ValueError):
        ValidatorMetrics(max_consecutive_skips=0)
    with pytest.raises(ValueError):
        ValidatorMetrics(max_consecutive_skips=-5)


# --- set_weights + reconciliation counters -----------------------------------


def test_set_weights_counters():
    metrics, _ = make_metrics()
    metrics.record_set_weights(success=True)
    metrics.record_set_weights(success=False)
    text = metrics.exposition().decode()
    assert 'kubetee_set_weights_total{result="success"} 1.0' in text
    assert 'kubetee_set_weights_total{result="failure"} 1.0' in text


def test_reconciliation_counters():
    metrics, _ = make_metrics()
    metrics.record_reconciliation_deletion()
    metrics.record_reconciliation_conflict()
    metrics.record_reconciliation_suppressed(SuppressionReason.BELOW_THRESHOLD)
    text = metrics.exposition().decode()
    assert "kubetee_reconciliation_deletions_total 1.0" in text
    assert "kubetee_reconciliation_conflicts_total 1.0" in text
    assert (
        'kubetee_reconciliation_suppressed_total{reason="below_threshold"} 1.0'
        in text
    )


def test_cycle_outcome_counter():
    metrics, _ = make_metrics()
    metrics.record_cycle_outcome("skip")
    metrics.record_cycle_outcome("weights_set")
    metrics.record_cycle_outcome("weights_rejected")
    text = metrics.exposition().decode()
    assert 'kubetee_cycles_total{outcome="skip"} 1.0' in text
    assert 'kubetee_cycles_total{outcome="weights_set"} 1.0' in text
    assert 'kubetee_cycles_total{outcome="weights_rejected"} 1.0' in text
