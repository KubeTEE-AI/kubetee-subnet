#!/usr/bin/env python3
"""
Shared real-chain state queries for the KubeTEE single-node testing pyramid.

Every function here performs a live bt.Subtensor query (or accepts an
injected `subtensor` for testing) and returns the actual on-chain result, or
an explicit "error" string. Nothing here returns a hardcoded/placeholder
value - that was the bug in the original print_subnet_stats.py (stake,
ownership, and conviction text were baked-in strings, never queried) and the
root cause of the setup_single_node.py ownership fallback bug (a failed
`btcli subnet create` was assumed to mean success instead of being verified
against the real on-chain owner).

Used by scripts/setup_single_node.py (to decide whether owner-only calls are
safe to attempt) and scripts/print_subnet_stats.py (to report real state).
"""

from __future__ import annotations

import bittensor as bt


def query_subnet_ownership(
    netuid: int,
    our_coldkey_ss58: str,
    chain_endpoint: str,
    subtensor: bt.Subtensor | None = None,
) -> dict:
    """Query the real on-chain owner of `netuid` and compare to our_coldkey_ss58.

    Returns {"exists", "owner_ss58", "owned_by_us", "error"}. A query failure
    (e.g. HTTP 429, chain unreachable) is reported via "error", never
    swallowed into a default owned_by_us=True/False guess.
    """
    sub = (
        subtensor
        if subtensor is not None
        else bt.Subtensor(network=chain_endpoint)
    )
    try:
        head = sub.block()
        metagraph = sub.subnets.metagraph(
            netuid,
            block=head,
            commitments=False,
        )
        if metagraph is None:
            return {
                "exists": False,
                "owner_ss58": None,
                "owned_by_us": False,
                "error": None,
            }
        if metagraph.block != head:
            raise ValueError(
                "ownership snapshot is not pinned to the requested head"
            )
        owner_ss58 = metagraph.owner_coldkey
        if not isinstance(owner_ss58, str) or not owner_ss58:
            raise ValueError("ownership snapshot has no canonical owner")
        return {
            "exists": True,
            "owner_ss58": owner_ss58,
            "owned_by_us": owner_ss58 == our_coldkey_ss58,
            "error": None,
        }
    # Bittensor can surface transport, decoding, or SDK errors here.
    # pylint: disable-next=broad-exception-caught
    except Exception as e:
        return {
            "exists": None,
            "owner_ss58": None,
            "owned_by_us": False,
            "error": str(e),
        }


def query_wallet_stake(
    netuid: int,
    coldkey_ss58: str,
    hotkey_ss58: str,
    chain_endpoint: str,
    subtensor: bt.Subtensor | None = None,
) -> dict:
    """Query the real stake for coldkey_ss58/hotkey_ss58 on netuid.

    Returns {"stake_tao", "error"}. stake_tao is a real float (0.0 means
    genuinely no stake); a query failure sets stake_tao=None and populates
    "error" instead of silently reporting zero.
    """
    sub = (
        subtensor
        if subtensor is not None
        else bt.Subtensor(network=chain_endpoint)
    )
    try:
        balance = sub.staking.get(
            coldkey_ss58=coldkey_ss58, hotkey_ss58=hotkey_ss58, netuid=netuid
        )
        return {"stake_tao": float(balance.tao), "error": None}
    # Bittensor can surface transport, decoding, or SDK errors here.
    # pylint: disable-next=broad-exception-caught
    except Exception as e:
        return {"stake_tao": None, "error": str(e)}


def resolve_coldkey_ss58(
    wallet_name: str, hotkey: str = "default"
) -> str | None:
    """Resolve a local wallet coldkey SS58, returning None on failure."""
    try:
        return bt.Wallet(
            name=wallet_name, hotkey=hotkey
        ).coldkeypub.ss58_address
    # Wallet backends expose several implementation-specific failures.
    # pylint: disable-next=broad-exception-caught
    except Exception:
        return None


def resolve_hotkey_ss58(
    wallet_name: str, hotkey: str = "default"
) -> str | None:
    """Resolve a local wallet hotkey SS58, returning None on failure."""
    try:
        return bt.Wallet(
            name=wallet_name, hotkey=hotkey
        ).hotkeypub.ss58_address
    # Wallet backends expose several implementation-specific failures.
    # pylint: disable-next=broad-exception-caught
    except Exception:
        return None
