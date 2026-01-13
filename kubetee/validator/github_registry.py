"""
GitHub Registry for KubeTEE Subnet Validator.

Manages GitHub-hotkey links via smart contract events. On startup, loads all
GitHubLinked events into an in-memory cache. Uses this cache to decide whether
to write new events to the blockchain, avoiding unnecessary gas costs.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError, TransactionNotFound

# Configure module logger
logger = logging.getLogger(__name__)


# Default path to contract artifacts relative to this file
DEFAULT_ARTIFACTS_PATH = Path(__file__).parent.parent / "contracts" / "artifacts"


def load_contract_abi(
    contract_name: str = "KubeTEEGitHubRegistry",
    artifacts_path: Optional[Path] = None,
) -> List[dict]:
    """
    Load contract ABI from compiled Hardhat artifacts.
    
    Args:
        contract_name: Name of the contract (without .sol extension).
        artifacts_path: Optional custom path to artifacts directory.
                       Defaults to kubetee/contracts/artifacts.
    
    Returns:
        The contract ABI as a list of dictionaries.
    
    Raises:
        FileNotFoundError: If the artifact file doesn't exist.
        json.JSONDecodeError: If the artifact file is not valid JSON.
        KeyError: If the 'abi' key is not found in the artifact.
    
    Example:
        >>> abi = load_contract_abi("KubeTEEGitHubRegistry")
        >>> len(abi) > 0
        True
    """
    if artifacts_path is None:
        artifacts_path = DEFAULT_ARTIFACTS_PATH
    
    # Construct path to artifact JSON file
    # Pattern: artifacts/contracts/{ContractName}.sol/{ContractName}.json
    artifact_file = (
        artifacts_path / "contracts" / f"{contract_name}.sol" / f"{contract_name}.json"
    )
    
    if not artifact_file.exists():
        raise FileNotFoundError(
            f"Contract artifact not found at {artifact_file}. "
            f"Ensure the contract has been compiled with 'npx hardhat compile'."
        )
    
    logger.debug(f"Loading ABI from {artifact_file}")
    
    with open(artifact_file, "r") as f:
        artifact = json.load(f)
    
    if "abi" not in artifact:
        raise KeyError(f"'abi' key not found in artifact file: {artifact_file}")
    
    return artifact["abi"]


def get_contract_address_from_env(
    env_var: str = "GITHUB_REGISTRY_CONTRACT_ADDRESS",
) -> Optional[str]:
    """
    Get contract address from environment variable.
    
    Args:
        env_var: Name of the environment variable containing the contract address.
    
    Returns:
        The contract address if set, None otherwise.
    """
    address = os.environ.get(env_var)
    if address:
        # Ensure checksum address
        return Web3.to_checksum_address(address)
    return None


class GitHubRegistry:
    """
    Manages GitHub-hotkey links via smart contract events.
    
    On startup, loads all GitHubLinked events from the contract into an in-memory
    cache. The cache is used to determine whether a new link request requires a
    blockchain write or if it can be skipped (if unchanged).
    
    Attributes:
        web3: Web3 instance for blockchain interaction.
        contract: The KubeTEEGitHubRegistry contract instance.
        _cache: In-memory cache mapping hotkey → {mechanism_id → github_username}.
        _events_loaded: Whether events have been loaded from the contract.
        _start_block: Block number from which to start loading events.
    
    Example:
        >>> from web3 import Web3
        >>> w3 = Web3(Web3.HTTPProvider("http://localhost:8545"))
        >>> abi = load_contract_abi()
        >>> registry = GitHubRegistry(w3, "0x...", abi)
        >>> await registry.load_events_on_startup()
        >>> registry.get_github("5Grw...", mechanism_id=0)
        'alice'
    """
    
    def __init__(
        self,
        web3: Web3,
        contract_address: str,
        contract_abi: List[dict],
        start_block: int = 0,
    ):
        """
        Initialize the GitHubRegistry.
        
        Args:
            web3: Web3 instance connected to an Ethereum node.
            contract_address: Address of the deployed KubeTEEGitHubRegistry contract.
            contract_abi: The contract's ABI.
            start_block: Block number to start loading events from (default: 0).
        
        Raises:
            ValueError: If contract_address is invalid.
        """
        self.web3 = web3
        
        # Validate and checksum the address
        if not Web3.is_address(contract_address):
            raise ValueError(f"Invalid contract address: {contract_address}")
        
        self.contract: Contract = web3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi,
        )
        
        # In-memory cache: hotkey → {mechanism_id → github_username}
        self._cache: Dict[str, Dict[int, str]] = {}
        self._events_loaded: bool = False
        self._start_block: int = start_block
        
        logger.info(
            f"GitHubRegistry initialized with contract at {contract_address}"
        )
    
    async def load_events_on_startup(self, from_block: Optional[int] = None) -> int:
        """
        Load all GitHubLinked events from the contract into the cache.
        
        This method should be called once when the validator starts. It retrieves
        all historical GitHubLinked events and populates the in-memory cache.
        Later events overwrite earlier ones for the same hotkey/mechanism combo,
        ensuring the cache reflects the latest state.
        
        Args:
            from_block: Block number to start from. If None, uses self._start_block.
        
        Returns:
            Number of events loaded into the cache.
        
        Raises:
            Exception: If there's an error fetching events from the blockchain.
        
        Note:
            This method uses synchronous Web3 calls internally but is declared
            async for consistency with the overall async architecture. For true
            async operation, consider using web3.py's async API.
        """
        if from_block is None:
            from_block = self._start_block
        
        logger.info(f"Loading GitHubLinked events from block {from_block}...")
        
        try:
            # Get all GitHubLinked events from the specified block to latest
            # web3.py's get_logs is synchronous but we wrap in async interface
            events = self.contract.events.GitHubLinked.get_logs(
                fromBlock=from_block,
                toBlock='latest',
            )
        except Exception as e:
            logger.error(f"Failed to fetch GitHubLinked events: {e}")
            raise
        
        events_count = 0
        
        for event in events:
            try:
                hotkey = event.args.hotkey
                mechanism_id = event.args.mechanismId
                github_username = event.args.githubUsername
                timestamp = event.args.timestamp
                validator = event.args.validator
                
                # Initialize nested dict if needed
                if hotkey not in self._cache:
                    self._cache[hotkey] = {}
                
                # Latest event wins (events are processed in chronological order)
                self._cache[hotkey][mechanism_id] = github_username
                events_count += 1
                
                logger.debug(
                    f"Cached: {hotkey[:16]}... → {github_username} "
                    f"(mechanism={mechanism_id}, validator={validator}, ts={timestamp})"
                )
            except Exception as e:
                logger.warning(f"Error processing event {event}: {e}")
                continue
        
        self._events_loaded = True
        
        logger.info(
            f"Loaded {events_count} GitHubLinked events into cache "
            f"({len(self._cache)} unique hotkeys)"
        )
        
        return events_count
    
    def get_github(self, hotkey: str, mechanism_id: int = 0) -> Optional[str]:
        """
        Get the cached GitHub username for a hotkey.
        
        Args:
            hotkey: The Bittensor SS58 hotkey to look up.
            mechanism_id: The mechanism ID (default: 0 for bounty mechanism).
        
        Returns:
            The GitHub username if found, None otherwise.
        
        Example:
            >>> registry.get_github("5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY")
            'alice'
            >>> registry.get_github("unknown_hotkey")
            None
        """
        if not self._events_loaded:
            logger.warning(
                "Cache not initialized. Call load_events_on_startup() first."
            )
        
        return self._cache.get(hotkey, {}).get(mechanism_id)
    
    def is_linked(self, hotkey: str, mechanism_id: int = 0) -> bool:
        """
        Check if a hotkey is already linked to a GitHub account.
        
        Args:
            hotkey: The Bittensor SS58 hotkey to check.
            mechanism_id: The mechanism ID (default: 0 for bounty mechanism).
        
        Returns:
            True if the hotkey is linked, False otherwise.
        
        Example:
            >>> registry.is_linked("5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY")
            True
            >>> registry.is_linked("unknown_hotkey")
            False
        """
        return self.get_github(hotkey, mechanism_id) is not None
    
    async def link_github(
        self,
        hotkey: str,
        mechanism_id: int,
        github_username: str,
        validator_private_key: str,
        gas_limit: int = 150000,
        wait_for_receipt: bool = True,
        timeout: int = 120,
    ) -> Tuple[Optional[str], str]:
        """
        Write a GitHub link to the contract if new or changed.
        
        This method checks the cache first to avoid unnecessary blockchain writes:
        - If the link doesn't exist, creates a new one ("created")
        - If the link exists but GitHub changed, updates it ("updated")
        - If the link is unchanged, skips the write ("unchanged")
        
        Args:
            hotkey: Bittensor SS58 hotkey to link.
            mechanism_id: Mechanism ID (0 = bounty, etc.).
            github_username: GitHub username to link.
            validator_private_key: Private key of the validator for signing.
            gas_limit: Maximum gas for the transaction (default: 150000).
            wait_for_receipt: If True, wait for transaction receipt (default: True).
            timeout: Timeout in seconds for waiting for receipt (default: 120).
        
        Returns:
            Tuple of (tx_hash, status) where:
            - tx_hash: Transaction hash (hex string) or None if unchanged
            - status: One of "created", "updated", or "unchanged"
        
        Raises:
            ValueError: If parameters are invalid.
            ContractLogicError: If the contract call reverts.
            Exception: If there's an error sending the transaction.
        
        Example:
            >>> tx_hash, status = await registry.link_github(
            ...     hotkey="5Grw...",
            ...     mechanism_id=0,
            ...     github_username="alice",
            ...     validator_private_key="0x..."
            ... )
            >>> status
            'created'
        """
        # Validate inputs
        if not hotkey:
            raise ValueError("hotkey cannot be empty")
        if not github_username:
            raise ValueError("github_username cannot be empty")
        if not validator_private_key:
            raise ValueError("validator_private_key cannot be empty")
        
        # Check cache for existing link
        existing = self.get_github(hotkey, mechanism_id)
        
        # Same link already exists - no write needed
        if existing == github_username:
            logger.info(
                f"Link unchanged for {hotkey[:16]}... → {github_username} "
                f"(mechanism={mechanism_id})"
            )
            return (None, "unchanged")
        
        # Determine status
        status = "created" if existing is None else "updated"
        
        logger.info(
            f"Link {status} for {hotkey[:16]}... → {github_username} "
            f"(mechanism={mechanism_id}, previous={existing})"
        )
        
        try:
            # Get validator account from private key
            account = self.web3.eth.account.from_key(validator_private_key)
            validator_address = account.address
            
            # Get current nonce
            nonce = self.web3.eth.get_transaction_count(validator_address)
            
            # Build the transaction
            tx = self.contract.functions.linkGitHub(
                hotkey,
                mechanism_id,
                github_username,
            ).build_transaction({
                'from': validator_address,
                'nonce': nonce,
                'gas': gas_limit,
                'gasPrice': self.web3.eth.gas_price,
            })
            
            logger.debug(f"Built transaction: nonce={nonce}, gas={gas_limit}")
            
            # Sign the transaction
            signed_tx = self.web3.eth.account.sign_transaction(
                tx, validator_private_key
            )
            
            # Send the transaction
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            
            logger.info(f"Transaction sent: {tx_hash_hex}")
            
            # Optionally wait for receipt
            if wait_for_receipt:
                logger.debug(f"Waiting for transaction receipt (timeout={timeout}s)...")
                receipt = self.web3.eth.wait_for_transaction_receipt(
                    tx_hash, timeout=timeout
                )
                
                if receipt.status == 1:
                    logger.info(
                        f"Transaction confirmed in block {receipt.blockNumber}"
                    )
                else:
                    logger.error(f"Transaction failed: {receipt}")
                    raise Exception(f"Transaction reverted: {tx_hash_hex}")
            
            # Update local cache immediately
            if hotkey not in self._cache:
                self._cache[hotkey] = {}
            self._cache[hotkey][mechanism_id] = github_username
            
            logger.debug(f"Cache updated: {hotkey[:16]}... → {github_username}")
            
            return (tx_hash_hex, status)
            
        except ContractLogicError as e:
            logger.error(f"Contract call reverted: {e}")
            raise
        except Exception as e:
            logger.error(f"Error sending transaction: {e}")
            raise
    
    def get_all_links(self, mechanism_id: int = 0) -> Dict[str, str]:
        """
        Return all cached links for a specific mechanism.
        
        Args:
            mechanism_id: The mechanism ID to filter by (default: 0).
        
        Returns:
            Dictionary mapping hotkey → github_username for all linked hotkeys
            in the specified mechanism.
        
        Example:
            >>> links = registry.get_all_links(mechanism_id=0)
            >>> len(links)
            42
            >>> links["5Grw..."]
            'alice'
        """
        if not self._events_loaded:
            logger.warning(
                "Cache not initialized. Call load_events_on_startup() first."
            )
        
        result: Dict[str, str] = {}
        
        for hotkey, mechanisms in self._cache.items():
            if mechanism_id in mechanisms:
                result[hotkey] = mechanisms[mechanism_id]
        
        return result
    
    def get_hotkeys_for_github(
        self, github_username: str, mechanism_id: int = 0
    ) -> List[str]:
        """
        Get all hotkeys linked to a specific GitHub username.
        
        Args:
            github_username: The GitHub username to look up.
            mechanism_id: The mechanism ID to filter by (default: 0).
        
        Returns:
            List of hotkeys linked to the GitHub username.
        
        Example:
            >>> registry.get_hotkeys_for_github("alice")
            ['5Grw...', '5HGj...']
        """
        if not self._events_loaded:
            logger.warning(
                "Cache not initialized. Call load_events_on_startup() first."
            )
        
        result: List[str] = []
        
        for hotkey, mechanisms in self._cache.items():
            if mechanisms.get(mechanism_id) == github_username:
                result.append(hotkey)
        
        return result
    
    def cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about the current cache state.
        
        Returns:
            Dictionary with cache statistics:
            - total_hotkeys: Total number of unique hotkeys
            - total_links: Total number of hotkey-mechanism-github links
            - mechanisms: Number of unique mechanism IDs
        """
        total_links = sum(len(mechs) for mechs in self._cache.values())
        all_mechanisms = set()
        
        for mechanisms in self._cache.values():
            all_mechanisms.update(mechanisms.keys())
        
        return {
            "total_hotkeys": len(self._cache),
            "total_links": total_links,
            "mechanisms": len(all_mechanisms),
            "events_loaded": self._events_loaded,
        }
    
    def clear_cache(self) -> None:
        """
        Clear the in-memory cache.
        
        This does not affect the blockchain state, only the local cache.
        Call load_events_on_startup() to repopulate the cache.
        """
        self._cache.clear()
        self._events_loaded = False
        logger.info("Cache cleared")
    
    async def refresh_cache(self) -> int:
        """
        Refresh the cache by reloading all events from the blockchain.
        
        Returns:
            Number of events loaded.
        """
        self.clear_cache()
        return await self.load_events_on_startup()


# Factory function for convenience
def create_github_registry(
    rpc_url: str,
    contract_address: Optional[str] = None,
    start_block: int = 0,
) -> GitHubRegistry:
    """
    Factory function to create a GitHubRegistry instance.
    
    Args:
        rpc_url: HTTP/HTTPS URL of the Ethereum JSON-RPC endpoint.
        contract_address: Address of the deployed contract. If None, attempts
                         to read from GITHUB_REGISTRY_CONTRACT_ADDRESS env var.
        start_block: Block number to start loading events from.
    
    Returns:
        Configured GitHubRegistry instance.
    
    Raises:
        ValueError: If contract_address is not provided and not in environment.
        FileNotFoundError: If contract ABI cannot be loaded.
    
    Example:
        >>> registry = create_github_registry(
        ...     rpc_url="http://localhost:8545",
        ...     contract_address="0x..."
        ... )
    """
    # Get contract address
    if contract_address is None:
        contract_address = get_contract_address_from_env()
    
    if contract_address is None:
        raise ValueError(
            "Contract address must be provided or set in "
            "GITHUB_REGISTRY_CONTRACT_ADDRESS environment variable"
        )
    
    # Create Web3 instance
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not web3.is_connected():
        logger.warning(f"Web3 not connected to {rpc_url}")
    
    # Load ABI
    abi = load_contract_abi()
    
    # Create and return registry
    return GitHubRegistry(
        web3=web3,
        contract_address=contract_address,
        contract_abi=abi,
        start_block=start_block,
    )
