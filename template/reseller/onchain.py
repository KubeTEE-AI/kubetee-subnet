"""
KubeTEE AI - Reseller On-Chain Integration

On-chain payment system for Resellers/White Label partners.
Resellers are a category of miners but they DON'T receive emissions.

ARCHITECTURE:
═══════════════════════════════════════════════════════════════════════════════

                          RESELLER FLOW
┌──────────────────┐     ┌────────────────────┐     ┌─────────────────────┐
│   Reseller       │     │  Rancher Fleet     │     │  On-Chain Contract  │
│   (coldkey/hot)  │────▶│  register-reseller │────▶│  KubeTEEPayment.sol │
│                  │     │                    │     │  (Bittensor EVM)    │
└──────────────────┘     └────────────────────┘     └─────────────────────┘
        │                                                    │
        ▼                                                    │
┌──────────────────┐                                        │
│   Rancher        │◀───────────────────────────────────────┘
│   Account/NS     │        Project ID stored on-chain
└──────────────────┘

                          PAYMENT FLOW
┌──────────────────┐     ┌────────────────────┐     ┌─────────────────────┐
│   Reseller       │────▶│  deposit()         │────▶│  Contract Balance   │
│   Alpha/TAO      │     │                    │     │                     │
└──────────────────┘     └────────────────────┘     └─────────────────────┘
                                                            │
                                                            ▼
┌──────────────────┐     ┌────────────────────┐     ┌─────────────────────┐
│   Validators     │────▶│  reportEpochUsage()│────▶│  Deduct from        │
│   (per epoch)    │     │  (multi-sig)       │     │  reseller balance   │
└──────────────────┘     └────────────────────┘     └─────────────────────┘
                                                            │
                                                            ▼
                                                    ┌─────────────────────┐
                                                    │  Transfer to        │
                                                    │  KubeTEE Owner Key  │
                                                    └─────────────────────┘

FUTURE COMPATIBILITY:
- ERC-8004 (Decentralized Paymaster)
- x.402 (HTTP 402 Payment Required protocol)

═══════════════════════════════════════════════════════════════════════════════
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import json
import hashlib
import time

# Bittensor imports
try:
    import bittensor as bt
except ImportError:
    bt = None

# Web3 imports for Bittensor EVM interaction
try:
    from web3 import Web3
    from eth_account import Account
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class OnChainConfig:
    """On-chain payment contract configuration."""
    
    # Bittensor EVM RPC endpoint
    rpc_url: str = "https://evm.bittensor.network"
    
    # Chain ID for Bittensor EVM
    chain_id: int = 461
    
    # KubeTEEPayment contract address (deployed)
    contract_address: str = ""
    
    # Payment token address (wTAO or Alpha)
    payment_token_address: str = ""
    
    # Wholesale discount (resellers pay 50% of retail)
    wholesale_discount_bps: int = 5000
    
    # Minimum deposit amount (in wei)
    min_deposit: int = 10**18  # 1 token


# Contract ABI (key functions only)
KUBETEE_PAYMENT_ABI = [
    {
        "name": "registerReseller",
        "type": "function",
        "inputs": [
            {"name": "hotkey", "type": "bytes32"},
            {"name": "coldkey", "type": "bytes32"},
            {"name": "rancherProjectId", "type": "string"}
        ],
        "outputs": []
    },
    {
        "name": "deposit",
        "type": "function",
        "inputs": [{"name": "amount", "type": "uint256"}],
        "outputs": []
    },
    {
        "name": "withdraw",
        "type": "function",
        "inputs": [{"name": "amount", "type": "uint256"}],
        "outputs": []
    },
    {
        "name": "reportEpochUsage",
        "type": "function",
        "inputs": [
            {"name": "reports", "type": "tuple[]", "components": [
                {"name": "reseller", "type": "address"},
                {"name": "usageAmount", "type": "uint256"},
                {"name": "tokensProcessed", "type": "uint256"},
                {"name": "gpuSecondsUsed", "type": "uint256"}
            ]}
        ],
        "outputs": []
    },
    {
        "name": "getResellerBalance",
        "type": "function",
        "inputs": [{"name": "wallet", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view"
    },
    {
        "name": "resellers",
        "type": "function",
        "inputs": [{"name": "", "type": "address"}],
        "outputs": [
            {"name": "wallet", "type": "address"},
            {"name": "hotkey", "type": "bytes32"},
            {"name": "coldkey", "type": "bytes32"},
            {"name": "registeredAt", "type": "uint256"},
            {"name": "active", "type": "bool"},
            {"name": "rancherProjectId", "type": "string"},
            {"name": "depositBalance", "type": "uint256"},
            {"name": "totalDeposited", "type": "uint256"},
            {"name": "totalSpent", "type": "uint256"},
            {"name": "currentEpochUsage", "type": "uint256"},
            {"name": "lastSettledEpoch", "type": "uint256"}
        ],
        "stateMutability": "view"
    },
    {
        "name": "currentEpoch",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view"
    },
    {
        "name": "getAllResellers",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "address[]"}],
        "stateMutability": "view"
    }
]

ERC20_ABI = [
    {
        "name": "approve",
        "type": "function",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "outputs": [{"name": "", "type": "bool"}]
    },
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view"
    }
]


# =============================================================================
# RESELLER DATA
# =============================================================================

@dataclass
class ResellerInfo:
    """On-chain reseller information."""
    wallet: str
    hotkey: bytes
    coldkey: bytes
    registered_at: int
    active: bool
    rancher_project_id: str
    deposit_balance: int
    total_deposited: int
    total_spent: int
    current_epoch_usage: int
    last_settled_epoch: int


@dataclass
class EpochUsageReport:
    """Usage report for epoch settlement."""
    reseller: str          # EVM wallet address
    usage_amount: int      # Amount in wei (50% of retail)
    tokens_processed: int  # LLM tokens processed
    gpu_seconds_used: int  # GPU compute seconds


# =============================================================================
# ON-CHAIN CLIENT
# =============================================================================

class OnChainClient:
    """
    Client for interacting with KubeTEEPayment smart contract.
    
    Used by:
    - Rancher Fleet: For reseller registration and deposits
    - Validators: For reporting epoch usage and settlements
    """
    
    def __init__(self, config: OnChainConfig):
        """Initialize the on-chain client."""
        if not HAS_WEB3:
            raise ImportError("web3 package required: pip install web3")
        
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to {config.rpc_url}")
        
        # Initialize contract
        if config.contract_address:
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(config.contract_address),
                abi=KUBETEE_PAYMENT_ABI
            )
        else:
            self.contract = None
        
        # Payment token
        if config.payment_token_address:
            self.token = self.w3.eth.contract(
                address=Web3.to_checksum_address(config.payment_token_address),
                abi=ERC20_ABI
            )
        else:
            self.token = None
    
    # =========================================================================
    # RESELLER FUNCTIONS
    # =========================================================================
    
    def register_reseller(
        self,
        private_key: str,
        hotkey_ss58: str,
        coldkey_ss58: str,
        rancher_project_id: str
    ) -> str:
        """
        Register as a reseller on-chain.
        
        Called via Rancher Fleet after Rancher account creation.
        
        Args:
            private_key: EVM private key for transaction
            hotkey_ss58: Bittensor hotkey (SS58 format)
            coldkey_ss58: Bittensor coldkey (SS58 format)
            rancher_project_id: Rancher project/namespace ID
            
        Returns:
            Transaction hash
        """
        if not self.contract:
            raise ValueError("Contract not configured")
        
        # Convert SS58 addresses to bytes32
        hotkey_bytes = self._ss58_to_bytes32(hotkey_ss58)
        coldkey_bytes = self._ss58_to_bytes32(coldkey_ss58)
        
        account = Account.from_key(private_key)
        
        # Build transaction
        tx = self.contract.functions.registerReseller(
            hotkey_bytes,
            coldkey_bytes,
            rancher_project_id
        ).build_transaction({
            'from': account.address,
            'nonce': self.w3.eth.get_transaction_count(account.address),
            'gas': 300000,
            'gasPrice': self.w3.eth.gas_price,
            'chainId': self.config.chain_id
        })
        
        # Sign and send
        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        
        return tx_hash.hex()
    
    def deposit(
        self,
        private_key: str,
        amount: int
    ) -> str:
        """
        Deposit tokens to reseller account.
        
        Args:
            private_key: EVM private key
            amount: Amount in wei to deposit
            
        Returns:
            Transaction hash
        """
        if not self.contract or not self.token:
            raise ValueError("Contracts not configured")
        
        account = Account.from_key(private_key)
        
        # First approve token transfer
        approve_tx = self.token.functions.approve(
            self.config.contract_address,
            amount
        ).build_transaction({
            'from': account.address,
            'nonce': self.w3.eth.get_transaction_count(account.address),
            'gas': 100000,
            'gasPrice': self.w3.eth.gas_price,
            'chainId': self.config.chain_id
        })
        
        signed_approve = self.w3.eth.account.sign_transaction(approve_tx, private_key)
        self.w3.eth.send_raw_transaction(signed_approve.rawTransaction)
        
        # Wait for approval
        time.sleep(5)
        
        # Then deposit
        deposit_tx = self.contract.functions.deposit(amount).build_transaction({
            'from': account.address,
            'nonce': self.w3.eth.get_transaction_count(account.address),
            'gas': 200000,
            'gasPrice': self.w3.eth.gas_price,
            'chainId': self.config.chain_id
        })
        
        signed_deposit = self.w3.eth.account.sign_transaction(deposit_tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_deposit.rawTransaction)
        
        return tx_hash.hex()
    
    def get_balance(self, wallet: str) -> int:
        """Get reseller deposit balance."""
        if not self.contract:
            return 0
        
        return self.contract.functions.getResellerBalance(
            Web3.to_checksum_address(wallet)
        ).call()
    
    def get_reseller_info(self, wallet: str) -> Optional[ResellerInfo]:
        """Get full reseller information."""
        if not self.contract:
            return None
        
        try:
            data = self.contract.functions.resellers(
                Web3.to_checksum_address(wallet)
            ).call()
            
            return ResellerInfo(
                wallet=data[0],
                hotkey=data[1],
                coldkey=data[2],
                registered_at=data[3],
                active=data[4],
                rancher_project_id=data[5],
                deposit_balance=data[6],
                total_deposited=data[7],
                total_spent=data[8],
                current_epoch_usage=data[9],
                last_settled_epoch=data[10]
            )
        except Exception:
            return None
    
    # =========================================================================
    # VALIDATOR FUNCTIONS
    # =========================================================================
    
    def report_epoch_usage(
        self,
        private_key: str,
        reports: List[EpochUsageReport]
    ) -> str:
        """
        Report reseller usage for epoch settlement.
        
        Called by validators each epoch. Multiple validators must
        confirm for settlement to finalize.
        
        Args:
            private_key: Validator EVM private key
            reports: List of usage reports
            
        Returns:
            Transaction hash
        """
        if not self.contract:
            raise ValueError("Contract not configured")
        
        account = Account.from_key(private_key)
        
        # Format reports for contract
        formatted_reports = [
            (
                Web3.to_checksum_address(r.reseller),
                r.usage_amount,
                r.tokens_processed,
                r.gpu_seconds_used
            )
            for r in reports
        ]
        
        tx = self.contract.functions.reportEpochUsage(
            formatted_reports
        ).build_transaction({
            'from': account.address,
            'nonce': self.w3.eth.get_transaction_count(account.address),
            'gas': 500000 + (len(reports) * 50000),  # Scale with reports
            'gasPrice': self.w3.eth.gas_price,
            'chainId': self.config.chain_id
        })
        
        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        
        return tx_hash.hex()
    
    def get_current_epoch(self) -> int:
        """Get current contract epoch."""
        if not self.contract:
            return 0
        return self.contract.functions.currentEpoch().call()
    
    def get_all_resellers(self) -> List[str]:
        """Get all registered reseller addresses."""
        if not self.contract:
            return []
        return self.contract.functions.getAllResellers().call()
    
    # =========================================================================
    # UTILITY FUNCTIONS
    # =========================================================================
    
    @staticmethod
    def _ss58_to_bytes32(ss58_address: str) -> bytes:
        """Convert SS58 address to bytes32 for on-chain storage."""
        # Hash the SS58 address to get a deterministic bytes32
        return hashlib.sha256(ss58_address.encode()).digest()
    
    @staticmethod
    def calculate_wholesale_price(retail_price: int, discount_bps: int = 5000) -> int:
        """
        Calculate wholesale price (50% of retail).
        
        Args:
            retail_price: Retail price in wei
            discount_bps: Discount in basis points (5000 = 50%)
            
        Returns:
            Wholesale price in wei
        """
        return retail_price * (10000 - discount_bps) // 10000


# =============================================================================
# VALIDATOR EPOCH PROCESSOR
# =============================================================================

class ValidatorEpochProcessor:
    """
    Validator-side processor for on-chain epoch settlements.
    
    Collects usage data from Rancher/Prometheus and submits
    on-chain reports each epoch.
    """
    
    def __init__(
        self,
        client: OnChainClient,
        validator_private_key: str
    ):
        """Initialize the epoch processor."""
        self.client = client
        self.validator_private_key = validator_private_key
        self.last_processed_epoch = 0
    
    async def process_epoch(
        self,
        rancher_usage_data: Dict[str, Dict]
    ) -> Optional[str]:
        """
        Process epoch and submit on-chain settlement.
        
        Args:
            rancher_usage_data: Usage data from Rancher/Prometheus
                Format: {rancher_project_id: {tokens: int, gpu_seconds: int}}
        
        Returns:
            Transaction hash if submitted, None otherwise
        """
        current_epoch = self.client.get_current_epoch()
        
        if current_epoch <= self.last_processed_epoch:
            return None
        
        # Get all resellers
        resellers = self.client.get_all_resellers()
        
        reports = []
        for wallet in resellers:
            info = self.client.get_reseller_info(wallet)
            if not info or not info.active:
                continue
            
            # Match Rancher project to usage data
            usage = rancher_usage_data.get(info.rancher_project_id, {})
            tokens = usage.get('tokens', 0)
            gpu_seconds = usage.get('gpu_seconds', 0)
            
            if tokens == 0 and gpu_seconds == 0:
                continue
            
            # Calculate usage amount (50% of retail)
            # Pricing: $0.001 per token, $0.01 per GPU second
            retail_price = (tokens * 10**15) + (gpu_seconds * 10**16)
            wholesale_price = OnChainClient.calculate_wholesale_price(retail_price)
            
            reports.append(EpochUsageReport(
                reseller=wallet,
                usage_amount=wholesale_price,
                tokens_processed=tokens,
                gpu_seconds_used=gpu_seconds
            ))
        
        if not reports:
            return None
        
        # Submit on-chain
        tx_hash = self.client.report_epoch_usage(
            self.validator_private_key,
            reports
        )
        
        self.last_processed_epoch = current_epoch
        
        if bt:
            bt.logging.info(
                f"📤 Epoch {current_epoch} settlement submitted: {tx_hash}"
            )
        
        return tx_hash


# =============================================================================
# CLI HELPER FUNCTIONS
# =============================================================================

def cli_register_reseller(
    rpc_url: str,
    contract_address: str,
    private_key: str,
    hotkey_ss58: str,
    coldkey_ss58: str,
    rancher_project_id: str
) -> str:
    """
    CLI helper to register a reseller.
    
    Usage:
        kubetee reseller register \\
            --hotkey <hotkey_ss58> \\
            --coldkey <coldkey_ss58> \\
            --rancher-project <project_id>
    """
    config = OnChainConfig(
        rpc_url=rpc_url,
        contract_address=contract_address
    )
    client = OnChainClient(config)
    
    return client.register_reseller(
        private_key,
        hotkey_ss58,
        coldkey_ss58,
        rancher_project_id
    )


def cli_deposit(
    rpc_url: str,
    contract_address: str,
    token_address: str,
    private_key: str,
    amount: str  # Human readable (e.g., "100.5")
) -> str:
    """
    CLI helper to deposit tokens.
    
    Usage:
        kubetee reseller deposit --amount 100.5
    """
    config = OnChainConfig(
        rpc_url=rpc_url,
        contract_address=contract_address,
        payment_token_address=token_address
    )
    client = OnChainClient(config)
    
    # Convert to wei
    amount_wei = int(float(amount) * 10**18)
    
    return client.deposit(private_key, amount_wei)


def cli_balance(
    rpc_url: str,
    contract_address: str,
    wallet: str
) -> float:
    """
    CLI helper to check balance.
    
    Usage:
        kubetee reseller balance --wallet <address>
    """
    config = OnChainConfig(
        rpc_url=rpc_url,
        contract_address=contract_address
    )
    client = OnChainClient(config)
    
    balance_wei = client.get_balance(wallet)
    return balance_wei / 10**18

