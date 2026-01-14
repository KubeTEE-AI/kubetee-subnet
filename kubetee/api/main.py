"""
KubeTEE API - Local Development Server.

Run the GitHub linking API locally for testing.

Usage:
    python -m kubetee.api.main
    # or
    python kubetee/api/main.py

    # With custom port
    python -m kubetee.api.main --port 8080

    # With mock mode (no blockchain, no GitHub API calls)
    python -m kubetee.api.main --mock

Environment Variables:
    RPC_URL - Ethereum RPC URL (default: http://localhost:8545)
    GITHUB_REGISTRY_CONTRACT_ADDRESS - Contract address
    VALIDATOR_PRIVATE_KEY - Private key for signing transactions
    GITHUB_TOKEN - GitHub API token for higher rate limits
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kubetee.api.github import router as github_router, ValidatorContext

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def create_app(mock_mode: bool = False) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        mock_mode: If True, use mock dependencies for testing.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="KubeTEE GitHub Linking API",
        description="""
API for linking Bittensor hotkeys to GitHub accounts.

## Overview

This API allows miners on KubeTEE (Subnet 62) to link their Bittensor
hotkey to their GitHub account. This enables participation in:

- **Open Source Mechanism**: Earn rewards for code contributions
- **Bounty System**: Claim bounties for completing GitHub issues

## Authentication Flow

1. Create a public GitHub gist with a `HOTKEY.md` file
2. Sign a message with your Bittensor hotkey
3. Submit the link request with gist URL and signature
4. Validator verifies ownership and writes to blockchain

## Verification Checks

The API performs 6 verification checks:
- [A] Hotkey is registered on subnet 62
- [B] Signature is valid (signed by claimed hotkey)
- [C] Gist exists and is public
- [D] HOTKEY.md contains valid hotkey format
- [E] All hotkeys match (claimed, signed, gist)
- [F] GitHub user exists
        """,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Add CORS middleware for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(github_router)

    # Root endpoint
    @app.get("/", tags=["root"])
    async def root():
        """API root - returns basic info."""
        return {
            "name": "KubeTEE GitHub Linking API",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/api/github/health",
            "mock_mode": mock_mode,
        }

    return app


class MockSubtensor:
    """Mock subtensor for local testing."""

    def __init__(self, registered_hotkeys: Optional[list] = None):
        """
        Initialize mock subtensor.

        Args:
            registered_hotkeys: List of hotkeys to consider as registered.
                              If None, all hotkeys are considered registered.
        """
        self.registered_hotkeys = registered_hotkeys

    def get_uid_for_hotkey_on_subnet(
        self, hotkey_ss58: str, netuid: int
    ) -> Optional[int]:
        """Mock method - returns UID if hotkey is in registered list."""
        if self.registered_hotkeys is None:
            # All hotkeys are registered in permissive mode
            return 1
        if hotkey_ss58 in self.registered_hotkeys:
            return self.registered_hotkeys.index(hotkey_ss58)
        return None


class MockGitHubRegistry:
    """Mock registry for local testing (no blockchain writes)."""

    def __init__(self):
        self._cache = {}
        self._events_loaded = True

    def get_github(self, hotkey: str, mechanism_id: int = 0) -> Optional[str]:
        """Get cached GitHub username."""
        return self._cache.get(hotkey, {}).get(mechanism_id)

    def is_linked(self, hotkey: str, mechanism_id: int = 0) -> bool:
        """Check if hotkey is linked."""
        return self.get_github(hotkey, mechanism_id) is not None

    async def link_github(
        self,
        hotkey: str,
        mechanism_id: int,
        github_username: str,
        validator_private_key: str,
        **kwargs,
    ) -> tuple:
        """Mock link - just updates cache, no blockchain write."""
        existing = self.get_github(hotkey, mechanism_id)

        if existing == github_username:
            return (None, "unchanged")

        status = "created" if existing is None else "updated"

        if hotkey not in self._cache:
            self._cache[hotkey] = {}
        self._cache[hotkey][mechanism_id] = github_username

        # Return mock tx hash
        mock_tx = f"0xmock_{hotkey[:8]}_{mechanism_id}_{github_username[:8]}"
        logger.info(f"[MOCK] Link {status}: {hotkey[:16]}... -> {github_username}")

        return (mock_tx, status)


class MockGitHubVerifier:
    """Mock verifier for local testing."""

    def __init__(self, always_pass: bool = False):
        """
        Initialize mock verifier.

        Args:
            always_pass: If True, all verifications pass.
        """
        self.always_pass = always_pass

    async def verify_link_request(
        self,
        claimed_hotkey: str,
        gist_url: str,
        message: str,
        signature: str,
        subtensor: Any,
        netuid: int,
    ):
        """
        Mock verification - performs real validation but with configurable bypass.
        """
        from kubetee.validator.github_verifier import (
            GitHubVerifier,
            VerificationResult,
        )

        if self.always_pass:
            # Extract username from gist URL for mock
            import re
            match = re.search(r"gist\.github\.com/([^/]+)/", gist_url)
            username = match.group(1) if match else "mock_user"

            logger.info(f"[MOCK] Verification bypassed for {claimed_hotkey[:16]}...")
            return VerificationResult(success=True, github_username=username)

        # Use real verifier for actual validation
        real_verifier = GitHubVerifier()
        return await real_verifier.verify_link_request(
            claimed_hotkey=claimed_hotkey,
            gist_url=gist_url,
            message=message,
            signature=signature,
            subtensor=subtensor,
            netuid=netuid,
        )


def setup_mock_context(always_pass: bool = False) -> ValidatorContext:
    """
    Set up ValidatorContext with mock dependencies.

    Args:
        always_pass: If True, all verifications pass automatically.

    Returns:
        Configured ValidatorContext.
    """
    logger.info("Setting up mock context for local testing...")

    context = ValidatorContext.configure(
        subtensor=MockSubtensor(),
        netuid=62,
        registry=MockGitHubRegistry(),
        verifier=MockGitHubVerifier(always_pass=always_pass),
        validator_private_key="0x" + "1" * 64,  # Mock private key
    )

    logger.info("Mock context configured successfully")
    return context


def setup_real_context() -> ValidatorContext:
    """
    Set up ValidatorContext with real dependencies from environment.

    Returns:
        Configured ValidatorContext.

    Raises:
        ValueError: If required environment variables are missing.
    """
    from kubetee.validator.github_registry import create_github_registry
    from kubetee.validator.github_verifier import GitHubVerifier

    logger.info("Setting up real context from environment...")

    # Get required environment variables
    rpc_url = os.environ.get("RPC_URL", "http://localhost:8545")
    contract_address = os.environ.get("GITHUB_REGISTRY_CONTRACT_ADDRESS")
    validator_private_key = os.environ.get("VALIDATOR_PRIVATE_KEY")
    github_token = os.environ.get("GITHUB_TOKEN")

    if not contract_address:
        raise ValueError(
            "GITHUB_REGISTRY_CONTRACT_ADDRESS environment variable is required"
        )

    if not validator_private_key:
        raise ValueError("VALIDATOR_PRIVATE_KEY environment variable is required")

    # Create registry
    registry = create_github_registry(
        rpc_url=rpc_url,
        contract_address=contract_address,
    )

    # Create verifier
    verifier = GitHubVerifier(github_token=github_token)

    # For real context, we need a real subtensor
    # In local dev, we might not have one, so create a mock
    logger.warning(
        "Using mock subtensor - hotkey registration checks will be permissive"
    )
    subtensor = MockSubtensor()

    context = ValidatorContext.configure(
        subtensor=subtensor,
        netuid=62,
        registry=registry,
        verifier=verifier,
        validator_private_key=validator_private_key,
    )

    logger.info(f"Real context configured: RPC={rpc_url}, Contract={contract_address}")
    return context


async def load_events_if_needed(context: ValidatorContext):
    """Load contract events into cache if using real registry."""
    from kubetee.validator.github_registry import GitHubRegistry

    if isinstance(context.registry, GitHubRegistry):
        logger.info("Loading events from contract...")
        count = await context.registry.load_events_on_startup()
        logger.info(f"Loaded {count} events into cache")


def main():
    """Main entry point for the API server."""
    parser = argparse.ArgumentParser(
        description="KubeTEE GitHub Linking API Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with mock mode (no blockchain, permissive validation)
    python -m kubetee.api.main --mock

    # Run with real dependencies from environment
    export RPC_URL=http://localhost:8545
    export GITHUB_REGISTRY_CONTRACT_ADDRESS=0x...
    export VALIDATOR_PRIVATE_KEY=0x...
    python -m kubetee.api.main

    # Run with auto-pass mode (all verifications pass)
    python -m kubetee.api.main --mock --auto-pass
        """,
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock dependencies (no blockchain, no real GitHub API)",
    )
    parser.add_argument(
        "--auto-pass",
        action="store_true",
        help="Auto-pass all verifications (use with --mock for quick testing)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Create app
    app = create_app(mock_mode=args.mock)

    # Setup context
    if args.mock:
        context = setup_mock_context(always_pass=args.auto_pass)
    else:
        try:
            context = setup_real_context()
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            logger.info("Tip: Use --mock flag for local testing without blockchain")
            sys.exit(1)

    # Load events on startup
    @app.on_event("startup")
    async def startup_event():
        await load_events_if_needed(context)
        logger.info(f"API server ready at http://{args.host}:{args.port}")
        logger.info(f"API docs at http://{args.host}:{args.port}/docs")

    # Run server
    logger.info(f"Starting KubeTEE API server on {args.host}:{args.port}...")
    logger.info(f"Mock mode: {args.mock}, Auto-pass: {args.auto_pass}")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
