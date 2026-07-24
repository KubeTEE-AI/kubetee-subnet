"""Metagraph identity, miner discovery, and weight decisions.

Pure functions over injected data — no chain, no HTTP, no clock. The loop
feeds a metagraph snapshot plus infrastructure verdict scores in and applies
the returned decision. Rancher policy lives in ``infrastructure_validation``.
"""

from __future__ import annotations

import dataclasses
import enum
import math


class SkipReason(enum.Enum):
    """Fixed-enum reasons a cycle refuses to set weights (fail-closed)."""

    METAGRAPH_UNAVAILABLE = "metagraph_unavailable"
    METAGRAPH_STALE = "metagraph_stale"
    OWNER_UNRESOLVED = "owner_unresolved"
    IDENTITY_VIOLATION = "identity_violation"
    RANCHER_UNAVAILABLE = "rancher_unavailable"
    UNEXPECTED_RUNTIME = "unexpected_runtime"


def validate_share(value) -> float:
    """Fail-fast validation of KUBETEE_MINER_SHARE (D12): finite, in [0, 1]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("miner share must be a number")
    share = float(value)
    if not math.isfinite(share) or not 0.0 <= share <= 1.0:
        raise ValueError("miner share must be finite and within [0, 1]")
    return share


@dataclasses.dataclass(frozen=True)
class CycleConfig:
    """Static per-process configuration, validated fail-fast at construction."""

    owner_hotkey: str
    validator_hotkey: str
    miner_share: float

    def __post_init__(self) -> None:
        owner = (self.owner_hotkey or "").strip()
        validator = (self.validator_hotkey or "").strip()
        if not owner or not validator:
            raise ValueError("owner and validator hotkeys must be configured")
        if owner == validator:
            raise ValueError("owner and validator hotkeys must be distinct")
        object.__setattr__(self, "owner_hotkey", owner)
        object.__setattr__(self, "validator_hotkey", validator)
        object.__setattr__(
            self, "miner_share", validate_share(self.miner_share)
        )


@dataclasses.dataclass(frozen=True)
class WeightsDecision:
    weights: dict[int, float]
    miner_scores: dict[str, float]


@dataclasses.dataclass(frozen=True)
class SkipCycle:
    reason: SkipReason
    detail: str = ""


def decide_cycle(
    neurons: list[dict],
    miner_scores: dict[str, float],
    config: CycleConfig,
) -> WeightsDecision | SkipCycle:
    """Resolve identities, discover miners, and compute the weight vector.

    ``neurons`` is the metagraph snapshot as UID/hotkey/coldkey entries;
    ``miner_scores`` maps miner hotkeys to their binary infrastructure score
    (missing entries are treated as 0 — never as open trust).
    """
    for neuron in neurons:
        if (
            not isinstance(neuron, dict)
            or neuron.get("uid") is None
            or not neuron.get("hotkey")
            or not neuron.get("coldkey")
        ):
            return SkipCycle(
                SkipReason.IDENTITY_VIOLATION,
                "neuron missing uid, hotkey, or coldkey",
            )
        uid = neuron["uid"]
        hotkey = neuron["hotkey"]
        coldkey = neuron["coldkey"]
        if (
            isinstance(uid, bool)
            or not isinstance(uid, int)
            or uid < 0
            or not isinstance(hotkey, str)
            or not hotkey.strip()
            or not isinstance(coldkey, str)
            or not coldkey.strip()
        ):
            return SkipCycle(
                SkipReason.IDENTITY_VIOLATION,
                "neuron uid, hotkey, or coldkey has invalid shape",
            )

    uids = [n["uid"] for n in neurons]
    if len(uids) != len(set(uids)):
        return SkipCycle(
            SkipReason.IDENTITY_VIOLATION, "duplicate uid in metagraph"
        )

    hotkeys = [n["hotkey"] for n in neurons]
    if len(hotkeys) != len(set(hotkeys)):
        return SkipCycle(
            SkipReason.IDENTITY_VIOLATION, "duplicate hotkey in metagraph"
        )

    by_hotkey = {}
    for n in neurons:
        uid = n.get("uid")
        hotkey = n.get("hotkey")
        by_hotkey[hotkey] = uid
    owner_uid = by_hotkey.get(config.owner_hotkey)
    if owner_uid is None:
        return SkipCycle(
            SkipReason.OWNER_UNRESOLVED, "owner hotkey not registered"
        )
    validator_uid = by_hotkey.get(config.validator_hotkey)
    if validator_uid is None:
        return SkipCycle(
            SkipReason.IDENTITY_VIOLATION, "validator hotkey not registered"
        )

    own_uids = {owner_uid, validator_uid}
    miners = {
        n["hotkey"]: n["uid"] for n in neurons if n["uid"] not in own_uids
    }

    share = config.miner_share
    # Scoring v2: scores are non-negative floats (capacity x tenure); the
    # miner share is split PROPORTIONALLY to score. Binary 0/1 inputs
    # degenerate to the historical equal split.
    scores = {
        hotkey: float(miner_scores.get(hotkey, 0) or 0) for hotkey in miners
    }
    scoring = {
        hotkey: score
        for hotkey, score in scores.items()
        if score > 0.0 and math.isfinite(score)
    }
    weights: dict[int, float] = {n["uid"]: 0.0 for n in neurons}
    total_score = sum(scoring.values())
    if scoring and share > 0.0 and total_score > 0.0:
        for hotkey, score in scoring.items():
            weights[miners[hotkey]] = share * (score / total_score)
        weights[owner_uid] = 1.0 - share
    else:
        weights[owner_uid] = 1.0
    return WeightsDecision(
        weights=weights,
        miner_scores=scores,
    )
