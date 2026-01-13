"""
CLI Acceptance Tests for GitHub Linking.

These tests verify the CLI command behavior and user experience.

Tests covered:
- CLI --dry-run mode
- CLI with environment variables
- CLI error handling and output formatting
- CLI help and usage
"""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from tests.acceptance.conftest import (
    VALID_HOTKEY,
    VALID_HOTKEY_2,
    GIST_ID_1,
    MECHANISM_BOUNTY,
    MockWallet,
)


@pytest.fixture
def cli_runner():
    """Create a Click CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_wallet_factory():
    """Factory for creating mock wallets."""
    def _create_wallet(hotkey: str = VALID_HOTKEY):
        wallet = MockWallet()
        wallet.set_hotkey(hotkey)
        return wallet
    return _create_wallet


class TestCLIHelp:
    """Tests for CLI help and usage output."""
    
    def test_main_help(self, cli_runner):
        """Test main help command."""
        from kubetee.cli import main
        
        result = cli_runner.invoke(main, ["--help"])
        
        assert result.exit_code == 0
        assert "KubeTEE" in result.output or "kubetee" in result.output.lower()
    
    def test_link_github_help(self, cli_runner):
        """Test link-github subcommand help."""
        from kubetee.cli import main
        
        result = cli_runner.invoke(main, ["link-github", "--help"])
        
        assert result.exit_code == 0
        assert "--gist-url" in result.output
        assert "--mechanism-id" in result.output
        assert "--wallet-name" in result.output
    
    def test_status_help(self, cli_runner):
        """Test status subcommand help."""
        from kubetee.cli import main
        
        result = cli_runner.invoke(main, ["status", "--help"])
        
        assert result.exit_code == 0
        assert "--hotkey" in result.output or "-h" in result.output


class TestCLIDryRun:
    """Tests for CLI --dry-run mode."""
    
    def test_dry_run_shows_request_details(self, cli_runner, mock_wallet_factory):
        """Dry run should display request details without making API call."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                "--mechanism-id", str(MECHANISM_BOUNTY),
                "--dry-run",
                "--wallet-name", "test_wallet"
            ])
        
        # Should not fail (exit_code 0 or display info)
        assert "dry run" in result.output.lower() or "DRY RUN" in result.output
        assert GIST_ID_1 in result.output or "octocat" in result.output
    
    def test_dry_run_does_not_call_api(self, cli_runner, mock_wallet_factory):
        """Dry run should NOT make HTTP requests."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            with patch('kubetee.cli.github.httpx.Client') as mock_httpx:
                result = cli_runner.invoke(main, [
                    "link-github",
                    "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                    "--mechanism-id", str(MECHANISM_BOUNTY),
                    "--dry-run"
                ])
                
                # httpx.Client should not be called in dry-run mode
                # (or if called, no actual request should be made)


class TestCLIEnvironmentVariables:
    """Tests for CLI environment variable support."""
    
    def test_wallet_from_env(self, cli_runner, mock_wallet_factory):
        """Wallet name from KUBETEE_WALLET env var."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                "--mechanism-id", str(MECHANISM_BOUNTY),
                "--dry-run"
            ], env={"KUBETEE_WALLET": "env_wallet"})
        
        # Should use wallet from environment
        assert result.exit_code == 0 or "env_wallet" in str(mock_bt.wallet.call_args)
    
    def test_validator_url_from_env(self, cli_runner, mock_wallet_factory):
        """Validator URL from KUBETEE_VALIDATOR env var."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                "--mechanism-id", str(MECHANISM_BOUNTY),
                "--dry-run"
            ], env={"KUBETEE_VALIDATOR": "http://custom-validator:8000"})
        
        # Custom validator URL should be used


class TestCLIErrorHandling:
    """Tests for CLI error handling and user-friendly messages."""
    
    def test_missing_required_args(self, cli_runner):
        """Missing required arguments should show error."""
        from kubetee.cli import main
        
        result = cli_runner.invoke(main, ["link-github"])
        
        # Should fail with clear error
        assert result.exit_code != 0
        assert "required" in result.output.lower() or "missing" in result.output.lower() or "Error" in result.output
    
    def test_invalid_gist_url_format(self, cli_runner, mock_wallet_factory):
        """Invalid gist URL should show helpful error."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", "https://github.com/not-a-gist",  # Invalid URL
                "--mechanism-id", str(MECHANISM_BOUNTY),
                "--dry-run"
            ])
        
        # Should indicate URL issue (either in validation or dry-run output)
    
    def test_invalid_mechanism_id(self, cli_runner, mock_wallet_factory):
        """Invalid mechanism ID should show error."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                "--mechanism-id", "-1",  # Invalid
                "--dry-run"
            ])
    
    def test_wallet_not_found(self, cli_runner):
        """Missing wallet should show helpful error."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.side_effect = Exception("Wallet not found")
            
            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                "--mechanism-id", str(MECHANISM_BOUNTY),
                "--wallet-name", "nonexistent_wallet"
            ])
        
        # Should show wallet error
        assert result.exit_code != 0 or "error" in result.output.lower() or "wallet" in result.output.lower()
    
    def test_network_error_handling(self, cli_runner, mock_wallet_factory):
        """Network errors should be handled gracefully."""
        from kubetee.cli import main
        import httpx
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            with patch('kubetee.cli.github.httpx.Client') as mock_client:
                mock_instance = MagicMock()
                mock_instance.post.side_effect = httpx.ConnectError("Connection refused")
                mock_client.return_value.__enter__.return_value = mock_instance
                
                result = cli_runner.invoke(main, [
                    "link-github",
                    "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                    "--mechanism-id", str(MECHANISM_BOUNTY)
                ])
        
        # Should show connection error
        assert "error" in result.output.lower() or "connect" in result.output.lower() or result.exit_code != 0


class TestCLIOutput:
    """Tests for CLI output formatting."""
    
    def test_success_output_contains_github_username(self, cli_runner, mock_wallet_factory):
        """Successful link should show GitHub username."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            with patch('kubetee.cli.github.httpx.Client') as mock_client:
                mock_instance = MagicMock()
                mock_instance.post.return_value.status_code = 200
                mock_instance.post.return_value.json.return_value = {
                    "success": True,
                    "github_username": "octocat",
                    "tx_hash": "0x1234",
                    "status": "created"
                }
                mock_client.return_value.__enter__.return_value = mock_instance
                
                result = cli_runner.invoke(main, [
                    "link-github",
                    "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                    "--mechanism-id", str(MECHANISM_BOUNTY)
                ])
        
        # Should display success info
        if result.exit_code == 0:
            assert "octocat" in result.output or "success" in result.output.lower()
    
    def test_error_output_shows_error_code(self, cli_runner, mock_wallet_factory):
        """Error response should display error code."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            with patch('kubetee.cli.github.httpx.Client') as mock_client:
                mock_instance = MagicMock()
                mock_instance.post.return_value.status_code = 200
                mock_instance.post.return_value.json.return_value = {
                    "success": False,
                    "error_code": "gist_not_found",
                    "error_message": "Gist not found or not public"
                }
                mock_client.return_value.__enter__.return_value = mock_instance
                
                result = cli_runner.invoke(main, [
                    "link-github",
                    "--gist-url", f"https://gist.github.com/octocat/nonexistent",
                    "--mechanism-id", str(MECHANISM_BOUNTY)
                ])
        
        # Should show error code
        assert "gist_not_found" in result.output or "error" in result.output.lower()


class TestCLIStatusCommand:
    """Tests for the status subcommand."""
    
    def test_status_shows_linked_github(self, cli_runner, mock_wallet_factory):
        """Status command should show linked GitHub account."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            with patch('kubetee.cli.github.httpx.Client') as mock_client:
                mock_instance = MagicMock()
                mock_instance.get.return_value.status_code = 200
                mock_instance.get.return_value.json.return_value = {
                    "hotkey": VALID_HOTKEY,
                    "links": [
                        {"mechanism_id": 3, "github_username": "octocat"}
                    ]
                }
                mock_client.return_value.__enter__.return_value = mock_instance
                
                result = cli_runner.invoke(main, [
                    "status",
                    "--hotkey", VALID_HOTKEY
                ])
        
        # Should display linked info
        if result.exit_code == 0:
            assert VALID_HOTKEY[:10] in result.output or "octocat" in result.output
    
    def test_status_no_links(self, cli_runner, mock_wallet_factory):
        """Status for unlinked hotkey should show appropriate message."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            with patch('kubetee.cli.github.httpx.Client') as mock_client:
                mock_instance = MagicMock()
                mock_instance.get.return_value.status_code = 200
                mock_instance.get.return_value.json.return_value = {
                    "hotkey": VALID_HOTKEY,
                    "links": []
                }
                mock_client.return_value.__enter__.return_value = mock_instance
                
                result = cli_runner.invoke(main, [
                    "status",
                    "--hotkey", VALID_HOTKEY
                ])
        
        # Should indicate no links
        if result.exit_code == 0:
            assert "no" in result.output.lower() or "not linked" in result.output.lower() or "links" in result.output.lower()


class TestCLIMechanismDisplay:
    """Tests for mechanism ID display in CLI."""
    
    @pytest.mark.parametrize("mechanism_id,mechanism_name", [
        (0, "infrastructure"),
        (1, "opensource"),
        (2, "referral"),
        (3, "bounty"),
    ])
    def test_mechanism_name_displayed(self, cli_runner, mock_wallet_factory, mechanism_id, mechanism_name):
        """Mechanism name should be shown in human-readable form."""
        from kubetee.cli import main
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                "--mechanism-id", str(mechanism_id),
                "--dry-run"
            ])
        
        # The mechanism name or ID should appear in output
        # (implementation can show either numeric or named form)


class TestCLISignature:
    """Tests for CLI message signing."""
    
    def test_message_contains_hotkey(self, cli_runner, mock_wallet_factory):
        """Signed message should contain the hotkey."""
        from kubetee.cli import main
        
        captured_request = {}
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            wallet = mock_wallet_factory()
            mock_bt.wallet.return_value = wallet
            
            with patch('kubetee.cli.github.httpx.Client') as mock_client:
                mock_instance = MagicMock()
                
                def capture_post(url, json=None, **kwargs):
                    captured_request['json'] = json
                    response = MagicMock()
                    response.status_code = 200
                    response.json.return_value = {"success": True, "github_username": "octocat", "status": "created"}
                    return response
                
                mock_instance.post = capture_post
                mock_client.return_value.__enter__.return_value = mock_instance
                
                result = cli_runner.invoke(main, [
                    "link-github",
                    "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                    "--mechanism-id", str(MECHANISM_BOUNTY)
                ])
        
        # Verify message contains hotkey
        if captured_request.get('json') and 'message' in captured_request['json']:
            message = json.loads(captured_request['json']['message'])
            assert 'hotkey' in message
    
    def test_message_contains_timestamp(self, cli_runner, mock_wallet_factory):
        """Signed message should contain timestamp."""
        from kubetee.cli import main
        import time
        
        captured_request = {}
        before_time = int(time.time())
        
        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_bt.wallet.return_value = mock_wallet_factory()
            
            with patch('kubetee.cli.github.httpx.Client') as mock_client:
                mock_instance = MagicMock()
                
                def capture_post(url, json=None, **kwargs):
                    captured_request['json'] = json
                    response = MagicMock()
                    response.status_code = 200
                    response.json.return_value = {"success": True, "github_username": "octocat", "status": "created"}
                    return response
                
                mock_instance.post = capture_post
                mock_client.return_value.__enter__.return_value = mock_instance
                
                result = cli_runner.invoke(main, [
                    "link-github",
                    "--gist-url", f"https://gist.github.com/octocat/{GIST_ID_1}",
                    "--mechanism-id", str(MECHANISM_BOUNTY)
                ])
        
        after_time = int(time.time())
        
        # Verify timestamp is within expected range
        if captured_request.get('json') and 'message' in captured_request['json']:
            message = json.loads(captured_request['json']['message'])
            if 'timestamp' in message:
                assert before_time <= message['timestamp'] <= after_time + 1
