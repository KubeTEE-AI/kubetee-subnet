# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
Credit Tracking System for Reseller Wholesale Model

Tracks all credit transactions:
- Deposits from resellers
- Service consumption
- Miner payments
- Treasury accumulation
"""

import time
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from pathlib import Path
from enum import Enum
import bittensor as bt


class TransactionType(str, Enum):
    """Types of credit transactions."""
    DEPOSIT = "deposit"                    # Reseller deposits Alpha
    SERVICE_CHARGE = "service_charge"      # Charge for service usage
    MINER_PAYMENT = "miner_payment"        # Payment to miner
    TREASURY_SHARE = "treasury_share"      # Treasury receives share
    MINER_WITHDRAWAL = "miner_withdrawal"  # Miner withdraws earnings
    REFUND = "refund"                      # Refund to reseller


@dataclass
class CreditTransaction:
    """Record of a credit transaction."""
    
    transaction_id: str
    timestamp: float
    transaction_type: TransactionType
    
    # Parties involved
    from_hotkey: Optional[str] = None  # Source of funds
    to_hotkey: Optional[str] = None    # Destination of funds
    
    # Amounts
    amount: float = 0.0
    
    # Context
    service_request_id: Optional[str] = None
    description: str = ""
    
    # For linking related transactions
    related_transaction_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['transaction_type'] = self.transaction_type.value
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "CreditTransaction":
        data['transaction_type'] = TransactionType(data['transaction_type'])
        return cls(**data)


class CreditTracker:
    """
    Tracks all credit transactions in the wholesale system.
    
    Provides:
    - Transaction logging
    - Balance verification
    - Audit trail
    - Analytics
    """
    
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # All transactions
        self.transactions: List[CreditTransaction] = []
        
        # Running balances
        self.reseller_balances: Dict[str, float] = {}
        self.miner_earnings: Dict[str, float] = {}
        self.treasury_balance: float = 0.0
        
        # Load existing data
        self._load_transactions()
        
        bt.logging.info(f"CreditTracker initialized with {len(self.transactions)} transactions")
    
    def record_deposit(
        self,
        reseller_hotkey: str,
        amount: float,
        description: str = "Alpha deposit",
    ) -> CreditTransaction:
        """Record a reseller deposit."""
        tx = CreditTransaction(
            transaction_id=self._generate_tx_id(),
            timestamp=time.time(),
            transaction_type=TransactionType.DEPOSIT,
            to_hotkey=reseller_hotkey,
            amount=amount,
            description=description,
        )
        
        self._add_transaction(tx)
        self.reseller_balances[reseller_hotkey] = self.reseller_balances.get(reseller_hotkey, 0) + amount
        
        return tx
    
    def record_service_charge(
        self,
        reseller_hotkey: str,
        miner_hotkey: str,
        total_amount: float,
        miner_share: float,
        treasury_share: float,
        service_request_id: str,
    ) -> List[CreditTransaction]:
        """
        Record a service charge with miner and treasury splits.
        
        Creates 3 linked transactions:
        1. Service charge to reseller
        2. Payment to miner (50% of wholesale)
        3. Share to treasury (50% of wholesale)
        """
        base_tx_id = self._generate_tx_id()
        transactions = []
        
        # 1. Charge reseller
        charge_tx = CreditTransaction(
            transaction_id=f"{base_tx_id}-charge",
            timestamp=time.time(),
            transaction_type=TransactionType.SERVICE_CHARGE,
            from_hotkey=reseller_hotkey,
            amount=total_amount,
            service_request_id=service_request_id,
            description=f"Service charge for request {service_request_id[:8]}",
        )
        self._add_transaction(charge_tx)
        self.reseller_balances[reseller_hotkey] = self.reseller_balances.get(reseller_hotkey, 0) - total_amount
        transactions.append(charge_tx)
        
        # 2. Pay miner
        miner_tx = CreditTransaction(
            transaction_id=f"{base_tx_id}-miner",
            timestamp=time.time(),
            transaction_type=TransactionType.MINER_PAYMENT,
            to_hotkey=miner_hotkey,
            amount=miner_share,
            service_request_id=service_request_id,
            related_transaction_id=charge_tx.transaction_id,
            description=f"Miner payment (50% of wholesale)",
        )
        self._add_transaction(miner_tx)
        self.miner_earnings[miner_hotkey] = self.miner_earnings.get(miner_hotkey, 0) + miner_share
        transactions.append(miner_tx)
        
        # 3. Treasury share
        treasury_tx = CreditTransaction(
            transaction_id=f"{base_tx_id}-treasury",
            timestamp=time.time(),
            transaction_type=TransactionType.TREASURY_SHARE,
            amount=treasury_share,
            service_request_id=service_request_id,
            related_transaction_id=charge_tx.transaction_id,
            description=f"Treasury share (50% of wholesale)",
        )
        self._add_transaction(treasury_tx)
        self.treasury_balance += treasury_share
        transactions.append(treasury_tx)
        
        return transactions
    
    def record_miner_withdrawal(
        self,
        miner_hotkey: str,
        amount: float,
    ) -> CreditTransaction:
        """Record a miner withdrawal."""
        tx = CreditTransaction(
            transaction_id=self._generate_tx_id(),
            timestamp=time.time(),
            transaction_type=TransactionType.MINER_WITHDRAWAL,
            from_hotkey=miner_hotkey,
            amount=amount,
            description=f"Miner withdrawal: {amount:.6f} Alpha",
        )
        
        self._add_transaction(tx)
        self.miner_earnings[miner_hotkey] = self.miner_earnings.get(miner_hotkey, 0) - amount
        
        return tx
    
    def get_reseller_balance(self, hotkey: str) -> float:
        """Get current reseller balance."""
        return self.reseller_balances.get(hotkey, 0.0)
    
    def get_miner_earnings(self, hotkey: str) -> float:
        """Get current miner earnings (pending withdrawal)."""
        return self.miner_earnings.get(hotkey, 0.0)
    
    def get_transactions_for_reseller(self, hotkey: str) -> List[CreditTransaction]:
        """Get all transactions for a reseller."""
        return [
            tx for tx in self.transactions
            if tx.from_hotkey == hotkey or tx.to_hotkey == hotkey
        ]
    
    def get_transactions_for_miner(self, hotkey: str) -> List[CreditTransaction]:
        """Get all transactions for a miner."""
        return [
            tx for tx in self.transactions
            if tx.to_hotkey == hotkey and tx.transaction_type in [
                TransactionType.MINER_PAYMENT,
                TransactionType.MINER_WITHDRAWAL,
            ]
        ]
    
    def get_statistics(self) -> Dict:
        """Get credit system statistics."""
        total_deposits = sum(
            tx.amount for tx in self.transactions
            if tx.transaction_type == TransactionType.DEPOSIT
        )
        total_charges = sum(
            tx.amount for tx in self.transactions
            if tx.transaction_type == TransactionType.SERVICE_CHARGE
        )
        total_miner_payments = sum(
            tx.amount for tx in self.transactions
            if tx.transaction_type == TransactionType.MINER_PAYMENT
        )
        total_treasury = sum(
            tx.amount for tx in self.transactions
            if tx.transaction_type == TransactionType.TREASURY_SHARE
        )
        
        return {
            "total_transactions": len(self.transactions),
            "total_deposits": total_deposits,
            "total_service_charges": total_charges,
            "total_miner_payments": total_miner_payments,
            "total_treasury_accumulated": total_treasury,
            "current_treasury_balance": self.treasury_balance,
            "active_resellers": len(self.reseller_balances),
            "active_miners": len(self.miner_earnings),
        }
    
    def _generate_tx_id(self) -> str:
        """Generate a unique transaction ID."""
        import hashlib
        data = f"{time.time()}-{len(self.transactions)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _add_transaction(self, tx: CreditTransaction):
        """Add a transaction to the log."""
        self.transactions.append(tx)
        self._save_transactions()
    
    def _save_transactions(self):
        """Save transactions to disk."""
        filepath = self.storage_path / "credit_transactions.json"
        
        data = {
            "transactions": [tx.to_dict() for tx in self.transactions[-10000:]],  # Keep last 10k
            "reseller_balances": self.reseller_balances,
            "miner_earnings": self.miner_earnings,
            "treasury_balance": self.treasury_balance,
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_transactions(self):
        """Load transactions from disk."""
        filepath = self.storage_path / "credit_transactions.json"
        if not filepath.exists():
            return
        
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            
            self.transactions = [
                CreditTransaction.from_dict(tx)
                for tx in data.get("transactions", [])
            ]
            self.reseller_balances = data.get("reseller_balances", {})
            self.miner_earnings = data.get("miner_earnings", {})
            self.treasury_balance = data.get("treasury_balance", 0.0)
            
        except Exception as e:
            bt.logging.warning(f"Could not load credit transactions: {e}")

