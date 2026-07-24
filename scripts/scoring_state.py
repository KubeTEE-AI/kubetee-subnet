"""Scoring v2 reliability state machine, tenure, capacity, persistence.

Spec: kubetee/docs/superpowers/specs/2026-07-24-scoring-v2-design.md.

Per-hotkey states:

- PROBATION(k): entry state for new miners and after any failed cycle.
  Scores 0. Each fully-healthy cycle increments k; a failed cycle resets
  k to 0; reaching ``probation_cycles`` promotes to EARNING (tenure clock
  starts). ``probation_cycles == 0`` disables the gate.
- EARNING: scored ``capacity x tenure``. Any failed cycle demotes to
  PROBATION(0) and forfeits tenure.

Fault model: the engine is simply NOT called on skipped validator cycles
(Rancher/metagraph outage), which freezes every counter — the same
discipline as reconciliation absence counters. A validator restart reloads
the persisted state file, so restarts never punish miners; a missing or
corrupt file seeds the ``bootstrap_earning`` hotkeys (derived from on-chain
weights) as EARNING so state loss never zeroes a working miner.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import math
import os
import pathlib
import re
import time
from collections.abc import Callable

from loguru import logger

from infrastructure_validation import ValidationProfile

# Static Phase-0 instantiation of the Targon supply-side benchmark
# (docs/COMPETITIVE-PRICING.md): 24/28/52/64 TAO per 8-card node.
DEFAULT_GPU_WEIGHTS: dict[str, float] = {
    "H100": 1.0,
    "H200": 1.17,
    "B200": 2.17,
    "B300": 2.67,
}

# Placeholder $/GPU/hour card (Targon-ratio-consistent, $2 H100 base) until
# the operator's real USD price card lands via KUBETEE_GPU_USD_PRICES.
DEFAULT_GPU_USD_PRICES: dict[str, float] = {
    "H100": 2.00,
    "H200": 2.34,
    "B200": 4.34,
    "B300": 5.34,
}

_GPU_CLASS = re.compile(r"(?<![A-Z0-9])(H100|H200|B200|B300)(?![A-Z0-9])")
_STATE_VERSION = 1


class MinerState(enum.Enum):
    """Reliability state of one miner."""

    PROBATION = "probation"
    EARNING = "earning"


@dataclasses.dataclass(frozen=True)
class ScoringConfig:
    """Validated scoring constants (fail-fast at construction)."""

    probation_cycles: int
    tenure_bonus: float
    tenure_days: float
    gpu_weights: dict[str, float]

    def __post_init__(self) -> None:
        if (
            isinstance(self.probation_cycles, bool)
            or not isinstance(self.probation_cycles, int)
            or self.probation_cycles < 0
        ):
            raise ValueError("probation_cycles must be an integer >= 0")
        if (
            not isinstance(self.tenure_bonus, float)
            or not math.isfinite(self.tenure_bonus)
            or self.tenure_bonus < 0
        ):
            raise ValueError("tenure_bonus must be a finite float >= 0")
        if (
            not isinstance(self.tenure_days, float)
            or not math.isfinite(self.tenure_days)
            or self.tenure_days <= 0
        ):
            raise ValueError("tenure_days must be a finite float > 0")
        if not isinstance(self.gpu_weights, dict) or not self.gpu_weights:
            raise ValueError("gpu_weights must be a non-empty mapping")


def parse_gpu_weights(raw: str) -> dict[str, float]:
    """Parse ``"H100=1.0,B200=2.17"`` fail-fast into class weights."""
    weights: dict[str, float] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        name, eq, value = pair.partition("=")
        if not eq or not name.strip():
            raise ValueError(f"gpu weight entry must be CLASS=FLOAT: {pair!r}")
        try:
            weight = float(value)
        except ValueError as error:
            raise ValueError(
                f"gpu weight for {name.strip()!r} must be a number"
            ) from error
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError(
                f"gpu weight for {name.strip()!r} must be finite and > 0"
            )
        weights[name.strip()] = weight
    if not weights:
        raise ValueError("gpu weights must contain at least one CLASS=FLOAT")
    return weights


def node_gpu_count(node: object) -> int:
    if not isinstance(node, dict):
        return 0
    capacity = node.get("capacity")
    if not isinstance(capacity, dict):
        return 0
    raw = capacity.get("nvidia.com/gpu")
    try:
        count = int(str(raw))
    except (TypeError, ValueError):
        return 0
    return count if count > 0 else 0


def node_gpu_class(node: object) -> str | None:
    if not isinstance(node, dict):
        return None
    labels = node.get("labels")
    if not isinstance(labels, dict):
        return None
    product = labels.get("nvidia.com/gpu.product")
    if not isinstance(product, str):
        return None
    match = _GPU_CLASS.search(product)
    return match.group(1) if match else None


def capacity_score(
    nodes: object,
    profile: ValidationProfile,
    gpu_weights: dict[str, float],
) -> float:
    """Hardware capacity of one already-eligible cluster.

    Production: sum over nodes of GPU count x class weight (unknown class or
    count fails closed to 0 for that node). Debug: active node count (no GPU
    inventory exists on the disposable local stack).
    """
    if not isinstance(nodes, list):
        return 0.0
    if profile is ValidationProfile.DEBUG:
        return float(len(nodes))
    total = 0.0
    for node in nodes:
        count = node_gpu_count(node)
        gpu_class = node_gpu_class(node)
        if count <= 0 or gpu_class is None:
            continue
        weight = gpu_weights.get(gpu_class)
        if weight is None:
            continue
        total += count * weight
    return total


def usd_target_per_hour(
    nodes: object,
    profile: ValidationProfile,
    usd_card: dict[str, float],
) -> float:
    """USD/hour compensation target of one already-eligible cluster
    (scoring v3): production = sum over nodes of GPU count x $/GPU/hour for
    the node's class (unknown class or count fails closed to 0 for that
    node); debug = node count x the H100 card price (the disposable local
    stack has no GPU inventory).
    """
    if not isinstance(nodes, list):
        return 0.0
    if profile is ValidationProfile.DEBUG:
        return float(len(nodes)) * float(usd_card.get("H100", 0.0))
    total = 0.0
    for node in nodes:
        count = node_gpu_count(node)
        gpu_class = node_gpu_class(node)
        if count <= 0 or gpu_class is None:
            continue
        price = usd_card.get(gpu_class)
        if price is None:
            continue
        total += count * float(price)
    return total


@dataclasses.dataclass
class _MinerRecord:
    state: MinerState
    probation_count: int
    earning_since: float | None


@dataclasses.dataclass(frozen=True)
class MinerScore:
    """One miner's reliability observation for the current cycle."""

    state: MinerState
    probation_cycles: int
    tenure_factor: float
    transitioned: str | None  # "to_earning" | "to_probation" | None


class ScoringStateEngine:
    """Per-hotkey reliability state with file persistence."""

    def __init__(
        self,
        config: ScoringConfig,
        state_file: pathlib.Path | None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._state_file = (
            pathlib.Path(state_file) if state_file is not None else None
        )
        self._clock = clock
        self._miners: dict[str, _MinerRecord] = {}

    # -- persistence -----------------------------------------------------------

    def load(self, bootstrap_earning: set[str]) -> None:
        """Load persisted state; on a missing/corrupt file, seed the
        bootstrap hotkeys as EARNING (tenure restarts now)."""
        if self._state_file is not None:
            try:
                raw = json.loads(self._state_file.read_text(encoding="utf-8"))
                miners = raw["miners"]
                loaded: dict[str, _MinerRecord] = {}
                for hotkey, record in miners.items():
                    state = MinerState(record["state"])
                    loaded[hotkey] = _MinerRecord(
                        state=state,
                        probation_count=int(record["probation_count"]),
                        earning_since=(
                            float(record["earning_since"])
                            if record.get("earning_since") is not None
                            else None
                        ),
                    )
                self._miners = loaded
                return
            except (OSError, ValueError, KeyError, TypeError):
                logger.warning(
                    "scoring state file unreadable; bootstrapping",
                    extra={
                        "state_file": str(self._state_file),
                        "bootstrap_earning": len(bootstrap_earning),
                    },
                )
        now = self._clock()
        self._miners = {
            hotkey: _MinerRecord(
                state=MinerState.EARNING,
                probation_count=0,
                earning_since=now,
            )
            for hotkey in bootstrap_earning
        }

    def save(self) -> None:
        """Atomically persist the current state (tmp + rename)."""
        if self._state_file is None:
            return
        payload = {
            "version": _STATE_VERSION,
            "miners": {
                hotkey: {
                    "state": record.state.value,
                    "probation_count": record.probation_count,
                    "earning_since": record.earning_since,
                }
                for hotkey, record in self._miners.items()
            },
        }
        tmp = self._state_file.with_suffix(self._state_file.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            os.replace(tmp, self._state_file)
        except OSError:
            logger.warning(
                "scoring state persist failed",
                extra={"state_file": str(self._state_file)},
            )

    # -- observation -----------------------------------------------------------

    def observe(self, hotkey: str, healthy: bool) -> MinerScore:
        """Advance one miner's state for a completed (non-skipped) cycle."""
        record = self._miners.get(hotkey)
        if record is None:
            record = _MinerRecord(
                state=MinerState.PROBATION,
                probation_count=0,
                earning_since=None,
            )
            self._miners[hotkey] = record

        transitioned: str | None = None
        if record.state is MinerState.EARNING:
            if not healthy:
                record.state = MinerState.PROBATION
                record.probation_count = 0
                record.earning_since = None
                transitioned = "to_probation"
        else:  # PROBATION
            if healthy:
                record.probation_count += 1
                # The gate is N full cycles at score 0; earning starts on the
                # observation AFTER the counter passes N (N=0 disables).
                if record.probation_count > self._config.probation_cycles:
                    record.state = MinerState.EARNING
                    record.earning_since = self._clock()
                    transitioned = "to_earning"
            else:
                record.probation_count = 0

        return MinerScore(
            state=record.state,
            probation_cycles=record.probation_count,
            tenure_factor=self._tenure(record),
            transitioned=transitioned,
        )

    def drop_missing(self, current_hotkeys: set[str]) -> None:
        """Forget miners that left the metagraph (reaper owns the cluster)."""
        for hotkey in list(self._miners):
            if hotkey not in current_hotkeys:
                del self._miners[hotkey]

    def snapshot(self) -> dict[str, str]:
        """Bounded view for logs/metrics: hotkey -> state value."""
        return {
            hotkey: record.state.value
            for hotkey, record in self._miners.items()
        }

    # -- internals -------------------------------------------------------------

    def _tenure(self, record: _MinerRecord) -> float:
        if record.state is not MinerState.EARNING:
            return 0.0
        if record.earning_since is None:
            record.earning_since = self._clock()
        days = max(0.0, (self._clock() - record.earning_since) / 86400.0)
        ramp = min(days / self._config.tenure_days, 1.0)
        return 1.0 + self._config.tenure_bonus * ramp
