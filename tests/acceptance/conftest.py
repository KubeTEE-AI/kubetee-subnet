"""
Shared fixtures for acceptance tests.

Provides:
- Mock GitHub gist server
- Mock Bittensor subtensor
- Mock wallet with signing capabilities
- FastAPI test client with configured context
- Hardhat node management (for contract integration tests)
"""

import pytest
import json
import time
import asyncio
import subprocess
import os
from typing import Dict, Optional, Generator, Any
from dataclasses import dataclass, field
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx


# Test hotkeys - valid SS58 format starting with 5
VALID_HOTKEY = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
VALID_HOTKEY_2 = "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"
VALID_HOTKEY_3 = "5HGjWAeFDfFCWPsjFQdVV2Msvz2XtMktvgocEZcCj68kUMaw"

# Test gist IDs (lowercase hex)
GIST_ID_1 = "abc123def456"
GIST_ID_2 = "def456789abc"

# Mechanism IDs
MECHANISM_INFRASTRUCTURE = 0
MECHANISM_OPENSOURCE = 1
MECHANISM_REFERRAL = 2
MECHANISM_BOUNTY = 3


@dataclass
class MockGist:
    """Represents a mock GitHub gist."""
    gist_id: str
    owner: str
    public: bool = True
    files: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def add_hotkey_file(self, hotkey: str, truncated: bool = False):
        """Add a HOTKEY.md file with the given hotkey."""
        self.files["HOTKEY.md"] = {
            "content": f"# KubeTEE Registration\nhotkey: {hotkey}\n",
            "truncated": truncated
        }
        return self
    
    def to_api_response(self) -> dict:
        """Convert to GitHub API response format."""
        return {
            "id": self.gist_id,
            "public": self.public,
            "owner": {"login": self.owner},
            "files": self.files
        }


class MockGistServer:
    """
    Mock GitHub Gist API server for testing.
    
    Simulates GitHub API responses for gist and user verification.
    """
    
    def __init__(self):
        self.gists: Dict[str, MockGist] = {}
        self.users: set = {"octocat", "testuser", "minerdev"}
        self.rate_limited: bool = False
        self.rate_limit_remaining: int = 60
    
    def add_gist(self, gist: MockGist) -> "MockGistServer":
        """Add a gist to the mock server."""
        self.gists[gist.gist_id] = gist
        return self
    
    def remove_gist(self, gist_id: str):
        """Remove a gist from the mock server."""
        self.gists.pop(gist_id, None)
    
    def add_user(self, username: str):
        """Add a user to the mock server."""
        self.users.add(username)
    
    def set_rate_limited(self, limited: bool):
        """Set rate limiting state."""
        self.rate_limited = limited
        self.rate_limit_remaining = 0 if limited else 60
    
    def get_gist_response(self, gist_id: str) -> tuple[int, dict]:
        """Get mock response for gist API call."""
        if self.rate_limited:
            return 403, {"message": "API rate limit exceeded"}
        
        gist = self.gists.get(gist_id)
        if gist is None:
            return 404, {"message": "Not Found"}
        
        return 200, gist.to_api_response()
    
    def get_user_response(self, username: str) -> tuple[int, dict]:
        """Get mock response for user API call."""
        if self.rate_limited:
            return 403, {"message": "API rate limit exceeded"}
        
        if username in self.users:
            return 200, {"login": username, "id": hash(username) % 100000}
        
        return 404, {"message": "Not Found"}


class MockSubtensor:
    """
    Mock Bittensor subtensor for testing.
    
    Simulates subnet registration checks.
    """
    
    def __init__(self):
        self.registered_hotkeys: Dict[int, set] = {62: set()}
        self.hotkey_to_uid: Dict[str, int] = {}
        self._uid_counter = 1
    
    def register_hotkey(self, hotkey: str, netuid: int = 62) -> int:
        """Register a hotkey on a subnet."""
        if netuid not in self.registered_hotkeys:
            self.registered_hotkeys[netuid] = set()
        
        self.registered_hotkeys[netuid].add(hotkey)
        uid = self._uid_counter
        self.hotkey_to_uid[hotkey] = uid
        self._uid_counter += 1
        return uid
    
    def unregister_hotkey(self, hotkey: str, netuid: int = 62):
        """Unregister a hotkey from a subnet."""
        if netuid in self.registered_hotkeys:
            self.registered_hotkeys[netuid].discard(hotkey)
        self.hotkey_to_uid.pop(hotkey, None)
    
    def get_uid_for_hotkey_on_subnet(self, hotkey_ss58: str, netuid: int) -> Optional[int]:
        """Check if hotkey is registered and return UID."""
        if netuid in self.registered_hotkeys and hotkey_ss58 in self.registered_hotkeys[netuid]:
            return self.hotkey_to_uid.get(hotkey_ss58, 1)
        return None


class MockWallet:
    """
    Mock Bittensor wallet for testing.
    
    Simulates wallet operations including signing.
    """
    
    def __init__(self, name: str = "test_wallet", hotkey_name: str = "default"):
        self.name = name
        self.hotkey_str = VALID_HOTKEY  # Default hotkey
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
            """Mock sign operation - returns deterministic signature."""
            # Return a deterministic mock signature based on message hash
            msg_hash = hash(message)
            return bytes([msg_hash % 256] * 64)
    
    @property
    def hotkey(self) -> HotkeyWrapper:
        """Get hotkey wrapper."""
        return self.HotkeyWrapper(self)


class MockGitHubRegistry:
    """
    Mock GitHub Registry for testing without blockchain.
    
    Simulates the on-chain registry using in-memory storage.
    """
    
    def __init__(self):
        self.links: Dict[str, Dict[int, str]] = {}  # hotkey -> {mechanism_id: github_username}
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
        validator_private_key: str = None,
        **kwargs
    ) -> tuple[Optional[str], str]:
        """
        Link a GitHub username to a hotkey.

        Returns (tx_hash, status) where status is "created", "updated", or "unchanged".
        """
        existing = self.get_github(hotkey, mechanism_id)

        if existing == github_username:
            return (None, "unchanged")

        status = "created" if existing is None else "updated"

        # Store the link
        if hotkey not in self.links:
            self.links[hotkey] = {}
        self.links[hotkey][mechanism_id] = github_username

        # Record event
        tx_hash = f"0x{hash((hotkey, mechanism_id, github_username)):064x}"[-66:]
        self.events.append({
            "hotkey": hotkey,
            "mechanism_id": mechanism_id,
            "github_username": github_username,
            "validator": validator_private_key,
            "timestamp": int(time.time()),
            "tx_hash": tx_hash
        })

        return (tx_hash, status)
    
    def get_all_links(self) -> list:
        """Get all recorded links."""
        return self.events


# ============ Fixtures ============

@pytest.fixture
def mock_gist_server() -> MockGistServer:
    """Create a mock gist server with default data."""
    server = MockGistServer()
    
    # Add default gists
    server.add_gist(
        MockGist(GIST_ID_1, "octocat")
        .add_hotkey_file(VALID_HOTKEY)
    )
    server.add_gist(
        MockGist(GIST_ID_2, "testuser")
        .add_hotkey_file(VALID_HOTKEY_2)
    )
    
    return server


@pytest.fixture
def mock_subtensor() -> MockSubtensor:
    """Create a mock subtensor with registered hotkeys."""
    subtensor = MockSubtensor()
    subtensor.register_hotkey(VALID_HOTKEY, 62)
    subtensor.register_hotkey(VALID_HOTKEY_2, 62)
    return subtensor


@pytest.fixture
def mock_wallet() -> MockWallet:
    """Create a mock wallet."""
    return MockWallet()


@pytest.fixture
def mock_registry() -> MockGitHubRegistry:
    """Create a mock GitHub registry."""
    return MockGitHubRegistry()


@pytest.fixture
def mock_verifier_success():
    """
    Create a verifier that always succeeds verification.
    
    Returns (verifier_mock, setup_function).
    """
    from kubetee.validator.github_verifier import GitHubVerifier, VerificationResult
    
    async def mock_verify_success(*args, **kwargs):
        return VerificationResult(success=True, github_username="octocat")
    
    verifier = Mock(spec=GitHubVerifier)
    verifier.verify_link_request = AsyncMock(side_effect=mock_verify_success)
    return verifier


@pytest.fixture
def api_test_client(mock_subtensor, mock_registry, mock_verifier_success) -> TestClient:
    """
    Create a FastAPI test client with configured context.
    """
    from kubetee.api.github import router, ValidatorContext
    
    app = FastAPI()
    app.include_router(router)
    
    # Configure the ValidatorContext
    ValidatorContext._subtensor = mock_subtensor
    ValidatorContext._netuid = 62
    ValidatorContext._registry = mock_registry
    ValidatorContext._verifier = mock_verifier_success
    ValidatorContext._validator_private_key = "0x" + "aa" * 32
    
    yield TestClient(app)
    
    # Cleanup
    ValidatorContext.reset()


@pytest.fixture
def signed_message(mock_wallet) -> tuple[str, str]:
    """
    Create a signed message for testing.
    
    Returns (message_json, signature_hex).
    """
    message = json.dumps({
        "hotkey": mock_wallet.hotkey_str,
        "timestamp": int(time.time())
    })
    
    signature_bytes = mock_wallet.hotkey.sign(message.encode())
    signature_hex = "0x" + signature_bytes.hex()
    
    return message, signature_hex


def create_link_request(
    hotkey: str = VALID_HOTKEY,
    mechanism_id: int = MECHANISM_BOUNTY,
    gist_url: str = f"https://gist.github.com/octocat/{GIST_ID_1}",
    message: Optional[str] = None,
    signature: Optional[str] = None
) -> dict:
    """Helper function to create a link request payload."""
    if message is None:
        message = json.dumps({
            "hotkey": hotkey,
            "timestamp": int(time.time())
        })
    
    if signature is None:
        # Create a mock signature
        signature = "0x" + "aa" * 64
    
    return {
        "hotkey": hotkey,
        "mechanism_id": mechanism_id,
        "gist_url": gist_url,
        "message": message,
        "signature": signature
    }


# ============ Async HTTP Client Mock ============

@contextmanager
def mock_httpx_for_gist_server(server: MockGistServer):
    """
    Context manager that patches httpx to use the mock gist server.
    """
    async def mock_get(url: str, **kwargs):
        response = Mock()
        
        # Parse URL to determine endpoint
        if "api.github.com/gists/" in url:
            gist_id = url.split("/")[-1]
            status, data = server.get_gist_response(gist_id)
        elif "api.github.com/users/" in url:
            username = url.split("/")[-1]
            status, data = server.get_user_response(username)
        else:
            status, data = 404, {"message": "Unknown endpoint"}
        
        response.status_code = status
        response.json.return_value = data
        response.headers = {"X-RateLimit-Remaining": str(server.rate_limit_remaining)}
        
        return response
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=mock_get)
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        yield mock_client


# ============ Hardhat Node Fixtures ============

class HardhatNode:
    """
    Manages a Hardhat local node for contract integration tests.
    """
    
    def __init__(self, contracts_dir: str):
        self.contracts_dir = contracts_dir
        self.process: Optional[subprocess.Popen] = None
        self.url = "http://127.0.0.1:8545"
        self.deployed_address: Optional[str] = None
    
    def start(self) -> bool:
        """Start the Hardhat node."""
        if self.process is not None:
            return True
        
        try:
            self.process = subprocess.Popen(
                ["npx", "hardhat", "node"],
                cwd=self.contracts_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True  # Required on Windows
            )
            # Wait for node to start
            time.sleep(3)
            return self.process.poll() is None
        except Exception as e:
            print(f"Failed to start Hardhat node: {e}")
            return False
    
    def stop(self):
        """Stop the Hardhat node."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
    
    def deploy_contract(self) -> Optional[str]:
        """Deploy the contract and return its address."""
        try:
            result = subprocess.run(
                ["npx", "hardhat", "run", "scripts/deploy.js", "--network", "localhost"],
                cwd=self.contracts_dir,
                capture_output=True,
                text=True,
                shell=True
            )
            
            # Parse contract address from output
            output = result.stdout
            for line in output.split("\n"):
                if "deployed to" in line.lower():
                    # Extract address (0x...)
                    parts = line.split()
                    for part in parts:
                        if part.startswith("0x"):
                            self.deployed_address = part
                            return part
            
            return None
        except Exception as e:
            print(f"Failed to deploy contract: {e}")
            return None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


@pytest.fixture(scope="session")
def contracts_dir() -> str:
    """Get the contracts directory path."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "kubetee", "contracts"
    )


@pytest.fixture(scope="session")
def hardhat_node(contracts_dir) -> Generator[HardhatNode, None, None]:
    """
    Start a Hardhat node for the test session.
    
    Note: This fixture is session-scoped and will run the node
    for all tests in the session.
    """
    node = HardhatNode(contracts_dir)
    
    # Only start if npm dependencies are installed
    if os.path.exists(os.path.join(contracts_dir, "node_modules")):
        if node.start():
            yield node
        else:
            pytest.skip("Could not start Hardhat node")
            yield node
    else:
        pytest.skip("Hardhat dependencies not installed")
        yield node
    
    node.stop()


# ============ Test Data Constants ============

# Export commonly used test data
TEST_HOTKEYS = [VALID_HOTKEY, VALID_HOTKEY_2, VALID_HOTKEY_3]
TEST_GIST_IDS = [GIST_ID_1, GIST_ID_2]
TEST_USERNAMES = ["octocat", "testuser", "minerdev"]
MECHANISM_IDS = [
    MECHANISM_INFRASTRUCTURE,
    MECHANISM_OPENSOURCE,
    MECHANISM_REFERRAL,
    MECHANISM_BOUNTY
]
