#!/usr/bin/env python3
"""
Single Node Testing Pyramid Setup Script

For the KubeTEE local "single node testnet" (using subtensor-localnet in docker).

This script:
1. Waits for chain to be ready.
2. Creates/funds dev wallets using *pinned dev seeds* (owner + alice + bob triad, D7)
   for stable SS58 addresses and predictable UIDs on the localnet.
3. Creates/registers the subnet (if needed) on local.
4. Registers the owner hotkey as a neuron (to get a UID for emissions).
5. Starts emissions (sudo start).
6. Sets hyperparams:
   - owner_cut_auto_lock_enabled = true   (auto-locks owner cut emissions into CONVICTION lock)
   - recycle_or_burn = Recycle            (recycle instead of burn for owner-directed emissions)

This enables:
- Owner emissions (cut + trick-weighted miner emissions) go into conviction
  (locked, builds conviction over time).
- Recycle instead of burn for the directed emissions.
- Full emissions flow for testing (no burn waste).

Primary usage (self-contained in container):
  The validator container entrypoint runs this first (with ws://chain:9944),
  then starts the owner validator.

Manual usage (from host, with bittensor installed):
  python scripts/setup_single_node.py --netuid 1 --chain-endpoint ws://127.0.0.1:9944

Then view everything in dozzle: http://localhost:8080

Requires: bittensor + bittensor-cli (btcli) in PATH. Inside the validator image
this is guaranteed. For pure local dev it uses *pinned dev seeds*
(owner/alice/bob) exactly like fdn-subnet pins Alith etc.
  for reproducible registration, hypers, and UID targeting in the single-node test pyramid.

Note: On localnet with FAST_BLOCKS, tempos are fast.
"""

import argparse
import os
import subprocess
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
#   This makes the owner UID predictable (usually 0 for the first/owner registration)
#   and the whole "setup then validator" flow deterministic.
#
# !!! ONLY FOR LOCALNET / SINGLE-NODE TEST PYRAMID !!!
# These seeds control nothing on real chains. Never use against testnet or mainnet.
# =====================================================================================

DEV_ALICE_SEED = (
    "0xe5be9a5092b81bca64be81d212e7f2f9eba183bb7a90954f7b76361f6edb5c0a"
)

# Pinned dev seed for the subnet *owner* wallet (the one that creates the subnet,
# registers its hotkey, sets hypers via sudo, and the validator weights to).
# Derived SS58 (cold+hot for dev simplicity): 5FLbZav21bAsjH5SAdmJZwTP5C4b3bcaaWqC6GSmGmsbzUJ9
DEV_OWNER_SEED = (
    "0x398f0c28f98885e046333d4a41c19cee4c37368a9832c749be0086a2a9b4e8c0"
)
DEV_OWNER_COLD_SS58 = "5FLbZav21bAsjH5SAdmJZwTP5C4b3bcaaWqC6GSmGmsbzUJ9"

# Pinned dev seed for the "bob" miner wallet (g004 D7): the miner whose
# Rancher cluster carries the canonical kubetee.ai/hotkey binding used by
# the basic validator. Replaces the retired legacy sample "miner" wallet.
# Localnet-only,
# PUBLIC by design. NOTE (#20): must be an ordinary random hex seed - the
# previous all-0x0b value was serialised as raw bytes into the keyfile's
# secretSeed, producing a wallet bittensor could not read back (bob could
# never sign or register). ss58: 5FsfgiqMdQzgqtJQLb15ox6MzcZLvFG55vtAsy4TYuDCEEFs
DEV_BOB_SEED = (
    "0x907fd5b32015c612b7badd5c4ab60de2fbb641333989e5eeabcd226a240a4689"
)


def run(cmd: list[str], check=True, capture=False, env=None, dry_run=False):
    if dry_run:
        print(f"[DRY-RUN] $ {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, returncode=0)
    print(f"$ {' '.join(cmd)}")
    res = subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        env=env or os.environ,
    )
    if capture:
        print(res.stdout)
    return res


def wait_for_chain(
    chain_endpoint: str = "ws://127.0.0.1:9944", timeout=120, dry_run=False
):
    print(f"Waiting for chain RPC at {chain_endpoint} ...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            # btcli accepts --network as ws://... or "local"
            run(
                [
                    "btcli",
                    "query",
                    "block",
                    "--network",
                    chain_endpoint,
                    "--yes",
                ],
                check=False,
                capture=True,
                dry_run=dry_run,
            )
            print("Chain is up!")
            return True
        # The CLI/SDK boundary can raise subprocess, transport, or SDK errors.
        # pylint: disable-next=broad-exception-caught
        except Exception as e:
            print(f"  ... not ready yet: {e}")
            time.sleep(5)
    raise TimeoutError(
        "Chain did not become ready in time. Check docker logs."
    )


def _regenerate_wallet_key(
    key_kind: str,
    name: str,
    seed: str,
    hotkey: str = "default",
    dry_run: bool = False,
):
    """Regenerate one pinned local wallet key without exposing its seed."""
    if key_kind not in {"coldkey", "hotkey"}:
        raise ValueError("key_kind must be coldkey or hotkey")

    base_wallet_path = str(Path.home() / ".bittensor" / "wallets")
    command = [
        "btcli",
        "wallet",
        f"regen-{key_kind}",
        "--wallet",
        name,
        "--wallet-hotkey",
        hotkey,
        "--wallet-path",
        base_wallet_path,
        "--seed",
        seed,
    ]
    if key_kind == "coldkey":
        command.append("--no-password")
    command.extend(["--overwrite", "--quiet"])
    redacted_command = [
        "<redacted-seed>" if argument == seed else argument
        for argument in command
    ]
    print(f"$ {' '.join(redacted_command)}")
    if dry_run:
        return

    execution_failed = False
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, shell=False
        )
    except Exception:
        execution_failed = True
    if execution_failed or result.returncode != 0:
        raise RuntimeError(f"{key_kind} regeneration failed")


def ensure_dev_wallet(
    name: str, seed: str, hotkey: str = "default", dry_run=False
):
    """Ensure a wallet exists using a *pinned dev seed* (regen, not random new_coldkey).

    This follows the fdn-subnet pattern of using well-known dev keys (Alith etc.)
    so that owner addresses / UIDs are stable for the single-node pyramid.
    We regen BOTH coldkey (for sudo/ownership) and hotkey (for registration + signing weights).
    """
    print(
        f"Ensuring dev wallet {name} (pinned seed for cold+hot, hotkey={hotkey}) ..."
    )
    _regenerate_wallet_key("coldkey", name, seed, hotkey, dry_run=dry_run)
    _regenerate_wallet_key("hotkey", name, seed, hotkey, dry_run=dry_run)

    print(f"  dev wallet {name} ready (cold+hot seed-pinned).")


def get_wallet_coldkey_ss58(
    name: str, hotkey: str = "default", dry_run=False
) -> str:
    """Resolve a wallet coldkey SS58 through the SDK or btcli."""
    if bt is not None:
        try:
            w = bt.Wallet(name=name, hotkey=hotkey)
            addr = w.coldkeypub.ss58_address
            print(f"  resolved {name} coldkey ss58 via SDK: {addr}")
            return addr
        # Fall back to btcli for any SDK-specific wallet failure.
        # pylint: disable-next=broad-exception-caught
        except Exception as e:
            print(
                f"  bt.Wallet resolve for {name} failed: {e}, will try btcli"
            )

    # Fallback: use btcli wallet inspect and parse ss58 (best effort)
    base_wallet_path = str(Path.home() / ".bittensor" / "wallets")
    res = run(
        [
            "btcli",
            "wallet",
            "inspect",
            "--wallet",
            name,
            "--wallet-hotkey",
            hotkey,
            "--wallet-path",
            base_wallet_path,
            "--quiet",
        ],
        check=False,
        capture=True,
        dry_run=dry_run,
    )
    out = (res.stdout or "") + (res.stderr or "")
    # crude parse for ss58 in output
    import re

    m = re.search(r"(5[0-9a-zA-Z]{46,48})", out)
    if m:
        addr = m.group(1)
        print(f"  resolved {name} coldkey ss58 via btcli inspect: {addr}")
        return addr
    # last resort
    print(
        f"  WARNING: could not resolve ss58 for {name}, using placeholder (funding may fail)"
    )
    return "5GT5Ycu59s7xiGj4VkRRZsEkypEFbECeMBCeQ14t8G7H8h8F"


def fund_from_alice(
    dest_name: str,
    amount: int = 10000,
    chain_endpoint: str = "ws://127.0.0.1:9944",
    dry_run=False,
):
    """Fund using local Alice dev key (standard for localnet)."""
    print(
        f"Funding {dest_name} from Alice dev account (endpoint={chain_endpoint})..."
    )
    _regenerate_wallet_key("coldkey", "alice", DEV_ALICE_SEED, dry_run=dry_run)

    # Resolve the *actual* address for dest_name so we fund the wallet later
    # used for create/sudo.
    dest_ss58 = get_wallet_coldkey_ss58(dest_name, dry_run=dry_run)
    run(
        [
            "btcli",
            "wallet",
            "transfer",
            "--dest",
            dest_ss58,
            "--amount",
            str(amount),
            "--wallet",
            "alice",
            "--wallet-hotkey",
            "default",
            "--network",
            chain_endpoint,
            "--yes",
        ],
        check=True,
        dry_run=dry_run,
    )


def _snapshot_subnet_netuids(chain_endpoint: str) -> set[int]:
    """Return one complete, validated live snapshot of subnet netuids."""
    if bt is None:
        raise RuntimeError("unable to snapshot subnet netuids")

    try:
        subnet_infos = bt.Subtensor(network=chain_endpoint).subnets.subnets()
        netuids = [subnet.netuid for subnet in subnet_infos]
    except Exception:
        snapshot_failed = True
    else:
        snapshot_failed = False
    if snapshot_failed:
        raise RuntimeError("unable to snapshot subnet netuids")

    if (
        any(type(netuid) is not int or netuid < 0 for netuid in netuids)
        or len(netuids) != len(set(netuids))
    ):
        raise RuntimeError("invalid subnet netuid snapshot")
    return set(netuids)


def create_subnet_if_needed(
    netuid: int,
    owner_name: str,
    chain_endpoint: str = "ws://127.0.0.1:9944",
    dry_run=False,
):
    if dry_run:
        return netuid

    print(
        "Creating/ensuring subnet "
        f"(target {netuid}, owner={owner_name}, network={chain_endpoint})..."
    )
    before = _snapshot_subnet_netuids(chain_endpoint)
    command = [
        "btcli",
        "subnet",
        "create",
        "--wallet",
        owner_name,
        "--wallet-hotkey",
        "default",
        "--network",
        chain_endpoint,
        "--yes",
        "--json",
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
    except Exception:
        creation_failed = True
    else:
        creation_failed = False
    if creation_failed:
        raise RuntimeError("subnet creation failed")

    after = _snapshot_subnet_netuids(chain_endpoint)
    created = after - before
    if len(created) != 1:
        raise RuntimeError(
            "subnet creation did not yield exactly one new netuid"
        )
    actual = created.pop()
    print(f"  Live chain postcondition resolved netuid {actual}.")
    return actual


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
            "reason": (
                f"ownership query failed ({ownership['error']}); "
                "failing closed, not retrying blindly"
            ),
        }
    if not ownership.get("exists"):
        return {
            "proceed": False,
            "reason": "target netuid does not exist on chain",
        }
    if not ownership.get("owned_by_us"):
        return {
            "proceed": False,
            "reason": f"netuid is owned by {ownership.get('owner_ss58')!r}, not our wallet",
        }
    return {"proceed": True, "reason": "confirmed on-chain owner match"}


def registration_plan(owner_wallet: str = "owner") -> list[dict]:
    """The g004 wallet triad (D7), in registration order. Pure data consumed
    by main() and asserted by tests.

    owner (the recycle target) registers first for a stable UID; alice is
    the validator that signs set_weights (its stake attempt is best-effort:
    the pinned localnet image can reject add_stake with SubtokenDisabled,
    reported honestly by the btcli output); bob is the miner - a new pinned
    dev seed replacing the retired legacy sample "miner" wallet.
    """
    return [
        {
            "wallet": owner_wallet,
            "seed": DEV_OWNER_SEED,
            "role": "owner",
            "validator": True,
            "stake": 200,
        },
        {
            "wallet": "alice",
            "seed": DEV_ALICE_SEED,
            "role": "validator",
            "validator": True,
            "stake": 100,
        },
        {
            "wallet": "bob",
            "seed": DEV_BOB_SEED,
            "role": "miner",
            "validator": False,
            "stake": 50,
        },
    ]


def register_neuron(
    netuid: int,
    wallet_name: str,
    hotkey: str = "default",
    as_validator: bool = True,
    chain_endpoint: str = "ws://127.0.0.1:9944",
    dry_run: bool = False,
):
    role = "validator" if as_validator else "miner"
    print(
        f"Registering {wallet_name} as {role} on netuid {netuid} "
        f"(network={chain_endpoint}) ..."
    )
    # Use burned register on local (faucet enabled).
    run(
        [
            "btcli",
            "subnet",
            "register",
            "--netuid",
            str(netuid),
            "--wallet",
            wallet_name,
            "--wallet-hotkey",
            hotkey,
            "--network",
            chain_endpoint,
            "--yes",
        ],
        check=True,
        dry_run=dry_run,
    )


def start_emissions(
    netuid: int,
    owner_name: str,
    chain_endpoint: str = "ws://127.0.0.1:9944",
    dry_run: bool = False,
):
    print(
        f"Starting emissions for netuid {netuid} (network={chain_endpoint}) ..."
    )
    # Correct command for current bittensor-cli in the image: `btcli subnets start`
    # (older code used `btcli sudo start` which no longer exists)
    run(
        [
            "btcli",
            "subnets",
            "start",
            "--netuid",
            str(netuid),
            "--wallet",
            owner_name,
            "--wallet-hotkey",
            "default",
            "--network",
            chain_endpoint,
            "--yes",
        ],
        check=False,
        dry_run=dry_run,
    )


def add_stake(
    netuid: int,
    wallet_name: str,
    amount: int = 100,
    chain_endpoint: str = "ws://127.0.0.1:9944",
    dry_run: bool = False,
):
    """Stake on the subnet so the wallet is visible in the metagraph."""
    print(
        f"Adding stake {amount} TAO on netuid {netuid} for {wallet_name} ..."
    )
    # --unsafe to avoid shield/safe mode issues seen on this btcli + localnet combination.
    run(
        [
            "btcli",
            "stake",
            "add",
            "--netuid",
            str(netuid),
            "--wallet",
            wallet_name,
            "--wallet-hotkey",
            "default",
            "--amount",
            str(amount),
            "--network",
            chain_endpoint,
            "--yes",
            "--unsafe",
        ],
        check=False,
        dry_run=dry_run,
    )


def set_hyperparam(
    netuid: int,
    owner_name: str,
    param: str,
    value: str,
    chain_endpoint: str = "ws://127.0.0.1:9944",
    dry_run: bool = False,
):
    print(
        f"Setting {param}={value} on netuid {netuid} (network={chain_endpoint}) ..."
    )
    # v11 uses btcli sudo set or tx set-hyperparameter
    run(
        [
            "btcli",
            "sudo",
            "set",
            "--netuid",
            str(netuid),
            "--param",
            param,
            "--value",
            value,
            "--wallet",
            owner_name,
            "--wallet-hotkey",
            "default",
            "--network",
            chain_endpoint,
            "--yes",
        ],
        check=False,
        dry_run=dry_run,
    )


def set_conviction_and_recycle(
    netuid: int,
    owner_name: str,
    chain_endpoint: str = "ws://127.0.0.1:9944",
    dry_run: bool = False,
):
    """Set owner emissions into conviction + recycle instead of burn."""
    # 1. Auto lock owner cut into conviction
    set_hyperparam(
        netuid,
        owner_name,
        "owner_cut_auto_lock_enabled",
        "true",
        chain_endpoint,
        dry_run=dry_run,
    )
    # 2. Recycle instead of burn for owner-directed (burn UID) emissions
    set_hyperparam(
        netuid,
        owner_name,
        "recycle_or_burn",
        "Recycle",
        chain_endpoint,
        dry_run=dry_run,
    )
    print("Conviction auto-lock + Recycle mode enabled for owner emissions.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--netuid", type=int, default=1)
    parser.add_argument("--owner-wallet", default="owner")
    parser.add_argument(
        "--chain-endpoint",
        default=os.getenv("BT_NETWORK", "ws://127.0.0.1:9944"),
        help="ws://... endpoint or 'local'. Inside docker compose use ws://chain:9944",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands instead of executing them",
    )
    args = parser.parse_args()

    netuid = args.netuid
    owner = args.owner_wallet
    chain_endpoint = args.chain_endpoint
    dry_run = args.dry_run

    print("=== KubeTEE Single-Node Pyramid Setup ===")
    print(f"Netuid: {netuid}, Owner wallet: {owner}")
    print(f"Chain endpoint: {chain_endpoint}")
    if dry_run:
        print("[DRY-RUN] Commands will be printed but not executed.")

    wait_for_chain(chain_endpoint, dry_run=dry_run)

    # Wallets using *pinned dev seeds* (fdn-subnet style) for stable SS58/UIDs.
    # The g004 triad (D7): owner (recycle target + sudo), alice (validator,
    # signs set_weights), bob (miner). Alice also stays the funding source.
    triad = registration_plan(owner)
    for entry in triad:
        ensure_dev_wallet(entry["wallet"], entry["seed"], dry_run=dry_run)

    # Fund the actual addresses of the wallets we will use.
    fund_from_alice(owner, 5000, chain_endpoint, dry_run=dry_run)
    fund_from_alice("bob", 2000, chain_endpoint, dry_run=dry_run)
    fund_from_alice(
        "alice", 1000, chain_endpoint, dry_run=dry_run
    )  # top up alice faucet

    # Wait for transfers to land (localnet is fast but extrinsic finality + balance query can lag)
    print("Waiting briefly for balances to settle after funding...")
    time.sleep(6)

    # Subnet + neuron setup (owner registers to have a UID for weighting)
    # create_subnet_if_needed now forces a create (to get ownership) and returns the actual netuid.
    netuid = create_subnet_if_needed(
        netuid, owner, chain_endpoint, dry_run=dry_run
    )

    # Register + stake the triad in plan order. Stake attempts are
    # best-effort and reported honestly: the pinned localnet image can
    # reject add_stake with SubtokenDisabled (T3 lesson) - the btcli output
    # below is the record; nothing here claims a stake that did not land.
    for entry in triad:
        register_neuron(
            netuid,
            entry["wallet"],
            "default",
            as_validator=entry["validator"],
            chain_endpoint=chain_endpoint,
            dry_run=dry_run,
        )
        add_stake(
            netuid,
            entry["wallet"],
            entry["stake"],
            chain_endpoint,
            dry_run=dry_run,
        )

    # Verify real on-chain ownership before attempting owner-only sudo calls.
    # create_subnet_if_needed's regex-parsed btcli stdout is NOT proof of ownership
    # (e.g. it silently falls back to the requested netuid when `btcli subnet create`
    # fails, such as with a SubtokenDisabled chain error) - only a live query is.
    our_owner_ss58 = get_wallet_coldkey_ss58(owner, dry_run=dry_run)
    ownership = chain_state.query_subnet_ownership(
        netuid, our_owner_ss58, chain_endpoint
    )
    decision = decide_owner_actions(ownership)
    print(
        f"\nOwnership check: netuid={netuid} our_wallet={our_owner_ss58} -> {ownership}"
    )
    print(f"Decision: proceed={decision['proceed']} ({decision['reason']})")

    if decision["proceed"]:
        # Start emissions
        start_emissions(netuid, owner, chain_endpoint, dry_run=dry_run)
        # Set the key hypers for conviction + recycle
        set_conviction_and_recycle(
            netuid, owner, chain_endpoint, dry_run=dry_run
        )
    else:
        print(
            f"  SKIPPING start_emissions + conviction/recycle hypers: {decision['reason']}"
        )
        print(
            "  (Retrying these against a netuid we don't own would fail "
            "every time and just hammer the chain.)"
        )

    # Record whether we actually own the netuid so other processes (compose's
    # conviction-setter loop, print_subnet_stats.py) can avoid repeating the
    # same doomed owner-only calls instead of retrying blindly forever.
    try:
        with open("/app/.kubetee_owned", "w", encoding="utf-8") as f:
            f.write("true" if decision["proceed"] else "false")
    # Status-file failure must not hide the on-chain setup outcome.
    # pylint: disable-next=broad-exception-caught
    except Exception as e:
        print(f"  Warning: could not write ownership status file: {e}")

    print("\n=== Setup complete ===")
    if decision["proceed"]:
        print("Owner emissions will now:")
        print(
            "  - Have owner cut auto-locked into CONVICTION (via owner_cut_auto_lock_enabled)"
        )
        print(
            "  - Miner emissions directed to owner UID will be RECYCLED (not burned)"
        )
    else:
        print(
            "Owner does NOT control this netuid's sudo-only hyperparameters on this chain:"
        )
        print(f"  {decision['reason']}")
        print(
            "  Conviction/recycle hypers were NOT set. See ownership "
            "check above for the real owner."
        )
    print(
        "\nUsing pinned dev seeds (owner SS58 ~5FLbZa... ) so the registered UID is stable."
    )
    print(
        "Next: The basic validator (alice) discovers miners from the "
        "metagraph, scores them via Rancher, and splits weights "
        "(default 10% miners / 90% owner recycle UID)."
    )
    print(
        "When used inside the validator container, this script runs first "
        "then the validator starts automatically."
    )

    # Write the actual netuid we own so the validator and other containers
    # can use the correct one.
    try:
        with open("/app/.kubetee_netuid", "w", encoding="utf-8") as f:
            f.write(str(netuid))
        print(
            f"  Wrote actual netuid={netuid} to /app/.kubetee_netuid for the validator phase."
        )
    # Status-file failure must not hide the on-chain setup outcome.
    # pylint: disable-next=broad-exception-caught
    except Exception as e:
        print(f"  Warning: could not write netuid file: {e}")


if __name__ == "__main__":
    main()
