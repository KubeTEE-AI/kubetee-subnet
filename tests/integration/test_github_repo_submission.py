"""
Integration Tests: GitHub Repository Submission

Tests the kubetee CLI for GitHub repository submission flow,
using https://github.com/chainswarm/template as the test repository.

This module provides pytest-based integration tests that can mock
the bittensor/subtensor layer without requiring on-chain registration.

Usage:
    pytest tests/integration/test_github_repo_submission.py -v
"""

import os
import json
import time
import pytest
import click
from typing import Optional, Dict, Any
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from dataclasses import dataclass

from click.testing import CliRunner

# Import CLI properly
from kubetee.cli.github import cli, load_wallet


# =============================================================================
# TEST CONFIGURATION
# =============================================================================

TEST_REPO_URL = "https://github.com/chainswarm/template"
TEST_REPO_OWNER = "chainswarm"
TEST_REPO_NAME = "template"

# Valid SS58 hotkey addresses for testing
VALID_HOTKEYS = [
    "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY",
    "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty",
    "5HGjWAeFDfFCWPsjFQdVV2Msvz2XtMktvgocEZcCj68kUMaw",
]

MECHANISM_IDS = {
    "infrastructure": 0,
    "opensource": 1,
    "referral": 2,
    "bounty": 3,
}


# =============================================================================
# MOCK CLASSES (following patterns from tests/acceptance/conftest.py)
# =============================================================================

@dataclass
class MockGist:
    """Mock GitHub Gist."""
    gist_id: str
    owner: str
    public: bool = True
    files: Dict[str, Dict[str, Any]] = None

    def __post_init__(self):
        if self.files is None:
            self.files = {}

    def add_hotkey_file(self, hotkey: str) -> "MockGist":
        """Add HOTKEY.md file with given hotkey."""
        self.files["HOTKEY.md"] = {
            "content": f"# KubeTEE Registration\nhotkey: {hotkey}\n",
            "truncated": False
        }
        return self


class MockSubtensor:
    """
    Mock Bittensor subtensor for testing without on-chain interaction.

    This allows testing the CLI without requiring actual subnet registration.
    """

    def __init__(self):
        self.registered_hotkeys: Dict[int, set] = {62: set()}
        self.hotkey_to_uid: Dict[str, int] = {}
        self._uid_counter = 1

    def register_hotkey(self, hotkey: str, netuid: int = 62) -> int:
        """Register a hotkey on a mock subnet."""
        if netuid not in self.registered_hotkeys:
            self.registered_hotkeys[netuid] = set()

        self.registered_hotkeys[netuid].add(hotkey)
        uid = self._uid_counter
        self.hotkey_to_uid[hotkey] = uid
        self._uid_counter += 1
        return uid

    def get_uid_for_hotkey_on_subnet(
        self, hotkey_ss58: str, netuid: int
    ) -> Optional[int]:
        """Check if hotkey is registered and return UID."""
        if (
            netuid in self.registered_hotkeys
            and hotkey_ss58 in self.registered_hotkeys[netuid]
        ):
            return self.hotkey_to_uid.get(hotkey_ss58, 1)
        return None


class MockWallet:
    """
    Mock Bittensor wallet for testing.

    Simulates wallet operations including signing without requiring
    actual wallet files on disk.
    """

    def __init__(self, name: str = "test_wallet", hotkey_name: str = "default"):
        self.name = name
        self.hotkey_str = VALID_HOTKEYS[0]
        self._hotkey_name = hotkey_name

    def set_hotkey(self, hotkey: str):
        """Set the hotkey address."""
        self.hotkey_str = hotkey

    class HotkeyWrapper:
        """Wrapper for hotkey operations."""

        def __init__(self, wallet: "MockWallet"):
            self._wallet = wallet
            self.ss58_address = wallet.hotkey_str

        def sign(self, message: bytes) -> bytes:
            """Mock sign - returns deterministic signature."""
            msg_hash = hash(message)
            return bytes([msg_hash % 256] * 64)

    class HotkeyFileWrapper:
        """Wrapper for hotkey file checks."""

        def __init__(self):
            self.path = "/mock/path/to/hotkey"

        def exists_on_device(self) -> bool:
            return True

    @property
    def hotkey(self) -> HotkeyWrapper:
        return self.HotkeyWrapper(self)

    @property
    def hotkey_file(self) -> HotkeyFileWrapper:
        return self.HotkeyFileWrapper()


class MockGitHubRegistry:
    """
    Mock GitHub Registry for testing without blockchain.

    Simulates the on-chain registry using in-memory storage.
    """

    def __init__(self):
        self.links: Dict[str, Dict[int, str]] = {}
        self.events: list = []

    def get_github(self, hotkey: str, mechanism_id: int) -> Optional[str]:
        """Get GitHub username for a hotkey and mechanism."""
        if hotkey in self.links:
            return self.links[hotkey].get(mechanism_id)
        return None

    async def link_github(
        self,
        hotkey: str,
        mechanism_id: int,
        github_username: str,
        **kwargs
    ) -> tuple[Optional[str], str]:
        """Link a GitHub username to a hotkey."""
        existing = self.get_github(hotkey, mechanism_id)

        if existing == github_username:
            return (None, "unchanged")

        status = "created" if existing is None else "updated"

        if hotkey not in self.links:
            self.links[hotkey] = {}
        self.links[hotkey][mechanism_id] = github_username

        tx_hash = f"0x{hash((hotkey, mechanism_id, github_username)):064x}"[-66:]
        self.events.append({
            "hotkey": hotkey,
            "mechanism_id": mechanism_id,
            "github_username": github_username,
            "timestamp": int(time.time()),
            "tx_hash": tx_hash
        })

        return (tx_hash, status)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def cli_runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_wallet():
    """Create a mock wallet."""
    return MockWallet()


@pytest.fixture
def mock_subtensor():
    """Create a mock subtensor with pre-registered hotkeys."""
    subtensor = MockSubtensor()
    for hotkey in VALID_HOTKEYS:
        subtensor.register_hotkey(hotkey, 62)
    return subtensor


@pytest.fixture
def mock_registry():
    """Create a mock GitHub registry."""
    return MockGitHubRegistry()


@pytest.fixture
def mock_load_wallet(mock_wallet):
    """Patch load_wallet to return mock wallet."""
    with patch('kubetee.cli.github.load_wallet') as mock_lw:
        mock_lw.return_value = mock_wallet
        yield mock_lw


# =============================================================================
# TEST CLASSES
# =============================================================================

class TestGitHubRepoIntegration:
    """
    Integration tests using https://github.com/chainswarm/template.

    These tests verify the CLI can handle GitHub repository-related
    operations correctly.
    """

    def test_repo_url_parsing(self):
        """Test that repository URL is correctly parsed."""
        import re

        match = re.match(
            r'https://github\.com/([^/]+)/([^/]+)',
            TEST_REPO_URL
        )

        assert match is not None
        assert match.group(1) == TEST_REPO_OWNER
        assert match.group(2) == TEST_REPO_NAME

    def test_gist_url_for_repo_owner(self, cli_runner, mock_load_wallet):
        """Test linking with gist URL from repo owner."""
        # cli imported at module level

        # Create gist URL for repo owner
        gist_url = f"https://gist.github.com/{TEST_REPO_OWNER}/abc123test"

        result = cli_runner.invoke(cli, [
            "link-github",
            "--gist-url", gist_url,
            "--mechanism-id", str(MECHANISM_IDS["opensource"]),
            "--dry-run"
        ])

        assert "DRY RUN" in result.output
        assert TEST_REPO_OWNER in result.output or "gist" in result.output.lower()

    def test_all_mechanism_ids_with_repo(self, cli_runner, mock_load_wallet):
        """Test all mechanism IDs with repo owner's gist."""
        # cli imported at module level

        gist_url = f"https://gist.github.com/{TEST_REPO_OWNER}/testgist123"

        for mech_name, mech_id in MECHANISM_IDS.items():
            result = cli_runner.invoke(cli, [
                "link-github",
                "--gist-url", gist_url,
                "--mechanism-id", str(mech_id),
                "--dry-run"
            ])

            assert result.exit_code == 0, f"Failed for mechanism {mech_name}"
            assert "DRY RUN" in result.output


class TestMockSubtensorIntegration:
    """
    Tests that verify mocking works correctly without on-chain interaction.
    """

    def test_mock_subtensor_registration(self, mock_subtensor):
        """Test mock subtensor registration."""
        # Pre-registered hotkeys should be found
        for hotkey in VALID_HOTKEYS:
            uid = mock_subtensor.get_uid_for_hotkey_on_subnet(hotkey, 62)
            assert uid is not None

        # Unregistered hotkey should return None
        uid = mock_subtensor.get_uid_for_hotkey_on_subnet(
            "5UnregisteredHotkey123", 62
        )
        assert uid is None

    def test_mock_wallet_signing(self, mock_wallet):
        """Test mock wallet can sign messages."""
        message = b"test message"
        signature = mock_wallet.hotkey.sign(message)

        assert isinstance(signature, bytes)
        assert len(signature) == 64

    def test_mock_registry_operations(self, mock_registry):
        """Test mock registry link operations."""
        import asyncio

        hotkey = VALID_HOTKEYS[0]
        mechanism_id = 3
        github_username = TEST_REPO_OWNER

        # Initial link
        tx_hash, status = asyncio.run(
            mock_registry.link_github(hotkey, mechanism_id, github_username)
        )
        assert status == "created"
        assert tx_hash is not None

        # Query the link
        result = mock_registry.get_github(hotkey, mechanism_id)
        assert result == github_username

        # Unchanged link
        tx_hash2, status2 = asyncio.run(
            mock_registry.link_github(hotkey, mechanism_id, github_username)
        )
        assert status2 == "unchanged"
        assert tx_hash2 is None

        # Update link
        tx_hash3, status3 = asyncio.run(
            mock_registry.link_github(hotkey, mechanism_id, "newuser")
        )
        assert status3 == "updated"


class TestCLIWithMockedBittensor:
    """
    CLI tests with fully mocked bittensor layer.

    These tests verify CLI behavior without any on-chain interaction.
    """

    def test_link_github_dry_run_success(self, cli_runner, mock_load_wallet):
        """Test successful dry-run of link-github."""
        # cli imported at module level

        result = cli_runner.invoke(cli, [
            "link-github",
            "--gist-url", f"https://gist.github.com/{TEST_REPO_OWNER}/abc123",
            "--mechanism-id", "3",
            "--validator-url", "http://localhost:8765",
            "--dry-run"
        ])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_link_github_with_all_options(self, cli_runner, mock_load_wallet):
        """Test link-github with all CLI options."""
        # cli imported at module level

        result = cli_runner.invoke(cli, [
            "link-github",
            "--gist-url", f"https://gist.github.com/{TEST_REPO_OWNER}/abc123",
            "--mechanism-id", "3",
            "--wallet-name", "test_wallet",
            "--wallet-hotkey", "default",
            "--validator-url", "http://localhost:8765",
            "--timeout", "30",
            "--dry-run"
        ])

        assert result.exit_code == 0

    def test_status_command_with_mock(self, cli_runner):
        """Test status command."""
        # cli imported at module level

        with patch('kubetee.cli.github.httpx.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.return_value.status_code = 200
            mock_instance.get.return_value.json.return_value = {
                "hotkey": VALID_HOTKEYS[0],
                "is_linked": True,
                "github_username": TEST_REPO_OWNER,
                "mechanism_id": 3,
                "links": [{"mechanism_id": 3, "github_username": TEST_REPO_OWNER}]
            }
            mock_client.return_value.__enter__.return_value = mock_instance

            result = cli_runner.invoke(cli, [
                "status",
                "--hotkey", VALID_HOTKEYS[0],
                "--validator-url", "http://localhost:8765"
            ])

            assert result.exit_code == 0


class TestCornerCases:
    """
    Corner case tests for edge conditions and error handling.
    """

    @pytest.mark.parametrize("invalid_url", [
        "",
        "not-a-url",
        "ftp://gist.github.com/user/123",
        "https://github.com/user/repo",  # Not a gist URL
        "https://gist.github.com/",  # Missing user/id
        "https://gist.github.com/user",  # Missing gist id
    ])
    def test_invalid_gist_urls(self, cli_runner, mock_load_wallet, invalid_url):
        """Test handling of invalid gist URLs."""
        # cli imported at module level

        result = cli_runner.invoke(cli, [
            "link-github",
            "--gist-url", invalid_url,
            "--mechanism-id", "3",
            "--dry-run"
        ])

        # Should either succeed with dry-run showing the URL, or fail gracefully
        # The important thing is no crash
        assert result.exception is None or isinstance(
            result.exception, (SystemExit, click.exceptions.BadParameter)
        )

    @pytest.mark.parametrize("hotkey", [
        "",
        "invalid",
        "5" + "x" * 100,  # Too long
        "5Grw",  # Too short
    ])
    def test_invalid_hotkey_in_status(self, cli_runner, hotkey):
        """Test status command with invalid hotkeys."""
        # cli imported at module level

        result = cli_runner.invoke(cli, [
            "status",
            "--hotkey", hotkey,
            "--validator-url", "http://localhost:8765"
        ])

        # Should handle gracefully (either reject or attempt query)
        # No crashes

    def test_network_timeout(self, cli_runner, mock_load_wallet):
        """Test handling of network timeout."""
        # cli imported at module level
        import httpx

        with patch('kubetee.cli.github.httpx.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.post.side_effect = httpx.TimeoutException("Timeout")
            mock_client.return_value.__enter__.return_value = mock_instance

            result = cli_runner.invoke(cli, [
                "link-github",
                "--gist-url", f"https://gist.github.com/{TEST_REPO_OWNER}/abc",
                "--mechanism-id", "3",
                "--validator-url", "http://localhost:8765"
            ])

            assert "timeout" in result.output.lower() or result.exit_code != 0

    def test_connection_refused(self, cli_runner, mock_load_wallet):
        """Test handling of connection refused."""
        # cli imported at module level
        import httpx

        with patch('kubetee.cli.github.httpx.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client.return_value.__enter__.return_value = mock_instance

            result = cli_runner.invoke(cli, [
                "link-github",
                "--gist-url", f"https://gist.github.com/{TEST_REPO_OWNER}/abc",
                "--mechanism-id", "3",
                "--validator-url", "http://localhost:8765"
            ])

            assert "connect" in result.output.lower() or result.exit_code != 0


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_wallet_from_env(self, cli_runner, mock_load_wallet):
        """Test KUBETEE_WALLET environment variable."""
        # cli imported at module level

        result = cli_runner.invoke(cli, [
            "link-github",
            "--gist-url", f"https://gist.github.com/{TEST_REPO_OWNER}/abc",
            "--mechanism-id", "3",
            "--dry-run"
        ], env={"KUBETEE_WALLET": "env_wallet"})

        assert result.exit_code == 0

    def test_validator_from_env(self, cli_runner, mock_load_wallet):
        """Test KUBETEE_VALIDATOR environment variable."""
        # cli imported at module level

        result = cli_runner.invoke(cli, [
            "link-github",
            "--gist-url", f"https://gist.github.com/{TEST_REPO_OWNER}/abc",
            "--mechanism-id", "3",
            "--dry-run"
        ], env={"KUBETEE_VALIDATOR": "http://custom:9999"})

        assert result.exit_code == 0
        assert "custom:9999" in result.output


class TestRepoSubmissionFlow:
    """
    Tests simulating the full repository submission flow.

    This represents how a user would interact with the CLI when
    submitting code to https://github.com/chainswarm/template.
    """

    def test_full_submission_flow_dry_run(self, cli_runner, mock_load_wallet):
        """Test complete submission flow in dry-run mode."""
        # cli imported at module level

        # Step 1: User creates gist with their hotkey
        gist_url = f"https://gist.github.com/{TEST_REPO_OWNER}/submission123"

        # Step 2: User links GitHub via CLI
        result = cli_runner.invoke(cli, [
            "link-github",
            "--gist-url", gist_url,
            "--mechanism-id", str(MECHANISM_IDS["opensource"]),
            "--dry-run"
        ])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output

        # Step 3: User checks status
        with patch('kubetee.cli.github.httpx.Client') as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.return_value.status_code = 200
            mock_instance.get.return_value.json.return_value = {
                "hotkey": VALID_HOTKEYS[0],
                "is_linked": False,
                "links": []
            }
            mock_client.return_value.__enter__.return_value = mock_instance

            status_result = cli_runner.invoke(cli, [
                "status",
                "--hotkey", VALID_HOTKEYS[0]
            ])

            assert status_result.exit_code == 0

    def test_bounty_submission_flow(self, cli_runner, mock_load_wallet):
        """Test bounty submission flow for opensource contributions."""
        # cli imported at module level

        # For bounty mechanism (id=3)
        gist_url = f"https://gist.github.com/{TEST_REPO_OWNER}/bounty_claim"

        result = cli_runner.invoke(cli, [
            "link-github",
            "--gist-url", gist_url,
            "--mechanism-id", str(MECHANISM_IDS["bounty"]),
            "--validator-url", "http://localhost:8765",
            "--dry-run"
        ])

        assert result.exit_code == 0
        # Bounty mechanism should be mentioned or shown in dry-run
        assert "DRY RUN" in result.output


# =============================================================================
# INTEGRATION WITH EXISTING TEST INFRASTRUCTURE
# =============================================================================

class TestWithExistingMocks:
    """
    Tests using the existing mock infrastructure from tests/acceptance/.

    This ensures compatibility with the existing test patterns.
    """

    def test_using_acceptance_test_patterns(self, cli_runner):
        """Test using patterns from acceptance tests."""
        # Pattern from tests/acceptance/test_cli_acceptance.py
        # bittensor is imported inside load_wallet, so we patch load_wallet
        with patch('kubetee.cli.github.load_wallet') as mock_lw:
            mock_wallet = MockWallet()
            mock_lw.return_value = mock_wallet

            result = cli_runner.invoke(cli, [
                "link-github",
                "--gist-url", "https://gist.github.com/octocat/abc123def456",
                "--mechanism-id", "3",
                "--dry-run"
            ])

            assert "DRY RUN" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
