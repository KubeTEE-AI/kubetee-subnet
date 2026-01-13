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

# Lazy imports to avoid loading heavy dependencies for CLI usage


def __getattr__(name: str):
    """Lazy import submodules on first access."""
    if name == "cli":
        from kubetee import cli as _cli

        return _cli
    if name == "api":
        from kubetee import api as _api

        return _api
    if name == "validator":
        from kubetee import validator as _validator

        return _validator
    if name == "miner":
        from kubetee import miner as _miner

        return _miner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["cli", "api", "validator", "miner", "__version__"]
