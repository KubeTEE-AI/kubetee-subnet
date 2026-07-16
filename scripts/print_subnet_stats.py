#!/usr/bin/env python3
"""
Clean, log-friendly subnet stats printer.
No wide tables, no unicode boxes, simple key: value + short summaries.
Used inside the validator container's stats loop.

Every value below comes from a live chain_state query (see scripts/chain_state.py)
against a real bt.Subtensor connection - there is no hardcoded/placeholder text.
Query failures (e.g. HTTP 429) are surfaced via an explicit "error" field
instead of being silently reported as a fixed success/failure string.

Supports an internal loop (--loop/--interval) that reuses a single
bt.Subtensor connection for the life of the process, instead of the previous
docker-compose pattern of spawning a fresh python process (and therefore a
fresh chain connection) every cycle - that reconnect churn was a contributor
to the chain node's HTTP 429 throttling.
"""

import argparse
import os
import time

import bittensor as bt

import chain_state

HYPER_FIELDS = [
    "tempo",
    "owner_cut_auto_lock_enabled",
    "min_burn",
    "max_burn",
    "immunity_period",
    "activity_cutoff",
]


def build_report(netuid: int, chain_endpoint: str, wallets: dict, subtensor=None) -> dict:
    """Query real chain state for netuid + the given wallets.

    wallets: {"<name>": {"coldkey_ss58": str, "hotkey_ss58": str} | None, ...}
    The first entry is treated as the "owner" wallet for the ownership check.
    """
    sub = subtensor if subtensor is not None else bt.Subtensor(network=chain_endpoint)
    report = {"netuid": netuid, "network": chain_endpoint}

    try:
        h = sub.get_subnet_hyperparameters(netuid=netuid)
        hypers = {f: getattr(h, f, "?") for f in HYPER_FIELDS}
        try:
            hypers["recycle_or_burn"] = h.recycle_or_burn
        except Exception:
            pass
        report["hyperparameters"] = hypers
        report["hyperparameters_error"] = None
    except Exception as e:
        report["hyperparameters"] = None
        report["hyperparameters_error"] = str(e)

    owner_info = wallets.get("owner")
    if owner_info and owner_info.get("coldkey_ss58"):
        report["ownership"] = chain_state.query_subnet_ownership(
            netuid, owner_info["coldkey_ss58"], chain_endpoint, subtensor=sub
        )
    else:
        report["ownership"] = {
            "exists": None,
            "owner_ss58": None,
            "owned_by_us": False,
            "error": "owner wallet ss58 could not be resolved",
        }
    report["our_owner_ss58"] = owner_info.get("coldkey_ss58") if owner_info else None

    report["stake"] = {}
    for name, info in wallets.items():
        if not info or not info.get("coldkey_ss58") or not info.get("hotkey_ss58"):
            report["stake"][name] = {"stake_tao": None, "error": f"{name} wallet ss58 could not be resolved"}
        else:
            report["stake"][name] = chain_state.query_wallet_stake(
                netuid, info["coldkey_ss58"], info["hotkey_ss58"], chain_endpoint, subtensor=sub
            )

    return report


def format_report(report: dict) -> str:
    lines = []
    lines.append("========================================================")
    lines.append(f"=== KubeTEE Subnet Stats @ {time.strftime('%c')} netuid={report['netuid']} ===")
    lines.append("")
    lines.append(f"NETUID: {report['netuid']}")
    lines.append(f"Network: {report['network']}")

    if report["hyperparameters_error"]:
        lines.append(f"  hypers error: {report['hyperparameters_error']}")
    else:
        lines.append("Key Hyperparameters (conviction + recycle):")
        for k, v in report["hyperparameters"].items():
            lines.append(f"  {k}: {v}")

    lines.append("")
    lines.append("Stake (target wallets):")
    for name, stake in report["stake"].items():
        if stake["error"]:
            lines.append(f"  {name}: query failed ({stake['error']})")
        else:
            lines.append(f"  {name}: {stake['stake_tao']} TAO")

    lines.append("")
    lines.append("Subnet overview (short):")
    ownership = report["ownership"]
    if ownership["error"]:
        lines.append(f"  Subnet {report['netuid']} ownership query failed: {ownership['error']}")
    elif not ownership["exists"]:
        lines.append(f"  Subnet {report['netuid']} does not exist on this chain")
    elif ownership["owned_by_us"]:
        lines.append(f"  Subnet {report['netuid']} is owned by our owner wallet ({ownership['owner_ss58']})")
    else:
        lines.append(
            f"  Subnet {report['netuid']} owner is {ownership['owner_ss58']} "
            f"(NOT our owner wallet {report['our_owner_ss58']})"
        )

    lines.append("")
    lines.append("Conviction:")
    if report["hyperparameters_error"]:
        lines.append(f"  unknown (hypers query failed: {report['hyperparameters_error']})")
    else:
        lock_enabled = report["hyperparameters"].get("owner_cut_auto_lock_enabled")
        if ownership["owned_by_us"]:
            lines.append(f"  owner_cut_auto_lock_enabled: {lock_enabled}")
        else:
            lines.append(f"  owner_cut_auto_lock_enabled: {lock_enabled} (we are not the subnet owner, cannot sudo set this)")

    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI defaults (g004 D7): the owner wallet is the subnet owner
    (KUBETEE_OWNER_WALLET, NOT BT_WALLET - that is alice, the validator
    signing wallet) and the default miner wallet is bob."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--netuid", type=int, default=int(os.environ.get("KUBETEE_SUBNET_NETUID", "1")))
    parser.add_argument("--network", default=os.environ.get("BT_NETWORK", "ws://chain:9944"))
    parser.add_argument("--owner-wallet", default=os.environ.get("KUBETEE_OWNER_WALLET", "owner"))
    parser.add_argument("--miner-wallet", default="bob")
    parser.add_argument("--loop", action="store_true", help="Loop forever, reusing a single chain connection.")
    parser.add_argument("--interval", type=float, default=25.0, help="Seconds between reports when --loop is set.")
    return parser


def main():
    args = build_arg_parser().parse_args()

    wallets = {
        "owner": {
            "coldkey_ss58": chain_state.resolve_coldkey_ss58(args.owner_wallet),
            "hotkey_ss58": chain_state.resolve_hotkey_ss58(args.owner_wallet),
        },
        "miner": {
            "coldkey_ss58": chain_state.resolve_coldkey_ss58(args.miner_wallet),
            "hotkey_ss58": chain_state.resolve_hotkey_ss58(args.miner_wallet),
        },
    }

    subtensor = bt.Subtensor(network=args.network)

    while True:
        report = build_report(args.netuid, args.network, wallets, subtensor=subtensor)
        print(format_report(report))
        if not args.loop:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
