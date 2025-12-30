# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
KubeTEE CLI

Command-line interface for KubeTEE AI subnet operations.

═══════════════════════════════════════════════════════════════════════════════
                              COMMANDS
═══════════════════════════════════════════════════════════════════════════════

# Reseller Commands (USDC on BASE)
kubetee reseller register --namespace my-company --name "My Company"
kubetee reseller deposit 100
kubetee reseller balance
kubetee reseller withdraw 50
kubetee reseller status

# Wallet Commands
kubetee wallet create
kubetee wallet import --private-key <key>
kubetee wallet balance

# API Commands
kubetee api status
kubetee api inference "What is Bittensor?"

═══════════════════════════════════════════════════════════════════════════════
"""

from .reseller import ResellerCLI, main as reseller_main

__all__ = [
    "ResellerCLI",
    "reseller_main",
]

