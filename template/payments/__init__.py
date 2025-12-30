# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
KubeTEE AI Payment System

Multi-chain payment infrastructure supporting:

1. BITTENSOR NATIVE (Primary for subnet operations):
   - KubeTEE α token emissions (Infrastructure + Open Source)
   - KubeTEEPayment.sol for reseller epoch settlements
   - On-chain validator consensus

2. BASE L2 (Primary for retail/micropayments):
   - wKUBETEE wrapped token
   - x402 Protocol for HTTP micropayments
   - ERC-8004 for AI agent payments
   - Uniswap V3 liquidity

═══════════════════════════════════════════════════════════════════════════════
                         WHY BASE?
═══════════════════════════════════════════════════════════════════════════════

1. x402 Protocol Native Support
   - HTTP 402 Payment Required for micropayments
   - Coinbase and Cloudflare are facilitators
   - 10.5M+ cumulative transactions

2. Coinbase Distribution
   - 100M+ users with direct access
   - No bridge friction for retail

3. AI/Agent Ecosystem
   - Virtuals Protocol, agent projects chose BASE
   - Growing AI x Crypto mindshare

4. Deep DeFi Liquidity
   - 46% of L2 DeFi TVL
   - Aerodrome, Uniswap V3

═══════════════════════════════════════════════════════════════════════════════
                         PAYMENT MODELS
═══════════════════════════════════════════════════════════════════════════════

┌──────────────────┬────────────────────┬─────────────────────────────────────┐
│     Model        │      Network       │           Best For                  │
├──────────────────┼────────────────────┼─────────────────────────────────────┤
│ Emissions        │ Bittensor Subnet   │ Miners (infrastructure + code)      │
│ Reseller Epoch   │ Bittensor EVM      │ B2B wholesale, enterprise           │
│ x402 Micropay    │ BASE L2            │ AI agents, developers, retail       │
│ ERC-8004 Agents  │ BASE L2            │ Autonomous AI-to-AI transactions    │
└──────────────────┴────────────────────┴─────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                         FUTURE ROADMAP
═══════════════════════════════════════════════════════════════════════════════

Phase 1 (Now): Bittensor native emissions + reseller epoch payments
Phase 2: Deploy wKUBETEE on BASE, Uniswap liquidity
Phase 3: x402 Protocol integration for API micropayments
Phase 4: ERC-8004 agent marketplace registration

Reference:
- x402: https://www.x402.org/
- ERC-8004: https://www.erc8021.com/
- BASE: https://base.org/
"""

from .x402 import (
    X402Config,
    X402Server,
    PaymentRequest,
    PaymentAuthorization,
    SupportedNetwork,
    SupportedToken,
    x402_paywall,
    estimate_cost,
)

__all__ = [
    "X402Config",
    "X402Server",
    "PaymentRequest",
    "PaymentAuthorization",
    "SupportedNetwork",
    "SupportedToken",
    "x402_paywall",
    "estimate_cost",
]

