# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
Reseller/White-Label Wholesale System

Implements the B2B wholesale model:
- Resellers pay 50% of retail price
- Miners receive 50% of wholesale price (25% of retail)
- KubeTEE receives 50% of wholesale price (25% of retail)

NO EMISSIONS USED - Pure B2B commerce!
"""

import time
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set
from pathlib import Path
from enum import Enum
import bittensor as bt


# =============================================================================
# PRICING CONSTANTS
# =============================================================================

# Resellers pay 50% of suggested retail price
WHOLESALE_DISCOUNT = 0.50  # 50% discount from retail

# Of the wholesale price received:
# - 50% goes to the miner who served the request
# - 50% goes to KubeTEE (subnet treasury/operations)
MINER_REVENUE_SHARE = 0.50  # Miners get 50% of wholesale price


@dataclass
class WholesalePricing:
    """Pricing structure for wholesale services."""
    
    # Retail prices (what end users would pay)
    retail_per_1k_tokens: float = 0.02  # Alpha per 1K tokens
    retail_per_gpu_second: float = 0.002  # Alpha per GPU second
    retail_per_embedding_1k: float = 0.01  # Alpha per 1K embedding tokens
    retail_per_storage_gb_day: float = 0.001  # Alpha per GB per day
    
    @property
    def wholesale_per_1k_tokens(self) -> float:
        """Reseller pays 50% of retail."""
        return self.retail_per_1k_tokens * WHOLESALE_DISCOUNT
    
    @property
    def wholesale_per_gpu_second(self) -> float:
        return self.retail_per_gpu_second * WHOLESALE_DISCOUNT
    
    @property
    def wholesale_per_embedding_1k(self) -> float:
        return self.retail_per_embedding_1k * WHOLESALE_DISCOUNT
    
    @property
    def wholesale_per_storage_gb_day(self) -> float:
        return self.retail_per_storage_gb_day * WHOLESALE_DISCOUNT
    
    def calculate_wholesale_cost(
        self,
        tokens: int = 0,
        gpu_seconds: float = 0,
        embedding_tokens: int = 0,
        storage_gb_days: float = 0,
    ) -> float:
        """Calculate total wholesale cost for a service."""
        cost = 0.0
        cost += (tokens / 1000) * self.wholesale_per_1k_tokens
        cost += gpu_seconds * self.wholesale_per_gpu_second
        cost += (embedding_tokens / 1000) * self.wholesale_per_embedding_1k
        cost += storage_gb_days * self.wholesale_per_storage_gb_day
        return cost
    
    def calculate_miner_payment(self, wholesale_cost: float) -> float:
        """Calculate miner's share (50% of wholesale)."""
        return wholesale_cost * MINER_REVENUE_SHARE
    
    def calculate_treasury_share(self, wholesale_cost: float) -> float:
        """Calculate treasury's share (50% of wholesale)."""
        return wholesale_cost * (1 - MINER_REVENUE_SHARE)


class ResellerStatus(str, Enum):
    """Status of a reseller account."""
    PENDING = "pending"           # Awaiting approval
    ACTIVE = "active"             # Active and can use services
    SUSPENDED = "suspended"       # Temporarily suspended
    TERMINATED = "terminated"     # Account terminated


@dataclass
class ResellerAccount:
    """
    Reseller/White-Label partner account.
    
    Resellers are PURE DISTRIBUTORS - they DON'T have infrastructure!
    
    Business Model:
    - Have their own coldkey/hotkey (for identity, not subnet registration)
    - Deposit Alpha to get credits at 50% of retail price
    - Use credits to access AI services on SUBNET MINERS' infrastructure
    - Charge their own customers whatever they want
    - Profit = Customer price - 50% wholesale price
    
    They DON'T need:
    - Kubernetes infrastructure
    - GPU/CPU resources
    - Technical operations
    
    They just need:
    - Hotkey/Coldkey with Alpha
    - Customers to resell to
    """
    
    # Identity (NOT registered on subnet)
    hotkey: str
    coldkey: str
    
    # Account info
    company_name: str
    contact_email: str
    registration_timestamp: float = field(default_factory=time.time)
    status: ResellerStatus = ResellerStatus.PENDING
    
    # KYC/Verification
    kyc_verified: bool = False
    kyc_timestamp: Optional[float] = None
    
    # Credit balance (in Alpha, at wholesale prices)
    credit_balance: float = 0.0
    total_deposited: float = 0.0
    total_spent: float = 0.0
    
    # API access
    api_key: Optional[str] = None
    api_key_created: Optional[float] = None
    rate_limit_per_minute: int = 100
    
    # Usage tracking
    total_requests: int = 0
    total_tokens_processed: int = 0
    total_gpu_seconds: float = 0.0
    
    def deposit(self, amount: float):
        """Add credits from Alpha deposit."""
        self.credit_balance += amount
        self.total_deposited += amount
    
    def spend(self, amount: float) -> bool:
        """Spend credits for a service. Returns False if insufficient."""
        if amount > self.credit_balance:
            return False
        self.credit_balance -= amount
        self.total_spent += amount
        return True
    
    def has_sufficient_credits(self, amount: float) -> bool:
        """Check if reseller has enough credits."""
        return self.credit_balance >= amount
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "ResellerAccount":
        data['status'] = ResellerStatus(data['status'])
        return cls(**data)


@dataclass
class MinerProvider:
    """
    Miner who provides infrastructure services.
    
    Miners PROVIDE THE INFRASTRUCTURE that resellers use!
    
    Two types of miners:
    
    1. REGISTERED MINERS (on Bittensor subnet):
       - Earn emissions (60% Infrastructure, 40% Open Source)
       - ALSO earn 50% of wholesale payments from reseller requests
       - Full participation in subnet
    
    2. WHOLESALE-ONLY MINERS (NOT registered on subnet):
       - DON'T earn emissions
       - ONLY earn 50% of wholesale payments
       - Simpler onboarding, just need hotkey/coldkey
       - Provide infrastructure for reseller requests
    
    Both need:
    - Coldkey/Hotkey (for identity and payment)
    - Alpha tokens (for receiving payments)
    - Kubernetes infrastructure (to serve requests)
    """
    
    # Identity (NOT registered on subnet)
    hotkey: str
    coldkey: str
    
    # Infrastructure info
    cluster_id: str
    region: str
    
    # Capabilities
    gpu_model: Optional[str] = None
    gpu_count: int = 0
    tee_enabled: bool = False
    max_concurrent_requests: int = 100
    
    # Registration
    registration_timestamp: float = field(default_factory=time.time)
    verified: bool = False
    active: bool = True
    
    # Earnings (from wholesale payments, NOT emissions)
    total_earned: float = 0.0
    pending_payment: float = 0.0
    total_requests_served: int = 0
    
    # Performance metrics
    uptime_percentage: float = 100.0
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0
    
    def record_earnings(self, amount: float):
        """Record earnings from serving a request."""
        self.pending_payment += amount
        self.total_earned += amount
        self.total_requests_served += 1
    
    def claim_payment(self) -> float:
        """Claim pending payment (for withdrawal)."""
        amount = self.pending_payment
        self.pending_payment = 0.0
        return amount
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "MinerProvider":
        return cls(**data)


class WholesaleManager:
    """
    Manages the wholesale/white-label system.
    
    This is the OFF-CHAIN implementation (MVP).
    For trustless on-chain implementation, see contracts/KubeTEEEscrow.sol
    """
    
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.pricing = WholesalePricing()
        
        # Reseller accounts (by hotkey)
        self.resellers: Dict[str, ResellerAccount] = {}
        
        # Miner providers (by hotkey)
        self.miners: Dict[str, MinerProvider] = {}
        
        # Treasury balance (subnet's share)
        self.treasury_balance: float = 0.0
        
        # Load existing data
        self._load_data()
        
        bt.logging.info(
            f"WholesaleManager initialized:\n"
            f"  Wholesale Discount: {WHOLESALE_DISCOUNT * 100}% off retail\n"
            f"  Miner Share: {MINER_REVENUE_SHARE * 100}% of wholesale\n"
            f"  Active Resellers: {len([r for r in self.resellers.values() if r.status == ResellerStatus.ACTIVE])}\n"
            f"  Active Miners: {len([m for m in self.miners.values() if m.active])}"
        )
    
    # =========================================================================
    # RESELLER MANAGEMENT
    # =========================================================================
    
    def register_reseller(
        self,
        hotkey: str,
        coldkey: str,
        company_name: str,
        contact_email: str,
    ) -> ResellerAccount:
        """Register a new reseller account."""
        if hotkey in self.resellers:
            raise ValueError(f"Reseller with hotkey {hotkey[:16]}... already exists")
        
        account = ResellerAccount(
            hotkey=hotkey,
            coldkey=coldkey,
            company_name=company_name,
            contact_email=contact_email,
        )
        
        self.resellers[hotkey] = account
        self._save_data()
        
        bt.logging.info(f"Registered reseller: {company_name} ({hotkey[:16]}...)")
        return account
    
    def approve_reseller(self, hotkey: str, api_key: str):
        """Approve a reseller and issue API key."""
        if hotkey not in self.resellers:
            raise ValueError(f"Reseller {hotkey[:16]}... not found")
        
        reseller = self.resellers[hotkey]
        reseller.status = ResellerStatus.ACTIVE
        reseller.api_key = api_key
        reseller.api_key_created = time.time()
        
        self._save_data()
        bt.logging.info(f"Approved reseller: {reseller.company_name}")
    
    def process_deposit(self, hotkey: str, alpha_amount: float):
        """
        Process an Alpha deposit from a reseller.
        
        The reseller pays Alpha at 50% of retail price.
        """
        if hotkey not in self.resellers:
            raise ValueError(f"Reseller {hotkey[:16]}... not found")
        
        reseller = self.resellers[hotkey]
        reseller.deposit(alpha_amount)
        
        self._save_data()
        bt.logging.info(
            f"Deposit processed: {reseller.company_name}, "
            f"amount={alpha_amount:.6f} Alpha, "
            f"new_balance={reseller.credit_balance:.6f}"
        )
    
    def get_reseller(self, hotkey: str) -> Optional[ResellerAccount]:
        """Get reseller by hotkey."""
        return self.resellers.get(hotkey)
    
    def get_reseller_by_api_key(self, api_key: str) -> Optional[ResellerAccount]:
        """Get reseller by API key."""
        for reseller in self.resellers.values():
            if reseller.api_key == api_key:
                return reseller
        return None
    
    # =========================================================================
    # MINER MANAGEMENT
    # =========================================================================
    
    def register_miner(
        self,
        hotkey: str,
        coldkey: str,
        cluster_id: str,
        region: str,
        **kwargs
    ) -> MinerProvider:
        """
        Register a miner provider.
        
        NOTE: Miners DON'T need to register on Bittensor subnet!
        They just need hotkey/coldkey for identity and payment.
        """
        if hotkey in self.miners:
            raise ValueError(f"Miner with hotkey {hotkey[:16]}... already exists")
        
        miner = MinerProvider(
            hotkey=hotkey,
            coldkey=coldkey,
            cluster_id=cluster_id,
            region=region,
            **kwargs
        )
        
        self.miners[hotkey] = miner
        self._save_data()
        
        bt.logging.info(f"Registered miner: {cluster_id} in {region} ({hotkey[:16]}...)")
        return miner
    
    def get_miner(self, hotkey: str) -> Optional[MinerProvider]:
        """Get miner by hotkey."""
        return self.miners.get(hotkey)
    
    def get_available_miners(self, region: Optional[str] = None) -> List[MinerProvider]:
        """Get list of available miners, optionally filtered by region."""
        miners = [m for m in self.miners.values() if m.active and m.verified]
        if region:
            miners = [m for m in miners if m.region == region]
        return miners
    
    # =========================================================================
    # SERVICE PROCESSING
    # =========================================================================
    
    def process_service_request(
        self,
        reseller_hotkey: str,
        miner_hotkey: str,
        tokens: int = 0,
        gpu_seconds: float = 0,
        embedding_tokens: int = 0,
    ) -> Dict:
        """
        Process a service request from a reseller.
        
        Flow:
        1. Calculate wholesale cost
        2. Deduct from reseller credits
        3. Pay miner 50% of wholesale
        4. Treasury receives 50% of wholesale
        
        Returns:
            Dict with transaction details
        """
        reseller = self.resellers.get(reseller_hotkey)
        miner = self.miners.get(miner_hotkey)
        
        if not reseller:
            raise ValueError(f"Reseller {reseller_hotkey[:16]}... not found")
        if not miner:
            raise ValueError(f"Miner {miner_hotkey[:16]}... not found")
        if reseller.status != ResellerStatus.ACTIVE:
            raise ValueError(f"Reseller account is not active")
        
        # Calculate costs
        wholesale_cost = self.pricing.calculate_wholesale_cost(
            tokens=tokens,
            gpu_seconds=gpu_seconds,
            embedding_tokens=embedding_tokens,
        )
        
        miner_payment = self.pricing.calculate_miner_payment(wholesale_cost)
        treasury_share = self.pricing.calculate_treasury_share(wholesale_cost)
        
        # Check reseller has sufficient credits
        if not reseller.has_sufficient_credits(wholesale_cost):
            raise ValueError(
                f"Insufficient credits: need {wholesale_cost:.6f}, "
                f"have {reseller.credit_balance:.6f}"
            )
        
        # Process transaction
        reseller.spend(wholesale_cost)
        reseller.total_requests += 1
        reseller.total_tokens_processed += tokens + embedding_tokens
        reseller.total_gpu_seconds += gpu_seconds
        
        miner.record_earnings(miner_payment)
        
        self.treasury_balance += treasury_share
        
        self._save_data()
        
        bt.logging.debug(
            f"Service processed: reseller={reseller.company_name}, "
            f"miner={miner.cluster_id}, cost={wholesale_cost:.6f}, "
            f"miner_payment={miner_payment:.6f}"
        )
        
        return {
            "wholesale_cost": wholesale_cost,
            "miner_payment": miner_payment,
            "treasury_share": treasury_share,
            "reseller_balance": reseller.credit_balance,
            "miner_pending": miner.pending_payment,
        }
    
    # =========================================================================
    # MINER PAYMENTS
    # =========================================================================
    
    def process_miner_withdrawal(self, miner_hotkey: str) -> float:
        """
        Process a miner's withdrawal of pending payments.
        
        In the off-chain model, this triggers a manual Alpha transfer.
        In the on-chain model, this calls the smart contract.
        
        Returns:
            Amount to be transferred
        """
        miner = self.miners.get(miner_hotkey)
        if not miner:
            raise ValueError(f"Miner {miner_hotkey[:16]}... not found")
        
        amount = miner.claim_payment()
        self._save_data()
        
        bt.logging.info(
            f"Miner withdrawal: {miner.cluster_id}, amount={amount:.6f} Alpha"
        )
        
        return amount
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_statistics(self) -> Dict:
        """Get wholesale system statistics."""
        active_resellers = [r for r in self.resellers.values() if r.status == ResellerStatus.ACTIVE]
        active_miners = [m for m in self.miners.values() if m.active]
        
        total_reseller_balance = sum(r.credit_balance for r in self.resellers.values())
        total_reseller_spent = sum(r.total_spent for r in self.resellers.values())
        total_miner_earned = sum(m.total_earned for m in self.miners.values())
        total_miner_pending = sum(m.pending_payment for m in self.miners.values())
        
        return {
            "active_resellers": len(active_resellers),
            "active_miners": len(active_miners),
            "total_reseller_balance": total_reseller_balance,
            "total_reseller_spent": total_reseller_spent,
            "total_miner_earned": total_miner_earned,
            "total_miner_pending": total_miner_pending,
            "treasury_balance": self.treasury_balance,
            "wholesale_discount": f"{WHOLESALE_DISCOUNT * 100}%",
            "miner_revenue_share": f"{MINER_REVENUE_SHARE * 100}%",
        }
    
    # =========================================================================
    # PERSISTENCE
    # =========================================================================
    
    def _save_data(self):
        """Save all data to disk."""
        data = {
            "resellers": {k: v.to_dict() for k, v in self.resellers.items()},
            "miners": {k: v.to_dict() for k, v in self.miners.items()},
            "treasury_balance": self.treasury_balance,
            "pricing": asdict(self.pricing),
        }
        
        filepath = self.storage_path / "wholesale_data.json"
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_data(self):
        """Load data from disk."""
        filepath = self.storage_path / "wholesale_data.json"
        if not filepath.exists():
            return
        
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            
            for k, v in data.get("resellers", {}).items():
                self.resellers[k] = ResellerAccount.from_dict(v)
            
            for k, v in data.get("miners", {}).items():
                self.miners[k] = MinerProvider.from_dict(v)
            
            self.treasury_balance = data.get("treasury_balance", 0.0)
            
            bt.logging.info(
                f"Loaded wholesale data: "
                f"{len(self.resellers)} resellers, "
                f"{len(self.miners)} miners"
            )
        except Exception as e:
            bt.logging.warning(f"Could not load wholesale data: {e}")

