"""
Unit tests for GitHubVerifier class.

Tests cover:
- Hotkey format validation
- Gist URL parsing
- Hotkey extraction from content
- Signature verification (mocked)
- GitHub API calls (mocked)
- Rate limiting handling
- Full verification flow
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json

from kubetee.validator.github_verifier import GitHubVerifier, VerificationResult


# Test hotkeys - valid SS58 format starting with 5
VALID_HOTKEY = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
VALID_HOTKEY_2 = "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"


class TestHotkeyValidation:
    """Test hotkey format validation."""
    
    @pytest.fixture
    def verifier(self):
        """Create a GitHubVerifier instance for testing."""
        return GitHubVerifier()
    
    def test_valid_hotkey_format(self, verifier):
        """Valid SS58 hotkey starting with 5 should match pattern."""
        assert verifier.HOTKEY_PATTERN.fullmatch(VALID_HOTKEY) is not None
    
    def test_valid_hotkey_format_alternative(self, verifier):
        """Another valid SS58 hotkey should match pattern."""
        assert verifier.HOTKEY_PATTERN.fullmatch(VALID_HOTKEY_2) is not None
    
    def test_invalid_hotkey_too_short(self, verifier):
        """Hotkey that is too short should not match."""
        invalid = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNeh"  # Only 38 chars
        assert verifier.HOTKEY_PATTERN.fullmatch(invalid) is None
    
    def test_invalid_hotkey_too_long(self, verifier):
        """Hotkey that is too long should not match."""
        invalid = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQYabc"  # 51 chars
        assert verifier.HOTKEY_PATTERN.fullmatch(invalid) is None
    
    def test_invalid_hotkey_wrong_prefix(self, verifier):
        """Hotkey not starting with 5 should not match."""
        invalid = "1GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
        assert verifier.HOTKEY_PATTERN.fullmatch(invalid) is None
    
    def test_invalid_hotkey_special_chars(self, verifier):
        """Hotkey with special characters should not match."""
        invalid = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKut!@"
        assert verifier.HOTKEY_PATTERN.fullmatch(invalid) is None
    
    def test_invalid_hotkey_empty(self, verifier):
        """Empty string should not match."""
        assert verifier.HOTKEY_PATTERN.fullmatch("") is None


class TestGistUrlParsing:
    """Test gist URL parsing."""
    
    @pytest.fixture
    def verifier(self):
        return GitHubVerifier()
    
    def test_extract_gist_id_full_url(self, verifier):
        """Extract gist ID and username from full URL."""
        url = "https://gist.github.com/octocat/abc123def456"
        match = verifier.GIST_URL_PATTERN.match(url)
        assert match is not None
        assert match.group(1) == "octocat"
        assert match.group(2) == "abc123def456"
    
    def test_extract_gist_id_http(self, verifier):
        """Extract gist ID from HTTP URL (non-HTTPS)."""
        url = "http://gist.github.com/user123/deadbeef1234"
        match = verifier.GIST_URL_PATTERN.match(url)
        assert match is not None
        assert match.group(1) == "user123"
        assert match.group(2) == "deadbeef1234"
    
    def test_extract_gist_id_long_id(self, verifier):
        """Extract gist ID with longer hex ID."""
        url = "https://gist.github.com/testuser/1234567890abcdef1234567890abcdef"
        match = verifier.GIST_URL_PATTERN.match(url)
        assert match is not None
        assert match.group(2) == "1234567890abcdef1234567890abcdef"
    
    def test_invalid_gist_url_wrong_domain(self, verifier):
        """Invalid URL with wrong domain should not match."""
        url = "https://github.com/octocat/abc123def456"
        assert verifier.GIST_URL_PATTERN.match(url) is None
    
    def test_invalid_gist_url_no_id(self, verifier):
        """Invalid URL without gist ID should not match."""
        url = "https://gist.github.com/octocat/"
        assert verifier.GIST_URL_PATTERN.match(url) is None
    
    def test_invalid_gist_url_uppercase_hex(self, verifier):
        """Gist ID with uppercase hex should not match (GitHub uses lowercase)."""
        url = "https://gist.github.com/octocat/ABC123DEF456"
        # Note: The regex uses [a-f0-9]+ so uppercase won't match
        assert verifier.GIST_URL_PATTERN.match(url) is None
    
    def test_invalid_gist_url_empty(self, verifier):
        """Empty string should not match."""
        assert verifier.GIST_URL_PATTERN.match("") is None


class TestHotkeyExtraction:
    """Test hotkey extraction from HOTKEY.md content."""
    
    @pytest.fixture
    def verifier(self):
        return GitHubVerifier()
    
    def test_extract_hotkey_standard_format(self, verifier):
        """Extract hotkey from standard format."""
        content = f"# My Hotkey\nhotkey: {VALID_HOTKEY}\n"
        result = verifier.extract_hotkey_from_content(content)
        assert result == VALID_HOTKEY
    
    def test_extract_hotkey_no_newline(self, verifier):
        """Extract hotkey without trailing newline."""
        content = f"hotkey: {VALID_HOTKEY}"
        result = verifier.extract_hotkey_from_content(content)
        assert result == VALID_HOTKEY
    
    def test_extract_hotkey_extra_whitespace(self, verifier):
        """Extract hotkey with extra whitespace."""
        content = f"hotkey:   {VALID_HOTKEY}  \n"
        result = verifier.extract_hotkey_from_content(content)
        assert result == VALID_HOTKEY
    
    def test_extract_hotkey_multiline_content(self, verifier):
        """Extract hotkey from multiline content."""
        content = f"""
# KubeTEE GitHub Linking
## Hotkey Registration

hotkey: {VALID_HOTKEY}

## Notes
This is my miner hotkey for subnet 62.
"""
        result = verifier.extract_hotkey_from_content(content)
        assert result == VALID_HOTKEY
    
    def test_extract_hotkey_missing(self, verifier):
        """Return None when hotkey is missing."""
        content = "# My Hotkey\nNo hotkey here\n"
        result = verifier.extract_hotkey_from_content(content)
        assert result is None
    
    def test_extract_hotkey_invalid_format(self, verifier):
        """Return None when hotkey format is invalid."""
        content = "hotkey: invalid_hotkey_here\n"
        result = verifier.extract_hotkey_from_content(content)
        assert result is None
    
    def test_extract_hotkey_wrong_prefix(self, verifier):
        """Return None when hotkey has wrong prefix."""
        content = "hotkey: 1GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY\n"
        result = verifier.extract_hotkey_from_content(content)
        assert result is None
    
    def test_extract_hotkey_empty_content(self, verifier):
        """Return None for empty content."""
        result = verifier.extract_hotkey_from_content("")
        assert result is None


class TestSignatureVerification:
    """Test signature verification with mocked Keypair."""
    
    @pytest.fixture
    def verifier(self):
        return GitHubVerifier()
    
    @patch('kubetee.validator.github_verifier.Keypair')
    def test_verify_signature_valid(self, mock_keypair_class, verifier):
        """Valid signature should return True."""
        # Setup mock
        mock_keypair = Mock()
        mock_keypair.verify.return_value = True
        mock_keypair_class.return_value = mock_keypair
        
        message = json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890})
        signature = "0x" + "aa" * 64  # 128 hex chars
        
        result = verifier.verify_signature(message, signature, VALID_HOTKEY)
        
        assert result is True
        mock_keypair_class.assert_called_once_with(ss58_address=VALID_HOTKEY)
        mock_keypair.verify.assert_called_once()
    
    @patch('kubetee.validator.github_verifier.Keypair')
    def test_verify_signature_invalid(self, mock_keypair_class, verifier):
        """Invalid signature should return False."""
        mock_keypair = Mock()
        mock_keypair.verify.return_value = False
        mock_keypair_class.return_value = mock_keypair
        
        message = json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890})
        signature = "0x" + "bb" * 64
        
        result = verifier.verify_signature(message, signature, VALID_HOTKEY)
        
        assert result is False
    
    @patch('kubetee.validator.github_verifier.Keypair')
    def test_verify_signature_without_0x_prefix(self, mock_keypair_class, verifier):
        """Signature without 0x prefix should be handled."""
        mock_keypair = Mock()
        mock_keypair.verify.return_value = True
        mock_keypair_class.return_value = mock_keypair
        
        message = json.dumps({"hotkey": VALID_HOTKEY})
        signature = "aa" * 64  # No 0x prefix
        
        result = verifier.verify_signature(message, signature, VALID_HOTKEY)
        
        assert result is True
    
    @patch('kubetee.validator.github_verifier.Keypair')
    def test_verify_signature_exception(self, mock_keypair_class, verifier):
        """Exception during verification should return False."""
        mock_keypair_class.side_effect = Exception("Keypair error")
        
        message = json.dumps({"hotkey": VALID_HOTKEY})
        signature = "0xdeadbeef"
        
        result = verifier.verify_signature(message, signature, VALID_HOTKEY)
        
        assert result is False
    
    @patch('kubetee.validator.github_verifier.Keypair')
    def test_verify_signature_invalid_hex(self, mock_keypair_class, verifier):
        """Invalid hex signature should return False."""
        # The bytes.fromhex will raise ValueError for invalid hex
        message = json.dumps({"hotkey": VALID_HOTKEY})
        signature = "0xZZZZZ"  # Invalid hex
        
        result = verifier.verify_signature(message, signature, VALID_HOTKEY)
        
        assert result is False


class TestGistVerification:
    """Test gist verification with mocked HTTP client."""
    
    @pytest.fixture
    def verifier(self):
        return GitHubVerifier()
    
    @pytest.mark.asyncio
    async def test_verify_gist_exists(self, verifier):
        """Successful gist verification."""
        gist_url = "https://gist.github.com/octocat/abc123def456"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "public": True,
            "owner": {"login": "octocat"},
            "files": {
                "HOTKEY.md": {
                    "content": f"hotkey: {VALID_HOTKEY}",
                    "truncated": False
                }
            }
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            success, username, hotkey = await verifier.verify_gist(gist_url)
        
        assert success is True
        assert username == "octocat"
        assert hotkey == VALID_HOTKEY
    
    @pytest.mark.asyncio
    async def test_verify_gist_not_found(self, verifier):
        """Gist not found returns error."""
        gist_url = "https://gist.github.com/octocat/abc123def456"
        
        mock_response = Mock()
        mock_response.status_code = 404
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            success, error_code, error_message = await verifier.verify_gist(gist_url)
        
        assert success is False
        assert error_code == "gist_not_found"
        assert "not found" in error_message.lower()
    
    @pytest.mark.asyncio
    async def test_verify_gist_private(self, verifier):
        """Private gist returns error."""
        gist_url = "https://gist.github.com/octocat/abc123def456"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "public": False,
            "owner": {"login": "octocat"},
            "files": {}
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            success, error_code, error_message = await verifier.verify_gist(gist_url)
        
        assert success is False
        assert error_code == "gist_not_found"
        assert "not public" in error_message.lower()
    
    @pytest.mark.asyncio
    async def test_verify_gist_missing_hotkey_md(self, verifier):
        """Gist without HOTKEY.md returns error."""
        gist_url = "https://gist.github.com/octocat/abc123def456"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "public": True,
            "owner": {"login": "octocat"},
            "files": {
                "README.md": {"content": "Hello world"}
            }
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            success, error_code, error_message = await verifier.verify_gist(gist_url)
        
        assert success is False
        assert error_code == "hotkey_md_missing"
    
    @pytest.mark.asyncio
    async def test_verify_gist_invalid_hotkey_in_file(self, verifier):
        """Gist with invalid hotkey format returns error."""
        gist_url = "https://gist.github.com/octocat/abc123def456"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "public": True,
            "owner": {"login": "octocat"},
            "files": {
                "HOTKEY.md": {
                    "content": "hotkey: invalid_hotkey",
                    "truncated": False
                }
            }
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            success, error_code, error_message = await verifier.verify_gist(gist_url)
        
        assert success is False
        assert error_code == "invalid_hotkey_format"
    
    @pytest.mark.asyncio
    async def test_verify_gist_invalid_url_format(self, verifier):
        """Invalid gist URL format returns error."""
        gist_url = "https://github.com/octocat/repo"  # Not a gist URL
        
        success, error_code, error_message = await verifier.verify_gist(gist_url)
        
        assert success is False
        assert error_code == "gist_not_found"
        assert "invalid" in error_message.lower()


class TestRateLimiting:
    """Test rate limiting handling."""
    
    @pytest.fixture
    def verifier(self):
        return GitHubVerifier()
    
    @pytest.mark.asyncio
    async def test_rate_limited_gist_graceful(self, verifier):
        """Rate limited response handled gracefully."""
        gist_url = "https://gist.github.com/octocat/abc123def456"
        
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.headers = {"X-RateLimit-Remaining": "0"}
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            success, error_code, error_message = await verifier.verify_gist(gist_url)
        
        assert success is False
        assert error_code == "rate_limited"
        assert "rate limit" in error_message.lower()
    
    @pytest.mark.asyncio
    async def test_rate_limited_user_verification(self, verifier):
        """Rate limited user verification returns True (lenient)."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.headers = {"X-RateLimit-Remaining": "0"}
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await verifier.verify_github_user("octocat")
        
        # When rate limited, user verification is lenient and returns True
        assert result is True


class TestGitHubUserVerification:
    """Test GitHub user verification."""
    
    @pytest.fixture
    def verifier(self):
        return GitHubVerifier()
    
    @pytest.mark.asyncio
    async def test_verify_github_user_exists(self, verifier):
        """Existing user verification returns True."""
        mock_response = Mock()
        mock_response.status_code = 200
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await verifier.verify_github_user("octocat")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_verify_github_user_not_found(self, verifier):
        """Non-existing user verification returns False."""
        mock_response = Mock()
        mock_response.status_code = 404
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await verifier.verify_github_user("nonexistent_user_12345")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_verify_github_user_timeout(self, verifier):
        """Timeout returns False."""
        import httpx
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await verifier.verify_github_user("octocat")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_verify_github_user_network_error(self, verifier):
        """Network error returns False."""
        import httpx
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.RequestError("Network error")
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await verifier.verify_github_user("octocat")
        
        assert result is False


class TestSubnetRegistration:
    """Test subnet registration verification."""
    
    @pytest.fixture
    def verifier(self):
        return GitHubVerifier()
    
    @pytest.mark.asyncio
    async def test_verify_subnet_registration_registered(self, verifier):
        """Registered hotkey returns True."""
        mock_subtensor = Mock()
        mock_subtensor.get_uid_for_hotkey_on_subnet.return_value = 123
        
        result = await verifier.verify_subnet_registration(
            VALID_HOTKEY, mock_subtensor, netuid=62
        )
        
        assert result is True
        mock_subtensor.get_uid_for_hotkey_on_subnet.assert_called_once_with(
            hotkey_ss58=VALID_HOTKEY,
            netuid=62
        )
    
    @pytest.mark.asyncio
    async def test_verify_subnet_registration_not_registered(self, verifier):
        """Unregistered hotkey returns False."""
        mock_subtensor = Mock()
        mock_subtensor.get_uid_for_hotkey_on_subnet.return_value = None
        
        result = await verifier.verify_subnet_registration(
            VALID_HOTKEY, mock_subtensor, netuid=62
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_verify_subnet_registration_exception(self, verifier):
        """Exception returns False."""
        mock_subtensor = Mock()
        mock_subtensor.get_uid_for_hotkey_on_subnet.side_effect = Exception("Connection failed")
        
        result = await verifier.verify_subnet_registration(
            VALID_HOTKEY, mock_subtensor, netuid=62
        )
        
        assert result is False


class TestFullVerificationFlow:
    """Test the complete verification flow."""
    
    @pytest.fixture
    def verifier(self):
        return GitHubVerifier()
    
    @pytest.mark.asyncio
    async def test_verify_link_request_success(self, verifier):
        """Successful full verification flow."""
        mock_subtensor = Mock()
        mock_subtensor.get_uid_for_hotkey_on_subnet.return_value = 1
        
        message = json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890})
        gist_url = "https://gist.github.com/octocat/abc123def456"
        
        # Mock signature verification
        with patch.object(verifier, 'verify_signature', return_value=True):
            # Mock gist verification
            with patch.object(verifier, 'verify_gist', new_callable=AsyncMock) as mock_gist:
                mock_gist.return_value = (True, "octocat", VALID_HOTKEY)
                
                # Mock user verification
                with patch.object(verifier, 'verify_github_user', new_callable=AsyncMock) as mock_user:
                    mock_user.return_value = True
                    
                    result = await verifier.verify_link_request(
                        claimed_hotkey=VALID_HOTKEY,
                        gist_url=gist_url,
                        message=message,
                        signature="0x" + "aa" * 64,
                        subtensor=mock_subtensor,
                        netuid=62
                    )
        
        assert result.success is True
        assert result.github_username == "octocat"
        assert result.error_code is None
    
    @pytest.mark.asyncio
    async def test_verify_link_request_hotkey_not_registered(self, verifier):
        """Unregistered hotkey fails verification."""
        mock_subtensor = Mock()
        mock_subtensor.get_uid_for_hotkey_on_subnet.return_value = None
        
        message = json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890})
        
        result = await verifier.verify_link_request(
            claimed_hotkey=VALID_HOTKEY,
            gist_url="https://gist.github.com/octocat/abc123def456",
            message=message,
            signature="0x" + "aa" * 64,
            subtensor=mock_subtensor,
            netuid=62
        )
        
        assert result.success is False
        assert result.error_code == "hotkey_not_registered"
    
    @pytest.mark.asyncio
    async def test_verify_link_request_invalid_signature(self, verifier):
        """Invalid signature fails verification."""
        mock_subtensor = Mock()
        mock_subtensor.get_uid_for_hotkey_on_subnet.return_value = 1
        
        message = json.dumps({"hotkey": VALID_HOTKEY, "timestamp": 1234567890})
        
        with patch.object(verifier, 'verify_signature', return_value=False):
            result = await verifier.verify_link_request(
                claimed_hotkey=VALID_HOTKEY,
                gist_url="https://gist.github.com/octocat/abc123def456",
                message=message,
                signature="0x" + "aa" * 64,
                subtensor=mock_subtensor,
                netuid=62
            )
        
        assert result.success is False
        assert result.error_code == "invalid_signature"
    
    @pytest.mark.asyncio
    async def test_verify_link_request_hotkey_mismatch(self, verifier):
        """Mismatched hotkeys fail verification."""
        mock_subtensor = Mock()
        mock_subtensor.get_uid_for_hotkey_on_subnet.return_value = 1
        
        # Message with different hotkey than claimed
        message = json.dumps({"hotkey": VALID_HOTKEY_2, "timestamp": 1234567890})
        
        with patch.object(verifier, 'verify_signature', return_value=True):
            result = await verifier.verify_link_request(
                claimed_hotkey=VALID_HOTKEY,  # Different from message hotkey
                gist_url="https://gist.github.com/octocat/abc123def456",
                message=message,
                signature="0x" + "aa" * 64,
                subtensor=mock_subtensor,
                netuid=62
            )
        
        assert result.success is False
        assert result.error_code == "hotkey_mismatch"
    
    @pytest.mark.asyncio
    async def test_verify_link_request_invalid_message_json(self, verifier):
        """Invalid JSON message fails verification."""
        mock_subtensor = Mock()
        mock_subtensor.get_uid_for_hotkey_on_subnet.return_value = 1
        
        message = "not valid json"
        
        result = await verifier.verify_link_request(
            claimed_hotkey=VALID_HOTKEY,
            gist_url="https://gist.github.com/octocat/abc123def456",
            message=message,
            signature="0x" + "aa" * 64,
            subtensor=mock_subtensor,
            netuid=62
        )
        
        assert result.success is False
        assert result.error_code == "invalid_message_format"
    
    @pytest.mark.asyncio
    async def test_verify_link_request_missing_hotkey_in_message(self, verifier):
        """Message without hotkey field fails verification."""
        mock_subtensor = Mock()
        mock_subtensor.get_uid_for_hotkey_on_subnet.return_value = 1
        
        message = json.dumps({"timestamp": 1234567890})  # No hotkey field
        
        result = await verifier.verify_link_request(
            claimed_hotkey=VALID_HOTKEY,
            gist_url="https://gist.github.com/octocat/abc123def456",
            message=message,
            signature="0x" + "aa" * 64,
            subtensor=mock_subtensor,
            netuid=62
        )
        
        assert result.success is False
        assert result.error_code == "invalid_message_format"


class TestVerifierInitialization:
    """Test verifier initialization options."""
    
    def test_default_initialization(self):
        """Default initialization without token."""
        verifier = GitHubVerifier()
        
        assert verifier.github_token is None
        assert verifier.timeout == 30.0
    
    def test_initialization_with_token(self):
        """Initialization with GitHub token."""
        verifier = GitHubVerifier(github_token="ghp_test123")
        
        assert verifier.github_token == "ghp_test123"
        assert "Authorization" in verifier._get_http_headers()
        assert verifier._get_http_headers()["Authorization"] == "token ghp_test123"
    
    def test_initialization_with_custom_timeout(self):
        """Initialization with custom timeout."""
        verifier = GitHubVerifier(timeout=60.0)
        
        assert verifier.timeout == 60.0
    
    def test_http_headers_without_token(self):
        """HTTP headers without token."""
        verifier = GitHubVerifier()
        headers = verifier._get_http_headers()
        
        assert "Authorization" not in headers
        assert headers["Accept"] == "application/vnd.github.v3+json"
        assert "KubeTEE" in headers["User-Agent"]
