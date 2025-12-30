# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

"""
Revenue Tracking and Miner Revenue Sharing Module

This module implements the incentivization mechanism for miners who provide
infrastructure services to users. Miners receive 50% of the revenue generated
from user service consumption.

Revenue Model:
- Users pay for AI services using Alpha tokens
- Validators track resource usage per epoch
- 50% of revenue goes to miners as service rewards
- 50% goes to subnet operations/treasury

Revenue Distribution:
- Tracked per miner hotkey
- Calculated per epoch based on actual service usage
- Distributed proportionally based on:
  1. Total requests served
  2. Compute resources consumed (GPU hours, CPU, memory)
  3. Quality of service (latency, uptime, success rate)
"""

import json
import time
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import bittensor as bt


# Revenue sharing constants
MINER_REVENUE_SHARE = 0.50  # Miners receive 50% of revenue
SUBNET_OPERATIONS_SHARE = 0.50  # Subnet operations receive 50%


@dataclass
class ServiceUsage:
    """Tracks individual service usage by a user on a miner's infrastructure."""
    user_hotkey: str
    miner_hotkey: str
    miner_uid: int
    timestamp: float
    service_type: str  # e.g., "inference", "rag", "fine_tuning", "embedding"
    
    # Resource metrics
    gpu_seconds: float = 0.0
    cpu_seconds: float = 0.0
    memory_gb_seconds: float = 0.0
    tokens_processed: int = 0
    requests_count: int = 1
    
    # Quality metrics
    latency_ms: float = 0.0
    success: bool = True
    
    # Revenue (in Alpha tokens)
    billed_amount: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ServiceUsage":
        return cls(**data)


@dataclass
class MinerRevenueRecord:
    """Aggregated revenue record for a miner during an epoch."""
    miner_hotkey: str
    miner_uid: int
    epoch: int
    
    # Aggregated metrics
    total_requests: int = 0
    total_tokens: int = 0
    total_gpu_seconds: float = 0.0
    total_cpu_seconds: float = 0.0
    total_memory_gb_seconds: float = 0.0
    
    # Quality aggregates
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0
    uptime_percentage: float = 100.0
    
    # Revenue breakdown (in Alpha tokens)
    total_revenue: float = 0.0
    miner_share: float = 0.0  # 50% of total_revenue
    subnet_share: float = 0.0  # 50% of total_revenue
    
    # Service breakdown
    service_usage_count: Dict[str, int] = field(default_factory=dict)
    
    # User breakdown (for transparency)
    unique_users: int = 0
    
    def calculate_shares(self):
        """Calculate the miner and subnet shares based on total revenue."""
        self.miner_share = self.total_revenue * MINER_REVENUE_SHARE
        self.subnet_share = self.total_revenue * SUBNET_OPERATIONS_SHARE
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "MinerRevenueRecord":
        return cls(**data)


class RevenueTracker:
    """
    Tracks revenue generation across miners and calculates revenue sharing.
    
    This class is used by validators to:
    1. Record service usage by users on miner infrastructure
    2. Aggregate revenue per miner per epoch
    3. Calculate 50% revenue share for miners
    4. Persist and load revenue data
    """
    
    def __init__(self, storage_path: str):
        """
        Initialize the revenue tracker.
        
        Args:
            storage_path: Path to store revenue tracking data
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Current epoch tracking
        self.current_epoch: int = 0
        
        # Service usage records for current epoch
        self.service_usages: List[ServiceUsage] = []
        
        # Historical revenue records per miner per epoch
        self.revenue_history: Dict[str, List[MinerRevenueRecord]] = {}
        
        # Current epoch aggregates per miner
        self.current_epoch_revenue: Dict[str, MinerRevenueRecord] = {}
        
        bt.logging.info(f"RevenueTracker initialized with storage at {self.storage_path}")
    
    def record_service_usage(self, usage: ServiceUsage):
        """
        Record a service usage event.
        
        Args:
            usage: The service usage record to add
        """
        self.service_usages.append(usage)
        
        # Update current epoch aggregates
        miner_key = usage.miner_hotkey
        if miner_key not in self.current_epoch_revenue:
            self.current_epoch_revenue[miner_key] = MinerRevenueRecord(
                miner_hotkey=usage.miner_hotkey,
                miner_uid=usage.miner_uid,
                epoch=self.current_epoch
            )
        
        record = self.current_epoch_revenue[miner_key]
        record.total_requests += usage.requests_count
        record.total_tokens += usage.tokens_processed
        record.total_gpu_seconds += usage.gpu_seconds
        record.total_cpu_seconds += usage.cpu_seconds
        record.total_memory_gb_seconds += usage.memory_gb_seconds
        record.total_revenue += usage.billed_amount
        
        # Update service usage count
        if usage.service_type not in record.service_usage_count:
            record.service_usage_count[usage.service_type] = 0
        record.service_usage_count[usage.service_type] += usage.requests_count
        
        # Recalculate shares
        record.calculate_shares()
        
        bt.logging.debug(
            f"Recorded service usage: miner={usage.miner_hotkey[:16]}..., "
            f"type={usage.service_type}, revenue={usage.billed_amount}"
        )
    
    def get_miner_revenue(self, miner_hotkey: str, epoch: Optional[int] = None) -> Optional[MinerRevenueRecord]:
        """
        Get revenue record for a specific miner.
        
        Args:
            miner_hotkey: The miner's hotkey
            epoch: Specific epoch to query, None for current epoch
            
        Returns:
            MinerRevenueRecord if found, None otherwise
        """
        if epoch is None or epoch == self.current_epoch:
            return self.current_epoch_revenue.get(miner_hotkey)
        
        # Look in history
        if miner_hotkey in self.revenue_history:
            for record in self.revenue_history[miner_hotkey]:
                if record.epoch == epoch:
                    return record
        return None
    
    def get_all_miner_revenues(self, epoch: Optional[int] = None) -> Dict[str, MinerRevenueRecord]:
        """
        Get all miner revenue records for an epoch.
        
        Args:
            epoch: Specific epoch, None for current
            
        Returns:
            Dictionary mapping miner hotkeys to their revenue records
        """
        if epoch is None or epoch == self.current_epoch:
            return self.current_epoch_revenue.copy()
        
        # Build from history
        result = {}
        for miner_key, records in self.revenue_history.items():
            for record in records:
                if record.epoch == epoch:
                    result[miner_key] = record
                    break
        return result
    
    def calculate_revenue_rewards(self, miner_uids: List[int], metagraph) -> np.ndarray:
        """
        Calculate revenue-based rewards for miners.
        
        The reward is proportional to the miner's share of total revenue generated.
        
        Args:
            miner_uids: List of miner UIDs to calculate rewards for
            metagraph: The network metagraph for hotkey lookups
            
        Returns:
            Array of rewards normalized to [0, 1] for each miner UID
        """
        rewards = np.zeros(len(miner_uids), dtype=np.float32)
        
        # Calculate total revenue across all miners
        total_revenue = sum(
            record.miner_share for record in self.current_epoch_revenue.values()
        )
        
        if total_revenue <= 0:
            bt.logging.debug("No revenue generated this epoch, returning zero rewards")
            return rewards
        
        # Calculate proportional rewards for each miner
        for idx, uid in enumerate(miner_uids):
            try:
                miner_hotkey = metagraph.hotkeys[uid]
                record = self.current_epoch_revenue.get(miner_hotkey)
                
                if record is not None and record.miner_share > 0:
                    # Proportional reward based on miner's share of total revenue
                    rewards[idx] = record.miner_share / total_revenue
                    
                    bt.logging.debug(
                        f"Miner {uid} ({miner_hotkey[:16]}...): "
                        f"revenue_share=${record.miner_share:.4f}, "
                        f"reward={rewards[idx]:.4f}"
                    )
            except (IndexError, KeyError) as e:
                bt.logging.warning(f"Could not calculate revenue reward for UID {uid}: {e}")
                continue
        
        return rewards
    
    def finalize_epoch(self, epoch: int):
        """
        Finalize the current epoch and prepare for the next.
        
        This calculates final metrics, saves data, and resets for next epoch.
        
        Args:
            epoch: The epoch number being finalized
        """
        bt.logging.info(f"Finalizing revenue tracking for epoch {epoch}")
        
        # Calculate final quality metrics for each miner
        for miner_key, record in self.current_epoch_revenue.items():
            miner_usages = [u for u in self.service_usages if u.miner_hotkey == miner_key]
            
            if miner_usages:
                # Calculate average latency
                latencies = [u.latency_ms for u in miner_usages]
                record.avg_latency_ms = sum(latencies) / len(latencies)
                
                # Calculate success rate
                successes = sum(1 for u in miner_usages if u.success)
                record.success_rate = successes / len(miner_usages)
                
                # Count unique users
                record.unique_users = len(set(u.user_hotkey for u in miner_usages))
            
            # Save to history
            if miner_key not in self.revenue_history:
                self.revenue_history[miner_key] = []
            self.revenue_history[miner_key].append(record)
        
        # Log epoch summary
        total_revenue = sum(r.total_revenue for r in self.current_epoch_revenue.values())
        total_miner_share = sum(r.miner_share for r in self.current_epoch_revenue.values())
        
        bt.logging.info(
            f"Epoch {epoch} Revenue Summary: "
            f"total=${total_revenue:.4f}, "
            f"miner_share=${total_miner_share:.4f} (50%), "
            f"miners_earning={len(self.current_epoch_revenue)}"
        )
        
        # Save to disk
        self._save_epoch_data(epoch)
        
        # Reset for next epoch
        self.current_epoch = epoch + 1
        self.service_usages = []
        self.current_epoch_revenue = {}
    
    def _save_epoch_data(self, epoch: int):
        """Save epoch data to disk."""
        epoch_file = self.storage_path / f"epoch_{epoch}_revenue.json"
        
        data = {
            "epoch": epoch,
            "timestamp": time.time(),
            "miner_records": {
                k: v.to_dict() for k, v in self.current_epoch_revenue.items()
            },
            "service_usages": [u.to_dict() for u in self.service_usages]
        }
        
        with open(epoch_file, "w") as f:
            json.dump(data, f, indent=2)
        
        bt.logging.debug(f"Saved revenue data for epoch {epoch} to {epoch_file}")
    
    def load_epoch_data(self, epoch: int) -> bool:
        """Load epoch data from disk."""
        epoch_file = self.storage_path / f"epoch_{epoch}_revenue.json"
        
        if not epoch_file.exists():
            return False
        
        try:
            with open(epoch_file, "r") as f:
                data = json.load(f)
            
            for miner_key, record_data in data.get("miner_records", {}).items():
                record = MinerRevenueRecord.from_dict(record_data)
                if miner_key not in self.revenue_history:
                    self.revenue_history[miner_key] = []
                self.revenue_history[miner_key].append(record)
            
            bt.logging.debug(f"Loaded revenue data for epoch {epoch}")
            return True
        except Exception as e:
            bt.logging.error(f"Error loading epoch {epoch} data: {e}")
            return False
    
    def get_revenue_stats(self) -> Dict:
        """Get overall revenue statistics."""
        total_historical_revenue = sum(
            sum(r.total_revenue for r in records)
            for records in self.revenue_history.values()
        )
        total_miner_payouts = sum(
            sum(r.miner_share for r in records)
            for records in self.revenue_history.values()
        )
        
        current_revenue = sum(r.total_revenue for r in self.current_epoch_revenue.values())
        current_miner_share = sum(r.miner_share for r in self.current_epoch_revenue.values())
        
        return {
            "current_epoch": self.current_epoch,
            "current_epoch_revenue": current_revenue,
            "current_epoch_miner_share": current_miner_share,
            "historical_total_revenue": total_historical_revenue,
            "historical_total_miner_payouts": total_miner_payouts,
            "active_miners_current_epoch": len(self.current_epoch_revenue),
            "miner_revenue_share_percentage": MINER_REVENUE_SHARE * 100
        }


def create_service_usage_from_request(
    user_hotkey: str,
    miner_hotkey: str,
    miner_uid: int,
    service_type: str,
    tokens_processed: int = 0,
    gpu_seconds: float = 0.0,
    latency_ms: float = 0.0,
    success: bool = True,
    pricing_per_token: float = 0.00001,  # Alpha per token
    pricing_per_gpu_second: float = 0.001  # Alpha per GPU second
) -> ServiceUsage:
    """
    Helper function to create a ServiceUsage from a service request.
    
    Args:
        user_hotkey: The user's hotkey who made the request
        miner_hotkey: The miner's hotkey who served the request
        miner_uid: The miner's UID
        service_type: Type of service (inference, rag, fine_tuning, embedding)
        tokens_processed: Number of tokens processed
        gpu_seconds: GPU seconds consumed
        latency_ms: Request latency in milliseconds
        success: Whether the request was successful
        pricing_per_token: Price per token in Alpha
        pricing_per_gpu_second: Price per GPU second in Alpha
        
    Returns:
        ServiceUsage record with calculated billing
    """
    # Calculate billed amount
    billed_amount = (tokens_processed * pricing_per_token) + (gpu_seconds * pricing_per_gpu_second)
    
    return ServiceUsage(
        user_hotkey=user_hotkey,
        miner_hotkey=miner_hotkey,
        miner_uid=miner_uid,
        timestamp=time.time(),
        service_type=service_type,
        gpu_seconds=gpu_seconds,
        tokens_processed=tokens_processed,
        latency_ms=latency_ms,
        success=success,
        billed_amount=billed_amount
    )

