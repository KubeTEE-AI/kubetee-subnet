# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
KubeTEE AI Multi-Mechanism Incentive System

This module implements the native Bittensor Multiple Incentive Mechanisms feature
as documented at: https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets

═══════════════════════════════════════════════════════════════════════════════
                     EMISSION MECHANISMS (2 Total - On-Chain)
═══════════════════════════════════════════════════════════════════════════════

1. INFRASTRUCTURE (Mechanism 0) - 60% of emissions
   - Rewards miners for providing Kubernetes infrastructure
   - Metrics: uptime, TEE compliance, capacity, latency
   - Miners can ALSO be open source contributors

2. OPEN_SOURCE (Mechanism 1) - 40% of emissions
   - Rewards miners for improving the subnet tech stack
   - Metrics: benchmark scores, code quality, CI/CD compliance
   - Competition-based: best improvements get highest rewards

═══════════════════════════════════════════════════════════════════════════════
                     RESELLERS (NO Emissions - On-Chain Payments)
═══════════════════════════════════════════════════════════════════════════════

Resellers are a special category of "miners" that:
- Do NOT receive emissions
- Do NOT register on the Bittensor subnet
- DO register via KubeTEE CLI → Rancher account
- DO deposit Alpha/TAO to on-chain contract
- Validators calculate usage and transfer each epoch

See template/reseller/onchain.py for the on-chain payment system.

═══════════════════════════════════════════════════════════════════════════════

Each emission mechanism has:
- Independent weight matrix (validators set weights per mechanism)
- Separate bond pools (independent Yuma Consensus)
- Configurable emission split (on-chain transparency)
"""

from .definitions import (
    MechanismType,
    MechanismConfig,
    MECHANISM_INFRASTRUCTURE,
    MECHANISM_OPEN_SOURCE,
    MECHANISM_RESELLERS,
    EMISSION_MECHANISMS,
    ALL_MECHANISMS,
    MECHANISMS,  # Alias for EMISSION_MECHANISMS
    get_mechanism_by_id,
    get_emission_split_vector,
    DEFAULT_EMISSION_SPLITS,
)

from .infrastructure import (
    InfrastructureScorer,
    InfrastructureMetrics,
)

from .open_source import (
    OpenSourceScorer,
    OpenSourceMetrics,
)

from .bounty_system import (
    BountyManager,
    Bounty,
    BountyStatus,
    BountyDifficulty,
    BountyCategory,
    Contribution,
    ContributionType,
    MinerContributionProfile,
    BOUNTY_POOL_SHARE,
    CONTINUOUS_SHARE,
    BENCHMARK_BONUS_SHARE,
)

from .bounty_validator import (
    BountyValidationService,
    AICodeAnalyzer,
    GitHubCIRunner,
    BitsecSecurityScanner,
    CITestResult,
    AIAnalysisResult,
    BenchmarkResult,
    BitsecSecurityResult,
)

from .resellers import (
    ResellerScorer,
    ResellerMetrics,
)

from .manager import (
    MechanismManager,
)

__all__ = [
    # Definitions
    "MechanismType",
    "MechanismConfig",
    "MECHANISM_INFRASTRUCTURE",
    "MECHANISM_OPEN_SOURCE", 
    "MECHANISM_RESELLERS",
    "EMISSION_MECHANISMS",
    "ALL_MECHANISMS",
    "MECHANISMS",  # Alias for backward compat
    "get_mechanism_by_id",
    "get_emission_split_vector",
    "DEFAULT_EMISSION_SPLITS",
    # Scorers
    "InfrastructureScorer",
    "InfrastructureMetrics",
    "OpenSourceScorer",
    "OpenSourceMetrics",
    "ResellerScorer",
    "ResellerMetrics",
    # Bounty System
    "BountyManager",
    "Bounty",
    "BountyStatus",
    "BountyDifficulty",
    "BountyCategory",
    "Contribution",
    "ContributionType",
    "MinerContributionProfile",
    "BOUNTY_POOL_SHARE",
    "CONTINUOUS_SHARE",
    "BENCHMARK_BONUS_SHARE",
    # Bounty Validator (Automated)
    "BountyValidationService",
    "AICodeAnalyzer",
    "GitHubCIRunner",
    "BitsecSecurityScanner",
    "CITestResult",
    "AIAnalysisResult",
    "BenchmarkResult",
    "BitsecSecurityResult",
    # Manager
    "MechanismManager",
]

