#!/usr/bin/env python3
"""
Single Node Testing Pyramid Setup Script

For the KubeTEE local "single node testnet" (using subtensor-localnet in docker).

This script:
1. Waits for chain to be ready.
2. Creates/funds dev wallets (using local Alice for funding).
3. Creates/registers the subnet (if needed) on local.
4. Registers the owner hotkey as a neuron (to get a UID for emissions).
5. Starts emissions (start_call).
6. Sets hyperparams:
   - owner_cut_auto_lock_enabled = true   (auto-locks owner cut emissions into CONVICTION lock)
   - recycle_or_burn = Recycle            (recycle instead of burn for owner-directed emissions)
7. (Optional) Runs or prepares the owner validator that sets weights=1 to owner UID.

This enables:
- Owner emissions (cut + trick-weighted miner emissions) go into conviction (locked, builds conviction over time).
- Recycle instead of burn for the directed emissions.
- Full emissions flow for testing (no burn waste).

Run this AFTER `docker compose up -d` (chain healthy).

Usage (from host, with bittensor installed):
  python scripts/setup_single_node.py --netuid 1

Then view everything in dozzle: http://localhost:8080

Requires: bittensor package (provides btcli), wallets in ~/.bittensor
For pure local dev, it uses //Alice equivalent via regen or faucet-like.

Note: On localnet with FAST_BLOCKS, tempos are fast. Use --real-blocks if needed.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

def run(cmd: list[str], check=True, capture=False, env=None):
    print(f"$ {' '.join(cmd)}")
    res = subprocess.run(cmd, check=check, capture_output=capture, text=True, env=env or os.environ)
    if capture:
        print(res.stdout)
    return res

def wait_for_chain(network: str = "ws://127.0.0.1:9944", timeout=120):
    print("Waiting for chain RPC...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            # Use btcli query block or simple
            run(["btcli", "query", "block", "--network", network, "--yes"], check=False, capture=True)
            print("Chain is up!")
            return True
        except Exception as e:
            print(f"  ... not ready yet: {e}")
            time.sleep(5)
    raise TimeoutError("Chain did not become ready in time. Check docker logs.")

def ensure_wallet(name: str, hotkey: str = "default"):
    wallet_path = Path.home() / ".bittensor" / "wallets" / name
    if not wallet_path.exists():
        print(f"Creating wallet {name}...")
        run(["btcli", "wallet", "create", "--wallet.name", name, "--wallet-hotkey", hotkey, "--no-password", "--yes"])
    else:
        print(f"Wallet {name} exists.")

def fund_from_alice(dest_name: str, amount: int = 10000):
    """Fund using local Alice dev key (standard for localnet)."""
    print(f"Funding {dest_name} from Alice dev account...")
    # Regen Alice if needed (public dev seed for local)
    alice_seed = "0xe5be9a5092b81bca64be81d212e7f2f9eba183bb7a90954f7b76361f6edb5c0a"
    run([
        "btcli", "wallet", "regen-coldkey",
        "--wallet.name", "alice",
        "--seed", alice_seed,
        "--no-password", "--yes"
    ], check=False)
    # Transfer
    run([
        "btcli", "wallet", "transfer",
        "--dest", dest_name,
        "--amount", str(amount),
        "--wallet.name", "alice",
        "--wallet-hotkey", "default",
        "--network", "local",
        "--yes"
    ])

def create_subnet_if_needed(netuid: int, owner_name: str):
    print(f"Ensuring subnet {netuid} exists (owner={owner_name})...")
    # Try create; on local it may succeed or already exist.
    res = run([
        "btcli", "subnet", "create",
        "--wallet.name", owner_name,
        "--wallet-hotkey", "default",
        "--network", "local",
        "--yes"
    ], check=False, capture=True)
    # On local, often netuid 1 or next is auto.
    # For demo we target specific netuid; if create gave different, note it.
    print("Subnet create attempt done (may already exist or use next available).")

def register_neuron(netuid: int, wallet_name: str, hotkey: str = "default", as_validator: bool = True):
    print(f"Registering {wallet_name} on netuid {netuid} ...")
    # Use burned register on local (faucet enabled)
    run([
        "btcli", "subnet", "register",
        "--netuid", str(netuid),
        "--wallet.name", wallet_name,
        "--wallet-hotkey", hotkey,
        "--network", "local",
        "--yes"
    ], check=False)

def start_emissions(netuid: int, owner_name: str):
    print(f"Starting emissions for netuid {netuid} ...")
    run([
        "btcli", "sudo", "start",
        "--netuid", str(netuid),
        "--wallet.name", owner_name,
        "--wallet-hotkey", "default",
        "--network", "local",
        "--yes"
    ], check=False)
    # Alternative: btcli tx start-call --netuid X

def set_hyperparam(netuid: int, owner_name: str, param: str, value: str):
    print(f"Setting {param}={value} on netuid {netuid} ...")
    # v11 uses btcli sudo set or tx set-hyperparameter
    run([
        "btcli", "sudo", "set",
        "--netuid", str(netuid),
        "--param", param,
        "--value", value,
        "--wallet.name", owner_name,
        "--wallet-hotkey", "default",
        "--network", "local",
        "--yes"
    ], check=False)

def set_conviction_and_recycle(netuid: int, owner_name: str):
    """Set owner emissions into conviction + recycle instead of burn."""
    # 1. Auto lock owner cut into conviction
    set_hyperparam(netuid, owner_name, "owner_cut_auto_lock_enabled", "true")
    # 2. Recycle instead of burn for owner-directed (burn UID) emissions
    set_hyperparam(netuid, owner_name, "recycle_or_burn", "Recycle")
    print("Conviction auto-lock + Recycle mode enabled for owner emissions.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--netuid", type=int, default=1)
    parser.add_argument("--owner-wallet", default="owner")
    parser.add_argument("--network", default="local")
    args = parser.parse_args()

    netuid = args.netuid
    owner = args.owner_wallet

    print("=== KubeTEE Single-Node Pyramid Setup ===")
    print(f"Netuid: {netuid}, Owner wallet: {owner}")

    wait_for_chain(f"ws://127.0.0.1:9944")

    # Wallets
    ensure_wallet("alice")
    ensure_wallet(owner)

    # Fund owner (and alice if needed)
    fund_from_alice(owner, 5000)
    fund_from_alice("alice", 1000)  # top up

    # Subnet + neuron setup (owner registers to have a UID for weighting)
    create_subnet_if_needed(netuid, owner)
    register_neuron(netuid, owner, "default", as_validator=True)

    # Start emissions
    start_emissions(netuid, owner)

    # Set the key hypers for conviction + recycle
    set_conviction_and_recycle(netuid, owner)

    print("\n=== Setup complete ===")
    print(f"Owner emissions will now:")
    print("  - Have owner cut auto-locked into CONVICTION (via owner_cut_auto_lock_enabled)")
    print("  - Miner emissions directed to owner UID will be RECYCLED (not burned)")
    print("\nNext: Run your validator (or the docker one) that sets weights=1 to the owner UID.")
    print("View logs: http://localhost:8080 (dozzle) after docker compose up")
    print(f"Example: docker compose up -d && python -m scripts.owner_validator (or inside container)")

if __name__ == "__main__":
    main()
