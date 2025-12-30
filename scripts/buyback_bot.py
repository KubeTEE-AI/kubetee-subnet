#!/usr/bin/env python3
"""
KubeTEE Buyback & Burn Bot

Off-chain automation for the complete buyback cycle:
1. Monitor wTAO bridge arrivals on Bittensor
2. Swap TAO → Alpha via subnet AMM
3. Burn Alpha by sending to null address

Run with: python buyback_bot.py --daemon

═══════════════════════════════════════════════════════════════════════════════
                              ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│                           COMPLETE FLOW                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [BASE L2]                                                                 │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ KubeTEEBuybackBurn.sol                                               │  │
│   │ └── Chainlink Automation triggers daily                             │  │
│   │ └── Swaps USDC → wTAO via Uniswap                                   │  │
│   │ └── Initiates bridge to Bittensor                                   │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    │ Bridge (wTAO → TAO)                   │
│                                    ▼                                        │
│   [BITTENSOR]                                                               │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ This Bot (buyback_bot.py)                                            │  │
│   │                                                                      │  │
│   │ 1. Monitor TAO arrivals from bridge                                  │  │
│   │ 2. Swap TAO → Alpha via subnet AMM                                  │  │
│   │    subtensor.stake_into_alpha(netuid, amount)                       │  │
│   │ 3. Burn Alpha by sending to null address                            │  │
│   │    subtensor.transfer_alpha(netuid, BURN_ADDRESS, amount)           │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   BURN ADDRESS: 5C4hrfjw9DjXZTzV3MwzrrAr9P1MJhSrvWGWqi1eSuyUpnhM           │
│   (Polkadot/Substrate null address - tokens sent here are unrecoverable)   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
"""

import argparse
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Bittensor SDK
try:
    import bittensor as bt
    HAS_BITTENSOR = True
except ImportError:
    HAS_BITTENSOR = False
    bt = None

# Notifications (optional)
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# =============================================================================
# CONFIGURATION
# =============================================================================

# Bittensor burn address (Substrate null address)
BURN_ADDRESS = "5C4hrfjw9DjXZTzV3MwzrrAr9P1MJhSrvWGWqi1eSuyUpnhM"


@dataclass
class BotConfig:
    """Bot configuration."""
    
    # Bittensor network
    network: str = "finney"  # or "test" for testnet
    netuid: int = 0  # KubeTEE subnet ID
    
    # Wallet
    wallet_name: str = "buyback"
    wallet_hotkey: str = "default"
    
    # Thresholds
    min_tao_threshold: float = 0.1  # Minimum TAO to trigger swap
    min_alpha_threshold: float = 0.1  # Minimum Alpha to trigger burn
    
    # Timing
    check_interval: int = 300  # Check every 5 minutes
    
    # Notifications
    webhook_url: str = ""  # Discord/Slack webhook for notifications
    
    # Logging
    log_file: str = "buyback_bot.log"
    
    @classmethod
    def from_env(cls) -> "BotConfig":
        """Load config from environment variables."""
        return cls(
            network=os.getenv("BT_NETWORK", "finney"),
            netuid=int(os.getenv("KUBETEE_NETUID", "0")),
            wallet_name=os.getenv("BT_WALLET_NAME", "buyback"),
            wallet_hotkey=os.getenv("BT_WALLET_HOTKEY", "default"),
            min_tao_threshold=float(os.getenv("MIN_TAO_THRESHOLD", "0.1")),
            min_alpha_threshold=float(os.getenv("MIN_ALPHA_THRESHOLD", "0.1")),
            check_interval=int(os.getenv("CHECK_INTERVAL", "300")),
            webhook_url=os.getenv("NOTIFICATION_WEBHOOK", ""),
            log_file=os.getenv("LOG_FILE", "buyback_bot.log"),
        )


# =============================================================================
# LOGGING
# =============================================================================

def setup_logging(config: BotConfig) -> logging.Logger:
    """Set up logging."""
    logger = logging.getLogger("buyback_bot")
    logger.setLevel(logging.INFO)
    
    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s'
    ))
    logger.addHandler(console)
    
    # File handler
    file_handler = logging.FileHandler(config.log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s'
    ))
    logger.addHandler(file_handler)
    
    return logger


# =============================================================================
# NOTIFICATIONS
# =============================================================================

def send_notification(config: BotConfig, message: str, logger: logging.Logger):
    """Send notification via webhook."""
    if not config.webhook_url or not HAS_REQUESTS:
        return
    
    try:
        payload = {
            "content": f"🔥 **KubeTEE Buyback Bot**\n{message}",
            "username": "KubeTEE Bot"
        }
        requests.post(config.webhook_url, json=payload, timeout=10)
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")


# =============================================================================
# BUYBACK BOT
# =============================================================================

class BuybackBot:
    """
    KubeTEE Buyback & Burn Bot.
    
    Monitors TAO balance and executes:
    1. TAO → Alpha swap via subnet AMM
    2. Alpha → Burn (send to null address)
    """
    
    def __init__(self, config: BotConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        
        if not HAS_BITTENSOR:
            raise ImportError("bittensor package required: pip install bittensor")
        
        # Initialize Bittensor connection
        self.logger.info(f"Connecting to Bittensor {config.network}...")
        self.subtensor = bt.subtensor(network=config.network)
        
        # Load wallet
        self.logger.info(f"Loading wallet: {config.wallet_name}/{config.wallet_hotkey}")
        self.wallet = bt.wallet(name=config.wallet_name, hotkey=config.wallet_hotkey)
        
        # Verify wallet exists
        if not self.wallet.coldkeypub:
            raise ValueError(f"Wallet {config.wallet_name} not found")
        
        self.address = self.wallet.coldkeypub.ss58_address
        self.logger.info(f"Bot address: {self.address}")
        
        # Statistics
        self.stats = {
            "total_tao_swapped": 0.0,
            "total_alpha_burned": 0.0,
            "swap_count": 0,
            "burn_count": 0,
            "last_swap": None,
            "last_burn": None,
        }
    
    def get_tao_balance(self) -> float:
        """Get current TAO balance."""
        try:
            balance = self.subtensor.get_balance(self.address)
            return float(balance.tao)
        except Exception as e:
            self.logger.error(f"Failed to get TAO balance: {e}")
            return 0.0
    
    def get_alpha_balance(self) -> float:
        """Get current Alpha balance for subnet."""
        try:
            # Alpha balance is staked amount in the subnet
            stake = self.subtensor.get_stake_for_coldkey_and_hotkey(
                coldkey_ss58=self.wallet.coldkeypub.ss58_address,
                hotkey_ss58=self.wallet.hotkey.ss58_address,
                netuid=self.config.netuid,
            )
            return float(stake.tao) if stake else 0.0
        except Exception as e:
            self.logger.error(f"Failed to get Alpha balance: {e}")
            return 0.0
    
    def swap_tao_to_alpha(self, amount: float) -> bool:
        """
        Swap TAO to Alpha via subnet AMM.
        
        Uses Bittensor's native stake_into_alpha functionality.
        This stakes TAO into the subnet, receiving Alpha tokens.
        """
        self.logger.info(f"🔄 Swapping {amount:.4f} TAO → Alpha...")
        
        try:
            # Convert to Balance
            tao_amount = bt.Balance.from_tao(amount)
            
            # Stake TAO into subnet to get Alpha
            # This uses the native Bittensor AMM
            success = self.subtensor.add_stake(
                wallet=self.wallet,
                hotkey_ss58=self.wallet.hotkey.ss58_address,
                netuid=self.config.netuid,
                amount=tao_amount,
            )
            
            if success:
                self.stats["total_tao_swapped"] += amount
                self.stats["swap_count"] += 1
                self.stats["last_swap"] = datetime.utcnow().isoformat()
                
                self.logger.info(f"✅ Swapped {amount:.4f} TAO → Alpha")
                send_notification(
                    self.config,
                    f"✅ Swapped **{amount:.4f} TAO** → Alpha",
                    self.logger
                )
                return True
            else:
                self.logger.error("❌ Swap failed")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Swap error: {e}")
            return False
    
    def burn_alpha(self, amount: float) -> bool:
        """
        Burn Alpha by sending to null address.
        
        The Substrate null address (5C4hr...) is unrecoverable.
        Tokens sent there are effectively burned.
        """
        self.logger.info(f"🔥 Burning {amount:.4f} Alpha...")
        
        try:
            # First unstake Alpha to get it back as transferable
            alpha_amount = bt.Balance.from_tao(amount)
            
            # Unstake from subnet
            success = self.subtensor.unstake(
                wallet=self.wallet,
                hotkey_ss58=self.wallet.hotkey.ss58_address,
                netuid=self.config.netuid,
                amount=alpha_amount,
            )
            
            if not success:
                self.logger.error("❌ Unstake failed")
                return False
            
            # Now transfer to burn address
            success = self.subtensor.transfer(
                wallet=self.wallet,
                dest=BURN_ADDRESS,
                amount=alpha_amount,
            )
            
            if success:
                self.stats["total_alpha_burned"] += amount
                self.stats["burn_count"] += 1
                self.stats["last_burn"] = datetime.utcnow().isoformat()
                
                self.logger.info(f"🔥 Burned {amount:.4f} Alpha!")
                send_notification(
                    self.config,
                    f"🔥 **BURNED** {amount:.4f} Alpha!\n"
                    f"Total burned: {self.stats['total_alpha_burned']:.4f}",
                    self.logger
                )
                return True
            else:
                self.logger.error("❌ Burn transfer failed")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Burn error: {e}")
            return False
    
    def run_cycle(self):
        """Run one buyback cycle."""
        self.logger.info("=" * 60)
        self.logger.info("Starting buyback cycle...")
        
        # Check TAO balance
        tao_balance = self.get_tao_balance()
        self.logger.info(f"TAO Balance: {tao_balance:.4f}")
        
        # Swap TAO → Alpha if threshold met
        if tao_balance >= self.config.min_tao_threshold:
            # Reserve some TAO for fees
            swap_amount = tao_balance - 0.01
            if swap_amount > 0:
                self.swap_tao_to_alpha(swap_amount)
        
        # Check Alpha balance
        alpha_balance = self.get_alpha_balance()
        self.logger.info(f"Alpha Balance: {alpha_balance:.4f}")
        
        # Burn Alpha if threshold met
        if alpha_balance >= self.config.min_alpha_threshold:
            self.burn_alpha(alpha_balance)
        
        # Log stats
        self.logger.info(f"Stats: TAO swapped={self.stats['total_tao_swapped']:.4f}, "
                        f"Alpha burned={self.stats['total_alpha_burned']:.4f}")
        self.logger.info("=" * 60)
    
    async def run_daemon(self):
        """Run bot as daemon, executing cycles at interval."""
        self.logger.info("🚀 Starting KubeTEE Buyback Bot in daemon mode...")
        self.logger.info(f"Check interval: {self.config.check_interval}s")
        self.logger.info(f"Min TAO threshold: {self.config.min_tao_threshold}")
        self.logger.info(f"Min Alpha threshold: {self.config.min_alpha_threshold}")
        self.logger.info(f"Subnet: {self.config.netuid}")
        
        send_notification(
            self.config,
            f"🚀 Bot started!\n"
            f"Network: {self.config.network}\n"
            f"Subnet: {self.config.netuid}\n"
            f"Address: `{self.address}`",
            self.logger
        )
        
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                self.logger.error(f"Cycle error: {e}")
                send_notification(
                    self.config,
                    f"⚠️ Error in cycle: {e}",
                    self.logger
                )
            
            await asyncio.sleep(self.config.check_interval)
    
    def save_stats(self):
        """Save statistics to file."""
        stats_file = Path("buyback_stats.json")
        with open(stats_file, "w") as f:
            json.dump(self.stats, f, indent=2)
    
    def load_stats(self):
        """Load statistics from file."""
        stats_file = Path("buyback_stats.json")
        if stats_file.exists():
            with open(stats_file) as f:
                self.stats = json.load(f)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="KubeTEE Buyback & Burn Bot"
    )
    
    parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Run as daemon (continuous)"
    )
    
    parser.add_argument(
        "--once", "-o",
        action="store_true",
        help="Run single cycle and exit"
    )
    
    parser.add_argument(
        "--network",
        default="finney",
        help="Bittensor network (finney or test)"
    )
    
    parser.add_argument(
        "--netuid",
        type=int,
        default=0,
        help="KubeTEE subnet ID"
    )
    
    parser.add_argument(
        "--wallet",
        default="buyback",
        help="Wallet name"
    )
    
    parser.add_argument(
        "--hotkey",
        default="default",
        help="Hotkey name"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Check interval in seconds (daemon mode)"
    )
    
    args = parser.parse_args()
    
    # Build config
    config = BotConfig(
        network=args.network,
        netuid=args.netuid,
        wallet_name=args.wallet,
        wallet_hotkey=args.hotkey,
        check_interval=args.interval,
    )
    
    # Override with env vars if set
    if os.getenv("BT_NETWORK"):
        config.network = os.getenv("BT_NETWORK")
    if os.getenv("NOTIFICATION_WEBHOOK"):
        config.webhook_url = os.getenv("NOTIFICATION_WEBHOOK")
    
    # Setup
    logger = setup_logging(config)
    
    try:
        bot = BuybackBot(config, logger)
        
        if args.once:
            bot.run_cycle()
            bot.save_stats()
        elif args.daemon:
            asyncio.run(bot.run_daemon())
        else:
            print("Usage: buyback_bot.py [--daemon | --once]")
            print("  --daemon: Run continuously")
            print("  --once:   Run single cycle")
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()

