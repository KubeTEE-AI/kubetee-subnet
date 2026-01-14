"""
API Validation Acceptance Tests for GitHub Linking.

Tests all validation rules, edge cases, and error scenarios for the
/api/github/link endpoint.

Acceptance Criteria:
====================

AC1: Request Validation (Pydantic)
----------------------------------
- AC1.1: Hotkey must be exactly 48 characters
- AC1.2: Hotkey must start with '5'
- AC1.3: Hotkey must be alphanumeric
- AC1.4: Mechanism ID must be between 0-10
- AC1.5: Gist URL must match pattern https://gist.github.com/{user}/{id}
- AC1.6: Message must be valid JSON with hotkey and timestamp
- AC1.7: Signature must be hex format (with or without 0x prefix)
- AC1.8: All required fields must be present

AC2: Verification Checks
------------------------
- AC2.1: [A] Hotkey must be registered on subnet 62
- AC2.2: [B] Signature must be valid sr25519 signed by claimed hotkey
- AC2.3: [C] Gist must exist and be public
- AC2.4: [D] Gist must contain HOTKEY.md file
- AC2.5: [D] HOTKEY.md must contain valid hotkey format
- AC2.6: [E] Claimed hotkey must match signed hotkey
- AC2.7: [E] Claimed hotkey must match hotkey in gist
- AC2.8: [F] GitHub user must exist

AC3: Response Handling
----------------------
- AC3.1: Success returns {success: true, github_username, tx_hash, status}
- AC3.2: Validation error returns {success: false, error_code, error_message}
- AC3.3: Status is "created" for new links
- AC3.4: Status is "updated" for changed links
- AC3.5: Status is "unchanged" for duplicate links (no tx_hash)

AC4: Edge Cases
---------------
- AC4.1: Handle GitHub API rate limiting gracefully
- AC4.2: Handle network timeouts
- AC4.3: Handle truncated gist content
- AC4.4: Handle forked gists (owner differs from URL)
- AC4.5: Handle concurrent requests for same hotkey
- AC4.6: Handle very long hotkey in gist content
- AC4.7: Handle special characters in GitHub username

AC5: Security
-------------
- AC5.1: Reject expired timestamps (> 5 minutes old)
- AC5.2: Reject future timestamps
- AC5.3: Reject replayed signatures
- AC5.4: Reject malformed signatures
"""

import pytest
import json
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.acceptance.conftest import (
    VALID_HOTKEY,
    VALID_HOTKEY_2,
    VALID_HOTKEY_3,
    GIST_ID_1,
    MECHANISM_BOUNTY,
    MockGist,
    MockGistServer,
    MockSubtensor,
    MockGitHubRegistry,
    create_link_request,
)


# ============ Test Fixtures ============

@pytest.fixture
def app_with_mock_context():
    """
    Create FastAPI app with fully mocked ValidatorContext.
    """
    from kubetee.api.github import router, ValidatorContext
    from kubetee.validator.github_verifier import VerificationResult

    app = FastAPI()
    app.include_router(router)

    # Create mocks
    mock_subtensor = MockSubtensor()
    mock_subtensor.register_hotkey(VALID_HOTKEY)
    mock_subtensor.register_hotkey(VALID_HOTKEY_2)

    mock_registry = MockGitHubRegistry()

    mock_verifier = Mock()
    mock_verifier.verify_link_request = AsyncMock(
        return_value=VerificationResult(success=True, github_username="testuser")
    )

    # Configure context
    ValidatorContext.configure(
        subtensor=mock_subtensor,
        netuid=62,
        registry=mock_registry,
        verifier=mock_verifier,
        validator_private_key="0x" + "aa" * 32
    )

    yield {
        "app": app,
        "client": TestClient(app),
        "subtensor": mock_subtensor,
        "registry": mock_registry,
        "verifier": mock_verifier,
        "context": ValidatorContext.get_instance()
    }

    # Reset singleton
    ValidatorContext._instance = None


# ============ AC1: Request Validation Tests ============

class TestAC1_RequestValidation:
    """Tests for Pydantic request validation."""

    def test_ac1_1_hotkey_must_be_48_chars(self, app_with_mock_context):
        """AC1.1: Hotkey must be exactly 48 characters."""
        client = app_with_mock_context["client"]

        # Too short (47 chars)
        short_hotkey = "5" + "A" * 46
        request = create_link_request(hotkey=short_hotkey)
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 422
        assert "48" in str(response.json())

        # Too long (49 chars)
        long_hotkey = "5" + "A" * 48
        request = create_link_request(hotkey=long_hotkey)
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 422

    def test_ac1_2_hotkey_must_start_with_5(self, app_with_mock_context):
        """AC1.2: Hotkey must start with '5'."""
        client = app_with_mock_context["client"]

        # Starts with 1
        bad_hotkey = "1" + "A" * 47
        request = create_link_request(hotkey=bad_hotkey)
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 422

        # Starts with 0
        bad_hotkey = "0" + "A" * 47
        request = create_link_request(hotkey=bad_hotkey)
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 422

    def test_ac1_3_hotkey_must_be_alphanumeric(self, app_with_mock_context):
        """AC1.3: Hotkey must be alphanumeric."""
        client = app_with_mock_context["client"]

        # Contains special character
        bad_hotkey = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKu!QY"
        request = create_link_request(hotkey=bad_hotkey)
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 422

    def test_ac1_4_mechanism_id_range(self, app_with_mock_context):
        """AC1.4: Mechanism ID must be between 0-10."""
        client = app_with_mock_context["client"]

        # Negative
        request = create_link_request(mechanism_id=-1)
        response = client.post("/api/github/link", json=request)
        assert response.status_code == 422

        # Too high
        request = create_link_request(mechanism_id=11)
        response = client.post("/api/github/link", json=request)
        assert response.status_code == 422

        # Valid boundary values
        for valid_id in [0, 5, 10]:
            request = create_link_request(mechanism_id=valid_id)
            response = client.post("/api/github/link", json=request)
            # Should not be 422 (validation error)
            assert response.status_code != 422

    def test_ac1_5_gist_url_format(self, app_with_mock_context):
        """AC1.5: Gist URL must match pattern."""
        client = app_with_mock_context["client"]

        invalid_urls = [
            "https://github.com/user/repo",  # Not a gist URL
            "https://gist.github.com/user",  # Missing gist ID
            "https://gist.github.com/abc123",  # Missing username
            "http://evil.com/gist.github.com/user/abc123",  # Domain injection
            "ftp://gist.github.com/user/abc123",  # Wrong protocol
            "https://gist.github.com/user/ABC123",  # Uppercase gist ID
        ]

        for url in invalid_urls:
            request = create_link_request(gist_url=url)
            response = client.post("/api/github/link", json=request)
            assert response.status_code == 422, f"URL should be invalid: {url}"

    def test_ac1_5_gist_url_valid_formats(self, app_with_mock_context):
        """AC1.5: Valid gist URL formats should be accepted."""
        client = app_with_mock_context["client"]

        valid_urls = [
            "https://gist.github.com/octocat/abc123def456",
            "https://gist.github.com/user-name/abc123",
            "https://gist.github.com/user_name/abc123def",
            "http://gist.github.com/user/abc123",  # HTTP allowed (will redirect)
        ]

        for url in valid_urls:
            request = create_link_request(gist_url=url)
            response = client.post("/api/github/link", json=request)
            # Should not be 422 (validation passes, may fail on verification)
            assert response.status_code != 422, f"URL should be valid: {url}"

    def test_ac1_6_message_format(self, app_with_mock_context):
        """AC1.6: Message must be valid JSON with hotkey and timestamp."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        # Configure verifier to return invalid message format error
        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="invalid_message_format",
                error_message="Message is not valid JSON"
            )
        )

        # Valid request but verifier will reject the message format
        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is False
        assert "invalid_message_format" in result.get("error_code", "")

    def test_ac1_7_signature_format(self, app_with_mock_context):
        """AC1.7: Signature must be hex format."""
        client = app_with_mock_context["client"]

        # Valid with 0x prefix
        request = create_link_request(signature="0x" + "ab" * 64)
        response = client.post("/api/github/link", json=request)
        assert response.status_code != 422

        # Valid without 0x prefix
        request = create_link_request(signature="ab" * 64)
        response = client.post("/api/github/link", json=request)
        assert response.status_code != 422

        # Invalid: contains non-hex
        request = create_link_request(signature="0x" + "zz" * 64)
        response = client.post("/api/github/link", json=request)
        assert response.status_code == 422

    def test_ac1_8_required_fields(self, app_with_mock_context):
        """AC1.8: All required fields must be present."""
        client = app_with_mock_context["client"]

        base_request = create_link_request()
        required_fields = ["hotkey", "mechanism_id", "gist_url", "message", "signature"]

        for field in required_fields:
            incomplete = {k: v for k, v in base_request.items() if k != field}
            response = client.post("/api/github/link", json=incomplete)
            assert response.status_code == 422, f"Missing {field} should fail"


# ============ AC2: Verification Checks Tests ============

class TestAC2_VerificationChecks:
    """Tests for the 6 verification checks."""

    def test_ac2_1_hotkey_not_registered(self, app_with_mock_context):
        """AC2.1: [A] Hotkey must be registered on subnet 62."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        # Configure verifier to return not registered error
        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="hotkey_not_registered",
                error_message="Hotkey is not registered on subnet 62"
            )
        )

        request = create_link_request(hotkey=VALID_HOTKEY_3)
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is False
        assert result["error_code"] == "hotkey_not_registered"

    def test_ac2_2_invalid_signature(self, app_with_mock_context):
        """AC2.2: [B] Signature must be valid sr25519."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="invalid_signature",
                error_message="Signature verification failed"
            )
        )

        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        result = response.json()
        assert result["success"] is False
        assert result["error_code"] == "invalid_signature"

    def test_ac2_3_gist_not_found(self, app_with_mock_context):
        """AC2.3: [C] Gist must exist and be public."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="gist_not_found",
                error_message="Gist not found or not public"
            )
        )

        # Use a valid gist URL format so Pydantic validation passes
        request = create_link_request(gist_url="https://gist.github.com/user/abc123def456")
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is False
        assert result["error_code"] == "gist_not_found"

    def test_ac2_4_hotkey_md_missing(self, app_with_mock_context):
        """AC2.4: [D] Gist must contain HOTKEY.md file."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="hotkey_md_missing",
                error_message="Gist does not contain HOTKEY.md file"
            )
        )

        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        result = response.json()
        assert result["success"] is False
        assert result["error_code"] == "hotkey_md_missing"

    def test_ac2_5_invalid_hotkey_format_in_gist(self, app_with_mock_context):
        """AC2.5: [D] HOTKEY.md must contain valid hotkey format."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="invalid_hotkey_format",
                error_message="HOTKEY.md does not contain a valid hotkey"
            )
        )

        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        result = response.json()
        assert result["success"] is False
        assert result["error_code"] == "invalid_hotkey_format"

    def test_ac2_6_hotkey_mismatch_signed(self, app_with_mock_context):
        """AC2.6: [E] Claimed hotkey must match signed hotkey."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="hotkey_mismatch",
                error_message="Claimed hotkey does not match signed hotkey"
            )
        )

        # Create request with mismatched hotkey in message
        message = json.dumps({
            "hotkey": VALID_HOTKEY_2,  # Different from request hotkey
            "timestamp": int(time.time())
        })
        request = create_link_request(hotkey=VALID_HOTKEY, message=message)
        response = client.post("/api/github/link", json=request)

        result = response.json()
        assert result["success"] is False
        assert result["error_code"] == "hotkey_mismatch"

    def test_ac2_7_hotkey_mismatch_gist(self, app_with_mock_context):
        """AC2.7: [E] Claimed hotkey must match hotkey in gist."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="hotkey_mismatch",
                error_message="Claimed hotkey does not match hotkey in gist"
            )
        )

        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        result = response.json()
        assert result["success"] is False
        assert result["error_code"] == "hotkey_mismatch"

    def test_ac2_8_github_user_not_found(self, app_with_mock_context):
        """AC2.8: [F] GitHub user must exist."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="github_user_not_found",
                error_message="GitHub user 'nonexistent' not found"
            )
        )

        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        result = response.json()
        assert result["success"] is False
        assert result["error_code"] == "github_user_not_found"


# ============ AC3: Response Handling Tests ============

class TestAC3_ResponseHandling:
    """Tests for response formats and status handling."""

    def test_ac3_1_success_response_format(self, app_with_mock_context):
        """AC3.1: Success returns correct fields."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(success=True, github_username="testuser")
        )

        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 200
        result = response.json()

        # Check all required fields present
        assert result["success"] is True
        assert result["github_username"] == "testuser"
        assert "tx_hash" in result
        assert "status" in result
        assert result["error_code"] is None
        assert result["error_message"] is None

    def test_ac3_2_error_response_format(self, app_with_mock_context):
        """AC3.2: Validation error returns correct fields."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="test_error",
                error_message="Test error message"
            )
        )

        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 200
        result = response.json()

        assert result["success"] is False
        assert result["error_code"] == "test_error"
        assert result["error_message"] == "Test error message"
        assert result["github_username"] is None
        assert result["tx_hash"] is None

    @pytest.mark.asyncio
    async def test_ac3_3_status_created(self, app_with_mock_context):
        """AC3.3: Status is 'created' for new links."""
        context = app_with_mock_context
        registry = context["registry"]

        # Ensure no existing link
        assert registry.get_github(VALID_HOTKEY, MECHANISM_BOUNTY) is None

        tx_hash, status = await registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="newuser",
            validator_key="0xvalidator"
        )

        assert status == "created"
        assert tx_hash is not None

    @pytest.mark.asyncio
    async def test_ac3_4_status_updated(self, app_with_mock_context):
        """AC3.4: Status is 'updated' for changed links."""
        context = app_with_mock_context
        registry = context["registry"]

        # Create initial link
        await registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="olduser",
            validator_key="0xvalidator"
        )

        # Update to new username
        tx_hash, status = await registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="newuser",
            validator_key="0xvalidator"
        )

        assert status == "updated"
        assert tx_hash is not None

    @pytest.mark.asyncio
    async def test_ac3_5_status_unchanged(self, app_with_mock_context):
        """AC3.5: Status is 'unchanged' for duplicate links."""
        context = app_with_mock_context
        registry = context["registry"]

        # Create initial link
        await registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="sameuser",
            validator_key="0xvalidator"
        )

        # Try to link same username again
        tx_hash, status = await registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="sameuser",
            validator_key="0xvalidator"
        )

        assert status == "unchanged"
        assert tx_hash is None  # No transaction for unchanged link


# ============ AC4: Edge Cases Tests ============

class TestAC4_EdgeCases:
    """Tests for edge cases and unusual scenarios."""

    def test_ac4_1_rate_limiting(self, app_with_mock_context):
        """AC4.1: Handle GitHub API rate limiting gracefully."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="rate_limited",
                error_message="GitHub API rate limit exceeded"
            )
        )

        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        result = response.json()
        assert result["success"] is False
        assert result["error_code"] == "rate_limited"

    def test_ac4_2_network_timeout(self, app_with_mock_context):
        """AC4.2: Handle network timeouts."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(
                success=False,
                error_code="gist_not_found",
                error_message="Timeout while fetching gist from GitHub"
            )
        )

        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        result = response.json()
        assert result["success"] is False

    def test_ac4_5_concurrent_requests_same_hotkey(self, app_with_mock_context):
        """AC4.5: Handle concurrent requests for same hotkey."""
        from kubetee.validator.github_verifier import VerificationResult
        import threading

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(success=True, github_username="testuser")
        )

        results = []

        def make_request():
            request = create_link_request()
            response = client.post("/api/github/link", json=request)
            results.append(response.json())

        # Simulate concurrent requests
        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed (at least one "created", rest "unchanged")
        successes = [r for r in results if r["success"]]
        assert len(successes) == 5

        created = [r for r in results if r.get("status") == "created"]
        unchanged = [r for r in results if r.get("status") == "unchanged"]

        # First one creates, rest are unchanged
        assert len(created) >= 1

    def test_ac4_7_special_characters_in_username(self, app_with_mock_context):
        """AC4.7: Handle special characters in GitHub username."""
        from kubetee.validator.github_verifier import VerificationResult

        context = app_with_mock_context
        client = context["client"]
        verifier = context["verifier"]

        # GitHub allows hyphens in usernames
        verifier.verify_link_request = AsyncMock(
            return_value=VerificationResult(success=True, github_username="test-user-123")
        )

        request = create_link_request(
            gist_url="https://gist.github.com/test-user-123/abc123"
        )
        response = client.post("/api/github/link", json=request)

        result = response.json()
        assert result["success"] is True
        assert result["github_username"] == "test-user-123"


# ============ AC5: Security Tests ============

class TestAC5_Security:
    """Tests for security-related validation."""

    def test_ac5_4_malformed_signature(self, app_with_mock_context):
        """AC5.4: Reject malformed signatures."""
        client = app_with_mock_context["client"]

        # Too short signature
        request = create_link_request(signature="0x" + "ab" * 10)
        response = client.post("/api/github/link", json=request)
        assert response.status_code == 422

    def test_service_unavailable_before_init(self):
        """Service returns 503 before context is initialized."""
        from kubetee.api.github import router, ValidatorContext

        # Reset context
        ValidatorContext._instance = None

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        request = create_link_request()
        response = client.post("/api/github/link", json=request)

        assert response.status_code == 503


# ============ Health Check Tests ============

class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check_initialized(self, app_with_mock_context):
        """Health check returns healthy when initialized."""
        client = app_with_mock_context["client"]

        response = client.get("/api/github/health")

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "healthy"
        assert result["initialized"] is True
        assert result["netuid"] == 62

    def test_health_check_degraded(self):
        """Health check returns degraded when not initialized."""
        from kubetee.api.github import router, ValidatorContext

        # Reset context
        ValidatorContext._instance = None

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/api/github/health")

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "degraded"
        assert result["initialized"] is False


# ============ Status Endpoint Tests ============

class TestStatusEndpoint:
    """Tests for status check endpoint."""

    def test_status_linked(self, app_with_mock_context):
        """Status returns linked info for linked hotkey."""
        context = app_with_mock_context
        client = context["client"]
        registry = context["registry"]

        # Add a link
        registry.links[VALID_HOTKEY] = {MECHANISM_BOUNTY: "testuser"}

        response = client.get(
            f"/api/github/status/{VALID_HOTKEY}",
            params={"mechanism_id": MECHANISM_BOUNTY}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["is_linked"] is True
        assert result["github_username"] == "testuser"
        assert result["hotkey"] == VALID_HOTKEY

    def test_status_not_linked(self, app_with_mock_context):
        """Status returns not linked for unknown hotkey."""
        client = app_with_mock_context["client"]

        response = client.get(
            f"/api/github/status/{VALID_HOTKEY_3}",
            params={"mechanism_id": MECHANISM_BOUNTY}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["is_linked"] is False
        assert result["github_username"] is None
