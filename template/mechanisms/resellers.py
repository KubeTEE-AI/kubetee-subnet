# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
Resellers Mechanism (Mechanism 2) - 20% of Emissions

Rewards community integrators who bring users to the KubeTEE platform.
Distribution channel incentivization for system integrators and partners.

Scoring Criteria:
- Users Referred (40% weight): Number of active users brought
- Revenue Generated (35% weight): Total revenue from referred users
- User Retention (15% weight): Retention rate of referred users
- Enterprise Deals (10% weight): Bonus for enterprise-level deals

Uses native Bittensor multiple incentive mechanisms:
https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets
"""

import time
import json
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set
from pathlib import Path
import bittensor as bt

from .definitions import MECHANISM_RESELLERS, MechanismType


# Scoring weights for reseller evaluation
USERS_REFERRED_WEIGHT = 0.40
REVENUE_GENERATED_WEIGHT = 0.35
RETENTION_WEIGHT = 0.15
ENTERPRISE_WEIGHT = 0.10


@dataclass
class ResellerMetrics:
    """Metrics tracked per reseller/integrator."""
    reseller_hotkey: str
    reseller_uid: int
    
    # Registration info
    company_name: Optional[str] = None
    registration_timestamp: float = 0.0
    kyc_verified: bool = False
    
    # Referral tracking
    referred_users: Set[str] = field(default_factory=set)
    active_referred_users: Set[str] = field(default_factory=set)
    total_users_referred: int = 0
    
    # Revenue from referrals
    total_revenue_generated: float = 0.0
    current_epoch_revenue: float = 0.0
    
    # Retention metrics
    user_retention_rate: float = 0.0
    avg_user_lifetime_days: float = 0.0
    
    # Enterprise deals
    enterprise_deals_count: int = 0
    enterprise_revenue: float = 0.0
    
    # Commission tracking
    total_commission_earned: float = 0.0
    commission_rate: float = 0.10  # 10% of referred user revenue
    
    def add_referred_user(self, user_hotkey: str):
        """Add a new referred user."""
        if user_hotkey not in self.referred_users:
            self.referred_users.add(user_hotkey)
            self.active_referred_users.add(user_hotkey)
            self.total_users_referred = len(self.referred_users)
    
    def record_user_activity(self, user_hotkey: str, revenue: float):
        """Record activity from a referred user."""
        if user_hotkey in self.referred_users:
            self.active_referred_users.add(user_hotkey)
            self.total_revenue_generated += revenue
            self.current_epoch_revenue += revenue
            
            # Calculate commission
            commission = revenue * self.commission_rate
            self.total_commission_earned += commission
    
    def mark_user_churned(self, user_hotkey: str):
        """Mark a referred user as churned."""
        self.active_referred_users.discard(user_hotkey)
        self._update_retention()
    
    def _update_retention(self):
        """Update retention rate."""
        if self.total_users_referred > 0:
            self.user_retention_rate = len(self.active_referred_users) / self.total_users_referred
    
    def record_enterprise_deal(self, deal_value: float):
        """Record an enterprise deal."""
        self.enterprise_deals_count += 1
        self.enterprise_revenue += deal_value
    
    def to_dict(self) -> dict:
        data = asdict(self)
        # Convert sets to lists for JSON serialization
        data['referred_users'] = list(self.referred_users)
        data['active_referred_users'] = list(self.active_referred_users)
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "ResellerMetrics":
        # Convert lists back to sets
        data['referred_users'] = set(data.get('referred_users', []))
        data['active_referred_users'] = set(data.get('active_referred_users', []))
        return cls(**data)


class ResellerScorer:
    """
    Scores resellers/integrators for the Reseller mechanism.
    
    This scorer evaluates resellers based on:
    1. Number of users referred (40%)
    2. Revenue generated from referrals (35%)
    3. User retention rate (15%)
    4. Enterprise deals (10%)
    
    Scores are used to set weights for mechanism 2 in the
    native Bittensor multi-mechanism system.
    """
    
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Metrics per reseller
        self.metrics: Dict[str, ResellerMetrics] = {}
        
        # User to reseller mapping
        self.user_referrer_map: Dict[str, str] = {}
        
        # Load existing data
        self._load_metrics()
        
        bt.logging.info(
            f"ResellerScorer initialized: "
            f"emission={MECHANISM_RESELLERS.emission_percentage}%"
        )
    
    def get_or_create_metrics(self, reseller_hotkey: str, reseller_uid: int) -> ResellerMetrics:
        """Get existing metrics or create new for a reseller."""
        if reseller_hotkey not in self.metrics:
            self.metrics[reseller_hotkey] = ResellerMetrics(
                reseller_hotkey=reseller_hotkey,
                reseller_uid=reseller_uid,
                registration_timestamp=time.time()
            )
        return self.metrics[reseller_hotkey]
    
    def register_reseller(
        self,
        reseller_hotkey: str,
        reseller_uid: int,
        company_name: Optional[str] = None,
        kyc_verified: bool = False,
    ):
        """Register a new reseller/integrator."""
        metrics = self.get_or_create_metrics(reseller_hotkey, reseller_uid)
        metrics.company_name = company_name
        metrics.kyc_verified = kyc_verified
        
        bt.logging.info(
            f"Registered reseller {reseller_uid}: {company_name or 'Unknown'}"
        )
    
    def record_referral(
        self,
        reseller_hotkey: str,
        reseller_uid: int,
        user_hotkey: str,
    ):
        """Record a user referral."""
        metrics = self.get_or_create_metrics(reseller_hotkey, reseller_uid)
        metrics.add_referred_user(user_hotkey)
        
        # Track user to reseller mapping
        self.user_referrer_map[user_hotkey] = reseller_hotkey
        
        bt.logging.info(
            f"Referral recorded: reseller={reseller_uid}, user={user_hotkey[:16]}..."
        )
    
    def record_user_revenue(self, user_hotkey: str, revenue: float):
        """
        Record revenue from a user and attribute to their reseller.
        
        This is called when any user generates revenue. If the user was
        referred by a reseller, the revenue is attributed to that reseller.
        """
        if user_hotkey in self.user_referrer_map:
            reseller_hotkey = self.user_referrer_map[user_hotkey]
            if reseller_hotkey in self.metrics:
                self.metrics[reseller_hotkey].record_user_activity(user_hotkey, revenue)
                
                bt.logging.debug(
                    f"Revenue attributed: user={user_hotkey[:16]}..., "
                    f"reseller={reseller_hotkey[:16]}..., amount={revenue:.6f}"
                )
    
    def record_enterprise_deal(
        self,
        reseller_hotkey: str,
        reseller_uid: int,
        deal_value: float,
    ):
        """Record an enterprise deal facilitated by a reseller."""
        metrics = self.get_or_create_metrics(reseller_hotkey, reseller_uid)
        metrics.record_enterprise_deal(deal_value)
        
        bt.logging.info(
            f"Enterprise deal: reseller={reseller_uid}, value={deal_value:.2f}"
        )
    
    def calculate_score(self, reseller_hotkey: str) -> float:
        """
        Calculate the reseller score.
        
        Score components:
        - Users referred: 40% weight
        - Revenue generated: 35% weight
        - User retention: 15% weight
        - Enterprise deals: 10% weight
        
        Returns:
            Score between 0.0 and 1.0
        """
        if reseller_hotkey not in self.metrics:
            return 0.0
        
        metrics = self.metrics[reseller_hotkey]
        
        # Get max values for normalization
        all_metrics = list(self.metrics.values())
        
        max_users = max((m.total_users_referred for m in all_metrics), default=1)
        max_revenue = max((m.total_revenue_generated for m in all_metrics), default=1.0)
        max_enterprise = max((m.enterprise_deals_count for m in all_metrics), default=1)
        
        # Users referred score (normalized)
        if max_users > 0:
            users_score = min(1.0, metrics.total_users_referred / max_users)
        else:
            users_score = 0.0
        
        # Revenue score (normalized)
        if max_revenue > 0:
            revenue_score = min(1.0, metrics.total_revenue_generated / max_revenue)
        else:
            revenue_score = 0.0
        
        # Retention score (already 0-1)
        retention_score = metrics.user_retention_rate
        
        # Enterprise score (normalized with bonus)
        if max_enterprise > 0:
            enterprise_score = min(1.0, (metrics.enterprise_deals_count / max_enterprise) * 1.2)
        else:
            enterprise_score = 0.0
        
        # Combined weighted score
        total_score = (
            USERS_REFERRED_WEIGHT * users_score +
            REVENUE_GENERATED_WEIGHT * revenue_score +
            RETENTION_WEIGHT * retention_score +
            ENTERPRISE_WEIGHT * enterprise_score
        )
        
        return min(1.0, max(0.0, total_score))
    
    def calculate_weights(
        self,
        miner_uids: List[int],
        metagraph,
    ) -> np.ndarray:
        """
        Calculate weights for all miners for the Reseller mechanism.
        
        These weights are set via subtensor.set_weights with mechanism_id=2.
        
        Note: Not all miners are resellers. Miners who haven't registered
        as resellers or haven't referred any users will have 0 weight.
        
        Args:
            miner_uids: List of miner UIDs
            metagraph: Network metagraph
            
        Returns:
            Normalized weight array for mechanism 2
        """
        weights = np.zeros(len(miner_uids), dtype=np.float32)
        
        for idx, uid in enumerate(miner_uids):
            try:
                hotkey = metagraph.hotkeys[uid]
                weights[idx] = self.calculate_score(hotkey)
            except (IndexError, KeyError):
                continue
        
        # Normalize weights
        total = np.sum(weights)
        if total > 0:
            weights = weights / total
        
        return weights
    
    def get_reseller_summary(self) -> Dict:
        """Get summary of reseller activity."""
        active_resellers = [m for m in self.metrics.values() if m.total_users_referred > 0]
        
        total_revenue = sum(m.total_revenue_generated for m in self.metrics.values())
        total_users = sum(m.total_users_referred for m in self.metrics.values())
        total_commissions = sum(m.total_commission_earned for m in self.metrics.values())
        
        return {
            "active_resellers": len(active_resellers),
            "total_users_referred": total_users,
            "total_revenue_generated": total_revenue,
            "total_commissions_paid": total_commissions,
            "enterprise_deals": sum(m.enterprise_deals_count for m in self.metrics.values()),
            "top_resellers": sorted(
                [
                    {
                        "hotkey": m.reseller_hotkey[:16] + "...",
                        "company": m.company_name or "Unknown",
                        "users": m.total_users_referred,
                        "revenue": m.total_revenue_generated,
                        "commission": m.total_commission_earned,
                    }
                    for m in self.metrics.values()
                    if m.total_users_referred > 0
                ],
                key=lambda x: x["revenue"],
                reverse=True
            )[:10]
        }
    
    def _save_metrics(self):
        """Save metrics to disk."""
        data = {
            "resellers": {
                hotkey: metrics.to_dict()
                for hotkey, metrics in self.metrics.items()
            },
            "user_referrer_map": self.user_referrer_map,
        }
        
        filepath = self.storage_path / "reseller_metrics.json"
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_metrics(self):
        """Load metrics from disk."""
        filepath = self.storage_path / "reseller_metrics.json"
        if filepath.exists():
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                
                for hotkey, metrics_data in data.get("resellers", {}).items():
                    self.metrics[hotkey] = ResellerMetrics.from_dict(metrics_data)
                
                self.user_referrer_map = data.get("user_referrer_map", {})
                
                bt.logging.info(f"Loaded reseller metrics for {len(self.metrics)} resellers")
            except Exception as e:
                bt.logging.warning(f"Could not load reseller metrics: {e}")
    
    def finalize_epoch(self, epoch: int):
        """Finalize epoch and reset epoch-specific counters."""
        summary = self.get_reseller_summary()
        
        bt.logging.info(
            f"Reseller Epoch {epoch} Summary:\n"
            f"  Active Resellers: {summary['active_resellers']}\n"
            f"  Total Users Referred: {summary['total_users_referred']}\n"
            f"  Revenue Generated: ${summary['total_revenue_generated']:.4f}\n"
            f"  Commissions Paid: ${summary['total_commissions_paid']:.4f}"
        )
        
        # Reset epoch revenue counters
        for metrics in self.metrics.values():
            metrics.current_epoch_revenue = 0.0
        
        self._save_metrics()

