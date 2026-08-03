"""Verdict -> on-chain weight: USD-denominated miner/owner split (scoring v3).

An EARNING miner's score is:
    usd_target_per_hour x tenure x window_hours / usd_per_alpha
where usd_target_per_hour applies the GPU $/GPU/hour card to that miner's GPU
capacity, and tenure is 0..1 for a clean probation streak. Whatever miners do
not earn is recycled to the owner UID (set as weight on the owner's hotkey).
Weights are normalized to sum 1.0.

Model: the epoch emission is a single pot expressed in USD (a fixed,
configurable emission budget `emission_usd_per_epoch`). Each EARNING miner
earns `usd_per_hour x tenure x window_hours` toward that pot. Miners' earned
USD is converted to weight proportional to their earned USD; the unallocated
remainder of the pot (pot minus total earned) is recycled to the owner UID.
If nothing is earned, everything is recycled to the owner UID.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_GPUS_PER_WORKER = 8


@dataclass(frozen=True)
class MinerInput:
    uid: int
    hotkey: str
    ready: bool
    gpu_class: str | None  # dominant card class (for inventory/logs)
    gpu_workers: int  # workers in the dominant class
    gpu_breakdown: tuple = ()  # ((klass, workers), ...) per qualifying class
    total_qualifying_workers: int = 0  # sum across all classes
    cluster_name: str | None = (
        None  # Rancher cluster name for this miner (dashboard)
    )
    tenure: float = 1.0  # 0..1: 1.0 while the reliability gate is not wired


@dataclass(frozen=True)
class ScoreWeights:
    weights: dict[int, float]  # uid -> normalized weight (sums to 1.0)
    miner_usd: dict[int, float]  # uid -> usd earned toward the pot this epoch
    owner_weight: float  # the owner's normalized remainder share
    total_pool_usd: float  # miner_earned_usd + owner_remainder

    @property
    def miner_shares(self) -> dict[int, float]:
        """uid -> share of the total pool (0..1)."""
        if self.total_pool_usd <= 0:
            return {}
        return {u: v / self.total_pool_usd for u, v in self.miner_usd.items()}


def usd_target_per_hour(
    gpu_class: str | None, gpu_workers: int, usd_card: dict[str, float]
) -> float:
    """USD compensation target per hour for one miner, dominant-class × count."""
    if gpu_class is None or gpu_workers <= 0:
        return 0.0
    per_gpu = usd_card.get(gpu_class.upper(), 0.0)
    return per_gpu * _GPUS_PER_WORKER * gpu_workers


def usd_from_breakdown(
    gpu_breakdown: tuple, usd_card: dict[str, float]
) -> float:
    """USD compensation target per hour summed across all qualifying classes.

    `gpu_breakdown` is ((klass, gpu_count), ...) — gpu_count is the total
    number of qualifying GPUs of that class (from the node label), so
    usd = Σ class_price × gpu_count.
    """
    total = 0.0
    for klass, gpu_count in gpu_breakdown:
        per_gpu = usd_card.get(str(klass).upper(), 0.0)
        total += per_gpu * int(gpu_count)
    return total


def compute_weights(
    miners: list[MinerInput],
    usd_card: dict[str, float],
    usd_per_alpha: float,
    window_hours: float,
    owner_uid: int,
    emission_pool_usd: float,
) -> ScoreWeights:
    """Split the epoch emission weight between eligible miners and the owner.

    Each EARNING miner's USD target = GPU_count × card_price × hours_per_epoch.
    The weight = USD_target / emission_pool_usd (Targon-style: the pool is the
    denominator, not usd_per_alpha). If the sum of weights > 1, they are
    pro-rata normalized (the chain does this anyway). The remainder is
    recycled to the owner UID (set as weight on the owner's hotkey).
    """
    if emission_pool_usd <= 0:
        raise ValueError("emission_pool_usd must be positive")

    miner_usd: dict[int, float] = {}
    owner_present = any(m.uid == owner_uid for m in miners)

    for miner in miners:
        if not miner.ready:
            continue
        if miner.gpu_breakdown:
            target = usd_from_breakdown(miner.gpu_breakdown, usd_card)
        else:
            target = usd_target_per_hour(
                miner.gpu_class, miner.gpu_workers, usd_card
            )
        tenure = min(1.0, max(0.0, miner.tenure))
        earned = target * tenure * window_hours
        if earned > 0:
            miner_usd[miner.uid] = earned

    if not miner_usd:
        if owner_present or owner_uid == 0:
            weights = {owner_uid: 1.0} if owner_present else _even(miners)
        else:
            weights = _even(miners)
        return ScoreWeights(
            weights,
            miner_usd,
            owner_weight=1.0,
            total_pool_usd=emission_pool_usd,
        )

    total_earned = sum(miner_usd.values())

    # Weight = miner USD target / emission pool (Targon-style).
    # If sum > 1, pro-rata normalize (chain does this anyway).
    weights: dict[int, float] = {}
    for uid, earned in miner_usd.items():
        w = earned / emission_pool_usd
        weights[uid] = w

    # Pro-rata normalize if weights exceed 1.0
    total_weight = sum(weights.values())
    if total_weight > 1.0:
        scale = 1.0 / total_weight
        weights = {uid: w * scale for uid, w in weights.items()}
        total_weight = 1.0

    # Recycle to owner UID: what miners didn't earn of the pool
    owner_weight = max(0.0, 1.0 - total_weight)
    if owner_present:
        weights[owner_uid] = weights.get(owner_uid, 0.0) + owner_weight
    elif owner_weight > 0:
        # Owner not in metagraph; fold remainder back proportionally
        if total_weight > 0:
            weights = {uid: w / total_weight for uid, w in weights.items()}

    return ScoreWeights(
        weights,
        miner_usd,
        owner_weight=owner_weight,
        total_pool_usd=emission_pool_usd,
    )


def _even(miners: list[MinerInput]) -> dict[int, float]:
    if not miners:
        return {}
    share = 1.0 / len(miners)
    return {m.uid: share for m in miners}
