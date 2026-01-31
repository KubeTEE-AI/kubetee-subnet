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
  TARGET_UID=1 \
  python -m scripts.owner_validator

For full subnet: register owner hotkey as neuron, discover UID via metagraph,
set weights to it every epoch, and ensure RecycleOrBurn=Recycle on the subnet.
"""

import asyncio
import os
import sys
from pathlib import Path

import bittensor as sub
from bittensor.wallet import Wallet

# Simple config via env for now (will be proper config in full pyramid)
NETWORK = os.getenv("BT_NETWORK", "local")
WALLET_NAME = os.getenv("BT_WALLET", "owner")
HOTKEY_NAME = os.getenv("BT_WALLET_HOTKEY", "default")
NETUID = int(os.getenv("KUBE TEE_SUBNET_NETUID", "1"))
TARGET_UID = int(os.getenv("TARGET_UID", "0"))  # UID of the owner-registered key

# For testing pyramid: allow injection of client/wallet for mocks
async def set_owner_weights(
    client: sub.Client | sub.SyncClient | None = None,
    wallet: Wallet | None = None,
    netuid: int = NETUID,
    target_uid: int = TARGET_UID,
) -> dict:
    """Core logic: set weight 1.0 to target UID (owner key).

    Returns result dict for testing/assertion.
    """
    if wallet is None:
        wallet = Wallet(name=WALLET_NAME, hotkey=HOTKEY_NAME)

    if client is None:
        # Use async by default for v11
        async with sub.Client(NETWORK) as c:
            return await _do_set_weights(c, wallet, netuid, target_uid)
    else:
        if isinstance(client, sub.SyncClient):
            return _do_set_weights_sync(client, wallet, netuid, target_uid)
        return await _do_set_weights(client, wallet, netuid, target_uid)

async def _do_set_weights(client, wallet, netuid, target_uid):
    intent = sub.SetWeights(
        netuid=netuid,
        weights={target_uid: 1.0},  # full weight to owner for recycle use case
        # version_key etc. as needed; defaults ok for local
    )
    result = await client.execute(intent, wallet)
    return {
        "success": result.success,
        "netuid": netuid,
        "target_uid": target_uid,
        "block_hash": getattr(result, "block_hash", None),
        "error": str(result.error) if not result.success else None,
    }

def _do_set_weights_sync(client, wallet, netuid, target_uid):
    intent = sub.SetWeights(netuid=netuid, weights={target_uid: 1.0})
    result = client.execute(intent, wallet)  # sync facade
    return {
        "success": result.success,
        "netuid": netuid,
        "target_uid": target_uid,
        "block_hash": getattr(result, "block_hash", None),
        "error": str(result.error) if not result.success else None,
    }

def main():
    print(f"Starting KubeTEE owner validator (recycle mode)")
    print(f"  network={NETWORK} netuid={NETUID} target_uid={TARGET_UID}")
    print(f"  wallet={WALLET_NAME}/{HOTKEY_NAME}")
    print("  This sets 100% miner incentive weight to owner key.")
    print("  Ensure subnet RecycleOrBurn=Recycle (owner only) to recycle vs burn.")

    try:
        result = asyncio.run(set_owner_weights())
        print("SetWeights result:", result)
        if not result["success"]:
            print("WARNING: weights not set successfully. Check registration, permit, UID.")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
