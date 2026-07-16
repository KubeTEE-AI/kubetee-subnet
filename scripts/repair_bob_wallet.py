#!/usr/bin/env python3
"""Repair bob's dev wallet keyfile and ensure bob is registered (localnet).

The pinned ``DEV_BOB_SEED = "0x0b0b...0b"`` in ``setup_single_node.py`` is a
valid sr25519 seed, but ``btcli``/SDK regen serialise it with the raw 0x0b
*bytes* in the keyfile's ``secretSeed`` (instead of the hex text "0b0b..."),
so bittensor reads it back as corrupt ("Invalid character '\\u{b}'"). bob
therefore cannot sign and never registers - and with no miner registered the
validator can never score one.

This rewrites bob's cold+hot keyfiles with a correctly hex-encoded
``secretSeed`` (identity unchanged: ss58 ``5C5Z3GAF...``) and burned-registers
bob if absent. Idempotent; safe to run on every container start.

This is a dev-stack workaround. The proper fix is to replace DEV_BOB_SEED with
an ordinary hex seed so this script is no longer needed.
"""
from __future__ import annotations

import json
import os

import bittensor as bt

SEED = "0x" + "0b" * 32
NET = os.environ.get("BT_NETWORK", "ws://chain:9944")
BOB_COLDKEY = "/root/.bittensor/wallets/bob/coldkey"
BOB_HOTKEY = "/root/.bittensor/wallets/bob/hotkeys/default"


def _resolve_netuid() -> int:
    try:
        return int(open("/app/.kubetee_netuid").read().strip())
    except Exception:
        return int(os.environ.get("KUBETEE_SUBNET_NETUID", "1"))


def _write_keyfile(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    os.chmod(path, 0o600)


def main() -> None:
    keypair = bt.Keypair.create_from_seed(SEED)
    private_key = None
    try:
        private_key = "0x" + keypair.private_key.hex()
    except Exception:
        pass
    keyfile = json.dumps({
        "accountId": "0x" + keypair.public_key.hex(),
        "publicKey": "0x" + keypair.public_key.hex(),
        "privateKey": private_key,
        "secretPhrase": None,
        "secretSeed": SEED,
        "ss58Address": keypair.ss58_address,
        "cryptoType": 1,
    }).encode()
    _write_keyfile(BOB_COLDKEY, keyfile)
    _write_keyfile(BOB_HOTKEY, keyfile)
    print(f"[repair_bob] keyfile repaired for {keypair.ss58_address}")

    netuid = _resolve_netuid()
    subtensor = bt.Subtensor(network=NET)
    wallet = bt.Wallet(name="bob", hotkey="default")
    hotkey = wallet.hotkey.ss58_address
    metagraph = subtensor.metagraph(netuid=netuid)
    if hotkey in metagraph.hotkeys:
        print(f"[repair_bob] already registered at uid {metagraph.hotkeys.index(hotkey)}")
        return
    result = subtensor.burned_register(
        wallet=wallet, netuid=netuid,
        wait_for_inclusion=True, wait_for_finalization=True,
    )
    print("[repair_bob] register:", getattr(result, "success", result))


if __name__ == "__main__":
    main()
