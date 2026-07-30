"""Verdict -> on-chain weight: USD-denominated miner/owner split (scoring v3).

An EARNING miner's score is:
    usd_target_per_hour x tenure x window_hours / usd_per_alpha
where usd_target_per_hour applies the GPU $/GPU/hour card to that miner's GPU
capacity, and tenure is 0..1 for a clean probation streak. Whatever miners do
not earn recycles to the owner UID. Weights are normalized to sum 1.0.

Model: the epoch emission is a single pot expressed in USD (a fixed,
configurable emission budget `emission_usd_per_epoch`). Each EARNING miner
earns `usd_per_hour x tenure x window_hours` toward that pot. Miners' earned
USD is converted to weight proportional to their earned USD; the owner takes
the unallocated remainder of the pot (pot minus total earned). If nothing is
earned, everything recycles to the owner.
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
    cluster_name: str | None = None  # Rancher cluster name for this miner (dashboard)
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
    emission_usd_per_epoch: float,
) -> ScoreWeights:
    """Split the epoch emission weight between eligible miners and the owner.

    - Each EARNING (ready) miner earns `usd_per_hour x tenure x window_hours`
      of USD toward the pot (in alpha terms ÷ usd_per_alpha, which cancels in
      the normalized split but validates the feed is real).
    - The owner's remainder is `max(0, emission_usd_per_epoch - total_earned)`.
    - Weights are the earned-USD shares plus the owner remainder share.
    """
    if usd_per_alpha <= 0:
        raise ValueError("usd_per_alpha must be positive")
    if emission_usd_per_epoch < 0:
        raise ValueError("emission_usd_per_epoch must be non-negative")

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
        # Nothing earned: everything recycles to the owner (or splits evenly
        # among uids if the owner itself is not in the metagraph).
        if owner_present or owner_uid == 0:
            weights = {owner_uid: 1.0} if owner_present else _even(miners)
        else:
            weights = _even(miners)
        return ScoreWeights(weights, miner_usd, owner_weight=1.0, total_pool_usd=sum(miner_usd.values()) + emission_usd_per_epoch)

    total_earned = sum(miner_usd.values())
    owner_usd = max(0.0, emission_usd_per_epoch - total_earned)

    # Normalize earned USD + owner remainder into a weight vector summing 1.0.
    total_pool = total_earned + owner_usd
    weights: dict[int, float] = {
        uid: earned / total_pool for uid, earned in miner_usd.items()
    }
    owner_weight = owner_usd / total_pool

    if owner_present:
        weights[owner_uid] = weights.get(owner_uid, 0.0) + owner_weight
    elif owner_usd > 0:
        # Owner is not a metagraph uid; fold its remainder back to the miners
        # so weights still sum to 1.0 on-chain. The published pool reflects
        # only the miners' earned USD (the owner_usd is a "would-be" remainder
        # that is not represented on-chain).
        total_earned_only = sum(miner_usd.values())
        weights = {uid: e / total_earned_only for uid, e in miner_usd.items()}
        owner_weight = 0.0
        total_pool = total_earned_only

    return ScoreWeights(weights, miner_usd, owner_weight=owner_weight, total_pool_usd=total_pool)


def _even(miners: list[MinerInput]) -> dict[int, float]:
    if not miners:
        return {}
    share = 1.0 / len(miners)
    return {m.uid: share for m in miners}
