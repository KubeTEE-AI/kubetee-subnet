"""Discovery, scoring, and weight logic for the KubeTEE basic validator (g004 V3).

Pure functions over injected data — no chain, no HTTP, no clock. The loop
(V6) feeds a metagraph snapshot and Rancher collections in and applies the
returned decision. Spec §4.2 steps 1/3/4; decisions D4, D9, D12.
"""

from __future__ import annotations

import dataclasses
import enum
import math

MINER_LABEL = "kubetee.ai/miner-hotkey"
ACTIVE = "active"
NOT_TRANSITIONING = "no"


class SkipReason(enum.Enum):
    """Fixed-enum reasons a cycle refuses to set weights (fail-closed)."""

    METAGRAPH_UNAVAILABLE = "metagraph_unavailable"
    OWNER_UNRESOLVED = "owner_unresolved"
    IDENTITY_VIOLATION = "identity_violation"
    RANCHER_UNAVAILABLE = "rancher_unavailable"


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
        object.__setattr__(self, "miner_share", validate_share(self.miner_share))


@dataclasses.dataclass(frozen=True)
class WeightsDecision:
    weights: dict[int, float]
    miner_scores: dict[str, int]


@dataclasses.dataclass(frozen=True)
class SkipCycle:
    reason: SkipReason
    detail: str = ""


def _is_active(obj: dict) -> bool:
    return (
        isinstance(obj, dict)
        and obj.get("state") == ACTIVE
        and obj.get("transitioning", NOT_TRANSITIONING) == NOT_TRANSITIONING
    )


def score_miner(
    hotkey: str,
    clusters: list[dict],
    nodes_by_cluster: dict[str, list[dict]],
) -> int:
    """Binary fail-closed node-active score for one miner (spec §4.2 step 3)."""
    matches = [
        c for c in clusters
        if isinstance(c, dict) and (c.get("labels") or {}).get(MINER_LABEL) == hotkey
    ]
    if len(matches) != 1:
        return 0
    cluster = matches[0]
    if not _is_active(cluster):
        return 0
    nodes = nodes_by_cluster.get(cluster.get("id"))
    if not isinstance(nodes, list) or not nodes:
        return 0
    return 1 if any(_is_active(n) for n in nodes) else 0


def decide_cycle(
    neurons: list[dict],
    miner_scores: dict[str, int],
    config: CycleConfig,
) -> WeightsDecision | SkipCycle:
    """Resolve identities, discover miners, and compute the weight vector.

    ``neurons`` is the metagraph snapshot as ``{"uid": int, "hotkey": str}``
    entries; ``miner_scores`` maps miner hotkeys to their binary score
    (missing entries are treated as 0 — never as open trust).
    """
    hotkeys = [n.get("hotkey") for n in neurons]
    if not all(hotkeys):
        return SkipCycle(SkipReason.IDENTITY_VIOLATION, "neuron missing hotkey in metagraph")
    if len(hotkeys) != len(set(hotkeys)):
        return SkipCycle(SkipReason.IDENTITY_VIOLATION, "duplicate hotkey in metagraph")

    by_hotkey = {}
    for n in neurons:
        uid = n.get("uid")
        hotkey = n.get("hotkey")
        if hotkey is None or uid is None:
            return SkipCycle(SkipReason.IDENTITY_VIOLATION, "neuron missing hotkey or uid")
        by_hotkey[hotkey] = uid
    owner_uid = by_hotkey.get(config.owner_hotkey)
    if owner_uid is None:
        return SkipCycle(SkipReason.OWNER_UNRESOLVED, "owner hotkey not registered")
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
    scoring = [hotkey for hotkey in miners if miner_scores.get(hotkey, 0) == 1]
    weights: dict[int, float] = {n["uid"]: 0.0 for n in neurons}
    if scoring and share > 0.0:
        per_miner = share / len(scoring)
        for hotkey in scoring:
            weights[miners[hotkey]] = per_miner
        weights[owner_uid] = 1.0 - share
    else:
        weights[owner_uid] = 1.0
    return WeightsDecision(
        weights=weights,
        miner_scores={h: miner_scores.get(h, 0) for h in miners},
    )
