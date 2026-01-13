"""
Tests for GitHub Linking API Endpoints.

Tests cover:
- POST /api/github/link endpoint
- GET /api/github/health endpoint
- GET /api/github/status/{hotkey} endpoint
- Request validation
- Error responses
- Context initialization
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kubetee.api.github import (
    router,
    ValidatorContext,
    LinkGitHubRequest,
    LinkGitHubResponse,
)
from kubetee.validator.github_verifier import VerificationResult


# Test hotkeys - valid SS58 format starting with 5
VALID_HOTKEY = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
VALID_HOTKEY_2 = "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"


@pytest.fixture
def app():
    """Create a FastAPI app with the GitHub router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def mock_context():
    """Create a mock ValidatorContext with all dependencies."""
    context = ValidatorContext()
    context.subtensor = Mock()
    context.netuid = 62
    context.registry = Mock()
    context.verifier = Mock()
    context.validator_private_key = "0x" + "aa" * 32
    return context


@pytest.fixture
def client(app, mock_context):
    """Create a test client with mocked context."""
    # Reset singleton and set our mock
    ValidatorContext._instance = None
    ValidatorContext._instance = mock_context
    
    yield TestClient(app)
    
    # Cleanup
    ValidatorContext._instance = None


@pytest.fixture
def uninitialized_client(app):
    """Create a test client without initialized context."""
    ValidatorContext._instance = None
    
    yield TestClient(app)
    
    # Cleanup
    ValidatorContext._instance = None


class TestLinkGitHubEndpoint:
    """Tests for POST /api/github/link endpoint."""
    
    def test_link_github_success(self, client, mock_context):
        """Successful link creates registry entry."""
        # Setup mock verifier to return success
        mock_context.verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=True,
                github_username="octocat"
            )
        )
        
        # Setup mock registry to return transaction
        mock_context.registry.link_github = AsyncMock(
            return_value=("0xabcd1234", "created")
        )
        
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["github_username"] == "octocat"
        assert data["tx_hash"] == "0xabcd1234"
        assert data["status"] == "created"
    
    def test_link_github_already_linked(self, client, mock_context):
        """Link that already exists returns unchanged status."""
        mock_context.verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=True,
                github_username="octocat"
            )
        )
        
        mock_context.registry.link_github = AsyncMock(
            return_value=(None, "unchanged")
        )
        
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "unchanged"
        assert data["tx_hash"] is None
    
    def test_link_github_updated(self, client, mock_context):
        """Updating an existing link returns updated status."""
        mock_context.verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=True,
                github_username="newuser"
            )
        )
        
        mock_context.registry.link_github = AsyncMock(
            return_value=("0xef567890", "updated")
        )
        
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/newuser/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "updated"
        assert data["github_username"] == "newuser"
    
    def test_link_github_verification_fails(self, client, mock_context):
        """Verification failure returns proper error code."""
        mock_context.verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="hotkey_not_registered",
                error_message="Hotkey is not registered on subnet 62"
            )
        )
        
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "hotkey_not_registered"
        assert "not registered" in data["error_message"].lower()
    
    def test_link_github_invalid_signature(self, client, mock_context):
        """Invalid signature verification returns error."""
        mock_context.verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="invalid_signature",
                error_message="Signature verification failed"
            )
        )
        
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "bb" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "invalid_signature"
    
    def test_link_github_internal_error(self, client, mock_context):
        """Internal error returns generic error response."""
        mock_context.verifier.verify_link_request = AsyncMock(
            side_effect=Exception("Unexpected error")
        )
        
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "internal_error"


class TestRequestValidation:
    """Tests for request validation."""
    
    def test_invalid_hotkey_format_too_short(self, client):
        """Hotkey that is too short returns 422."""
        request_data = {
            "hotkey": "5GrwvaEF5zXb26",  # Too short
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": "5GrwvaEF5zXb26", "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 422
    
    def test_invalid_hotkey_format_wrong_prefix(self, client):
        """Hotkey not starting with 5 returns 422."""
        request_data = {
            "hotkey": "1GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY",
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 422
    
    def test_invalid_mechanism_id_negative(self, client):
        """Negative mechanism ID returns 422."""
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": -1,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 422
    
    def test_invalid_mechanism_id_too_large(self, client):
        """Mechanism ID > 10 returns 422."""
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 99,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 422
    
    def test_invalid_gist_url_format(self, client):
        """Invalid gist URL format returns 422."""
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            "gist_url": "https://github.com/octocat/repo",  # Not a gist URL
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 422
    
    def test_invalid_signature_format(self, client):
        """Invalid signature format returns 422."""
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "not_hex_signature!"
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 422
    
    def test_missing_required_field(self, client):
        """Missing required field returns 422."""
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            # Missing gist_url, message, signature
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 422


class TestHealthEndpoint:
    """Tests for GET /api/github/health endpoint."""
    
    def test_health_endpoint_initialized(self, client, mock_context):
        """Health check returns healthy when initialized."""
        response = client.get("/api/github/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["initialized"] is True
        assert data["netuid"] == 62
    
    def test_health_endpoint_not_initialized(self, uninitialized_client):
        """Health check returns degraded when not initialized."""
        response = uninitialized_client.get("/api/github/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["initialized"] is False


class TestStatusEndpoint:
    """Tests for GET /api/github/status/{hotkey} endpoint."""
    
    def test_status_endpoint_linked(self, client, mock_context):
        """Status check returns linked info."""
        mock_context.registry.get_github.return_value = "octocat"
        
        response = client.get(f"/api/github/status/{VALID_HOTKEY}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["hotkey"] == VALID_HOTKEY
        assert data["is_linked"] is True
        assert data["github_username"] == "octocat"
        assert data["mechanism_id"] == 3  # Default
    
    def test_status_endpoint_not_linked(self, client, mock_context):
        """Status check returns not linked info."""
        mock_context.registry.get_github.return_value = None
        
        response = client.get(f"/api/github/status/{VALID_HOTKEY}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["hotkey"] == VALID_HOTKEY
        assert data["is_linked"] is False
        assert data["github_username"] is None
    
    def test_status_endpoint_with_mechanism_id(self, client, mock_context):
        """Status check with specific mechanism ID."""
        mock_context.registry.get_github.return_value = "octocat"
        
        response = client.get(f"/api/github/status/{VALID_HOTKEY}?mechanism_id=1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["mechanism_id"] == 1
        mock_context.registry.get_github.assert_called_with(VALID_HOTKEY, 1)
    
    def test_status_endpoint_not_initialized(self, uninitialized_client):
        """Status check returns 503 when not initialized."""
        response = uninitialized_client.get(f"/api/github/status/{VALID_HOTKEY}")
        
        assert response.status_code == 503


class TestServiceUnavailable:
    """Tests for service unavailable scenarios."""
    
    def test_link_endpoint_not_initialized(self, uninitialized_client):
        """Link endpoint returns 503 when context not initialized."""
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = uninitialized_client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 503
        data = response.json()
        assert "service_unavailable" in str(data).lower() or "not fully initialized" in str(data).lower()


class TestValidatorContext:
    """Tests for ValidatorContext singleton."""
    
    def test_context_singleton(self):
        """Context is a singleton."""
        ValidatorContext._instance = None
        
        context1 = ValidatorContext.get_instance()
        context2 = ValidatorContext.get_instance()
        
        assert context1 is context2
        
        ValidatorContext._instance = None
    
    def test_context_is_initialized_false(self):
        """Context is not initialized by default."""
        ValidatorContext._instance = None
        context = ValidatorContext.get_instance()
        
        assert context.is_initialized() is False
        
        ValidatorContext._instance = None
    
    def test_context_is_initialized_partial(self):
        """Context is not initialized with partial config."""
        ValidatorContext._instance = None
        context = ValidatorContext.get_instance()
        context.subtensor = Mock()
        context.netuid = 62
        # Missing registry, verifier, validator_private_key
        
        assert context.is_initialized() is False
        
        ValidatorContext._instance = None
    
    def test_context_configure(self):
        """Context can be configured with all dependencies."""
        ValidatorContext._instance = None
        
        mock_subtensor = Mock()
        mock_registry = Mock()
        mock_verifier = Mock()
        
        context = ValidatorContext.configure(
            subtensor=mock_subtensor,
            netuid=62,
            registry=mock_registry,
            verifier=mock_verifier,
            validator_private_key="0xdeadbeef"
        )
        
        assert context.is_initialized() is True
        assert context.subtensor is mock_subtensor
        assert context.netuid == 62
        assert context.registry is mock_registry
        assert context.verifier is mock_verifier
        assert context.validator_private_key == "0xdeadbeef"
        
        ValidatorContext._instance = None


class TestLinkGitHubRequestModel:
    """Tests for LinkGitHubRequest Pydantic model."""
    
    def test_valid_request(self):
        """Valid request creates model successfully."""
        request = LinkGitHubRequest(
            hotkey=VALID_HOTKEY,
            mechanism_id=3,
            gist_url="https://gist.github.com/octocat/abc123def456",
            message=json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            signature="0x" + "aa" * 64
        )
        
        assert request.hotkey == VALID_HOTKEY
        assert request.mechanism_id == 3
    
    def test_valid_request_boundary_mechanism_id(self):
        """Mechanism ID at boundaries is valid."""
        # Test lower bound
        request_0 = LinkGitHubRequest(
            hotkey=VALID_HOTKEY,
            mechanism_id=0,
            gist_url="https://gist.github.com/octocat/abc123def456",
            message=json.dumps({"hotkey": VALID_HOTKEY}),
            signature="0x" + "aa" * 64
        )
        assert request_0.mechanism_id == 0
        
        # Test upper bound
        request_10 = LinkGitHubRequest(
            hotkey=VALID_HOTKEY,
            mechanism_id=10,
            gist_url="https://gist.github.com/octocat/abc123def456",
            message=json.dumps({"hotkey": VALID_HOTKEY}),
            signature="0x" + "aa" * 64
        )
        assert request_10.mechanism_id == 10


class TestLinkGitHubResponseModel:
    """Tests for LinkGitHubResponse Pydantic model."""
    
    def test_success_response(self):
        """Success response model is valid."""
        response = LinkGitHubResponse(
            success=True,
            github_username="octocat",
            tx_hash="0xabcd1234",
            status="created"
        )
        
        assert response.success is True
        assert response.github_username == "octocat"
        assert response.error_code is None
    
    def test_failure_response(self):
        """Failure response model is valid."""
        response = LinkGitHubResponse(
            success=False,
            error_code="invalid_signature",
            error_message="Signature verification failed"
        )
        
        assert response.success is False
        assert response.error_code == "invalid_signature"
        assert response.github_username is None


class TestAllMechanismIds:
    """Test all valid mechanism IDs."""
    
    @pytest.mark.parametrize("mechanism_id", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    def test_valid_mechanism_ids(self, client, mock_context, mechanism_id):
        """All mechanism IDs 0-10 should be accepted."""
        mock_context.verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=True,
                github_username="octocat"
            )
        )
        
        mock_context.registry.link_github = AsyncMock(
            return_value=("0xabcd1234", "created")
        )
        
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": mechanism_id,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 200


class TestErrorCodes:
    """Test all possible error codes."""
    
    @pytest.mark.parametrize("error_code,error_message", [
        ("hotkey_not_registered", "Hotkey is not registered on subnet 62"),
        ("invalid_signature", "Signature verification failed"),
        ("gist_not_found", "Gist not found or not public"),
        ("hotkey_md_missing", "Gist does not contain HOTKEY.md file"),
        ("invalid_hotkey_format", "HOTKEY.md does not contain a valid hotkey"),
        ("hotkey_mismatch", "Claimed hotkey does not match signed hotkey"),
        ("github_user_not_found", "GitHub user not found"),
        ("rate_limited", "GitHub API rate limit exceeded"),
    ])
    def test_verification_error_codes(self, client, mock_context, error_code, error_message):
        """All verification error codes are returned properly."""
        mock_context.verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code=error_code,
                error_message=error_message
            )
        )
        
        request_data = {
            "hotkey": VALID_HOTKEY,
            "mechanism_id": 3,
            "gist_url": "https://gist.github.com/octocat/abc123def456",
            "message": json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890}),
            "signature": "0x" + "aa" * 64
        }
        
        response = client.post("/api/github/link", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == error_code
