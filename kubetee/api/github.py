"""
GitHub Linking API Endpoints for KubeTEE Subnet.

Provides REST API endpoints for miners to link their Bittensor hotkey
to their GitHub account. The endpoint performs validation and writes
verified links to the smart contract.

Endpoint:
    POST /api/github/link - Link a hotkey to GitHub account
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from kubetee.validator.github_verifier import GitHubVerifier, VerificationResult
from kubetee.validator.github_registry import GitHubRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/github", tags=["github"])


class LinkGitHubRequest(BaseModel):
    """Request body for the GitHub link endpoint."""
    
    hotkey: str = Field(
        ...,
        min_length=48,
        max_length=48,
        pattern=r"^5[A-Za-z0-9]{47}$",
        description="SS58 hotkey address starting with 5 (48 characters)",
        examples=["5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"]
    )
    mechanism_id: int = Field(
        ...,
        ge=0,
        le=10,
        description="Mechanism ID (0=infra, 1=opensource, 2=referral, 3=bounty)"
    )
    gist_url: str = Field(
        ...,
        min_length=30,
        pattern=r"^https?://gist\.github\.com/[^/]+/[a-f0-9]+$",
        description="URL to public gist containing HOTKEY.md file",
        examples=["https://gist.github.com/octocat/abc123def456"]
    )
    message: str = Field(
        ...,
        min_length=10,
        description="JSON message containing hotkey and timestamp",
        examples=['{"hotkey":"5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY","timestamp":1234567890}']
    )
    signature: str = Field(
        ...,
        min_length=64,
        pattern=r"^(0x)?[a-fA-F0-9]+$",
        description="sr25519 signature of the message in hex format",
        examples=["0x1234567890abcdef..."]
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "hotkey": "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY",
                "mechanism_id": 3,
                "gist_url": "https://gist.github.com/octocat/abc123def456",
                "message": '{"hotkey":"5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY","timestamp":1234567890}',
                "signature": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
            }
        }
    }


class LinkGitHubResponse(BaseModel):
    """Response body for the GitHub link endpoint."""
    
    success: bool = Field(
        ...,
        description="Whether the linking operation was successful"
    )
    github_username: Optional[str] = Field(
        default=None,
        description="GitHub username that was linked (on success)"
    )
    tx_hash: Optional[str] = Field(
        default=None,
        description="Transaction hash of the contract write (if applicable)"
    )
    status: Optional[str] = Field(
        default=None,
        description="Link status: 'created', 'updated', or 'unchanged'"
    )
    error_code: Optional[str] = Field(
        default=None,
        description="Error code identifying the failure reason"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Human-readable error message"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "github_username": "octocat",
                    "tx_hash": "0xabc123...",
                    "status": "created",
                    "error_code": None,
                    "error_message": None
                },
                {
                    "success": False,
                    "github_username": None,
                    "tx_hash": None,
                    "status": None,
                    "error_code": "hotkey_not_registered",
                    "error_message": "Hotkey is not registered on subnet 62"
                }
            ]
        }
    }


class ValidatorContext:
    """
    Holds the validator's runtime context for API operations.
    
    This class stores references to the subtensor, registry, and verifier
    that are initialized when the validator starts. The API endpoints
    use dependency injection to access these services.
    
    Attributes:
        subtensor: Bittensor subtensor instance for querying the chain.
        netuid: Network UID of the subnet.
        registry: GitHubRegistry for contract interactions.
        verifier: GitHubVerifier for validation checks.
        validator_private_key: Private key for signing transactions.
    """
    
    _instance: Optional["ValidatorContext"] = None
    
    def __init__(self):
        self.subtensor: Optional[Any] = None
        self.netuid: Optional[int] = None
        self.registry: Optional[GitHubRegistry] = None
        self.verifier: Optional[GitHubVerifier] = None
        self.validator_private_key: Optional[str] = None
    
    @classmethod
    def get_instance(cls) -> "ValidatorContext":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        subtensor: Any,
        netuid: int,
        registry: GitHubRegistry,
        verifier: GitHubVerifier,
        validator_private_key: str
    ) -> "ValidatorContext":
        """
        Configure the validator context with runtime dependencies.
        
        This method should be called when the validator starts, before
        any API requests are processed.
        
        Args:
            subtensor: Bittensor subtensor instance.
            netuid: Network UID of the subnet.
            registry: GitHubRegistry for contract interactions.
            verifier: GitHubVerifier for validation checks.
            validator_private_key: Private key for signing transactions.
        
        Returns:
            The configured ValidatorContext instance.
        """
        instance = cls.get_instance()
        instance.subtensor = subtensor
        instance.netuid = netuid
        instance.registry = registry
        instance.verifier = verifier
        instance.validator_private_key = validator_private_key
        
        logger.info(
            f"ValidatorContext configured: netuid={netuid}, "
            f"registry={'initialized' if registry else 'None'}"
        )
        
        return instance
    
    def is_initialized(self) -> bool:
        """Check if all required dependencies are configured."""
        return all([
            self.subtensor is not None,
            self.netuid is not None,
            self.registry is not None,
            self.verifier is not None,
            self.validator_private_key is not None
        ])


# Dependency injection functions

def get_context() -> ValidatorContext:
    """
    Dependency that provides the ValidatorContext.
    
    Raises:
        HTTPException: If the context is not initialized (503 Service Unavailable).
    """
    context = ValidatorContext.get_instance()
    
    if not context.is_initialized():
        logger.warning("API request received but ValidatorContext is not initialized")
        raise HTTPException(
            status_code=503,
            detail={
                "success": False,
                "error_code": "service_unavailable",
                "error_message": "Validator is not fully initialized. Please try again later."
            }
        )
    
    return context


def get_verifier(context: ValidatorContext = Depends(get_context)) -> GitHubVerifier:
    """Dependency that provides the GitHubVerifier instance."""
    return context.verifier


def get_registry(context: ValidatorContext = Depends(get_context)) -> GitHubRegistry:
    """Dependency that provides the GitHubRegistry instance."""
    return context.registry


@router.post(
    "/link",
    response_model=LinkGitHubResponse,
    responses={
        200: {
            "description": "Link operation completed (success or validation failure)",
            "model": LinkGitHubResponse
        },
        400: {
            "description": "Invalid request format",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid hotkey format"
                    }
                }
            }
        },
        503: {
            "description": "Service unavailable - validator not initialized",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error_code": "service_unavailable",
                        "error_message": "Validator is not fully initialized"
                    }
                }
            }
        }
    },
    summary="Link Hotkey to GitHub",
    description="""
Link a miner's Bittensor hotkey to their GitHub account.

Performs 6 validation checks:
1. **Hotkey Registration**: Verifies the hotkey is registered on the subnet
2. **Signature Validation**: Confirms the message was signed by the hotkey
3. **Gist Existence**: Checks the gist exists and is public
4. **HOTKEY.md Validation**: Verifies the gist contains a valid HOTKEY.md file
5. **Hotkey Matching**: Ensures all hotkeys match (claimed, signed, and in gist)
6. **GitHub User**: Confirms the GitHub user exists

If all checks pass, the link is written to the smart contract.

**Note**: The link operation is idempotent - linking the same hotkey to the same
GitHub account multiple times will return status "unchanged" without a new transaction.
"""
)
async def link_github(
    request: LinkGitHubRequest,
    context: ValidatorContext = Depends(get_context)
) -> LinkGitHubResponse:
    """
    Link a miner's hotkey to their GitHub account.
    
    Args:
        request: The link request containing hotkey, gist URL, message, and signature.
        context: The validator context with runtime dependencies.
    
    Returns:
        LinkGitHubResponse with success/failure status and details.
    """
    logger.info(
        f"Received link request: hotkey={request.hotkey[:16]}..., "
        f"mechanism_id={request.mechanism_id}, gist={request.gist_url}"
    )
    
    try:
        # Step 1: Run all 6 verification checks
        verification_result: VerificationResult = await context.verifier.verify_link_request(
            claimed_hotkey=request.hotkey,
            gist_url=request.gist_url,
            message=request.message,
            signature=request.signature,
            subtensor=context.subtensor,
            netuid=context.netuid
        )
        
        # If verification failed, return error response
        if not verification_result.success:
            logger.warning(
                f"Verification failed for {request.hotkey[:16]}...: "
                f"{verification_result.error_code} - {verification_result.error_message}"
            )
            return LinkGitHubResponse(
                success=False,
                error_code=verification_result.error_code,
                error_message=verification_result.error_message
            )
        
        # Step 2: All checks passed - write to smart contract
        github_username = verification_result.github_username
        
        logger.info(
            f"Verification passed for {request.hotkey[:16]}... → {github_username}, "
            f"writing to contract..."
        )
        
        tx_hash, status = await context.registry.link_github(
            hotkey=request.hotkey,
            mechanism_id=request.mechanism_id,
            github_username=github_username,
            validator_private_key=context.validator_private_key
        )
        
        logger.info(
            f"Link completed: hotkey={request.hotkey[:16]}..., "
            f"github={github_username}, status={status}, tx_hash={tx_hash}"
        )
        
        return LinkGitHubResponse(
            success=True,
            github_username=github_username,
            tx_hash=tx_hash,
            status=status
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    
    except Exception as e:
        # Log unexpected errors and return a generic error response
        logger.exception(f"Unexpected error processing link request: {e}")
        
        return LinkGitHubResponse(
            success=False,
            error_code="internal_error",
            error_message="An unexpected error occurred. Please try again later."
        )


@router.get(
    "/health",
    summary="Health Check",
    description="Check if the GitHub linking API is operational.",
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "initialized": True,
                        "netuid": 62
                    }
                }
            }
        }
    }
)
async def health_check() -> dict:
    """
    Health check endpoint for the GitHub linking API.
    
    Returns:
        Dictionary with health status and initialization state.
    """
    context = ValidatorContext.get_instance()
    
    return {
        "status": "healthy" if context.is_initialized() else "degraded",
        "initialized": context.is_initialized(),
        "netuid": context.netuid
    }


@router.get(
    "/status/{hotkey}",
    summary="Check Link Status",
    description="Check if a hotkey is already linked to a GitHub account.",
    responses={
        200: {
            "description": "Link status retrieved",
            "content": {
                "application/json": {
                    "examples": {
                        "linked": {
                            "summary": "Hotkey is linked",
                            "value": {
                                "hotkey": "5Grw...",
                                "is_linked": True,
                                "github_username": "octocat",
                                "mechanism_id": 3
                            }
                        },
                        "not_linked": {
                            "summary": "Hotkey is not linked",
                            "value": {
                                "hotkey": "5Grw...",
                                "is_linked": False,
                                "github_username": None,
                                "mechanism_id": 3
                            }
                        }
                    }
                }
            }
        },
        503: {
            "description": "Service unavailable"
        }
    }
)
async def get_link_status(
    hotkey: str,
    mechanism_id: int = 3,
    context: ValidatorContext = Depends(get_context)
) -> dict:
    """
    Check if a hotkey is already linked to a GitHub account.
    
    Args:
        hotkey: The SS58 hotkey to check.
        mechanism_id: The mechanism ID to check (default: 3 for bounty).
        context: The validator context.
    
    Returns:
        Dictionary with link status information.
    """
    github_username = context.registry.get_github(hotkey, mechanism_id)
    
    return {
        "hotkey": hotkey,
        "is_linked": github_username is not None,
        "github_username": github_username,
        "mechanism_id": mechanism_id
    }
