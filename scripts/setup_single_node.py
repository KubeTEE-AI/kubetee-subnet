#!/usr/bin/env python3
"""
Single Node Testing Pyramid Setup Script

For the KubeTEE local "single node testnet" (using subtensor-localnet in docker).

This script:
1. Waits for chain to be ready.
2. Creates/funds dev wallets using *pinned dev seeds* (Alice + owner, fdn-subnet style)
   for stable SS58 addresses and predictable UIDs on the localnet.
3. Creates/registers the subnet (if needed) on local.
4. Registers the owner hotkey as a neuron (to get a UID for emissions).
5. Starts emissions (sudo start).
6. Sets hyperparams:
   - owner_cut_auto_lock_enabled = true   (auto-locks owner cut emissions into CONVICTION lock)
   - recycle_or_burn = Recycle            (recycle instead of burn for owner-directed emissions)

This enables:
- Owner emissions (cut + trick-weighted miner emissions) go into conviction (locked, builds conviction over time).
- Recycle instead of burn for the directed emissions.
- Full emissions flow for testing (no burn waste).

Primary usage (self-contained in container):
  The validator container entrypoint runs this first (with ws://chain:9944),
  then starts the owner validator.

Manual usage (from host, with bittensor installed):
  python scripts/setup_single_node.py --netuid 1 --chain-endpoint ws://127.0.0.1:9944

Then view everything in dozzle: http://localhost:8080

Requires: bittensor + bittensor-cli (btcli) in PATH. Inside the validator image this is guaranteed.
For pure local dev it uses *pinned dev seeds* (Alice + owner) exactly like fdn-subnet pins Alith etc.
  for reproducible registration, hypers, and UID targeting in the single-node test pyramid.

Note: On localnet with FAST_BLOCKS, tempos are fast.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# bittensor may be present inside the validator container image (and often on host too)
try:
    import bittensor as bt
except ImportError:
    bt = None

import chain_state


# =====================================================================================
# PINNED DEV KEYS (inspired by fdn-subnet's approach with Alith/Baltathar etc.)
#
# fdn-subnet uses well-known PUBLIC dev-genesis private keys (Alith etc.) + explicit
# .key files mounted under .swarm/keys for reproducible local --dev bringup and
# one-command registration.
#
# For kubetee bittensor localnet we do the equivalent:
# - Alice seed is the classic substrate dev seed (pre-funded by localnet --dev images).
# - Owner (the subnet creator / the key whose hotkey we register + weight to) uses a
#   pinned dev seed below so the coldkey/hotkey SS58 is *stable* across runs.
#   This makes TARGET_UID predictable (usually 0 for the first/owner registration)
#   and the whole "setup then validator" flow deterministic.
#
# !!! ONLY FOR LOCALNET / SINGLE-NODE TEST PYRAMID !!!
# These seeds control nothing on real chains. Never use against testnet or mainnet.
# =====================================================================================

DEV_ALICE_SEED = "0xe5be9a5092b81bca64be81d212e7f2f9eba183bb7a90954f7b76361f6edb5c0a"

# Pinned dev seed for the subnet *owner* wallet (the one that creates the subnet,
# registers its hotkey, sets hypers via sudo, and the validator weights to).
# Derived SS58 (cold+hot for dev simplicity): 5FLbZav21bAsjH5SAdmJZwTP5C4b3bcaaWqC6GSmGmsbzUJ9
DEV_OWNER_SEED = "0x398f0c28f98885e046333d4a41c19cee4c37368a9832c749be0086a2a9b4e8c0"
DEV_OWNER_COLD_SS58 = "5FLbZav21bAsjH5SAdmJZwTP5C4b3bcaaWqC6GSmGmsbzUJ9"

# Additional pinned dev seed for a sample "miner" (so we have something that looks like
# a miner whose incentive can be directed/recycled to the owner UID via weights).
DEV_MINER_SEED = "0x8075991ce870b93a8870eca0c0f91913d12f47948ca0fd25b49c6fa7cdbeee8b"

def run(cmd: list[str], check=True, capture=False, env=None):
    print(f"$ {' '.join(cmd)}")
    res = subprocess.run(cmd, check=check, capture_output=capture, text=True, env=env or os.environ)
    if capture:
        print(res.stdout)
    return res

def wait_for_chain(chain_endpoint: str = "ws://127.0.0.1:9944", timeout=120):
    print(f"Waiting for chain RPC at {chain_endpoint} ...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            # btcli accepts --network as ws://... or "local"
            run(["btcli", "query", "block", "--network", chain_endpoint, "--yes"], check=False, capture=True)
            print("Chain is up!")
            return True
        except Exception as e:
            print(f"  ... not ready yet: {e}")
            time.sleep(5)
    raise TimeoutError("Chain did not become ready in time. Check docker logs.")

def ensure_dev_wallet(name: str, seed: str, hotkey: str = "default"):
    """Ensure a wallet exists using a *pinned dev seed* (regen, not random new_coldkey).

    This follows the fdn-subnet pattern of using well-known dev keys (Alith etc.)
    so that owner addresses / UIDs are stable for the single-node pyramid.
    We regen BOTH coldkey (for sudo/ownership) and hotkey (for registration + signing weights).
    """
    base_wallet_path = str(Path.home() / ".bittensor" / "wallets")
    print(f"Ensuring dev wallet {name} (pinned seed for cold+hot, hotkey={hotkey}) ...")
    # Coldkey (owner/sudo privileges, funding)
    # Pipe 'y' to handle any "overwrite?" prompts that --quiet/--overwrite don't fully suppress in all btcli versions.
    run([
        "sh", "-c",
        f"yes y | btcli wallet regen-coldkey --wallet.name {name} --wallet-hotkey {hotkey} --wallet-path {base_wallet_path} --seed {seed} --no-use-password --overwrite --quiet"
    ], check=False)

    # Hotkey 
    run([
        "sh", "-c",
        f"yes y | btcli wallet regen-hotkey --wallet.name {name} --wallet-hotkey {hotkey} --wallet-path {base_wallet_path} --seed {seed} --no-use-password --overwrite --quiet"
    ], check=False)

    print(f"  dev wallet {name} ready (cold+hot seed-pinned).")

def get_wallet_coldkey_ss58(name: str, hotkey: str = "default") -> str:
    """Return the coldkey ss58 address for a wallet name. Prefers SDK, falls back to btcli inspect parsing."""
    if bt is not None:
        try:
            w = bt.Wallet(name=name, hotkey=hotkey)
            addr = w.coldkeypub.ss58_address
            print(f"  resolved {name} coldkey ss58 via SDK: {addr}")
            return addr
        except Exception as e:
            print(f"  bt.Wallet resolve for {name} failed: {e}, will try btcli")

    # Fallback: use btcli wallet inspect and parse ss58 (best effort)
    base_wallet_path = str(Path.home() / ".bittensor" / "wallets")
    res = run([
        "btcli", "wallet", "inspect",
        "--wallet.name", name,
        "--wallet-hotkey", hotkey,
        "--wallet-path", base_wallet_path,
        "--quiet"
    ], check=False, capture=True)
    out = (res.stdout or "") + (res.stderr or "")
    # crude parse for ss58 in output
    import re
    m = re.search(r"(5[0-9a-zA-Z]{46,48})", out)
    if m:
        addr = m.group(1)
        print(f"  resolved {name} coldkey ss58 via btcli inspect: {addr}")
        return addr
    # last resort
    print(f"  WARNING: could not resolve ss58 for {name}, using placeholder (funding may fail)")
    return "5GT5Ycu59s7xiGj4VkRRZsEkypEFbECeMBCeQ14t8G7H8h8F"


def fund_from_alice(dest_name: str, amount: int = 10000, chain_endpoint: str = "ws://127.0.0.1:9944"):
    """Fund using local Alice dev key (standard for localnet)."""
    print(f"Funding {dest_name} from Alice dev account (endpoint={chain_endpoint})...")
    base_wallet_path = str(Path.home() / ".bittensor" / "wallets")
    run([
        "sh", "-c",
        f"yes y | btcli wallet regen-coldkey --wallet.name alice --wallet-path {base_wallet_path} --seed {DEV_ALICE_SEED} --no-use-password --quiet"
    ], check=False)

    # Resolve the *actual* address for dest_name (critical so we fund the wallet we later use for create/sudo)
    dest_ss58 = get_wallet_coldkey_ss58(dest_name)
    run([
        "btcli", "wallet", "transfer",
        "--dest", dest_ss58,
        "--amount", str(amount),
        "--wallet.name", "alice",
        "--wallet-hotkey", "default",
        "--network", chain_endpoint,
        "--yes",
        "--allow-death"
    ], check=False)

def create_subnet_if_needed(netuid: int, owner_name: str, chain_endpoint: str = "ws://127.0.0.1:9944"):
    print(f"Creating/ensuring subnet (target {netuid}, owner={owner_name}, network={chain_endpoint})...")
    # Always attempt create. This will allocate the *next* free netuid and make our key the owner.
    # (If a specific netuid already exists we won't be its owner, so we force a fresh one.)
    res = run([
        "btcli", "subnet", "create",
        "--wallet.name", owner_name,
        "--wallet-hotkey", "default",
        "--network", chain_endpoint,
        "--yes"
    ], check=False, capture=True)
    out = (res.stdout or "") + (res.stderr or "")
    # Try to parse the netuid we actually got (common patterns in btcli output)
    import re
    m = re.search(r"netuid[:\s]+(\d+)", out, re.IGNORECASE)
    if not m:
        m = re.search(r"Registered on netuid[:\s]+(\d+)", out, re.IGNORECASE)
    if m:
        actual = int(m.group(1))
        print(f"  Create gave us netuid {actual} (we are now the owner).")
        return actual
    print("  Create attempt done. Falling back to requested netuid (may not own it).")
    return netuid

def decide_owner_actions(ownership: dict) -> dict:
    """Pure decision: given a chain_state.query_subnet_ownership() result, decide
    whether it's safe to attempt owner-only sudo operations (start emissions,
    set conviction/recycle hypers).

    This replaces the old behavior of trusting create_subnet_if_needed's
    regex-parsed btcli stdout as proof of ownership: a failed `btcli subnet
    create` (e.g. SubtokenDisabled on this chain) used to fall through to
    "use the requested netuid anyway", and every owner-only call downstream
    then failed forever in a retry loop. Never attempt an operation we
    already know will fail with "wallet doesn't own the specified subnet".
    """
    if ownership.get("error"):
        return {
            "proceed": False,
            "reason": f"ownership query failed ({ownership['error']}); failing closed, not retrying blindly",
        }
    if not ownership.get("exists"):
        return {"proceed": False, "reason": "target netuid does not exist on chain"}
    if not ownership.get("owned_by_us"):
        return {
            "proceed": False,
            "reason": f"netuid is owned by {ownership.get('owner_ss58')!r}, not our wallet",
        }
    return {"proceed": True, "reason": "confirmed on-chain owner match"}


def register_neuron(netuid: int, wallet_name: str, hotkey: str = "default", as_validator: bool = True, chain_endpoint: str = "ws://127.0.0.1:9944"):
    print(f"Registering {wallet_name} on netuid {netuid} (network={chain_endpoint}) ...")
    # Use burned register on local (faucet enabled).
    # --unsafe to bypass safe/ shield mode that can cause "extrinsic" errors on this localnet + btcli combo.
    run([
        "btcli", "subnet", "register",
        "--netuid", str(netuid),
        "--wallet.name", wallet_name,
        "--wallet-hotkey", hotkey,
        "--network", chain_endpoint,
        "--yes",
        "--unsafe"
    ], check=False)

def start_emissions(netuid: int, owner_name: str, chain_endpoint: str = "ws://127.0.0.1:9944"):
    print(f"Starting emissions for netuid {netuid} (network={chain_endpoint}) ...")
    # Correct command for current bittensor-cli in the image: `btcli subnets start`
    # (older code used `btcli sudo start` which no longer exists)
    run([
        "btcli", "subnets", "start",
        "--netuid", str(netuid),
        "--wallet.name", owner_name,
        "--wallet-hotkey", "default",
        "--network", chain_endpoint,
        "--yes"
    ], check=False)


def add_stake(netuid: int, wallet_name: str, amount: int = 100, chain_endpoint: str = "ws://127.0.0.1:9944"):
    """Put some stake on the subnet for the wallet (makes the neuron have skin in the game / visible in metagraph)."""
    print(f"Adding stake {amount} TAO on netuid {netuid} for {wallet_name} ...")
    # --unsafe to avoid shield/safe mode issues seen on this btcli + localnet combination.
    run([
        "btcli", "stake", "add",
        "--netuid", str(netuid),
        "--wallet.name", wallet_name,
        "--wallet-hotkey", "default",
        "--amount", str(amount),
        "--network", chain_endpoint,
        "--yes",
        "--unsafe"
    ], check=False)

def set_hyperparam(netuid: int, owner_name: str, param: str, value: str, chain_endpoint: str = "ws://127.0.0.1:9944"):
    print(f"Setting {param}={value} on netuid {netuid} (network={chain_endpoint}) ...")
    # v11 uses btcli sudo set or tx set-hyperparameter
    run([
        "btcli", "sudo", "set",
        "--netuid", str(netuid),
        "--param", param,
        "--value", value,
        "--wallet.name", owner_name,
        "--wallet-hotkey", "default",
        "--network", chain_endpoint,
        "--yes"
    ], check=False)

def set_conviction_and_recycle(netuid: int, owner_name: str, chain_endpoint: str = "ws://127.0.0.1:9944"):
    """Set owner emissions into conviction + recycle instead of burn."""
    # 1. Auto lock owner cut into conviction
    set_hyperparam(netuid, owner_name, "owner_cut_auto_lock_enabled", "true", chain_endpoint)
    # 2. Recycle instead of burn for owner-directed (burn UID) emissions
    set_hyperparam(netuid, owner_name, "recycle_or_burn", "Recycle", chain_endpoint)
    print("Conviction auto-lock + Recycle mode enabled for owner emissions.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--netuid", type=int, default=1)
    parser.add_argument("--owner-wallet", default="owner")
    parser.add_argument("--chain-endpoint", default=os.getenv("BT_NETWORK", "ws://127.0.0.1:9944"),
                        help="ws://... endpoint or 'local'. Inside docker compose use ws://chain:9944")
    args = parser.parse_args()

    netuid = args.netuid
    owner = args.owner_wallet
    chain_endpoint = args.chain_endpoint

    print("=== KubeTEE Single-Node Pyramid Setup ===")
    print(f"Netuid: {netuid}, Owner wallet: {owner}")
    print(f"Chain endpoint: {chain_endpoint}")

    wait_for_chain(chain_endpoint)

    # Wallets using *pinned dev seeds* (fdn-subnet style) for stable SS58/UIDs.
    # Alice funds; owner is the subnet owner (creates + sudo + the one we weight to).
    ensure_dev_wallet("alice", DEV_ALICE_SEED)
    ensure_dev_wallet(owner, DEV_OWNER_SEED)

    # Fund the actual addresses of the wallets we will use (owner for sudo+weights, miner for demo)
    fund_from_alice(owner, 5000, chain_endpoint)
    fund_from_alice("miner", 2000, chain_endpoint)
    fund_from_alice("alice", 1000, chain_endpoint)  # top up alice faucet

    # Wait for transfers to land (localnet is fast but extrinsic finality + balance query can lag)
    print("Waiting briefly for balances to settle after funding...")
    time.sleep(6)

    # Subnet + neuron setup (owner registers to have a UID for weighting)
    # create_subnet_if_needed now forces a create (to get ownership) and returns the actual netuid.
    netuid = create_subnet_if_needed(netuid, owner, chain_endpoint)

    register_neuron(netuid, owner, "default", as_validator=True, chain_endpoint=chain_endpoint)

    # Put some stake on the subnet (owner has stake; useful for metagraph/emission visibility and "skin in game")
    add_stake(netuid, owner, 200, chain_endpoint)

    # Also register + stake a sample "miner" wallet (pinned seed). The owner validator
    # can then set weights such that "miner" emissions get recycled to the owner UID.
    ensure_dev_wallet("miner", DEV_MINER_SEED)
    register_neuron(netuid, "miner", "default", as_validator=False, chain_endpoint=chain_endpoint)
    add_stake(netuid, "miner", 50, chain_endpoint)

    # Verify real on-chain ownership before attempting owner-only sudo calls.
    # create_subnet_if_needed's regex-parsed btcli stdout is NOT proof of ownership
    # (e.g. it silently falls back to the requested netuid when `btcli subnet create`
    # fails, such as with a SubtokenDisabled chain error) - only a live query is.
    our_owner_ss58 = get_wallet_coldkey_ss58(owner)
    ownership = chain_state.query_subnet_ownership(netuid, our_owner_ss58, chain_endpoint)
    decision = decide_owner_actions(ownership)
    print(f"\nOwnership check: netuid={netuid} our_wallet={our_owner_ss58} -> {ownership}")
    print(f"Decision: proceed={decision['proceed']} ({decision['reason']})")

    if decision["proceed"]:
        # Start emissions
        start_emissions(netuid, owner, chain_endpoint)
        # Set the key hypers for conviction + recycle
        set_conviction_and_recycle(netuid, owner, chain_endpoint)
    else:
        print(f"  SKIPPING start_emissions + conviction/recycle hypers: {decision['reason']}")
        print("  (Retrying these against a netuid we don't own would fail every time and just hammer the chain.)")

    # Record whether we actually own the netuid so other processes (compose's
    # conviction-setter loop, print_subnet_stats.py) can avoid repeating the
    # same doomed owner-only calls instead of retrying blindly forever.
    try:
        with open("/app/.kubetee_owned", "w") as f:
            f.write("true" if decision["proceed"] else "false")
    except Exception as e:
        print(f"  Warning: could not write ownership status file: {e}")

    print("\n=== Setup complete ===")
    if decision["proceed"]:
        print(f"Owner emissions will now:")
        print("  - Have owner cut auto-locked into CONVICTION (via owner_cut_auto_lock_enabled)")
        print("  - Miner emissions directed to owner UID will be RECYCLED (not burned)")
    else:
        print("Owner does NOT control this netuid's sudo-only hyperparameters on this chain:")
        print(f"  {decision['reason']}")
        print("  Conviction/recycle hypers were NOT set. See ownership check above for the real owner.")
    print("\nUsing pinned dev seeds (owner SS58 ~5FLbZa... ) so the registered UID is stable.")
    print("Next: The validator (if run after this) will set weights=1.0 to the owner UID.")
    print("When used inside the validator container, this script runs first then the validator starts automatically.")

    # Write the actual netuid we own so the subsequent validator (and other containers) can use the correct one.
    try:
        with open("/app/.kubetee_netuid", "w") as f:
            f.write(str(netuid))
        print(f"  Wrote actual netuid={netuid} to /app/.kubetee_netuid for the validator phase.")
    except Exception as e:
        print(f"  Warning: could not write netuid file: {e}")

if __name__ == "__main__":
    main()
