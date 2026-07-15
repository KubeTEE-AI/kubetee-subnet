# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
KubeTEE AI Referrer System (50% Revenue Share - NO Emissions)

═══════════════════════════════════════════════════════════════════════════════
                    UNIFIED PRICING + REFERRAL REVENUE SHARE MODEL
═══════════════════════════════════════════════════════════════════════════════

KEY PRINCIPLE: All users pay the SAME retail price!
- Direct users: 100% goes to KubeTEE
- Referred users: 50% to KubeTEE, 50% to Referrer

Referrers are partners that:
- Do NOT receive emissions
- Do NOT register on the Bittensor subnet on-chain
- DO register via Rancher Fleet → Get unique referral code
- DO receive 50% of revenue from users they refer

═══════════════════════════════════════════════════════════════════════════════
                         ARCHITECTURE OVERVIEW
═══════════════════════════════════════════════════════════════════════════════

                         EMISSION MECHANISMS (On-Chain Subnet)
┌─────────────────────────────────────────────────────────────────────────────┐
│  MECHANISM 0: INFRASTRUCTURE (60%)     MECHANISM 1: OPEN SOURCE (40%)       │
│  - Miners with K8s infrastructure      - Miners improving tech stack        │
│  - Registered on Bittensor subnet      - Registered on Bittensor subnet     │
│  - Earn emissions based on uptime      - Earn emissions based on PRs        │
└─────────────────────────────────────────────────────────────────────────────┘

                        REFERRER SYSTEM (50% Revenue Share - NO Emissions)
┌─────────────────────────────────────────────────────────────────────────────┐
│  REFERRERS / INTEGRATORS / WHITE LABEL                                      │
│  - NOT registered on Bittensor subnet (no emissions)                        │
│  - Register via Rancher Fleet → Get referral code                           │
│  - Refer users who pay SAME retail price                                    │
│  - Earn 50% of referred users' spend (USDC on BASE)                        │
│  - Automatic payouts per epoch                                              │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                              REFERRER TYPES
═══════════════════════════════════════════════════════════════════════════════

1. AFFILIATE: Refers users via referral link/code
   - Content creators, influencers, community members

2. INTEGRATOR: Embeds KubeTEE into their product via API
   - SaaS companies, AI platforms, dev tools
   - Uses X-KubeTEE-Referrer header for attribution

3. WHITE-LABEL: Rebrands KubeTEE for their customers
   - Enterprise resellers, agencies
   - Full API access with custom branding

All types earn the same 50% revenue share!

═══════════════════════════════════════════════════════════════════════════════
                              REFERRER FLOW
═══════════════════════════════════════════════════════════════════════════════

1. REFERRER REGISTRATION:
   kubetee referrer register --name "My Company" --payout-address 0x...
   └── Creates referrer account
   └── Generates unique referral code/link

2. SHARE REFERRAL:
   └── Link: https://kubetee.ai/signup?ref=ABC123
   └── API header: X-KubeTEE-Referrer: ABC123

3. USER SIGNS UP & USES SERVICES:
   └── User pays SAME retail price as direct users
   └── Attribution tracked on-chain (permanent)

4. REVENUE DISTRIBUTION (per transaction):
   └── 50% → KubeTEE Owner
   └── 50% → Referrer payout address

5. CHECK EARNINGS:
   kubetee referrer earnings
   └── Shows: Referred Users, Total Revenue, Your Share, Pending Payout

6. WITHDRAW:
   kubetee referrer withdraw
   └── USDC sent to payout address (manual or auto)

═══════════════════════════════════════════════════════════════════════════════
                        FUTURE PAYMENT PROTOCOLS
═══════════════════════════════════════════════════════════════════════════════

- ERC-8004 (Decentralized Paymaster) - gasless transactions
- x.402 (HTTP 402 Payment Required) - per-request micropayments

Reference for BASE L2:
https://docs.base.org/
"""

# Referral revenue share system (primary)
from .referral import (
    ReferralManager,
    ReferrerAccount,
    ReferrerType,
    ReferrerStatus,
    UserAttribution,
    RetailPricing,
    SubscriptionPlan,
    SUBSCRIPTION_PLANS,
    PLAN_BASIC,
    PLAN_PROFESSIONAL,
    PLAN_ENTERPRISE,
    H200_HOURLY_RATE,
    REFERRER_REVENUE_SHARE,
    generate_referrer_code,
)

# On-chain payment system
from .onchain import (
    OnChainClient,
    OnChainConfig,
    ResellerInfo,
    EpochUsageReport,
    ValidatorEpochProcessor,
    cli_register_reseller,
    cli_deposit,
    cli_balance,
)

# Legacy off-chain system (for migration/fallback)
from .wholesale import (
    WholesaleManager,
    ResellerAccount as LegacyResellerAccount,
    MinerProvider,
    WholesalePricing,
    WHOLESALE_DISCOUNT,
    MINER_REVENUE_SHARE,
)

from .credits import (
    CreditTracker,
    CreditTransaction,
    TransactionType,
)

__all__ = [
    # Referral system (primary)
    "ReferralManager",
    "ReferrerAccount",
    "ReferrerType",
    "ReferrerStatus",
    "UserAttribution",
    "RetailPricing",
    "SubscriptionPlan",
    "SUBSCRIPTION_PLANS",
    "PLAN_BASIC",
    "PLAN_PROFESSIONAL",
    "PLAN_ENTERPRISE",
    "H200_HOURLY_RATE",
    "REFERRER_REVENUE_SHARE",
    "generate_referrer_code",
    # On-chain
    "OnChainClient",
    "OnChainConfig",
    "ResellerInfo",
    "EpochUsageReport",
    "ValidatorEpochProcessor",
    "cli_register_reseller",
    "cli_deposit",
    "cli_balance",
    # Legacy off-chain
    "WholesaleManager",
    "LegacyResellerAccount",
    "MinerProvider",
    "WholesalePricing",
    "WHOLESALE_DISCOUNT",
    "MINER_REVENUE_SHARE",
    "CreditTracker",
    "CreditTransaction",
    "TransactionType",
]

