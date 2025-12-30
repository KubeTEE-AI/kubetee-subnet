# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
Referral Revenue Share System

Implements the unified pricing + 50% revenue share model:
- ALL users pay the SAME retail price (direct or via referrer)
- Referrers earn 50% of revenue from users they bring in
- Simple, transparent, and fair for everyone

NO EMISSIONS USED - Pure revenue sharing!
"""

import time
import json
import secrets
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set
from pathlib import Path
from enum import Enum
import bittensor as bt


# =============================================================================
# REVENUE SHARE CONSTANTS
# =============================================================================

# Referrers earn 50% of revenue from referred users
REFERRER_REVENUE_SHARE = 0.50  # 50% to referrer, 50% to KubeTEE

# Attribution is permanent (referred users stay attributed forever)
ATTRIBUTION_PERMANENT = True


@dataclass
class SubscriptionPlan:
    """
    Subscription plan configuration.
    
    Each tier includes specific resources:
    - Basic: RAG (CPU) + shared NIM models in TEE
    - Professional: RAG (1 H200) + Custom Model Inference (1 H200) + weekly fine-tuning
    - Enterprise: RAG (2 H200) + Custom Model Inference (2 H200) + continuous fine-tuning
    
    ALL TIERS:
    - 1 namespace per user
    - Access to shared KubeTEE NVIDIA NIM/AIQ Blueprint models in TEE
    """
    name: str
    monthly_price: float        # USDC - fixed monthly fee
    rag_storage_gb: int         # Included RAG vector storage
    rag_gpu_count: int          # H200 GPUs for RAG server (0 = CPU only)
    inference_gpu_count: int    # H200 GPUs for custom model inference
    fine_tuning_frequency: str  # "none", "weekly", "continuous"
    sla_uptime: float           # SLA uptime percentage
    features: list              # List of included features
    
    @property
    def total_gpu_count(self) -> int:
        """Total dedicated H200 GPUs."""
        return self.rag_gpu_count + self.inference_gpu_count


# GPU Pricing
H200_HOURLY_RATE = 2.00  # $2.00/hour for NVIDIA H200


# Subscription tiers
# NOTE: All users get 1 namespace and shared access to KubeTEE NVIDIA NIM models

PLAN_BASIC = SubscriptionPlan(
    name="Basic",
    monthly_price=499.00,       # $499/month
    rag_storage_gb=50,          # 50GB RAG storage
    rag_gpu_count=0,            # RAG on CPU (no dedicated GPU)
    inference_gpu_count=0,      # Uses shared NIM models only
    fine_tuning_frequency="none",  # No custom fine-tuning
    sla_uptime=99.0,
    features=[
        "1 dedicated namespace",
        "RAG Blueprint with 50GB vector storage (CPU)",
        "Shared access to KubeTEE NVIDIA NIM models (TEE)",
        "Pre-trained models: Llama, Mistral, Nemotron, etc.",
        "Community support",
    ],
)

PLAN_PROFESSIONAL = SubscriptionPlan(
    name="Professional",
    monthly_price=1499.00,      # $1,499/month
    rag_storage_gb=100,         # 100GB RAG storage
    rag_gpu_count=1,            # 1x H200 for RAG server
    inference_gpu_count=1,      # 1x H200 for custom model inference
    fine_tuning_frequency="weekly",  # Weekly fine-tuning
    sla_uptime=99.5,
    features=[
        "1 dedicated namespace",
        "RAG Blueprint with 100GB vector storage",
        "1x H200 GPU for RAG server (dedicated)",
        "1x H200 GPU for custom model inference (dedicated)",
        "Weekly custom model fine-tuning",
        "Shared access to KubeTEE NVIDIA NIM models (TEE)",
        "Email support",
        "99.5% SLA",
    ],
)

PLAN_ENTERPRISE = SubscriptionPlan(
    name="Enterprise",
    monthly_price=4999.00,      # $4,999/month
    rag_storage_gb=500,         # 500GB+ RAG storage
    rag_gpu_count=1,            # 1x H200 for RAG server
    inference_gpu_count=2,      # 2x H200 for custom model inference (higher throughput)
    fine_tuning_frequency="continuous",  # Daily/on-demand fine-tuning
    sla_uptime=99.9,
    features=[
        "1 dedicated namespace",
        "RAG Blueprint with 500GB+ vector storage",
        "1x H200 GPU for RAG server (dedicated)",
        "2x H200 GPU for custom model inference (dedicated, higher throughput)",
        "Continuous fine-tuning (daily/on-demand)",
        "Shared access to KubeTEE NVIDIA NIM models (TEE)",
        "24/7 priority support",
        "99.9% SLA",
        "SSO/SAML integration",
        "Audit logs",
        "Custom integrations",
        "Dedicated account manager",
    ],
)

SUBSCRIPTION_PLANS = {
    "basic": PLAN_BASIC,
    "professional": PLAN_PROFESSIONAL,
    "enterprise": PLAN_ENTERPRISE,
}


@dataclass
class RetailPricing:
    """
    Retail pricing for all users (same price for direct and referred users).
    
    Prices are in USDC on BASE L2.
    
    PRICING MODEL:
    - Fixed subscription tiers with included resources
    - Pay-as-you-go for additional usage beyond subscription
    
    Subscription Tiers:
    - Basic ($499/month): RAG 50GB, CPU only, no fine-tuning
    - Professional ($1,499/month): RAG 100GB, 1x H200, weekly fine-tuning
    - Enterprise ($4,999/month): RAG 500GB, H200 cluster, continuous fine-tuning
    
    Additional usage beyond included resources is billed separately.
    """
    
    # Subscription pricing (fixed monthly)
    basic_monthly: float = 499.00          # $499/month
    professional_monthly: float = 1499.00  # $1,499/month
    enterprise_monthly: float = 4999.00    # $4,999/month
    
    # GPU pricing (for additional hours beyond subscription)
    h200_per_hour: float = 2.00  # $2.00/hour for NVIDIA H200
    
    # Token pricing
    per_1k_tokens: float = 0.02  # $0.02 per 1K tokens
    per_1k_embedding_tokens: float = 0.01  # $0.01 per 1K embedding tokens
    
    # Storage pricing (for additional storage beyond subscription)
    per_storage_gb_month: float = 0.03  # $0.03 per GB per month
    
    def get_subscription_price(self, plan: str = "basic") -> float:
        """Get fixed monthly subscription price."""
        prices = {
            "basic": self.basic_monthly,
            "professional": self.professional_monthly,
            "enterprise": self.enterprise_monthly,
        }
        return prices.get(plan.lower(), self.basic_monthly)
    
    def get_subscription_plan(self, plan: str = "basic") -> SubscriptionPlan:
        """Get subscription plan details."""
        return SUBSCRIPTION_PLANS.get(plan.lower(), PLAN_BASIC)
    
    def calculate_extra_gpu_cost(self, extra_hours: float) -> float:
        """Calculate cost for GPU hours beyond subscription."""
        return extra_hours * self.h200_per_hour
    
    def calculate_extra_storage_cost(self, extra_gb: float) -> float:
        """Calculate cost for storage beyond subscription."""
        return extra_gb * self.per_storage_gb_month
    
    def calculate_token_cost(self, tokens: int = 0, embedding_tokens: int = 0) -> float:
        """Calculate token usage cost."""
        cost = 0.0
        cost += (tokens / 1000) * self.per_1k_tokens
        cost += (embedding_tokens / 1000) * self.per_1k_embedding_tokens
        return cost
    
    def calculate_total_monthly_bill(
        self,
        plan: str = "basic",
        tokens: int = 0,
        embedding_tokens: int = 0,
        extra_gpu_hours: float = 0,
        extra_storage_gb: float = 0,
    ) -> dict:
        """
        Calculate total monthly bill.
        
        Subscription includes specific resources (RAG storage, GPU, fine-tuning).
        Additional usage is billed on top.
        """
        subscription = self.get_subscription_price(plan)
        
        # Calculate additional usage costs
        token_cost = self.calculate_token_cost(tokens, embedding_tokens)
        gpu_cost = self.calculate_extra_gpu_cost(extra_gpu_hours)
        storage_cost = self.calculate_extra_storage_cost(extra_storage_gb)
        
        usage_total = token_cost + gpu_cost + storage_cost
        
        return {
            "subscription": subscription,
            "token_usage": token_cost,
            "extra_gpu_hours": gpu_cost,
            "extra_storage": storage_cost,
            "usage_total": usage_total,
            "total": subscription + usage_total,
        }
    
    def calculate_referrer_share(self, total_cost: float) -> float:
        """Calculate referrer's share (50% of total revenue)."""
        return total_cost * REFERRER_REVENUE_SHARE
    
    def calculate_kubetee_share(self, total_cost: float, is_referred: bool = False) -> float:
        """Calculate KubeTEE's share."""
        if is_referred:
            return total_cost * (1 - REFERRER_REVENUE_SHARE)
        return total_cost  # 100% for direct users


class ReferrerType(str, Enum):
    """Type of referrer."""
    AFFILIATE = "affiliate"       # Refers users via link/code
    INTEGRATOR = "integrator"     # Embeds KubeTEE in their product
    WHITE_LABEL = "white_label"   # Rebrands KubeTEE for customers


class ReferrerStatus(str, Enum):
    """Status of a referrer account."""
    PENDING = "pending"           # Awaiting approval
    ACTIVE = "active"             # Active and can refer users
    SUSPENDED = "suspended"       # Temporarily suspended
    TERMINATED = "terminated"     # Account terminated


@dataclass
class ReferrerAccount:
    """
    Referrer/Integrator/White-Label partner account.
    
    Referrers earn 50% of revenue from users they bring in.
    All users pay the same retail price!
    
    Referrer Types:
    - AFFILIATE: Refers users via referral link/code
    - INTEGRATOR: Embeds KubeTEE into their product (API header)
    - WHITE_LABEL: Rebrands KubeTEE for their customers
    
    They DON'T need:
    - Kubernetes infrastructure
    - GPU/CPU resources
    - Technical operations
    - Subnet registration
    
    They just need:
    - Wallet for payouts (USDC on BASE)
    - Users/customers to refer
    """
    
    # Identity
    referrer_code: str  # Unique referral code (e.g., ABC123)
    name: str           # Display name or company name
    
    # Wallet for payouts
    payout_address: str  # EVM address for USDC payouts (BASE L2)
    
    # Optional: Bittensor identity (for attribution/verification)
    hotkey: Optional[str] = None
    coldkey: Optional[str] = None
    
    # Account info
    referrer_type: ReferrerType = ReferrerType.AFFILIATE
    contact_email: Optional[str] = None
    registration_timestamp: float = field(default_factory=time.time)
    status: ReferrerStatus = ReferrerStatus.PENDING
    
    # Verification
    verified: bool = False
    verified_timestamp: Optional[float] = None
    
    # Earnings tracking (in USDC)
    total_earnings: float = 0.0      # Lifetime earnings
    pending_payout: float = 0.0      # Pending withdrawal
    total_withdrawn: float = 0.0     # Total withdrawn
    
    # Referred users
    referred_users: Set[str] = field(default_factory=set)  # User IDs/wallets
    total_referred_users: int = 0
    
    # Revenue attribution
    total_referred_revenue: float = 0.0  # Total spent by referred users
    
    # Referral link/API config
    referral_link: Optional[str] = None
    api_header_value: Optional[str] = None  # For X-KubeTEE-Referrer header
    
    def add_referred_user(self, user_id: str):
        """Add a new referred user."""
        if user_id not in self.referred_users:
            self.referred_users.add(user_id)
            self.total_referred_users += 1
    
    def record_revenue(self, amount: float):
        """Record revenue from a referred user and calculate earnings."""
        self.total_referred_revenue += amount
        earnings = amount * REFERRER_REVENUE_SHARE
        self.total_earnings += earnings
        self.pending_payout += earnings
        return earnings
    
    def withdraw(self, amount: Optional[float] = None) -> float:
        """Withdraw earnings. Returns amount withdrawn."""
        if amount is None:
            amount = self.pending_payout
        
        if amount > self.pending_payout:
            amount = self.pending_payout
        
        self.pending_payout -= amount
        self.total_withdrawn += amount
        return amount
    
    def generate_referral_link(self, base_url: str = "https://kubetee.ai") -> str:
        """Generate referral link."""
        self.referral_link = f"{base_url}/signup?ref={self.referrer_code}"
        self.api_header_value = self.referrer_code
        return self.referral_link
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['referrer_type'] = self.referrer_type.value
        data['status'] = self.status.value
        data['referred_users'] = list(self.referred_users)
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "ReferrerAccount":
        data['referrer_type'] = ReferrerType(data['referrer_type'])
        data['status'] = ReferrerStatus(data['status'])
        data['referred_users'] = set(data.get('referred_users', []))
        return cls(**data)


@dataclass 
class UserAttribution:
    """
    Tracks which referrer a user was attributed to.
    
    Attribution is permanent - once a user is linked to a referrer,
    all their future spending benefits that referrer.
    """
    user_id: str           # User wallet/ID
    referrer_code: str     # Referrer who brought this user
    attribution_time: float = field(default_factory=time.time)
    first_purchase_time: Optional[float] = None
    total_spent: float = 0.0
    
    def record_purchase(self, amount: float):
        """Record a purchase from this user."""
        if self.first_purchase_time is None:
            self.first_purchase_time = time.time()
        self.total_spent += amount


def generate_referrer_code(length: int = 8) -> str:
    """Generate a unique referrer code."""
    return secrets.token_urlsafe(length)[:length].upper()


class ReferralManager:
    """
    Manages the referral revenue share system.
    
    Key Features:
    - Referrer registration and code generation
    - User → Referrer attribution (permanent)
    - Revenue tracking and automatic 50% split
    - Payout processing
    """
    
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.pricing = RetailPricing()
        
        # Referrer accounts (by referrer_code)
        self.referrers: Dict[str, ReferrerAccount] = {}
        
        # User attributions (by user_id)
        self.attributions: Dict[str, UserAttribution] = {}
        
        # Pending payouts
        self.pending_payouts: List[Dict] = []
        
        # Load existing data
        self._load_data()
        
        bt.logging.info(
            f"ReferralManager initialized:\n"
            f"  Revenue Share: {REFERRER_REVENUE_SHARE * 100}% to referrers\n"
            f"  Active Referrers: {len([r for r in self.referrers.values() if r.status == ReferrerStatus.ACTIVE])}\n"
            f"  Total Attributed Users: {len(self.attributions)}"
        )
    
    # =========================================================================
    # REFERRER MANAGEMENT
    # =========================================================================
    
    def register_referrer(
        self,
        name: str,
        payout_address: str,
        referrer_type: ReferrerType = ReferrerType.AFFILIATE,
        contact_email: Optional[str] = None,
        hotkey: Optional[str] = None,
        coldkey: Optional[str] = None,
    ) -> ReferrerAccount:
        """Register a new referrer."""
        # Generate unique code
        referrer_code = generate_referrer_code()
        while referrer_code in self.referrers:
            referrer_code = generate_referrer_code()
        
        account = ReferrerAccount(
            referrer_code=referrer_code,
            name=name,
            payout_address=payout_address,
            referrer_type=referrer_type,
            contact_email=contact_email,
            hotkey=hotkey,
            coldkey=coldkey,
        )
        
        # Generate referral link
        account.generate_referral_link()
        
        self.referrers[referrer_code] = account
        self._save_data()
        
        bt.logging.info(f"Registered referrer: {name} (code: {referrer_code})")
        return account
    
    def activate_referrer(self, referrer_code: str):
        """Activate a referrer account."""
        if referrer_code not in self.referrers:
            raise ValueError(f"Referrer {referrer_code} not found")
        
        self.referrers[referrer_code].status = ReferrerStatus.ACTIVE
        self._save_data()
        bt.logging.info(f"Activated referrer: {referrer_code}")
    
    def get_referrer(self, referrer_code: str) -> Optional[ReferrerAccount]:
        """Get referrer by code."""
        return self.referrers.get(referrer_code)
    
    # =========================================================================
    # USER ATTRIBUTION
    # =========================================================================
    
    def attribute_user(self, user_id: str, referrer_code: str) -> bool:
        """
        Attribute a user to a referrer.
        
        Attribution is permanent - only the first referrer gets credit.
        Returns True if attribution was successful (first time).
        """
        # Check if already attributed
        if user_id in self.attributions:
            bt.logging.debug(f"User {user_id[:16]}... already attributed")
            return False
        
        # Validate referrer
        if referrer_code not in self.referrers:
            bt.logging.warning(f"Invalid referrer code: {referrer_code}")
            return False
        
        referrer = self.referrers[referrer_code]
        if referrer.status != ReferrerStatus.ACTIVE:
            bt.logging.warning(f"Referrer {referrer_code} not active")
            return False
        
        # Create attribution
        attribution = UserAttribution(
            user_id=user_id,
            referrer_code=referrer_code,
        )
        self.attributions[user_id] = attribution
        
        # Update referrer
        referrer.add_referred_user(user_id)
        
        self._save_data()
        bt.logging.info(f"Attributed user {user_id[:16]}... to referrer {referrer_code}")
        return True
    
    def get_user_referrer(self, user_id: str) -> Optional[str]:
        """Get the referrer code for a user, if any."""
        attribution = self.attributions.get(user_id)
        return attribution.referrer_code if attribution else None
    
    def is_referred_user(self, user_id: str) -> bool:
        """Check if a user was referred."""
        return user_id in self.attributions
    
    # =========================================================================
    # REVENUE PROCESSING
    # =========================================================================
    
    def process_payment(
        self,
        user_id: str,
        amount: float,
    ) -> Dict[str, float]:
        """
        Process a user payment and split revenue.
        
        Returns dict with 'kubetee_share' and optionally 'referrer_share'.
        """
        result = {
            'total': amount,
            'kubetee_share': amount,
            'referrer_share': 0.0,
            'referrer_code': None,
        }
        
        # Check if user is referred
        if user_id not in self.attributions:
            return result  # Direct user, 100% to KubeTEE
        
        attribution = self.attributions[user_id]
        referrer_code = attribution.referrer_code
        
        if referrer_code not in self.referrers:
            return result
        
        referrer = self.referrers[referrer_code]
        if referrer.status != ReferrerStatus.ACTIVE:
            return result
        
        # Split revenue 50/50
        referrer_share = self.pricing.calculate_referrer_share(amount)
        kubetee_share = amount - referrer_share
        
        # Update tracking
        attribution.record_purchase(amount)
        referrer.record_revenue(amount)
        
        result['kubetee_share'] = kubetee_share
        result['referrer_share'] = referrer_share
        result['referrer_code'] = referrer_code
        
        self._save_data()
        
        bt.logging.debug(
            f"Payment processed: ${amount:.4f} total, "
            f"${kubetee_share:.4f} KubeTEE, ${referrer_share:.4f} referrer {referrer_code}"
        )
        
        return result
    
    # =========================================================================
    # PAYOUTS
    # =========================================================================
    
    def get_pending_payouts(self, min_amount: float = 10.0) -> List[Dict]:
        """Get all referrers with pending payouts above minimum."""
        payouts = []
        for referrer in self.referrers.values():
            if referrer.status == ReferrerStatus.ACTIVE and referrer.pending_payout >= min_amount:
                payouts.append({
                    'referrer_code': referrer.referrer_code,
                    'name': referrer.name,
                    'payout_address': referrer.payout_address,
                    'amount': referrer.pending_payout,
                })
        return payouts
    
    def process_payout(self, referrer_code: str, amount: Optional[float] = None) -> float:
        """Process payout for a referrer. Returns amount paid."""
        if referrer_code not in self.referrers:
            raise ValueError(f"Referrer {referrer_code} not found")
        
        referrer = self.referrers[referrer_code]
        withdrawn = referrer.withdraw(amount)
        
        self._save_data()
        bt.logging.info(f"Processed payout: ${withdrawn:.2f} to {referrer_code}")
        return withdrawn
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_referrer_stats(self, referrer_code: str) -> Dict:
        """Get statistics for a referrer."""
        if referrer_code not in self.referrers:
            return {}
        
        referrer = self.referrers[referrer_code]
        return {
            'referrer_code': referrer.referrer_code,
            'name': referrer.name,
            'status': referrer.status.value,
            'referrer_type': referrer.referrer_type.value,
            'total_referred_users': referrer.total_referred_users,
            'total_referred_revenue': referrer.total_referred_revenue,
            'total_earnings': referrer.total_earnings,
            'pending_payout': referrer.pending_payout,
            'total_withdrawn': referrer.total_withdrawn,
            'referral_link': referrer.referral_link,
        }
    
    def get_global_stats(self) -> Dict:
        """Get global referral system statistics."""
        active_referrers = [r for r in self.referrers.values() if r.status == ReferrerStatus.ACTIVE]
        return {
            'total_referrers': len(self.referrers),
            'active_referrers': len(active_referrers),
            'total_attributed_users': len(self.attributions),
            'total_referred_revenue': sum(r.total_referred_revenue for r in self.referrers.values()),
            'total_referrer_earnings': sum(r.total_earnings for r in self.referrers.values()),
            'total_pending_payouts': sum(r.pending_payout for r in self.referrers.values()),
        }
    
    # =========================================================================
    # PERSISTENCE
    # =========================================================================
    
    def _save_data(self):
        """Save all data to storage."""
        data = {
            'referrers': {k: v.to_dict() for k, v in self.referrers.items()},
            'attributions': {k: asdict(v) for k, v in self.attributions.items()},
        }
        
        with open(self.storage_path / 'referral_data.json', 'w') as f:
            json.dump(data, f, indent=2)
    
    def _load_data(self):
        """Load data from storage."""
        data_file = self.storage_path / 'referral_data.json'
        if not data_file.exists():
            return
        
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            self.referrers = {
                k: ReferrerAccount.from_dict(v) 
                for k, v in data.get('referrers', {}).items()
            }
            self.attributions = {
                k: UserAttribution(**v) 
                for k, v in data.get('attributions', {}).items()
            }
            
            bt.logging.info(f"Loaded {len(self.referrers)} referrers, {len(self.attributions)} attributions")
        except Exception as e:
            bt.logging.error(f"Error loading referral data: {e}")

