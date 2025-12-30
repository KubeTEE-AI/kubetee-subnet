#!/usr/bin/env python3
"""
KubeTEE CLI - Reseller Commands

Simplified reseller management using USDC on BASE.

═══════════════════════════════════════════════════════════════════════════════
                              QUICK START
═══════════════════════════════════════════════════════════════════════════════

# 1. Register as a reseller
kubetee reseller register --namespace my-company --name "My Company LLC"

# 2. Deposit USDC ($100)
kubetee reseller deposit 100

# 3. Check your balance
kubetee reseller balance

# 4. View usage this epoch
kubetee reseller status

# 5. Withdraw unused funds
kubetee reseller withdraw 50

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
    from rich.progress import Progress
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
    reseller_contract: str = ""  # KubeTEEReseller.sol
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
        config.reseller_contract = os.getenv("KUBETEE_RESELLER_CONTRACT", "")
        config.api_url = os.getenv("KUBETEE_API_URL", config.api_url)
        
        # Load from config file
        config_path = Path.home() / ".kubetee" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
                config.reseller_contract = data.get("reseller_contract", config.reseller_contract)
                config.api_url = data.get("api_url", config.api_url)
        
        return config
    
    def load_wallet(self) -> bool:
        """Load wallet from keystore."""
        keystore_path = Path.home() / ".kubetee" / "wallet.json"
        
        if not keystore_path.exists():
            return False
        
        # For simplicity, store unencrypted (in production, use encrypted keystore)
        with open(keystore_path) as f:
            data = json.load(f)
            self.private_key = data.get("private_key", "")
            self.wallet_address = data.get("address", "")
        
        return bool(self.private_key)


# Contract ABI (minimal for reseller functions)
RESELLER_ABI = [
    {
        "name": "register",
        "type": "function",
        "inputs": [
            {"name": "namespace", "type": "string"},
            {"name": "name", "type": "string"}
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
        "name": "getResellerInfo",
        "type": "function",
        "inputs": [{"name": "wallet", "type": "address"}],
        "outputs": [
            {"name": "namespace", "type": "string"},
            {"name": "name", "type": "string"},
            {"name": "active", "type": "bool"},
            {"name": "balance", "type": "uint256"},
            {"name": "currentUsage", "type": "uint256"},
            {"name": "available", "type": "uint256"},
            {"name": "totalSpent", "type": "uint256"}
        ],
        "stateMutability": "view"
    },
    {
        "name": "isReseller",
        "type": "function",
        "inputs": [{"name": "wallet", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
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
    },
    {
        "name": "allowance",
        "type": "function",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"}
        ],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view"
    }
]


# =============================================================================
# CLI CLIENT
# =============================================================================

class ResellerCLI:
    """KubeTEE Reseller CLI Client."""
    
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
        if self.config.reseller_contract:
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.config.reseller_contract),
                abi=RESELLER_ABI
            )
        else:
            self.contract = None
        
        self.usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.config.usdc_address),
            abi=ERC20_ABI
        )
    
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
            self._error("Reseller contract not configured. Set KUBETEE_RESELLER_CONTRACT")
            return False
        return True
    
    def _to_usdc(self, amount: float) -> int:
        """Convert USD amount to USDC (6 decimals)."""
        return int(amount * 1_000_000)
    
    def _from_usdc(self, amount: int) -> float:
        """Convert USDC to USD amount."""
        return amount / 1_000_000
    
    def _send_tx(self, tx_func, description: str) -> Optional[str]:
        """Build, sign, and send a transaction."""
        if not self._ensure_wallet():
            return None
        
        account = Account.from_key(self.config.private_key)
        
        try:
            # Build transaction
            tx = tx_func.build_transaction({
                'from': account.address,
                'nonce': self.w3.eth.get_transaction_count(account.address),
                'gas': 300000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.config.chain_id
            })
            
            # Sign and send
            signed = self.w3.eth.account.sign_transaction(tx, self.config.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            self._print(f"⏳ {description}...")
            
            # Wait for confirmation
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
    
    def cmd_register(self, namespace: str, name: str):
        """
        Register as a KubeTEE reseller.
        
        Usage:
            kubetee reseller register --namespace acme --name "ACME Corp"
        """
        if not self._ensure_contract() or not self._ensure_wallet():
            return
        
        # Check if already registered
        is_reseller = self.contract.functions.isReseller(
            self.config.wallet_address
        ).call()
        
        if is_reseller:
            self._print("⚠️  You are already registered as a reseller")
            return self.cmd_status()
        
        # Register on contract
        result = self._send_tx(
            self.contract.functions.register(namespace, name),
            f"Registering as reseller '{name}'"
        )
        
        if result:
            self._success(f"🎉 Welcome aboard, {name}!")
            self._print("\n📋 Next steps:")
            self._print("   1. Deposit USDC: kubetee reseller deposit 100")
            self._print("   2. Check balance: kubetee reseller balance")
            self._print(f"\n   Your Rancher namespace: {namespace}")
    
    def cmd_deposit(self, amount: float):
        """
        Deposit USDC to your reseller account.
        
        Usage:
            kubetee reseller deposit 100
        """
        if not self._ensure_contract() or not self._ensure_wallet():
            return
        
        amount_usdc = self._to_usdc(amount)
        
        # Check USDC balance
        usdc_balance = self.usdc.functions.balanceOf(
            self.config.wallet_address
        ).call()
        
        if usdc_balance < amount_usdc:
            self._error(f"Insufficient USDC. Have: ${self._from_usdc(usdc_balance):.2f}, Need: ${amount:.2f}")
            return
        
        # Check allowance
        allowance = self.usdc.functions.allowance(
            self.config.wallet_address,
            self.config.reseller_contract
        ).call()
        
        # Approve if needed
        if allowance < amount_usdc:
            self._print("🔐 Approving USDC transfer...")
            self._send_tx(
                self.usdc.functions.approve(self.config.reseller_contract, amount_usdc),
                "Approving USDC"
            )
        
        # Deposit
        result = self._send_tx(
            self.contract.functions.deposit(amount_usdc),
            f"Depositing ${amount:.2f} USDC"
        )
        
        if result:
            self.cmd_balance()
    
    def cmd_withdraw(self, amount: float):
        """
        Withdraw USDC from your reseller account.
        
        Usage:
            kubetee reseller withdraw 50
        """
        if not self._ensure_contract() or not self._ensure_wallet():
            return
        
        amount_usdc = self._to_usdc(amount)
        
        result = self._send_tx(
            self.contract.functions.withdraw(amount_usdc),
            f"Withdrawing ${amount:.2f} USDC"
        )
        
        if result:
            self.cmd_balance()
    
    def cmd_balance(self):
        """
        Show your reseller balance.
        
        Usage:
            kubetee reseller balance
        """
        if not self._ensure_contract() or not self._ensure_wallet():
            return
        
        try:
            info = self.contract.functions.getResellerInfo(
                self.config.wallet_address
            ).call()
            
            namespace, name, active, balance, usage, available, total_spent = info
            
            if not active:
                self._error("Reseller account not active")
                return
            
            if HAS_RICH and self.console:
                table = Table(title="💰 Reseller Balance")
                table.add_column("Field", style="cyan")
                table.add_column("Value", style="green")
                
                table.add_row("Name", name)
                table.add_row("Namespace", namespace)
                table.add_row("Balance", f"${self._from_usdc(balance):.2f}")
                table.add_row("Current Usage", f"${self._from_usdc(usage):.2f}")
                table.add_row("Available", f"${self._from_usdc(available):.2f}")
                table.add_row("Total Spent", f"${self._from_usdc(total_spent):.2f}")
                
                self.console.print(table)
            else:
                print(f"\n💰 Reseller Balance")
                print(f"   Name: {name}")
                print(f"   Namespace: {namespace}")
                print(f"   Balance: ${self._from_usdc(balance):.2f}")
                print(f"   Current Usage: ${self._from_usdc(usage):.2f}")
                print(f"   Available: ${self._from_usdc(available):.2f}")
                print(f"   Total Spent: ${self._from_usdc(total_spent):.2f}")
                
        except Exception as e:
            self._error(f"Could not fetch balance: {e}")
    
    def cmd_status(self):
        """
        Show reseller status and current epoch.
        
        Usage:
            kubetee reseller status
        """
        self.cmd_balance()
        
        # Additional status info could be added here
        # - API connectivity check
        # - Rancher namespace status
        # - Current epoch info


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="kubetee reseller",
        description="KubeTEE Reseller Management (USDC on BASE)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Register
    reg_parser = subparsers.add_parser("register", help="Register as a reseller")
    reg_parser.add_argument("--namespace", "-n", required=True, help="Rancher namespace")
    reg_parser.add_argument("--name", required=True, help="Business name")
    
    # Deposit
    dep_parser = subparsers.add_parser("deposit", help="Deposit USDC")
    dep_parser.add_argument("amount", type=float, help="Amount in USD")
    
    # Withdraw
    with_parser = subparsers.add_parser("withdraw", help="Withdraw USDC")
    with_parser.add_argument("amount", type=float, help="Amount in USD")
    
    # Balance
    subparsers.add_parser("balance", help="Show balance")
    
    # Status
    subparsers.add_parser("status", help="Show status")
    
    args = parser.parse_args()
    
    cli = ResellerCLI()
    
    if args.command == "register":
        cli.cmd_register(args.namespace, args.name)
    elif args.command == "deposit":
        cli.cmd_deposit(args.amount)
    elif args.command == "withdraw":
        cli.cmd_withdraw(args.amount)
    elif args.command == "balance":
        cli.cmd_balance()
    elif args.command == "status":
        cli.cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

