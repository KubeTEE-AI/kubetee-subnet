#!/usr/bin/env python3
"""
KubeTEE CLI - Referrer Commands

Referral revenue share system using USDC on BASE.
Referrers earn 50% of revenue from users they bring in.

═══════════════════════════════════════════════════════════════════════════════
                              QUICK START
═══════════════════════════════════════════════════════════════════════════════

# 1. Register as a referrer
kubetee referrer register --name "My Company LLC" --payout-address 0x...

# 2. Get your referral link
kubetee referrer link

# 3. Share with users → They sign up normally

# 4. Check your earnings
kubetee referrer earnings

# 5. Withdraw your earnings
kubetee referrer withdraw

═══════════════════════════════════════════════════════════════════════════════
"""

import argparse
import os
import sys
import json
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

# Web3 for BASE interaction
try:
    from web3 import Web3
    from eth_account import Account
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False

# Rich for beautiful CLI output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    Console = None


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class Config:
    """CLI Configuration loaded from environment or config file."""
    
    # BASE L2 Network
    rpc_url: str = "https://mainnet.base.org"
    chain_id: int = 8453
    
    # Contract addresses (BASE mainnet)
    referral_contract: str = ""  # KubeTEEReferral.sol
    usdc_address: str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on BASE
    
    # KubeTEE API
    api_url: str = "https://api.kubetee.ai"
    
    # User wallet (loaded from keystore)
    private_key: str = ""
    wallet_address: str = ""
    
    @classmethod
    def load(cls) -> "Config":
        """Load config from environment or ~/.kubetee/config.json"""
        config = cls()
        
        # Load from environment
        config.rpc_url = os.getenv("KUBETEE_RPC_URL", config.rpc_url)
        config.referral_contract = os.getenv("KUBETEE_REFERRAL_CONTRACT", "")
        config.api_url = os.getenv("KUBETEE_API_URL", config.api_url)
        
        # Load from config file
        config_path = Path.home() / ".kubetee" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
                config.referral_contract = data.get("referral_contract", config.referral_contract)
                config.api_url = data.get("api_url", config.api_url)
        
        return config
    
    def load_wallet(self) -> bool:
        """Load wallet from keystore."""
        keystore_path = Path.home() / ".kubetee" / "wallet.json"
        
        if not keystore_path.exists():
            return False
        
        with open(keystore_path) as f:
            data = json.load(f)
            self.private_key = data.get("private_key", "")
            self.wallet_address = data.get("address", "")
        
        return bool(self.private_key)


# Contract ABI (minimal for referrer functions)
REFERRAL_ABI = [
    {
        "name": "registerReferrer",
        "type": "function",
        "inputs": [
            {"name": "name", "type": "string"},
            {"name": "payoutAddress", "type": "address"},
            {"name": "referrerType", "type": "uint8"}  # 0=affiliate, 1=integrator, 2=white_label
        ],
        "outputs": [{"name": "referrerCode", "type": "string"}]
    },
    {
        "name": "getReferrerInfo",
        "type": "function",
        "inputs": [{"name": "wallet", "type": "address"}],
        "outputs": [
            {"name": "referrerCode", "type": "string"},
            {"name": "name", "type": "string"},
            {"name": "payoutAddress", "type": "address"},
            {"name": "referrerType", "type": "uint8"},
            {"name": "active", "type": "bool"},
            {"name": "totalReferredUsers", "type": "uint256"},
            {"name": "totalReferredRevenue", "type": "uint256"},
            {"name": "totalEarnings", "type": "uint256"},
            {"name": "pendingPayout", "type": "uint256"},
            {"name": "totalWithdrawn", "type": "uint256"}
        ],
        "stateMutability": "view"
    },
    {
        "name": "withdraw",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "amount", "type": "uint256"}]
    },
    {
        "name": "isReferrer",
        "type": "function",
        "inputs": [{"name": "wallet", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view"
    },
    {
        "name": "getReferralLink",
        "type": "function",
        "inputs": [{"name": "wallet", "type": "address"}],
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view"
    }
]


# =============================================================================
# CLI CLIENT
# =============================================================================

class ReferrerCLI:
    """KubeTEE Referrer CLI Client."""
    
    def __init__(self):
        self.config = Config.load()
        self.console = Console() if HAS_RICH else None
        
        if not HAS_WEB3:
            self._error("web3 package required. Install: pip install web3")
            sys.exit(1)
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
        
        if not self.w3.is_connected():
            self._error(f"Cannot connect to {self.config.rpc_url}")
            sys.exit(1)
        
        # Load contracts
        if self.config.referral_contract:
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.config.referral_contract),
                abi=REFERRAL_ABI
            )
        else:
            self.contract = None
    
    def _print(self, msg: str):
        """Print message."""
        if self.console:
            self.console.print(msg)
        else:
            print(msg)
    
    def _error(self, msg: str):
        """Print error message."""
        if self.console:
            self.console.print(f"[red]❌ Error:[/red] {msg}")
        else:
            print(f"Error: {msg}")
    
    def _success(self, msg: str):
        """Print success message."""
        if self.console:
            self.console.print(f"[green]✅[/green] {msg}")
        else:
            print(f"✅ {msg}")
    
    def _ensure_wallet(self) -> bool:
        """Ensure wallet is loaded."""
        if not self.config.load_wallet():
            self._error("No wallet configured. Run: kubetee wallet create")
            return False
        return True
    
    def _ensure_contract(self) -> bool:
        """Ensure contract is configured."""
        if not self.contract:
            self._error("Referral contract not configured. Set KUBETEE_REFERRAL_CONTRACT")
            return False
        return True
    
    def _from_usdc(self, amount: int) -> float:
        """Convert USDC to USD amount."""
        return amount / 1_000_000
    
    def _get_referrer_type_name(self, type_id: int) -> str:
        """Get human-readable referrer type name."""
        types = {0: "Affiliate", 1: "Integrator", 2: "White-Label"}
        return types.get(type_id, "Unknown")
    
    def _send_tx(self, tx_func, description: str) -> Optional[str]:
        """Build, sign, and send a transaction."""
        if not self._ensure_wallet():
            return None
        
        account = Account.from_key(self.config.private_key)
        
        try:
            tx = tx_func.build_transaction({
                'from': account.address,
                'nonce': self.w3.eth.get_transaction_count(account.address),
                'gas': 300000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.config.chain_id
            })
            
            signed = self.w3.eth.account.sign_transaction(tx, self.config.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            self._print(f"⏳ {description}...")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            
            if receipt.status == 1:
                self._success(f"{description} complete!")
                self._print(f"   Transaction: {tx_hash.hex()}")
                return tx_hash.hex()
            else:
                self._error(f"{description} failed")
                return None
                
        except Exception as e:
            self._error(f"Transaction failed: {e}")
            return None

    # =========================================================================
    # COMMANDS
    # =========================================================================
    
    def cmd_register(
        self, 
        name: str, 
        payout_address: str, 
        referrer_type: str = "affiliate"
    ):
        """
        Register as a KubeTEE referrer.
        
        Usage:
            kubetee referrer register --name "My Company" --payout-address 0x...
        """
        if not self._ensure_contract() or not self._ensure_wallet():
            return
        
        # Check if already registered
        is_referrer = self.contract.functions.isReferrer(
            self.config.wallet_address
        ).call()
        
        if is_referrer:
            self._print("⚠️  You are already registered as a referrer")
            return self.cmd_earnings()
        
        # Map type string to enum
        type_map = {"affiliate": 0, "integrator": 1, "white_label": 2}
        type_id = type_map.get(referrer_type.lower(), 0)
        
        payout = Web3.to_checksum_address(payout_address)
        
        result = self._send_tx(
            self.contract.functions.registerReferrer(name, payout, type_id),
            f"Registering as referrer '{name}'"
        )
        
        if result:
            self._success(f"🎉 Welcome, {name}!")
            self._print("\n📋 Next steps:")
            self._print("   1. Get your referral link: kubetee referrer link")
            self._print("   2. Share with users")
            self._print("   3. Check earnings: kubetee referrer earnings")
            self._print("\n💰 You earn 50% of all revenue from referred users!")
    
    def cmd_link(self):
        """
        Get your referral link and code.
        
        Usage:
            kubetee referrer link
        """
        if not self._ensure_contract() or not self._ensure_wallet():
            return
        
        try:
            info = self.contract.functions.getReferrerInfo(
                self.config.wallet_address
            ).call()
            
            referrer_code = info[0]
            name = info[1]
            active = info[4]
            
            if not active:
                self._error("Referrer account not active")
                return
            
            link = f"https://kubetee.ai/signup?ref={referrer_code}"
            
            if HAS_RICH and self.console:
                panel = Panel(
                    f"[bold]Referral Code:[/bold] [cyan]{referrer_code}[/cyan]\n\n"
                    f"[bold]Referral Link:[/bold]\n[green]{link}[/green]\n\n"
                    f"[bold]API Header:[/bold]\n[yellow]X-KubeTEE-Referrer: {referrer_code}[/yellow]",
                    title=f"🔗 {name} - Referral Info",
                    expand=False
                )
                self.console.print(panel)
            else:
                print(f"\n🔗 Referral Info - {name}")
                print(f"   Code: {referrer_code}")
                print(f"   Link: {link}")
                print(f"   API Header: X-KubeTEE-Referrer: {referrer_code}")
            
            self._print("\n📤 Share your link to start earning 50% of referred user revenue!")
            
        except Exception as e:
            self._error(f"Could not fetch referral info: {e}")
    
    def cmd_earnings(self):
        """
        Show your referral earnings.
        
        Usage:
            kubetee referrer earnings
        """
        if not self._ensure_contract() or not self._ensure_wallet():
            return
        
        try:
            info = self.contract.functions.getReferrerInfo(
                self.config.wallet_address
            ).call()
            
            (referrer_code, name, payout_address, referrer_type, active,
             total_users, total_revenue, total_earnings, 
             pending_payout, total_withdrawn) = info
            
            if not active:
                self._error("Referrer account not active. Register first: kubetee referrer register")
                return
            
            if HAS_RICH and self.console:
                table = Table(title="💰 Referrer Earnings")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                
                table.add_row("Name", name)
                table.add_row("Referrer Code", referrer_code)
                table.add_row("Type", self._get_referrer_type_name(referrer_type))
                table.add_row("", "")
                table.add_row("Total Referred Users", str(total_users))
                table.add_row("Total Referred Revenue", f"${self._from_usdc(total_revenue):.2f}")
                table.add_row("", "")
                table.add_row("Your Earnings (50%)", f"${self._from_usdc(total_earnings):.2f}")
                table.add_row("[bold]Pending Payout[/bold]", f"[bold]${self._from_usdc(pending_payout):.2f}[/bold]")
                table.add_row("Total Withdrawn", f"${self._from_usdc(total_withdrawn):.2f}")
                table.add_row("", "")
                table.add_row("Payout Address", payout_address[:10] + "..." + payout_address[-8:])
                
                self.console.print(table)
                
                if pending_payout > 0:
                    self._print(f"\n💸 Withdraw your earnings: kubetee referrer withdraw")
            else:
                print(f"\n💰 Referrer Earnings - {name}")
                print(f"   Code: {referrer_code}")
                print(f"   Type: {self._get_referrer_type_name(referrer_type)}")
                print(f"\n   Total Referred Users: {total_users}")
                print(f"   Total Referred Revenue: ${self._from_usdc(total_revenue):.2f}")
                print(f"\n   Your Earnings (50%): ${self._from_usdc(total_earnings):.2f}")
                print(f"   Pending Payout: ${self._from_usdc(pending_payout):.2f}")
                print(f"   Total Withdrawn: ${self._from_usdc(total_withdrawn):.2f}")
                print(f"\n   Payout Address: {payout_address}")
                
        except Exception as e:
            self._error(f"Could not fetch earnings: {e}")
    
    def cmd_withdraw(self):
        """
        Withdraw your pending earnings.
        
        Usage:
            kubetee referrer withdraw
        """
        if not self._ensure_contract() or not self._ensure_wallet():
            return
        
        # Check pending balance first
        try:
            info = self.contract.functions.getReferrerInfo(
                self.config.wallet_address
            ).call()
            
            pending = info[8]  # pending_payout
            
            if pending == 0:
                self._print("No pending earnings to withdraw")
                return
            
            self._print(f"💰 Pending: ${self._from_usdc(pending):.2f}")
            
        except Exception as e:
            self._error(f"Could not check pending: {e}")
            return
        
        result = self._send_tx(
            self.contract.functions.withdraw(),
            f"Withdrawing ${self._from_usdc(pending):.2f} USDC"
        )
        
        if result:
            self._success("Earnings sent to your payout address!")
            self.cmd_earnings()
    
    def cmd_status(self):
        """
        Show full referrer status.
        
        Usage:
            kubetee referrer status
        """
        self.cmd_link()
        self._print("")
        self.cmd_earnings()


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="kubetee referrer",
        description="KubeTEE Referrer Management - Earn 50% Revenue Share (USDC on BASE)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Register
    reg_parser = subparsers.add_parser("register", help="Register as a referrer")
    reg_parser.add_argument("--name", "-n", required=True, help="Your name or company name")
    reg_parser.add_argument("--payout-address", "-p", required=True, help="USDC payout address (BASE)")
    reg_parser.add_argument(
        "--type", "-t", 
        choices=["affiliate", "integrator", "white_label"],
        default="affiliate",
        help="Referrer type"
    )
    
    # Link
    subparsers.add_parser("link", help="Get your referral link and code")
    
    # Earnings
    subparsers.add_parser("earnings", help="Show your earnings")
    
    # Withdraw
    subparsers.add_parser("withdraw", help="Withdraw pending earnings")
    
    # Status
    subparsers.add_parser("status", help="Show full status")
    
    args = parser.parse_args()
    
    cli = ReferrerCLI()
    
    if args.command == "register":
        cli.cmd_register(args.name, args.payout_address, args.type)
    elif args.command == "link":
        cli.cmd_link()
    elif args.command == "earnings":
        cli.cmd_earnings()
    elif args.command == "withdraw":
        cli.cmd_withdraw()
    elif args.command == "status":
        cli.cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

