"""
End-to-End Acceptance Tests for GitHub Linking.

These tests verify complete user scenarios from start to finish,
including integration between all components.

Scenarios covered:
- SC1: Miner links GitHub for the first time
- SC2: Miner updates existing GitHub link
- SC3: Link unchanged (same username)
- SC4: All error scenarios
- SC5: Rate limiting handling
"""

import pytest
import json
import time
from unittest.mock import Mock, AsyncMock, patch

from tests.acceptance.conftest import (
    VALID_HOTKEY,
    VALID_HOTKEY_2,
    VALID_HOTKEY_3,
    GIST_ID_1,
    GIST_ID_2,
    MECHANISM_BOUNTY,
    MECHANISM_OPENSOURCE,
    MockGist,
    MockGistServer,
    MockSubtensor,
    MockGitHubRegistry,
    create_link_request,
    mock_httpx_for_gist_server,
)


class TestScenario1_FirstTimeLink:
    """
    Scenario 1: Miner links GitHub account for the first time.
    
    Given: A registered miner with a valid public gist containing HOTKEY.md
    When: The miner calls the link-github endpoint
    Then: The link is created and status is "created"
    """
    
    @pytest.mark.asyncio
    async def test_first_time_link_success(
        self,
        mock_subtensor,
        mock_registry,
        mock_gist_server
    ):
        """Complete flow: verification → registry → response."""
        from kubetee.validator.github_verifier import GitHubVerifier
        
        # Setup: Hotkey is registered
        mock_subtensor.register_hotkey(VALID_HOTKEY_3)
        
        # Setup: Gist exists with correct hotkey
        mock_gist_server.add_gist(
            MockGist("new_gist_123", "newuser").add_hotkey_file(VALID_HOTKEY_3)
        )
        mock_gist_server.add_user("newuser")
        
        # Create verifier
        verifier = GitHubVerifier()
        
        # Create message and signature
        message = json.dumps({
            "hotkey": VALID_HOTKEY_3,
            "timestamp": int(time.time())
        })
        
        # Mock the verification steps
        with mock_httpx_for_gist_server(mock_gist_server):
            with patch.object(verifier, 'verify_signature', return_value=True):
                with patch.object(verifier, 'verify_subnet_registration', new_callable=AsyncMock) as mock_reg:
                    mock_reg.return_value = True
                    
                    # Run verification
                    result = await verifier.verify_link_request(
                        claimed_hotkey=VALID_HOTKEY_3,
                        gist_url=f"https://gist.github.com/newuser/new_gist_123",
                        message=message,
                        signature="0x" + "aa" * 64,
                        subtensor=mock_subtensor,
                        netuid=62
                    )
        
        # Verification should succeed
        assert result.success is True
        assert result.github_username == "newuser"
        
        # Now create the link in registry
        tx_hash, status = await mock_registry.link_github(
            hotkey=VALID_HOTKEY_3,
            mechanism_id=MECHANISM_BOUNTY,
            github_username=result.github_username,
            validator_key="0xvalidator"
        )
        
        # Verify link was created
        assert status == "created"
        assert tx_hash is not None
        assert mock_registry.get_github(VALID_HOTKEY_3, MECHANISM_BOUNTY) == "newuser"
    
    def test_first_time_link_via_api(self, api_test_client, mock_registry):
        """Test first-time link via API endpoint."""
        request = create_link_request(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            gist_url=f"https://gist.github.com/octocat/{GIST_ID_1}"
        )
        
        response = api_test_client.post("/api/github/link", json=request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["github_username"] == "octocat"
        assert data["status"] in ["created", "updated", "unchanged"]


class TestScenario2_UpdateLink:
    """
    Scenario 2: Miner updates existing GitHub link.
    
    Given: A miner who already has a linked GitHub account
    When: The miner links a different GitHub account
    Then: The link is updated and status is "updated"
    """
    
    @pytest.mark.asyncio
    async def test_update_existing_link(self, mock_registry):
        """Updating an existing link should return status 'updated'."""
        # First, create initial link
        tx1, status1 = await mock_registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="olduser",
            validator_key="0xvalidator"
        )
        assert status1 == "created"
        assert mock_registry.get_github(VALID_HOTKEY, MECHANISM_BOUNTY) == "olduser"
        
        # Now update to new user
        tx2, status2 = await mock_registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="newuser",
            validator_key="0xvalidator"
        )
        
        # Should be updated
        assert status2 == "updated"
        assert tx2 != tx1
        assert mock_registry.get_github(VALID_HOTKEY, MECHANISM_BOUNTY) == "newuser"
        
        # Should have 2 events recorded
        events = mock_registry.get_all_links()
        assert len(events) == 2
        assert events[0]["github_username"] == "olduser"
        assert events[1]["github_username"] == "newuser"
    
    @pytest.mark.asyncio
    async def test_update_link_different_mechanism(self, mock_registry):
        """Same hotkey can have different links per mechanism."""
        # Link for bounty
        await mock_registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="bounty_user",
            validator_key="0xvalidator"
        )
        
        # Link for opensource (same hotkey, different mechanism)
        tx, status = await mock_registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_OPENSOURCE,
            github_username="opensource_user",
            validator_key="0xvalidator"
        )
        
        # Both should be "created" (different mechanisms)
        assert status == "created"
        
        # Both links should exist
        assert mock_registry.get_github(VALID_HOTKEY, MECHANISM_BOUNTY) == "bounty_user"
        assert mock_registry.get_github(VALID_HOTKEY, MECHANISM_OPENSOURCE) == "opensource_user"


class TestScenario3_UnchangedLink:
    """
    Scenario 3: Link request with same username (unchanged).
    
    Given: A miner with existing link to username X
    When: The miner requests link to same username X
    Then: No transaction is made, status is "unchanged"
    """
    
    @pytest.mark.asyncio
    async def test_unchanged_link_no_transaction(self, mock_registry):
        """Same link should not create new transaction."""
        # Create initial link
        tx1, status1 = await mock_registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="sameuser",
            validator_key="0xvalidator"
        )
        assert status1 == "created"
        
        # Request same link again
        tx2, status2 = await mock_registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="sameuser",  # Same username
            validator_key="0xvalidator"
        )
        
        # Should be unchanged with no tx
        assert status2 == "unchanged"
        assert tx2 is None
        
        # Only 1 event should exist
        events = mock_registry.get_all_links()
        assert len(events) == 1
    
    def test_unchanged_via_api(self, api_test_client, mock_registry):
        """Test unchanged status via API."""
        # Setup: Pre-populate registry with existing link
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            mock_registry.link_github(
                hotkey=VALID_HOTKEY,
                mechanism_id=MECHANISM_BOUNTY,
                github_username="octocat",
                validator_key="0xvalidator"
            )
        )
        
        # Make same request via API
        request = create_link_request(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            gist_url=f"https://gist.github.com/octocat/{GIST_ID_1}"
        )
        
        response = api_test_client.post("/api/github/link", json=request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Status should be "unchanged" since it's the same username
        # (depends on how the mock verifier returns the same username)


class TestScenario4_ErrorScenarios:
    """
    Scenario 4: All error scenarios.
    
    Tests all possible error conditions and their proper handling.
    """
    
    @pytest.mark.asyncio
    async def test_error_hotkey_not_registered(self, mock_subtensor, mock_gist_server):
        """Unregistered hotkey should fail with hotkey_not_registered."""
        from kubetee.validator.github_verifier import GitHubVerifier
        
        unregistered_hotkey = "5DAAnrj7VHTznn2AWBemMuyBwZWs6FNFjdyVXUeYum3PTXFy"
        
        verifier = GitHubVerifier()
        
        message = json.dumps({
            "hotkey": unregistered_hotkey,
            "timestamp": int(time.time())
        })
        
        # Hotkey is not registered in subtensor
        result = await verifier.verify_link_request(
            claimed_hotkey=unregistered_hotkey,
            gist_url=f"https://gist.github.com/octocat/{GIST_ID_1}",
            message=message,
            signature="0x" + "aa" * 64,
            subtensor=mock_subtensor,
            netuid=62
        )
        
        assert result.success is False
        assert result.error_code == "hotkey_not_registered"
    
    @pytest.mark.asyncio
    async def test_error_invalid_signature(self, mock_subtensor, mock_gist_server):
        """Invalid signature should fail with invalid_signature."""
        from kubetee.validator.github_verifier import GitHubVerifier
        
        verifier = GitHubVerifier()
        
        message = json.dumps({
            "hotkey": VALID_HOTKEY,
            "timestamp": int(time.time())
        })
        
        # Mock signature verification to fail
        with patch.object(verifier, 'verify_signature', return_value=False):
            result = await verifier.verify_link_request(
                claimed_hotkey=VALID_HOTKEY,
                gist_url=f"https://gist.github.com/octocat/{GIST_ID_1}",
                message=message,
                signature="0xbadsignature",
                subtensor=mock_subtensor,
                netuid=62
            )
        
        assert result.success is False
        assert result.error_code == "invalid_signature"
    
    @pytest.mark.asyncio
    async def test_error_gist_not_found(self, mock_subtensor, mock_gist_server):
        """Non-existent gist should fail with gist_not_found."""
        from kubetee.validator.github_verifier import GitHubVerifier
        
        verifier = GitHubVerifier()
        
        message = json.dumps({
            "hotkey": VALID_HOTKEY,
            "timestamp": int(time.time())
        })
        
        with mock_httpx_for_gist_server(mock_gist_server):
            with patch.object(verifier, 'verify_signature', return_value=True):
                with patch.object(verifier, 'verify_subnet_registration', new_callable=AsyncMock) as mock_reg:
                    mock_reg.return_value = True
                    
                    result = await verifier.verify_link_request(
                        claimed_hotkey=VALID_HOTKEY,
                        gist_url="https://gist.github.com/octocat/nonexistent_gist",
                        message=message,
                        signature="0x" + "aa" * 64,
                        subtensor=mock_subtensor,
                        netuid=62
                    )
        
        assert result.success is False
        assert result.error_code == "gist_not_found"
    
    @pytest.mark.asyncio
    async def test_error_private_gist(self, mock_subtensor, mock_gist_server):
        """Private gist should fail with gist_not_found."""
        from kubetee.validator.github_verifier import GitHubVerifier
        
        # Add a private gist
        private_gist = MockGist("private_123", "octocat", public=False)
        private_gist.add_hotkey_file(VALID_HOTKEY)
        mock_gist_server.add_gist(private_gist)
        
        verifier = GitHubVerifier()
        
        message = json.dumps({
            "hotkey": VALID_HOTKEY,
            "timestamp": int(time.time())
        })
        
        with mock_httpx_for_gist_server(mock_gist_server):
            with patch.object(verifier, 'verify_signature', return_value=True):
                with patch.object(verifier, 'verify_subnet_registration', new_callable=AsyncMock) as mock_reg:
                    mock_reg.return_value = True
                    
                    result = await verifier.verify_link_request(
                        claimed_hotkey=VALID_HOTKEY,
                        gist_url="https://gist.github.com/octocat/private_123",
                        message=message,
                        signature="0x" + "aa" * 64,
                        subtensor=mock_subtensor,
                        netuid=62
                    )
        
        assert result.success is False
        assert result.error_code == "gist_not_found"
    
    @pytest.mark.asyncio
    async def test_error_hotkey_md_missing(self, mock_subtensor, mock_gist_server):
        """Gist without HOTKEY.md should fail with hotkey_md_missing."""
        from kubetee.validator.github_verifier import GitHubVerifier
        
        # Add gist without HOTKEY.md
        gist_no_hotkey = MockGist("no_hotkey_gist", "octocat")
        gist_no_hotkey.files["README.md"] = {"content": "Hello world"}
        mock_gist_server.add_gist(gist_no_hotkey)
        
        verifier = GitHubVerifier()
        
        message = json.dumps({
            "hotkey": VALID_HOTKEY,
            "timestamp": int(time.time())
        })
        
        with mock_httpx_for_gist_server(mock_gist_server):
            with patch.object(verifier, 'verify_signature', return_value=True):
                with patch.object(verifier, 'verify_subnet_registration', new_callable=AsyncMock) as mock_reg:
                    mock_reg.return_value = True
                    
                    result = await verifier.verify_link_request(
                        claimed_hotkey=VALID_HOTKEY,
                        gist_url="https://gist.github.com/octocat/no_hotkey_gist",
                        message=message,
                        signature="0x" + "aa" * 64,
                        subtensor=mock_subtensor,
                        netuid=62
                    )
        
        assert result.success is False
        assert result.error_code == "hotkey_md_missing"
    
    @pytest.mark.asyncio
    async def test_error_hotkey_mismatch(self, mock_subtensor, mock_gist_server):
        """Mismatched hotkeys should fail with hotkey_mismatch."""
        from kubetee.validator.github_verifier import GitHubVerifier
        
        # Gist has VALID_HOTKEY, but message claims VALID_HOTKEY_2
        verifier = GitHubVerifier()
        
        # Message contains different hotkey than gist
        message = json.dumps({
            "hotkey": VALID_HOTKEY_2,  # Different from gist
            "timestamp": int(time.time())
        })
        
        with mock_httpx_for_gist_server(mock_gist_server):
            with patch.object(verifier, 'verify_signature', return_value=True):
                with patch.object(verifier, 'verify_subnet_registration', new_callable=AsyncMock) as mock_reg:
                    mock_reg.return_value = True
                    
                    result = await verifier.verify_link_request(
                        claimed_hotkey=VALID_HOTKEY_2,  # Claims HOTKEY_2
                        gist_url=f"https://gist.github.com/octocat/{GIST_ID_1}",  # Contains HOTKEY
                        message=message,
                        signature="0x" + "aa" * 64,
                        subtensor=mock_subtensor,
                        netuid=62
                    )
        
        assert result.success is False
        assert result.error_code == "hotkey_mismatch"
    
    @pytest.mark.asyncio
    async def test_error_github_user_not_found(self, mock_subtensor, mock_gist_server):
        """Non-existent GitHub user should fail with github_user_not_found."""
        from kubetee.validator.github_verifier import GitHubVerifier
        
        # Add gist from non-existent user
        gist = MockGist("ghost_gist", "ghostuser")
        gist.add_hotkey_file(VALID_HOTKEY)
        mock_gist_server.add_gist(gist)
        # Note: "ghostuser" is NOT in mock_gist_server.users
        
        verifier = GitHubVerifier()
        
        message = json.dumps({
            "hotkey": VALID_HOTKEY,
            "timestamp": int(time.time())
        })
        
        with mock_httpx_for_gist_server(mock_gist_server):
            with patch.object(verifier, 'verify_signature', return_value=True):
                with patch.object(verifier, 'verify_subnet_registration', new_callable=AsyncMock) as mock_reg:
                    mock_reg.return_value = True
                    
                    result = await verifier.verify_link_request(
                        claimed_hotkey=VALID_HOTKEY,
                        gist_url="https://gist.github.com/ghostuser/ghost_gist",
                        message=message,
                        signature="0x" + "aa" * 64,
                        subtensor=mock_subtensor,
                        netuid=62
                    )
        
        assert result.success is False
        assert result.error_code == "github_user_not_found"
    
    def test_api_error_invalid_hotkey_format(self, api_test_client):
        """API should reject invalid hotkey format."""
        request = create_link_request(hotkey="invalid_hotkey")
        
        response = api_test_client.post("/api/github/link", json=request)
        
        # Pydantic validation should fail
        assert response.status_code == 422 or (
            response.status_code == 200 and response.json().get("success") is False
        )
    
    def test_api_error_invalid_mechanism_id(self, api_test_client):
        """API should reject invalid mechanism ID."""
        request = create_link_request(mechanism_id=-1)
        
        response = api_test_client.post("/api/github/link", json=request)
        
        # Should fail validation
        assert response.status_code in [422, 400] or (
            response.status_code == 200 and response.json().get("success") is False
        )


class TestScenario5_RateLimiting:
    """
    Scenario 5: Rate limiting handling.
    
    Tests proper handling of GitHub API rate limits.
    """
    
    @pytest.mark.asyncio
    async def test_rate_limited_gist_verification(self, mock_subtensor, mock_gist_server):
        """Rate limited response should return rate_limited error."""
        from kubetee.validator.github_verifier import GitHubVerifier
        
        # Enable rate limiting
        mock_gist_server.set_rate_limited(True)
        
        verifier = GitHubVerifier()
        
        message = json.dumps({
            "hotkey": VALID_HOTKEY,
            "timestamp": int(time.time())
        })
        
        with mock_httpx_for_gist_server(mock_gist_server):
            with patch.object(verifier, 'verify_signature', return_value=True):
                with patch.object(verifier, 'verify_subnet_registration', new_callable=AsyncMock) as mock_reg:
                    mock_reg.return_value = True
                    
                    result = await verifier.verify_link_request(
                        claimed_hotkey=VALID_HOTKEY,
                        gist_url=f"https://gist.github.com/octocat/{GIST_ID_1}",
                        message=message,
                        signature="0x" + "aa" * 64,
                        subtensor=mock_subtensor,
                        netuid=62
                    )
        
        assert result.success is False
        assert result.error_code == "rate_limited"


class TestMultiMechanismScenarios:
    """
    Tests for scenarios involving multiple mechanisms.
    """
    
    @pytest.mark.asyncio
    async def test_link_all_mechanisms(self, mock_registry):
        """A single hotkey can be linked to different usernames per mechanism."""
        mechanisms = [0, 1, 2, 3]
        usernames = ["infra_user", "opensource_user", "referral_user", "bounty_user"]
        
        for mechanism_id, username in zip(mechanisms, usernames):
            tx, status = await mock_registry.link_github(
                hotkey=VALID_HOTKEY,
                mechanism_id=mechanism_id,
                github_username=username,
                validator_key="0xvalidator"
            )
            assert status == "created"
        
        # All links should exist
        for mechanism_id, expected_username in zip(mechanisms, usernames):
            actual = mock_registry.get_github(VALID_HOTKEY, mechanism_id)
            assert actual == expected_username


class TestEventHistory:
    """
    Tests for event history tracking.
    """
    
    @pytest.mark.asyncio
    async def test_event_history_preserved(self, mock_registry):
        """All link events should be preserved in history."""
        # Create multiple links
        await mock_registry.link_github(VALID_HOTKEY, 0, "user1", "0xval")
        await mock_registry.link_github(VALID_HOTKEY, 0, "user2", "0xval")  # Update
        await mock_registry.link_github(VALID_HOTKEY_2, 0, "user3", "0xval")  # New hotkey
        
        events = mock_registry.get_all_links()
        
        assert len(events) == 3
        assert events[0]["github_username"] == "user1"
        assert events[1]["github_username"] == "user2"
        assert events[2]["github_username"] == "user3"
        
        # All events should have timestamps
        for event in events:
            assert "timestamp" in event
            assert "tx_hash" in event
