# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
Infrastructure Mechanism (Mechanism 0) - 50% of Emissions

Rewards miners for providing Kubernetes infrastructure to serve user requests.
Miners receive 50% of the revenue they generate from user services.

Scoring Criteria:
- Uptime (40% weight): Target 99.9%+
- TEE Compliance (25% weight): Intel TDX/SGX, AMD SEV, NVIDIA CC
- Latency (20% weight): Response time quality
- Capacity (15% weight): Available GPU/CPU resources

Uses native Bittensor multiple incentive mechanisms:
https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets
"""

import time
import json
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from pathlib import Path
import bittensor as bt

from .definitions import MECHANISM_INFRASTRUCTURE, MechanismType


# Scoring weights for infrastructure evaluation
UPTIME_WEIGHT = 0.40
TEE_WEIGHT = 0.25
LATENCY_WEIGHT = 0.20
CAPACITY_WEIGHT = 0.15

# Thresholds
EXCELLENT_UPTIME = 99.9
GOOD_UPTIME = 99.0
ACCEPTABLE_UPTIME = 95.0

EXCELLENT_LATENCY_MS = 100
GOOD_LATENCY_MS = 500
ACCEPTABLE_LATENCY_MS = 2000


@dataclass
class InfrastructureMetrics:
    """Metrics tracked per miner for infrastructure scoring."""
    miner_hotkey: str
    miner_uid: int
    
    # Uptime metrics
    uptime_percentage: float = 100.0
    total_checks: int = 0
    successful_checks: int = 0
    last_check_timestamp: float = 0.0
    
    # TEE compliance
    tee_enabled: bool = False
    tee_type: Optional[str] = None  # TDX, SGX, SEV, NVIDIA_CC
    fips_enabled: bool = False
    
    # Latency metrics (milliseconds)
    avg_latency_ms: float = 0.0
    latency_samples: List[float] = field(default_factory=list)
    
    # Capacity metrics
    gpu_available: float = 0.0
    gpu_total: float = 0.0
    cpu_available: float = 0.0
    memory_available_gb: float = 0.0
    
    # Revenue metrics (for 50% miner share)
    total_revenue_generated: float = 0.0
    total_requests_served: int = 0
    miner_revenue_share: float = 0.0  # 50% of total_revenue_generated
    
    # Cluster info
    cluster_id: Optional[str] = None
    region: Optional[str] = None
    
    def update_uptime(self, success: bool):
        """Update uptime metrics with a new check result."""
        self.total_checks += 1
        if success:
            self.successful_checks += 1
        self.uptime_percentage = (self.successful_checks / self.total_checks) * 100
        self.last_check_timestamp = time.time()
    
    def update_latency(self, latency_ms: float, max_samples: int = 100):
        """Update latency metrics with a new sample."""
        self.latency_samples.append(latency_ms)
        if len(self.latency_samples) > max_samples:
            self.latency_samples = self.latency_samples[-max_samples:]
        self.avg_latency_ms = sum(self.latency_samples) / len(self.latency_samples)
    
    def add_revenue(self, amount: float):
        """Add revenue and calculate miner's 50% share."""
        self.total_revenue_generated += amount
        self.total_requests_served += 1
        self.miner_revenue_share = self.total_revenue_generated * MECHANISM_INFRASTRUCTURE.miner_revenue_share
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['latency_samples'] = self.latency_samples[-10:]  # Only save last 10
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "InfrastructureMetrics":
        return cls(**data)


class InfrastructureScorer:
    """
    Scores miners for the Infrastructure mechanism.
    
    This scorer evaluates miners based on:
    1. Uptime reliability
    2. TEE compliance (security)
    3. Response latency
    4. Resource capacity
    
    Scores are used to set weights for mechanism 0 in the
    native Bittensor multi-mechanism system.
    """
    
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Metrics per miner
        self.metrics: Dict[str, InfrastructureMetrics] = {}
        
        # Load existing data
        self._load_metrics()
        
        bt.logging.info(
            f"InfrastructureScorer initialized: "
            f"emission={MECHANISM_INFRASTRUCTURE.emission_percentage}%, "
            f"miner_revenue_share={MECHANISM_INFRASTRUCTURE.miner_revenue_share*100}%"
        )
    
    def get_or_create_metrics(self, miner_hotkey: str, miner_uid: int) -> InfrastructureMetrics:
        """Get existing metrics or create new for a miner."""
        if miner_hotkey not in self.metrics:
            self.metrics[miner_hotkey] = InfrastructureMetrics(
                miner_hotkey=miner_hotkey,
                miner_uid=miner_uid
            )
        return self.metrics[miner_hotkey]
    
    def record_health_check(
        self,
        miner_hotkey: str,
        miner_uid: int,
        success: bool,
        latency_ms: float = 0.0,
        tee_enabled: bool = False,
        tee_type: Optional[str] = None,
        fips_enabled: bool = False,
        gpu_available: float = 0.0,
        gpu_total: float = 0.0,
        cluster_id: Optional[str] = None,
        region: Optional[str] = None,
    ):
        """Record a health check result for a miner."""
        metrics = self.get_or_create_metrics(miner_hotkey, miner_uid)
        
        # Update uptime
        metrics.update_uptime(success)
        
        # Update latency if check was successful
        if success and latency_ms > 0:
            metrics.update_latency(latency_ms)
        
        # Update TEE compliance
        metrics.tee_enabled = tee_enabled
        metrics.tee_type = tee_type
        metrics.fips_enabled = fips_enabled
        
        # Update capacity
        metrics.gpu_available = gpu_available
        metrics.gpu_total = gpu_total
        
        # Update cluster info
        metrics.cluster_id = cluster_id
        metrics.region = region
        
        bt.logging.debug(
            f"Health check: miner={miner_uid}, success={success}, "
            f"uptime={metrics.uptime_percentage:.2f}%, latency={latency_ms:.1f}ms"
        )
    
    def record_service_revenue(
        self,
        miner_hotkey: str,
        miner_uid: int,
        revenue_amount: float,
    ):
        """Record revenue generated by a miner (they get 50%)."""
        metrics = self.get_or_create_metrics(miner_hotkey, miner_uid)
        metrics.add_revenue(revenue_amount)
        
        bt.logging.debug(
            f"Service revenue: miner={miner_uid}, "
            f"amount={revenue_amount:.6f}, "
            f"miner_share={metrics.miner_revenue_share:.6f} (50%)"
        )
    
    def calculate_score(self, miner_hotkey: str) -> float:
        """
        Calculate the infrastructure score for a miner.
        
        Score components:
        - Uptime: 40% weight
        - TEE compliance: 25% weight
        - Latency: 20% weight
        - Capacity: 15% weight
        
        Returns:
            Score between 0.0 and 1.0
        """
        if miner_hotkey not in self.metrics:
            return 0.0
        
        metrics = self.metrics[miner_hotkey]
        
        # Uptime score (0-1)
        if metrics.uptime_percentage >= EXCELLENT_UPTIME:
            uptime_score = 1.0
        elif metrics.uptime_percentage >= GOOD_UPTIME:
            uptime_score = 0.8
        elif metrics.uptime_percentage >= ACCEPTABLE_UPTIME:
            uptime_score = 0.5
        else:
            uptime_score = metrics.uptime_percentage / 100.0
        
        # TEE compliance score (0-1)
        tee_score = 0.0
        if metrics.tee_enabled:
            tee_score = 0.6
            if metrics.tee_type in ["TDX", "SGX"]:
                tee_score = 0.8
            if metrics.fips_enabled:
                tee_score = 1.0
        
        # Latency score (0-1)
        if metrics.avg_latency_ms <= 0 or metrics.total_checks == 0:
            latency_score = 0.0
        elif metrics.avg_latency_ms <= EXCELLENT_LATENCY_MS:
            latency_score = 1.0
        elif metrics.avg_latency_ms <= GOOD_LATENCY_MS:
            latency_score = 0.7
        elif metrics.avg_latency_ms <= ACCEPTABLE_LATENCY_MS:
            latency_score = 0.4
        else:
            latency_score = max(0, 1.0 - (metrics.avg_latency_ms / 5000))
        
        # Capacity score (0-1)
        if metrics.gpu_total > 0:
            gpu_util = metrics.gpu_available / metrics.gpu_total
            capacity_score = min(1.0, gpu_util * 1.2)  # Bonus for high availability
        else:
            capacity_score = 0.0
        
        # Combined weighted score
        total_score = (
            UPTIME_WEIGHT * uptime_score +
            TEE_WEIGHT * tee_score +
            LATENCY_WEIGHT * latency_score +
            CAPACITY_WEIGHT * capacity_score
        )
        
        return min(1.0, max(0.0, total_score))
    
    def calculate_weights(
        self,
        miner_uids: List[int],
        metagraph,
    ) -> np.ndarray:
        """
        Calculate weights for all miners for the Infrastructure mechanism.
        
        These weights are set via subtensor.set_weights with mechanism_id=0.
        
        Args:
            miner_uids: List of miner UIDs
            metagraph: Network metagraph
            
        Returns:
            Normalized weight array for mechanism 0
        """
        weights = np.zeros(len(miner_uids), dtype=np.float32)
        
        for idx, uid in enumerate(miner_uids):
            try:
                hotkey = metagraph.hotkeys[uid]
                score = self.calculate_score(hotkey)
                
                # Boost score based on revenue (incentivize service provision)
                if hotkey in self.metrics:
                    revenue = self.metrics[hotkey].total_revenue_generated
                    if revenue > 0:
                        # Revenue bonus: up to 20% extra based on relative revenue
                        max_revenue = max(
                            (m.total_revenue_generated for m in self.metrics.values()),
                            default=1.0
                        )
                        if max_revenue > 0:
                            revenue_bonus = 0.2 * (revenue / max_revenue)
                            score = min(1.0, score + revenue_bonus)
                
                weights[idx] = score
                
            except (IndexError, KeyError):
                continue
        
        # Normalize weights
        total = np.sum(weights)
        if total > 0:
            weights = weights / total
        
        return weights
    
    def get_revenue_summary(self) -> Dict:
        """Get revenue summary for all miners."""
        total_revenue = sum(m.total_revenue_generated for m in self.metrics.values())
        total_miner_share = sum(m.miner_revenue_share for m in self.metrics.values())
        
        return {
            "total_revenue": total_revenue,
            "total_miner_share": total_miner_share,
            "miner_share_percentage": MECHANISM_INFRASTRUCTURE.miner_revenue_share * 100,
            "active_miners": len([m for m in self.metrics.values() if m.total_requests_served > 0]),
            "top_earners": sorted(
                [
                    {"hotkey": m.miner_hotkey[:16] + "...", "revenue": m.miner_revenue_share}
                    for m in self.metrics.values()
                    if m.miner_revenue_share > 0
                ],
                key=lambda x: x["revenue"],
                reverse=True
            )[:10]
        }
    
    def _save_metrics(self):
        """Save metrics to disk."""
        data = {
            hotkey: metrics.to_dict()
            for hotkey, metrics in self.metrics.items()
        }
        
        filepath = self.storage_path / "infrastructure_metrics.json"
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_metrics(self):
        """Load metrics from disk."""
        filepath = self.storage_path / "infrastructure_metrics.json"
        if filepath.exists():
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                
                for hotkey, metrics_data in data.items():
                    self.metrics[hotkey] = InfrastructureMetrics.from_dict(metrics_data)
                
                bt.logging.info(f"Loaded infrastructure metrics for {len(self.metrics)} miners")
            except Exception as e:
                bt.logging.warning(f"Could not load infrastructure metrics: {e}")
    
    def finalize_epoch(self, epoch: int):
        """Finalize epoch and save data."""
        summary = self.get_revenue_summary()
        bt.logging.info(
            f"Infrastructure Epoch {epoch} Summary:\n"
            f"  Total Revenue: ${summary['total_revenue']:.4f}\n"
            f"  Miner Share (50%): ${summary['total_miner_share']:.4f}\n"
            f"  Active Miners: {summary['active_miners']}"
        )
        self._save_metrics()

