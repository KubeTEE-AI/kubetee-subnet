"""
KubeTEE - GitHub Linking Feature Package

This package provides the core functionality for the KubeTEE subnet's
GitHub linking feature, enabling developers to link their GitHub accounts
to their Bittensor wallets for open-source contribution tracking and rewards.

Subpackages:
    - cli: Command-line interface tools for GitHub linking
    - api: REST API endpoints for the linking service
    - validator: Validator-side logic for verifying GitHub contributions
    - miner: Miner-side implementation for processing link requests
    - contracts: Smart contracts for on-chain verification (Hardhat project)
"""

__version__ = "0.1.0"
__author__ = "KubeTEE Team"

from kubetee import cli, api, validator, miner

__all__ = ["cli", "api", "validator", "miner", "__version__"]
