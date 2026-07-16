#!/usr/bin/env python3
"""
KubeTEE Owner Validator (v11 Bittensor)

Minimal validator for the "subnet owner recycle" use case:
- Sets weight 1.0 (full) to the configured owner UID.
- This directs the miner-incentive portion of emissions to the owner hotkey.
- Combined with subnet hyperparameter RecycleOrBurn=Recycle, the emissions
  are recycled (re-emittable) instead of burned (destroyed).

DYOR summary (from official docs):
- By default, emissions directed to subnet-owner hotkeys are BURNED (destroyed,
  stay in issuance but not re-emitted).
- Owner can set `recycle_or_burn=Recycle` (via sudo_set_recycle_or_burn).
  Then those emissions are RECYCLED (become unissued, available for future emission).
- Difference: Burn permanently reduces effective supply for that emission.
  Recycle allows re-emission (affects halvings timing less aggressively).
- In both cases, the amount counts toward the subnet's "miner burn" penalty (b_i)
  in root emission share calculation: share reduced when high % of miner incentive
  goes to owner UIDs.
- See:
  - https://www.bittensor.com/docs/concepts/emissions (b_i penalty, recycled vs burned)
  - https://docs.taostats.io/docs/burning
  - Subnet hyperparameters: recycle_or_burn

This is the "main validator code (our subnetowners)" to recycle instead of burn.

Usage (localnet example):
  BT_NETWORK=ws://127.0.0.1:9944 \
  KUBETEE_SUBNET_NETUID=1 \
  TARGET_UID=1 \
  python scripts/owner_validator.py

For full subnet: register owner hotkey as neuron, discover UID via metagraph,
set weights to it every epoch, and ensure RecycleOrBurn=Recycle on the subnet.
"""
from __future__ import annotations

import os
import time

import bittensor as bt

# Use Wallet from the installed bittensor version (v10 style has bt.Wallet)
Wallet = bt.Wallet

# Simple config via env for now (will be proper config in full pyramid)
NETWORK = os.getenv("BT_NETWORK", "local")
WALLET_NAME = os.getenv("BT_WALLET", "owner")
HOTKEY_NAME = os.getenv("BT_WALLET_HOTKEY", "default")
NETUID = int(os.getenv("KUBETEE_SUBNET_NETUID", "1"))
TARGET_UID = int(os.getenv("TARGET_UID", "0"))  # UID of the owner-registered key

# If the setup phase wrote the actual netuid we own (because create allocated e.g. 2 instead of 1),
# prefer it so the weights target the right subnet.
try:
    with open("/app/.kubetee_netuid") as f:
        n = f.read().strip()
        if n:
            NETUID = int(n)
            print(f"[owner_validator] using netuid={NETUID} from setup file")
except Exception:
    pass

# For testing pyramid: allow injection of subtensor/wallet for mocks
def set_owner_weights(
    subtensor: "bt.Subtensor" | None = None,
    wallet: Wallet | None = None,
    netuid: int = NETUID,
    target_uid: int = TARGET_UID,
) -> dict:
    """Core logic: set weight 1.0 to target UID (owner key) using v10 Subtensor API.

    Returns result dict for testing/assertion.
    """
    if wallet is None:
        wallet = Wallet(name=WALLET_NAME, hotkey=HOTKEY_NAME)

    if subtensor is None:
        subtensor = bt.Subtensor(network=NETWORK)

    # v10 style set_weights (synchronous in this package)
    try:
        success, message = subtensor.set_weights(
            wallet=wallet,
            netuid=netuid,
            uids=[target_uid],
            weights=[1.0],
        )
        return {
            "success": success,
            "netuid": netuid,
            "target_uid": target_uid,
            "message": message,
        }
    except Exception as e:
        return {
            "success": False,
            "netuid": netuid,
            "target_uid": target_uid,
            "error": str(e),
        }

def run_validator_loop(subtensor, wallet, netuid, target_uid, sleep=time.sleep):
    """Reassert weights forever using the SAME subtensor connection passed in.

    Regression fix: this used to be main()'s inline loop calling
    set_owner_weights() with no subtensor arg, which defaulted to constructing
    a brand new bt.Subtensor() (new websocket connection) every 10-20s -
    contributing to the chain node's HTTP 429 connection throttling. The
    caller builds the connection once; this loop never constructs its own.
    """
    while True:
        try:
            result = set_owner_weights(subtensor=subtensor, wallet=wallet, netuid=netuid, target_uid=target_uid)
            print("SetWeights result:", result)
            if result.get("success"):
                print("SUCCESS: weights set. Will re-set periodically to keep fresh.")
                sleep(20)  # re-assert every ~20s (localnet is fast)
            else:
                print("WARNING: weights not set successfully. Check registration, permit, UID, balance. Retrying soon...")
                sleep(10)
        except Exception as e:
            print(f"ERROR: {e}. Retrying...")
            sleep(10)


def main():
    print("Starting KubeTEE owner validator (recycle mode)")
    print(f"  network={NETWORK} netuid={NETUID} target_uid={TARGET_UID}")
    print(f"  wallet={WALLET_NAME}/{HOTKEY_NAME}")
    print("  This sets 100% miner incentive weight to owner key.")
    print("  Ensure subnet RecycleOrBurn=Recycle (owner only) to recycle vs burn.")
    print("  Will retry periodically until registration succeeds (common on first start).")

    wallet = Wallet(name=WALLET_NAME, hotkey=HOTKEY_NAME)
    subtensor = bt.Subtensor(network=NETWORK)  # built once, reused for the life of the process
    run_validator_loop(subtensor, wallet, NETUID, TARGET_UID)

if __name__ == "__main__":
    main()
