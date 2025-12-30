# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
Mechanism Definitions for KubeTEE AI Subnet

Defines the 3 incentive mechanisms using native Bittensor multi-mechanism support.
Reference: https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets

Emission Split Calculation:
- The proportion is calculated as: value / 65535
- Example: [32767, 19661, 13107] = 50%, 30%, 20%
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import List, Dict, Optional
import bittensor as bt


# Maximum value for emission split (used for percentage calculation)
EMISSION_SPLIT_MAX = 65535


class MechanismType(IntEnum):
    """
    KubeTEE AI Incentive Mechanism Types.
    
    ONLY 2 MECHANISMS USE EMISSIONS (on-chain, registered miners):
    - INFRASTRUCTURE (60%): Miners providing Kubernetes infrastructure
    - OPEN_SOURCE (40%): Miners contributing code improvements
    
    REFERRERS are a special category (NO EMISSIONS):
    - Do NOT receive emissions
    - Do NOT register on Bittensor subnet
    - Register via KubeTEE CLI → Get referral code
    - Refer users who pay SAME retail price as direct users
    - Earn 50% revenue share from referred users' spend
    
    Each emission mechanism has:
    - Weight matrix (validators set weights per miner per mechanism)
    - Bond pool (separate Yuma Consensus calculations)
    - Emission allocation (configured via sudo_set_mechanism_emission_split)
    """
    INFRASTRUCTURE = 0  # Infrastructure provision rewards (EMISSIONS)
    OPEN_SOURCE = 1     # Open source competition rewards (EMISSIONS)
    REFERRERS = 2       # Referrer/Integrator/Reseller (NO EMISSIONS - revenue share)


@dataclass
class MechanismConfig:
    """Configuration for a single incentive mechanism."""
    
    # Mechanism identification
    mechanism_id: int
    mechanism_type: MechanismType
    name: str
    description: str
    
    # Emission allocation (percentage, must sum to 100 across all mechanisms)
    emission_percentage: float
    
    # Revenue sharing (for Infrastructure mechanism)
    miner_revenue_share: float = 0.0  # 0.0 - 1.0
    
    # Scoring parameters
    weight_update_interval: int = 100  # blocks between weight updates
    min_score_threshold: float = 0.01  # minimum score to receive rewards
    
    def get_emission_split_value(self) -> int:
        """
        Calculate the emission split value for Bittensor extrinsic.
        
        The sudo_set_mechanism_emission_split extrinsic accepts values
        where the proportion is calculated as: value / 65535
        """
        return int(self.emission_percentage / 100.0 * EMISSION_SPLIT_MAX)
    
    def __str__(self) -> str:
        return (
            f"Mechanism {self.mechanism_id}: {self.name} "
            f"({self.emission_percentage}% emissions)"
        )


# ============================================================================
# MECHANISM DEFINITIONS
# ============================================================================

MECHANISM_INFRASTRUCTURE = MechanismConfig(
    mechanism_id=0,
    mechanism_type=MechanismType.INFRASTRUCTURE,
    name="Infrastructure",
    description="""
    Rewards miners for providing Kubernetes infrastructure to serve user requests.
    
    TWO REVENUE STREAMS:
    1. EMISSIONS (60% of subnet emissions)
       - Based on uptime, TEE compliance, latency, capacity
       - Requires subnet registration
    
    2. DIRECT PAYMENTS (from wholesale system)
       - Miners get 50% of wholesale price for reseller requests
       - Does NOT require subnet registration
       - Just need hotkey/coldkey with Alpha
    
    Evaluation Criteria for Emissions:
    - Uptime percentage (target: 99.9%+)
    - TEE compliance (Intel TDX/SGX, AMD SEV, NVIDIA CC)
    - FIPS-140-2 certification
    - Response latency
    - GPU/CPU capacity and availability
    """,
    emission_percentage=60.0,  # 60% of subnet emissions (increased from 50%)
    miner_revenue_share=0.50,  # Miners get 50% of wholesale payments
    weight_update_interval=100,
    min_score_threshold=0.01,
)

MECHANISM_OPEN_SOURCE = MechanismConfig(
    mechanism_id=1,
    mechanism_type=MechanismType.OPEN_SOURCE,
    name="Open Source Competition",
    description="""
    Rewards miners for improving the KubeTEE tech stack and NVIDIA Blueprints.
    
    EMISSIONS ONLY (40% of subnet emissions)
    
    Evaluation Criteria:
    - Benchmark performance scores (DeepResearch Bench, etc.)
    - Code quality via AI analysis
    - CI/CD pipeline compliance
    - Security vulnerability fixes
    - Feature contributions
    - Documentation improvements
    
    Competition Model:
    - Miners fork KubeTEE Blueprints repositories
    - Submit improvements via staging branch
    - Best improvements (highest benchmark gains) get highest rewards
    - Permissionless participation
    """,
    emission_percentage=40.0,  # 40% of subnet emissions (increased from 30%)
    miner_revenue_share=0.0,   # Competition-based, no direct revenue share
    weight_update_interval=360,  # Evaluate less frequently (code changes)
    min_score_threshold=0.05,
)

MECHANISM_REFERRERS = MechanismConfig(
    mechanism_id=2,
    mechanism_type=MechanismType.REFERRERS,
    name="Referrers (50% Revenue Share)",
    description="""
    REFERRAL REVENUE SHARE MODEL - NO EMISSIONS USED!
    
    UNIFIED PRICING + 50% REVENUE SHARE FOR REFERRERS!
    
    How it works:
    - ALL users pay the SAME retail price (direct or via referrer)
    - Referrers earn 50% of revenue from users they bring in
    - Simple, transparent, and fair for everyone
    
    Referrer Types:
    - Affiliate: Refers users via referral link/code
    - Integrator: Embeds KubeTEE into their product (API)
    - White-Label: Rebrands KubeTEE for their customers
    
    What Referrers DON'T need:
    - Kubernetes infrastructure
    - GPU/CPU resources
    - Technical operations
    - Subnet registration
    
    They ONLY need:
    - Hotkey/Coldkey for identity
    - Payout wallet address (USDC on BASE)
    - Users/customers to refer
    
    Revenue Flow:
    - User pays retail price (same as direct users)
    - 50% goes to KubeTEE Owner
    - 50% goes to Referrer who brought the user
    
    Benefits:
    - Same price for everyone → No customer confusion
    - Referrers get passive income → Strong incentive to promote
    - Simple tracking → On-chain attribution
    - Win-win-win → Users, referrers, and subnet all benefit
    """,
    emission_percentage=0.0,   # NO emissions - revenue share model
    miner_revenue_share=0.50,  # Referrers get 50% of referred user revenue
    weight_update_interval=0,  # Not using weight-based emissions
    min_score_threshold=0.0,
)


# EMISSION mechanisms only (for Bittensor subnet registration)
EMISSION_MECHANISMS: List[MechanismConfig] = [
    MECHANISM_INFRASTRUCTURE,
    MECHANISM_OPEN_SOURCE,
]

# All mechanisms including referrers (for reference)
ALL_MECHANISMS: List[MechanismConfig] = [
    MECHANISM_INFRASTRUCTURE,
    MECHANISM_OPEN_SOURCE,
    MECHANISM_REFERRERS,  # No emissions - revenue share model
]

# Alias for backward compatibility
MECHANISMS = EMISSION_MECHANISMS

# Default emission splits (percentages)
# NOTE: Referrers use revenue share model, NOT emissions!
# Only Infrastructure and Open Source use emissions.
DEFAULT_EMISSION_SPLITS: Dict[MechanismType, float] = {
    MechanismType.INFRASTRUCTURE: 60.0,  # 60% of emissions
    MechanismType.OPEN_SOURCE: 40.0,     # 40% of emissions
    MechanismType.REFERRERS: 0.0,        # NO emissions - 50% revenue share model
}


def get_mechanism_by_id(mechanism_id: int) -> Optional[MechanismConfig]:
    """Get mechanism configuration by ID."""
    for mechanism in MECHANISMS:
        if mechanism.mechanism_id == mechanism_id:
            return mechanism
    return None


def get_mechanism_by_type(mechanism_type: MechanismType) -> Optional[MechanismConfig]:
    """Get mechanism configuration by type."""
    for mechanism in MECHANISMS:
        if mechanism.mechanism_type == mechanism_type:
            return mechanism
    return None


def get_emission_split_vector() -> List[int]:
    """
    Get the emission split vector for sudo_set_mechanism_emission_split extrinsic.
    
    Returns a vector where each value represents the proportion of emissions
    for that mechanism, calculated as: value / 65535
    
    Example: [32767, 19661, 13107] = 50%, 30%, 20%
    
    Reference: https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets
    """
    return [mechanism.get_emission_split_value() for mechanism in MECHANISMS]


def validate_emission_splits() -> bool:
    """
    Validate that emission splits sum to 100%.
    
    The Bittensor extrinsic will reject if proportions don't sum to 100%.
    """
    total = sum(mechanism.emission_percentage for mechanism in MECHANISMS)
    if abs(total - 100.0) > 0.01:
        bt.logging.error(
            f"Emission splits must sum to 100%, got {total}%"
        )
        return False
    return True


def log_mechanism_config():
    """Log the current mechanism configuration."""
    bt.logging.info("=" * 60)
    bt.logging.info("KubeTEE AI Multi-Mechanism Configuration")
    bt.logging.info("=" * 60)
    
    for mechanism in MECHANISMS:
        bt.logging.info(f"\n{mechanism}")
        bt.logging.info(f"  Description: {mechanism.description.strip().split(chr(10))[0]}")
        if mechanism.miner_revenue_share > 0:
            bt.logging.info(f"  Miner Revenue Share: {mechanism.miner_revenue_share * 100}%")
    
    bt.logging.info(f"\nEmission Split Vector: {get_emission_split_vector()}")
    bt.logging.info("=" * 60)

