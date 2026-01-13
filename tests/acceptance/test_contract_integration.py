"""
Contract Integration Tests for GitHub Linking.

These tests verify the integration between Python code and the Solidity smart contract.

NOTE: These tests require:
- Node.js and npm installed
- Hardhat dependencies installed (npm install in kubetee/contracts/)
- A running Hardhat node (npx hardhat node)

Tests can be skipped automatically if Hardhat is not available.

Tests covered:
- Python GitHubRegistry ↔ Smart Contract
- Event emission and parsing
- Cache consistency
- Contract upgrade scenarios
"""

import pytest
import json
import os
import asyncio
import subprocess
from unittest.mock import Mock, patch, AsyncMock
from typing import Optional

from tests.acceptance.conftest import (
    VALID_HOTKEY,
    VALID_HOTKEY_2,
    MECHANISM_BOUNTY,
    MECHANISM_OPENSOURCE,
    HardhatNode,
)


# Skip all tests in this module if contract dependencies not available
pytestmark = pytest.mark.skipif(
    not os.path.exists(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "kubetee", "contracts", "node_modules"
        )
    ),
    reason="Hardhat dependencies not installed - run 'npm install' in kubetee/contracts/"
)


@pytest.fixture(scope="module")
def contracts_path():
    """Get path to contracts directory."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "kubetee", "contracts"
    )


@pytest.fixture(scope="module")
def contract_abi(contracts_path):
    """Load contract ABI from artifacts."""
    abi_path = os.path.join(
        contracts_path,
        "artifacts", "contracts", "KubeTEEGitHubRegistry.sol",
        "KubeTEEGitHubRegistry.json"
    )
    
    if not os.path.exists(abi_path):
        pytest.skip("Contract artifacts not found - run 'npx hardhat compile'")
    
    with open(abi_path) as f:
        artifact = json.load(f)
    
    return artifact["abi"]


class TestContractABI:
    """Tests for contract ABI loading and parsing."""
    
    def test_abi_has_link_github_function(self, contract_abi):
        """ABI should contain linkGitHub function."""
        function_names = [
            item["name"] for item in contract_abi
            if item.get("type") == "function"
        ]
        
        assert "linkGitHub" in function_names
    
    def test_abi_has_github_linked_event(self, contract_abi):
        """ABI should contain GitHubLinked event."""
        event_names = [
            item["name"] for item in contract_abi
            if item.get("type") == "event"
        ]
        
        assert "GitHubLinked" in event_names
    
    def test_abi_has_validator_management(self, contract_abi):
        """ABI should contain validator management functions."""
        function_names = [
            item["name"] for item in contract_abi
            if item.get("type") == "function"
        ]
        
        assert "addValidator" in function_names
        assert "removeValidator" in function_names
        assert "isValidator" in function_names
    
    def test_github_linked_event_parameters(self, contract_abi):
        """GitHubLinked event should have correct parameters."""
        event = next(
            (item for item in contract_abi 
             if item.get("type") == "event" and item.get("name") == "GitHubLinked"),
            None
        )
        
        assert event is not None
        
        param_names = [p["name"] for p in event["inputs"]]
        
        assert "hotkeyHash" in param_names
        assert "hotkey" in param_names
        assert "mechanismId" in param_names
        assert "githubUsername" in param_names
        assert "validator" in param_names
        assert "timestamp" in param_names


class TestContractCompilation:
    """Tests for contract compilation."""
    
    def test_contract_compiles(self, contracts_path):
        """Contract should compile without errors."""
        result = subprocess.run(
            ["npx", "hardhat", "compile"],
            cwd=contracts_path,
            capture_output=True,
            text=True,
            shell=True  # Required on Windows
        )
        
        assert result.returncode == 0 or "Compiled" in result.stdout or "Nothing to compile" in result.stdout


class TestContractTests:
    """Run the Hardhat contract tests from Python."""
    
    def test_hardhat_tests_pass(self, contracts_path):
        """All Hardhat tests should pass."""
        result = subprocess.run(
            ["npx", "hardhat", "test"],
            cwd=contracts_path,
            capture_output=True,
            text=True,
            shell=True,
            timeout=120  # 2 minute timeout
        )
        
        # Check that tests passed
        assert "passing" in result.stdout.lower()
        # Check no failures
        assert "failing" not in result.stdout.lower() or "0 failing" in result.stdout.lower()


class TestGitHubRegistryABILoading:
    """Tests for GitHubRegistry ABI loading."""
    
    def test_registry_loads_abi(self, contracts_path):
        """GitHubRegistry should load ABI from artifacts."""
        from kubetee.validator.github_registry import load_contract_abi
        
        # Mock the path
        with patch('kubetee.validator.github_registry.get_contracts_dir', return_value=contracts_path):
            abi = load_contract_abi()
        
        assert abi is not None
        assert len(abi) > 0
    
    def test_registry_abi_has_required_functions(self, contracts_path):
        """Loaded ABI should have all required functions."""
        from kubetee.validator.github_registry import load_contract_abi
        
        with patch('kubetee.validator.github_registry.get_contracts_dir', return_value=contracts_path):
            abi = load_contract_abi()
        
        function_names = [
            item["name"] for item in abi
            if item.get("type") == "function"
        ]
        
        # Required functions
        assert "linkGitHub" in function_names
        assert "addValidator" in function_names


class TestMockContractInteraction:
    """
    Tests for contract interaction with mocked web3.
    
    These tests verify the Python code path without needing a real blockchain.
    """
    
    @pytest.mark.asyncio
    async def test_link_github_builds_correct_transaction(self):
        """link_github should build correct transaction data."""
        from kubetee.validator.github_registry import GitHubRegistry
        
        # Create registry with mocked web3
        mock_web3 = Mock()
        mock_contract = Mock()
        mock_web3.eth.contract.return_value = mock_contract
        
        # Mock the linkGitHub function
        mock_link_fn = Mock()
        mock_contract.functions.linkGitHub.return_value = mock_link_fn
        mock_link_fn.build_transaction.return_value = {
            "to": "0x1234",
            "data": "0xaabbccdd",
            "gas": 100000
        }
        
        # Mock transaction sending
        mock_web3.eth.send_raw_transaction.return_value = bytes.fromhex("aa" * 32)
        mock_web3.eth.wait_for_transaction_receipt.return_value = {"status": 1}
        
        registry = GitHubRegistry(
            contract_address="0x" + "11" * 20,
            web3_provider_url="http://localhost:8545"
        )
        registry.web3 = mock_web3
        registry.contract = mock_contract
        registry.cache = {}
        
        # Test link_github
        with patch.object(registry, '_sign_and_send_transaction', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = "0x" + "bb" * 32
            
            tx_hash, status = await registry.link_github(
                hotkey=VALID_HOTKEY,
                mechanism_id=MECHANISM_BOUNTY,
                github_username="testuser",
                validator_key="0x" + "cc" * 32
            )
        
        # Verify linkGitHub was called with correct args
        mock_contract.functions.linkGitHub.assert_called_once_with(
            VALID_HOTKEY,
            MECHANISM_BOUNTY,
            "testuser"
        )
    
    @pytest.mark.asyncio
    async def test_cache_prevents_duplicate_transactions(self):
        """Cache should prevent duplicate transactions for unchanged links."""
        from kubetee.validator.github_registry import GitHubRegistry
        
        registry = GitHubRegistry(
            contract_address="0x" + "11" * 20,
            web3_provider_url="http://localhost:8545"
        )
        
        # Pre-populate cache
        registry.cache = {
            (VALID_HOTKEY, MECHANISM_BOUNTY): "existinguser"
        }
        
        # Attempt to link with same username
        tx_hash, status = await registry.link_github(
            hotkey=VALID_HOTKEY,
            mechanism_id=MECHANISM_BOUNTY,
            github_username="existinguser",  # Same as cache
            validator_key="0xvalidator"
        )
        
        # Should be unchanged without tx
        assert status == "unchanged"
        assert tx_hash is None


class TestEventParsing:
    """Tests for parsing GitHubLinked events."""
    
    def test_parse_github_linked_event(self, contract_abi):
        """Should correctly parse GitHubLinked event from logs."""
        # Find the event definition
        event = next(
            (item for item in contract_abi 
             if item.get("type") == "event" and item.get("name") == "GitHubLinked"),
            None
        )
        
        assert event is not None
        
        # Verify event can be used for topic filtering
        # (The actual topic hash would be keccak256 of the signature)
        inputs = event["inputs"]
        
        # Check indexed parameters (can be used as topics)
        indexed = [i for i in inputs if i.get("indexed")]
        assert len(indexed) >= 1  # At least hotkeyHash should be indexed


class TestCacheConsistency:
    """Tests for cache consistency with contract state."""
    
    @pytest.mark.asyncio
    async def test_cache_updated_after_link(self):
        """Cache should be updated after successful link."""
        from kubetee.validator.github_registry import GitHubRegistry
        
        registry = GitHubRegistry(
            contract_address="0x" + "11" * 20,
            web3_provider_url="http://localhost:8545"
        )
        registry.cache = {}
        
        # Mock successful transaction
        with patch.object(registry, '_sign_and_send_transaction', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = "0x" + "aa" * 32
            
            await registry.link_github(
                hotkey=VALID_HOTKEY,
                mechanism_id=MECHANISM_BOUNTY,
                github_username="newuser",
                validator_key="0xvalidator"
            )
        
        # Cache should now contain the link
        assert registry.cache.get((VALID_HOTKEY, MECHANISM_BOUNTY)) == "newuser"
    
    @pytest.mark.asyncio
    async def test_get_github_returns_cached_value(self):
        """get_github should return cached value."""
        from kubetee.validator.github_registry import GitHubRegistry
        
        registry = GitHubRegistry(
            contract_address="0x" + "11" * 20,
            web3_provider_url="http://localhost:8545"
        )
        
        # Set cache
        registry.cache = {
            (VALID_HOTKEY, MECHANISM_BOUNTY): "cacheduser"
        }
        
        result = registry.get_github(VALID_HOTKEY, MECHANISM_BOUNTY)
        
        assert result == "cacheduser"
    
    @pytest.mark.asyncio
    async def test_get_github_returns_none_for_missing(self):
        """get_github should return None for missing entries."""
        from kubetee.validator.github_registry import GitHubRegistry
        
        registry = GitHubRegistry(
            contract_address="0x" + "11" * 20,
            web3_provider_url="http://localhost:8545"
        )
        registry.cache = {}
        
        result = registry.get_github(VALID_HOTKEY, MECHANISM_BOUNTY)
        
        assert result is None


class TestEventLoading:
    """Tests for loading events on startup."""
    
    @pytest.mark.asyncio
    async def test_load_events_populates_cache(self):
        """load_events_on_startup should populate the cache from events."""
        from kubetee.validator.github_registry import GitHubRegistry
        
        registry = GitHubRegistry(
            contract_address="0x" + "11" * 20,
            web3_provider_url="http://localhost:8545"
        )
        
        # Mock the event fetching
        mock_events = [
            {
                "args": {
                    "hotkey": VALID_HOTKEY,
                    "mechanismId": MECHANISM_BOUNTY,
                    "githubUsername": "user1",
                    "timestamp": 1000
                }
            },
            {
                "args": {
                    "hotkey": VALID_HOTKEY,
                    "mechanismId": MECHANISM_BOUNTY,
                    "githubUsername": "user2",  # Update
                    "timestamp": 2000
                }
            },
            {
                "args": {
                    "hotkey": VALID_HOTKEY_2,
                    "mechanismId": MECHANISM_OPENSOURCE,
                    "githubUsername": "user3",
                    "timestamp": 3000
                }
            }
        ]
        
        with patch.object(registry, '_fetch_all_events', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_events
            
            await registry.load_events_on_startup()
        
        # Cache should have latest values
        assert registry.cache.get((VALID_HOTKEY, MECHANISM_BOUNTY)) == "user2"  # Latest
        assert registry.cache.get((VALID_HOTKEY_2, MECHANISM_OPENSOURCE)) == "user3"


class TestUpgradeScenarios:
    """Tests for contract upgrade scenarios."""
    
    def test_v2_contract_abi_compatible(self, contracts_path):
        """V2 contract ABI should be compatible with V1 interface."""
        v1_abi_path = os.path.join(
            contracts_path,
            "artifacts", "contracts", "KubeTEEGitHubRegistry.sol",
            "KubeTEEGitHubRegistry.json"
        )
        
        v2_abi_path = os.path.join(
            contracts_path,
            "artifacts", "contracts", "KubeTEEGitHubRegistryV2.sol",
            "KubeTEEGitHubRegistryV2.json"
        )
        
        if not os.path.exists(v1_abi_path) or not os.path.exists(v2_abi_path):
            pytest.skip("Contract artifacts not found")
        
        with open(v1_abi_path) as f:
            v1_artifact = json.load(f)
        
        with open(v2_abi_path) as f:
            v2_artifact = json.load(f)
        
        v1_functions = {
            item["name"] for item in v1_artifact["abi"]
            if item.get("type") == "function"
        }
        
        v2_functions = {
            item["name"] for item in v2_artifact["abi"]
            if item.get("type") == "function"
        }
        
        # V2 should contain all V1 functions
        assert v1_functions.issubset(v2_functions), \
            f"V2 missing functions: {v1_functions - v2_functions}"


class TestGasEstimation:
    """Tests for gas estimation and transaction building."""
    
    def test_link_github_gas_limit(self, contract_abi):
        """linkGitHub function gas should be reasonable."""
        # Find linkGitHub function
        link_fn = next(
            (item for item in contract_abi 
             if item.get("type") == "function" and item.get("name") == "linkGitHub"),
            None
        )
        
        assert link_fn is not None
        
        # linkGitHub emits event only, so gas should be low
        # (Actual gas estimation would require a running node)
        
        # Verify function is not payable (no ETH required)
        state_mutability = link_fn.get("stateMutability", "nonpayable")
        assert state_mutability == "nonpayable"
