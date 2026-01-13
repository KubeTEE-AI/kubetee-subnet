"""
KubeTEE API Module

REST API endpoints for the GitHub linking service.
Provides endpoints for:
    - GitHub OAuth callback handling
    - Link verification and status queries
    - Challenge generation and signature verification
    - Contribution metrics retrieval

The API is built with FastAPI and integrates with:
    - GitHub OAuth2 for authentication
    - Bittensor wallet verification
    - On-chain smart contract interactions
"""

from kubetee.api.github import (
    router as github_router,
    LinkGitHubRequest,
    LinkGitHubResponse,
    ValidatorContext,
)

__all__ = [
    "github_router",
    "LinkGitHubRequest",
    "LinkGitHubResponse",
    "ValidatorContext",
]
