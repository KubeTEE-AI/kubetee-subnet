"""
KubeTEE AI - x402 Payment Protocol Integration

The x402 protocol is an open payment standard that brings crypto payments
directly into HTTP server/client relationships. It uses the HTTP 402 
(Payment Required) status code to enable micropayments for API access.

PERFECT FOR:
- AI agent micropayments
- Per-request API billing
- Streaming payments
- Autonomous agent-to-agent transactions

Reference: https://www.x402.org/
GitHub: https://github.com/xpaysh/awesome-x402

═══════════════════════════════════════════════════════════════════════════════
                              x402 PAYMENT FLOW
═══════════════════════════════════════════════════════════════════════════════

1. CLIENT REQUEST:
   GET /api/inference HTTP/1.1
   
2. SERVER RESPONSE (if payment required):
   HTTP/1.1 402 Payment Required
   Content-Type: application/json
   X-Payment-Required: true
   
   {
     "amount": "0.001",
     "token": "USDC",
     "network": "base",
     "recipient": "0x...",
     "memo": "inference:llama-70b:1000tokens"
   }

3. CLIENT PAYS:
   Client signs payment with wallet
   Includes X-Payment-Authorization header

4. SERVER GRANTS ACCESS:
   Verifies payment on-chain
   Returns requested resource

═══════════════════════════════════════════════════════════════════════════════
                         KUBETEE AI INTEGRATION
═══════════════════════════════════════════════════════════════════════════════

KubeTEE AI uses x402 for:
- Direct API access payments (bypass reseller model)
- AI agent autonomous payments
- Per-token or per-request micropayments
- Multi-chain support (BASE primary, Bittensor EVM secondary)

Token Support:
- wKUBETEE (Wrapped KubeTEE Alpha on BASE)
- USDC (Universal stablecoin)
- wTAO (Wrapped TAO)

═══════════════════════════════════════════════════════════════════════════════
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import json
import hashlib
import time
import hmac

# Optional web3 for on-chain verification
try:
    from web3 import Web3
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False


# =============================================================================
# CONFIGURATION
# =============================================================================

class SupportedNetwork(Enum):
    """Supported networks for x402 payments."""
    BASE = "base"
    BASE_SEPOLIA = "base-sepolia"  # Testnet
    BITTENSOR_EVM = "bittensor-evm"
    ETHEREUM = "ethereum"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"


class SupportedToken(Enum):
    """Supported tokens for x402 payments."""
    USDC = "USDC"
    WKUBETEE = "wKUBETEE"  # Wrapped KubeTEE Alpha
    WTAO = "wTAO"         # Wrapped TAO
    ETH = "ETH"


@dataclass
class X402Config:
    """x402 Protocol configuration."""
    
    # Primary network (BASE recommended for x402)
    primary_network: SupportedNetwork = SupportedNetwork.BASE
    
    # Recipient address for payments
    recipient_address: str = ""
    
    # Token contract addresses by network
    token_addresses: Dict[SupportedNetwork, Dict[SupportedToken, str]] = field(
        default_factory=lambda: {
            SupportedNetwork.BASE: {
                SupportedToken.USDC: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                SupportedToken.WKUBETEE: "",  # To be deployed
                SupportedToken.ETH: "0x4200000000000000000000000000000000000006",  # WETH
            },
            SupportedNetwork.BASE_SEPOLIA: {
                SupportedToken.USDC: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Test USDC
            },
        }
    )
    
    # Pricing in USD
    pricing: Dict[str, float] = field(default_factory=lambda: {
        "inference_per_1k_tokens": 0.001,    # $0.001 per 1K tokens
        "embedding_per_1k_tokens": 0.0005,   # $0.0005 per 1K tokens
        "gpu_per_second": 0.01,              # $0.01 per GPU second
        "storage_per_gb_day": 0.001,         # $0.001 per GB/day
    })


# =============================================================================
# x402 DATA STRUCTURES
# =============================================================================

@dataclass
class PaymentRequest:
    """
    x402 Payment Request.
    
    Sent by server in HTTP 402 response.
    """
    amount: str              # Amount in token decimals (e.g., "1000000" for 1 USDC)
    token: SupportedToken    # Token to pay with
    network: SupportedNetwork
    recipient: str           # Payment recipient address
    memo: str               # Service/resource identifier
    expires_at: int         # Unix timestamp when payment offer expires
    nonce: str              # Unique nonce to prevent replay
    
    def to_json(self) -> str:
        """Convert to JSON for HTTP response."""
        return json.dumps({
            "x402": {
                "version": "1.0",
                "amount": self.amount,
                "token": self.token.value,
                "network": self.network.value,
                "recipient": self.recipient,
                "memo": self.memo,
                "expiresAt": self.expires_at,
                "nonce": self.nonce,
            }
        })
    
    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers."""
        return {
            "X-Payment-Required": "true",
            "X-Payment-Amount": self.amount,
            "X-Payment-Token": self.token.value,
            "X-Payment-Network": self.network.value,
            "X-Payment-Recipient": self.recipient,
            "X-Payment-Memo": self.memo,
            "X-Payment-Expires": str(self.expires_at),
            "X-Payment-Nonce": self.nonce,
        }


@dataclass
class PaymentAuthorization:
    """
    x402 Payment Authorization.
    
    Sent by client in subsequent request after signing payment.
    Uses ERC-3009 transferWithAuthorization for gasless transfers.
    """
    payer: str              # Payer's address
    amount: str             # Amount authorized
    token: SupportedToken
    network: SupportedNetwork
    nonce: str              # Must match PaymentRequest nonce
    valid_after: int        # Unix timestamp
    valid_before: int       # Unix timestamp
    signature: str          # EIP-712 signature (v, r, s concatenated)
    
    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> Optional["PaymentAuthorization"]:
        """Parse from HTTP headers."""
        auth_header = headers.get("X-Payment-Authorization")
        if not auth_header:
            return None
        
        try:
            data = json.loads(auth_header)
            return cls(
                payer=data["payer"],
                amount=data["amount"],
                token=SupportedToken(data["token"]),
                network=SupportedNetwork(data["network"]),
                nonce=data["nonce"],
                valid_after=data["validAfter"],
                valid_before=data["validBefore"],
                signature=data["signature"],
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None


# =============================================================================
# x402 SERVER (KubeTEE API Integration)
# =============================================================================

class X402Server:
    """
    x402 Server implementation for KubeTEE API.
    
    Integrates x402 payment protocol into API endpoints.
    """
    
    def __init__(self, config: X402Config):
        self.config = config
        
        # Initialize Web3 for on-chain verification
        if HAS_WEB3:
            self.w3 = Web3(Web3.HTTPProvider(self._get_rpc_url()))
        else:
            self.w3 = None
    
    def _get_rpc_url(self) -> str:
        """Get RPC URL for configured network."""
        urls = {
            SupportedNetwork.BASE: "https://mainnet.base.org",
            SupportedNetwork.BASE_SEPOLIA: "https://sepolia.base.org",
            SupportedNetwork.BITTENSOR_EVM: "https://evm.bittensor.network",
        }
        return urls.get(self.config.primary_network, urls[SupportedNetwork.BASE])
    
    def create_payment_request(
        self,
        service: str,
        units: int,
        token: SupportedToken = SupportedToken.USDC
    ) -> PaymentRequest:
        """
        Create a payment request for a service.
        
        Args:
            service: Service type (e.g., "inference_per_1k_tokens")
            units: Number of units (e.g., 5 for 5K tokens)
            token: Payment token
            
        Returns:
            PaymentRequest to include in 402 response
        """
        # Calculate price
        unit_price = self.config.pricing.get(service, 0.001)
        total_usd = unit_price * units
        
        # Convert to token amount (assuming 6 decimals for USDC)
        if token == SupportedToken.USDC:
            amount = str(int(total_usd * 1_000_000))  # 6 decimals
        else:
            amount = str(int(total_usd * 1e18))  # 18 decimals
        
        # Generate nonce
        nonce = hashlib.sha256(
            f"{time.time()}{service}{units}".encode()
        ).hexdigest()[:16]
        
        return PaymentRequest(
            amount=amount,
            token=token,
            network=self.config.primary_network,
            recipient=self.config.recipient_address,
            memo=f"kubetee:{service}:{units}",
            expires_at=int(time.time()) + 300,  # 5 minutes
            nonce=nonce,
        )
    
    def verify_payment(
        self,
        request: PaymentRequest,
        authorization: PaymentAuthorization
    ) -> bool:
        """
        Verify a payment authorization.
        
        In production, this would:
        1. Verify the signature is valid
        2. Check the payment was executed on-chain
        3. Confirm the amount matches
        
        Args:
            request: Original payment request
            authorization: Client's payment authorization
            
        Returns:
            True if payment is valid
        """
        # Verify nonce matches
        if authorization.nonce != request.nonce:
            return False
        
        # Verify amount matches
        if authorization.amount != request.amount:
            return False
        
        # Verify not expired
        if int(time.time()) > request.expires_at:
            return False
        
        # TODO: On-chain verification
        # In production, verify the transferWithAuthorization was executed
        # or execute it ourselves if using gasless pattern
        
        return True
    
    def get_402_response(
        self,
        service: str,
        units: int,
        token: SupportedToken = SupportedToken.USDC
    ) -> tuple:
        """
        Generate HTTP 402 response tuple.
        
        Returns:
            (status_code, headers, body) tuple for HTTP response
        """
        payment_request = self.create_payment_request(service, units, token)
        
        return (
            402,
            {
                "Content-Type": "application/json",
                **payment_request.to_headers(),
            },
            payment_request.to_json(),
        )


# =============================================================================
# FLASK/FASTAPI MIDDLEWARE EXAMPLE
# =============================================================================

def x402_paywall(amount: float, service: str = "api_call"):
    """
    Decorator for x402 paywall on API endpoints.
    
    Usage (Flask):
        @app.route('/api/inference')
        @x402_paywall(amount=0.001, service="inference_per_1k_tokens")
        def inference():
            return {"result": "..."}
    
    Usage (FastAPI):
        @app.get("/api/inference")
        @x402_paywall(amount=0.001, service="inference_per_1k_tokens")
        async def inference():
            return {"result": "..."}
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # This is a simplified example
            # In production, integrate with your framework's request context
            
            # Check for payment authorization header
            # If not present, return 402 with payment request
            # If present, verify and proceed
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# CLI HELPERS
# =============================================================================

def estimate_cost(
    config: X402Config,
    service: str,
    units: int
) -> Dict[str, Any]:
    """
    Estimate cost for a service.
    
    Usage:
        kubetee estimate-cost --service inference_per_1k_tokens --units 100
    """
    unit_price = config.pricing.get(service, 0.001)
    total_usd = unit_price * units
    
    return {
        "service": service,
        "units": units,
        "unit_price_usd": unit_price,
        "total_usd": total_usd,
        "total_usdc": f"{total_usd:.6f}",
        "network": config.primary_network.value,
    }


# =============================================================================
# INTEGRATION WITH KUBETEE RESELLER SYSTEM
# =============================================================================

"""
x402 vs Reseller Model Comparison:

┌─────────────────────────────────────────────────────────────────────────────┐
│                        PAYMENT MODEL COMPARISON                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   RESELLER MODEL (KubeTEEPayment.sol on Bittensor EVM):                    │
│   ─────────────────────────────────────────────────────────────────────    │
│   • Prepaid deposits                                                        │
│   • Epoch-based settlement                                                  │
│   • 50% wholesale discount                                                  │
│   • Best for: B2B, high-volume, consistent usage                           │
│                                                                             │
│   x402 MODEL (BASE L2):                                                     │
│   ─────────────────────────────────────────────────────────────────────    │
│   • Per-request micropayments                                               │
│   • Instant settlement                                                      │
│   • Retail pricing                                                          │
│   • Best for: AI agents, developers, sporadic usage                        │
│                                                                             │
│   HYBRID APPROACH (Recommended):                                            │
│   ─────────────────────────────────────────────────────────────────────    │
│   • Use x402 for direct API access (retail customers, AI agents)           │
│   • Use Reseller model for enterprise/wholesale                            │
│   • Both settle to KubeTEE Owner ultimately                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""

