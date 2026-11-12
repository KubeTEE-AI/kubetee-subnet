"""Finalize one authorized Gamma burn, then atomically credit its native key.

Every material deposit mutation is proven against finalized parent/child raw
storage in a bounded chronological window. Eligible amounts are not receipts:
an all-or-nothing spend can advance a claim without crediting, and its exact
remainder must force later eligible-vs-spendable reconciliation (or pause).
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from .chain import matching_events, pallet_units, raw_reference
from .management import (
    StateConflict,
    amount,
    exact_money,
    remaining_units,
    validate_identity,
)
from .protocol import (
    GENESIS,
    PublicResult,
    SettlementRef,
    settlement_reference,
)


class Pending(Exception):
    def __init__(self, reason: str, retry_after_seconds: int = 6):
        super().__init__(reason)
        self.reason, self.retry_after_seconds = reason, retry_after_seconds


class Ineligible(Exception):
    pass


@dataclass(frozen=True)
class DepositState:
    height: int
    block_hash: str
    stored: dict


def cap_state(row: dict) -> Optional[dict]:
    raw = row.get("daily_spend_cap")
    if raw is None:
        return None
    try:
        bucket = raw["bucket"]
        if type(bucket[0]) is not int or type(bucket[1]) is not int:
            raise ValueError()
        return {
            "cap_units": pallet_units(raw, "cap"),
            "bucket_units": bucket[0],
            "fed_at_block": bucket[1],
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise Ineligible("unrecognized finalized daily-cap bucket") from exc


def cap_spendable(row: dict, now: int) -> int:
    balance = pallet_units(row, "balance")
    state = cap_state(row)
    if state is None:
        return balance
    elapsed = max(0, now - state["fed_at_block"])
    return min(
        balance,
        state["cap_units"],
        state["bucket_units"] + state["cap_units"] * elapsed // 7200,
    )


def base_checkpoint(deposit: DepositState, *, quality: str) -> dict:
    row = deposit.stored
    if quality not in {"minted_pending", "donor", "delegated"}:
        raise ValueError("live observed origin required")
    return {
        "schema": 1,
        "network": "finney",
        "genesis_hash": GENESIS,
        "netuid": 90,
        "observation_height": deposit.height,
        "observation_hash": deposit.block_hash,
        "observation_coldkey": str(row["coldkey"]),
        "observation_spender": str(row["spender"]),
        "accepted_kind": quality,
        "delta_units": pallet_units(row, "balance"),
        "previous_units": 0,
        "receipt_ids": [],
        "total_settled_units": 0,
        "pending": None,
        "last_spent_height": None,
        "last_spent_amount": None,
        "last_spent_reference": None,
        "cap": cap_state(row),
        "needs_cap_audit": False,
    }


def hydrate(row: dict, cp: dict, *, hk: str) -> dict:
    """Validate the receipt and intake binding; not redundant truth fields."""
    if not cp:
        return {}
    cp = copy.deepcopy(cp)
    try:
        if (cp["network"], cp["genesis_hash"], cp["netuid"]) != (
            "finney",
            GENESIS,
            90,
        ):
            raise ValueError()
        if (
            type(cp["observation_height"]) is not int
            or cp["observation_height"] < 1
        ):
            raise ValueError()
        if type(cp["delta_units"]) is not int or cp["delta_units"] < 0:
            raise ValueError()
        if cp["accepted_kind"] not in {
            "minted_pending",
            "donor",
            "delegated",
            "settled",
        }:
            raise ValueError()
        if (
            not isinstance(cp["receipt_ids"], list)
            or len(cp["receipt_ids"]) > 100
        ):
            raise ValueError()
        for marker in cp["receipt_ids"]:
            SettlementRef.model_validate(marker).validate_identity(hk)
        if cp.get("pending") is not None:
            p = cp["pending"]
            ref = SettlementRef.model_validate(p["reference"])
            ref.validate_identity(hk)
            if (
                ref.block_hash != p.get("planning_hash")
                or ref.block_number != p["intake_height"]
            ):
                raise ValueError()
            if (
                type(p["intake_height"]) is not int
                or p["intake_height"] < cp["observation_height"]
            ):
                raise ValueError()
            if type(p["parent_units"]) is not int or p["parent_units"] < 0:
                raise ValueError()
            if type(p["attempts"]) is not int or p["attempts"] != 1:
                raise ValueError()
    except (KeyError, TypeError, ValueError) as exc:
        raise Ineligible(
            "malformed/unfenced native settlement checkpoint"
        ) from exc
    return cp


class Reconciler:
    """The store simulates the gateway's compare-and-swap Management operation."""

    def __init__(
        self,
        chain,
        management,
        store,
        signer=None,
        *,
        max_backfill: int = 7200,
        lease=None,
    ):
        self.chain, self.gateway, self.store = chain, management, store
        self.signer, self.max_backfill, self.lease = (
            signer,
            max_backfill,
            lease,
        )
        self.follow: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_guard = asyncio.Lock()

    async def prepare_observation(self, hk: str) -> None:
        """Validate live final storage and establish only blocked zero credit.

        A native reservation never contains a raw customer API key. This is
        intentionally the same per-H preparation used by authenticated claims.
        """
        if await self._row(hk) is not None:
            return
        if self.lease is not None and not await self.lease.acquire(hk):
            raise Pending("stale/nonleader worker")
        try:
            if await self._row(hk) is not None:
                return
            observed = await self.snapshot(hk)
            if (
                observed is None
                or str(observed.stored["spender"]) != self.chain.real_spender
            ):
                raise Pending("no finalized eligible service deposit")
            checkpoint = base_checkpoint(observed, quality="minted_pending")
            if self.store is None:
                await self.gateway.reserve(hk, checkpoint)
            else:
                row = await self.store.reserve(hk, checkpoint)
                validate_identity(row, hk, row["token_id"])
        finally:
            if self.lease is not None:
                await self.lease.release(hk)

    async def current_cap(self, hk: str):
        """One traceable finalized height/root, not a second unanchored RPC."""
        _, _, row = await self.finalized_snapshot(hk)
        return cap_state(row) if row else None

    async def finalized_snapshot(self, hk: str):
        return await self.chain.finalized_snapshot(hk)

    async def _row(self, hk: str) -> dict:
        return (
            await self.gateway.info(hk)
            if self.store is None
            else await self.store.key(hk)
        )

    async def current(self, hk: str):
        return await self.snapshot(hk)

    async def snapshot(self, hk: str) -> Optional[DepositState]:
        height, block_hash, row = await self.chain.finalized_snapshot(hk)
        if row is None:
            return None
        if row != (await self.chain.deposit_at(hk, height)):
            raise Pending("unstable finalized read")
        if height > await self.chain.client.finalized_block():
            raise Pending("snapshot no longer finalized")
        return DepositState(height, block_hash, row)

    async def remind(self, hk: str) -> None:
        """Re-evaluate only a known exact-H against the live capped allowance.

        The reminder never discovers identities, replaces receipt evidence, or
        fabricates a delta. Reconcile still must atomically settle a receipt.
        """
        row = await self._row(hk)
        if row is None:
            self.follow.discard(hk)
            return
        cp = row.get("metadata", {}).get("gamma") or {}
        if cp.get("pending") is not None:
            await self.reconcile(
                hk
            )  # Lookup/adjudication only, never new spend.
            return
        if (
            cp.get("last_spent_reference") is None
            and cp.get("due_allowance_units", 0) == 0
        ):
            return
        observed = await self.snapshot(hk)
        if observed is None:
            self.follow.discard(hk)
            return
        if str(observed.stored["spender"]) != self.chain.real_spender:
            self.follow.discard(hk)
            raise Ineligible("reminder lost exact finalized service spender")
        if observed.height - cp["observation_height"] > self.max_backfill:
            self.follow.add(hk)
            raise Pending("cap reminder exceeded bounded-history budget")
        if cap_spendable(observed.stored, observed.height) > 0:
            # Any live positive spending allowance is only a reason to revisit
            # this identity. The ordinary event-and-raw-balance walk must prove
            # a positive raw delta before spending. due_allowance_units is a
            # chained invariant, not a credit floor; the last spend alone does
            # not prove how much raw balance remains after further mints.
            self.follow.add(hk)
            await self.reconcile(hk)

    async def reconcile(self, hk: str) -> PublicResult:
        async with self._lock_guard:
            lock = self._locks.setdefault(hk, asyncio.Lock())
        if lock.locked():
            return pending(hk, "join active exact-H reconciliation")
        if self.lease is not None and not await self.lease.acquire(hk):
            return pending(hk, "stale/nonleader worker")
        async with lock:
            try:
                # Retain per-H fencing while reading the final native row.
                # Releasing between checkpoint and finish created two epochs
                # that could race a second worker's reserve/rotation read.
                await self._reconcile_locked(hk)
                return await self.finish(hk)
            finally:
                if self.lease is not None:
                    await self.lease.release(hk)

    async def _reconcile_locked(self, hk: str):
        row = await self._row(hk)
        if row is None:
            now = await self.snapshot(hk)
            if (
                now is None
                or str(now.stored["spender"]) != self.chain.real_spender
            ):
                raise Pending("no finalized eligible service deposit")
            if pallet_units(now.stored, "balance") > 0:
                self.follow.add(hk)
            raise Pending(
                "no native identity anchored by observed finalized event"
            )
        cp = hydrate(row, row.get("metadata", {}).get("gamma", {}), hk=hk)
        if not cp:
            raise Pending(
                "first live observed event must establish pending identity"
            )
        expected_alias = cp["observation_coldkey"] + "-" + hk.lower()
        if cp["pending"] and row["key_alias"] != expected_alias:
            raise Ineligible(
                "immutable pending alias differs from observed funding coldkey and exact hotkey"
            )
        if cp["pending"]:
            await self.recover(hk, row)
            return
        now = await self.snapshot(hk)
        if (
            cp["observation_height"]
            > await self.chain.client.finalized_block()
        ):
            raise Ineligible("crossed finalized cursor")
        if now is None:
            if cp["delta_units"]:
                raise Pending(
                    "deposit removed outside proven successful burn; pause"
                )
            self.follow.discard(hk)
            return
        if str(now.stored["spender"]) != self.chain.real_spender:
            raise Ineligible("wrong service spender")
        if row["key_alias"] != expected_alias:
            raise Pending(
                "exact-hotkey key_alias must preserve the chain-observed funding coldkey; pause"
            )
        if cp["delta_units"] + cp.get("due_allowance_units", 0) > pallet_units(
            now.stored, "balance"
        ):
            raise Ineligible("claim exceeds finalized deposit balance")
        if now.height == cp["observation_height"] and cp["delta_units"] > 0:
            if self.signer is None:
                self.follow.discard(hk)
                raise Pending("configured signer/preflight paused", 12)
            await self.plan_spend(hk, row, cp, now)
            return
        if now.height == cp["observation_height"]:
            if cp.get("due_allowance_units", 0) == 0:
                self.follow.discard(hk)
                return
        if now.height - cp["observation_height"] > self.max_backfill:
            self.follow.add(hk)
            raise Pending("bounded-history budget; no silent independence")
        if cp.get("delta_units", 0) == 0 and now.stored["balance"] > 0:
            # Reminder starts before any event walk or CAS. A failed checkpoint
            # cannot erase the need to revisit this newly observed deposit.
            self.follow.add(hk)
        cp, now = await self.advance(hk, row, cp, now)
        await self.plan_spend(hk, row, cp, now)

    async def advance(self, hk: str, row: dict, cp: dict, now: DepositState):
        added = 0
        preexisting_remainder = cp.get("due_allowance_units", 0)
        previous = cp["delta_units"] + preexisting_remainder
        events_kind = None
        moved_in = 0
        cap_changed = False
        observed_coldkey = cp["observation_coldkey"]
        for height in range(cp["observation_height"] + 1, now.height + 1):
            block_hash, events = await self.chain.events(height)
            stored_before = await self.chain.deposit_at(hk, height - 1)
            previous_coldkey = observed_coldkey
            positive, spent = 0, 0
            for _idx, name, a in matching_events(events, hk):
                if name == "GammaMinted":
                    if (
                        str(a.get("spender_ss58", a.get("spender")))
                        != self.chain.real_spender
                    ):
                        raise Ineligible("spender differs")
                    positive += pallet_units(a, "gamma")
                elif name == "GammaMoved":
                    if a.get("origin_hotkey") == hk:
                        raise Ineligible(
                            "outward move: audit before new credit"
                        )
                    if a.get("destination_hotkey") == hk:
                        if str(a.get("coldkey")) != observed_coldkey:
                            raise Ineligible(
                                "deposit ownership mutation during move"
                            )
                        positive += pallet_units(a)
                        moved_in += pallet_units(a)
                        if events_kind is None:
                            events_kind = "donor"
                elif name == "GammaSpent":
                    if str(a.get("coldkey")) != observed_coldkey:
                        raise Ineligible("settlement coldkey mutation; pause")
                    if str(a.get("spender")) != self.chain.real_spender:
                        raise Ineligible("foreign service burn")
                    if raw_reference(a.get("reference")) not in {
                        ref["reference"].lower() for ref in cp["receipt_ids"]
                    }:
                        raise Ineligible(
                            "unproven other worker burned; forensic credit required; never auto-resubmit"
                        )
                    spent += pallet_units(a)
                elif name == "GammaDepositSpenderSet":
                    if (
                        str(a.get("spender", a.get("new_spender")))
                        != self.chain.real_spender
                    ):
                        raise Ineligible("authorization revoked")
                elif name == "GammaDepositDailySpendCapSet":
                    cap_changed = True
                    # The pallet's exact cap event confirms Amount but the row
                    # still needs refilling vs previous checkpoint arithmetic.
                    if (
                        now.stored["balance"]
                        and positive + previous
                        and positive + previous > previous
                    ):
                        # Cap amount may comprise old allowance still eligible:
                        # compare since settlement, never simply replace by cap.
                        cap_handled_same_block = True
            stored_after = await self.chain.deposit_at(hk, height)
            if stored_after is None:
                raise Pending(
                    "deposit removed outside proven successful burn; pause"
                )
            after = pallet_units(stored_after, "balance")
            observed_coldkey = str(stored_after["coldkey"])
            if stored_before is not None and previous_coldkey != str(
                stored_before["coldkey"]
            ):
                if observed_coldkey != previous_coldkey:
                    raise Ineligible("unproven deposit coldkey change")
            if previous + positive - spent != after:
                raise Ineligible(
                    "finalized delta unexplained; storage-only moves are not automatic credit"
                )
            if positive and events_kind is None:
                events_kind = "minted_pending"
            previous += positive - spent
            added += positive
        if previous != now.stored["balance"]:
            raise Ineligible("raw chain finality mismatch")
        cap = cap_state(now.stored)
        next_cp = copy.deepcopy(cp)
        delta_units = cp["delta_units"] + added
        due_allowance_units = cp.get("due_allowance_units", 0)
        if cap_changed and cap is None and cp.get("cap") is not None:
            # A capped remainder cannot silently become uncapped credit after cap
            # removal. Preserve only newly chain-proven mint. No-mint removal
            # itself is not a credit and remains safe for later new eligible mints.
            delta_units = added
            due_allowance_units = 0
        next_cp.update(
            {
                # delta_units is a claim against raw storage, not only block-local events.
                # Keep an unspent baseline across zero-delta blocks until its receipt.
                "delta_units": delta_units,
                "due_allowance_units": due_allowance_units,
                "observation_height": now.height,
                "observation_hash": now.block_hash,
                "observation_coldkey": observed_coldkey,
                "observation_spender": str(now.stored["spender"]),
                "cap": cap,
            }
        )
        if events_kind is not None:
            next_cp["accepted_kind"] = events_kind
        next_cp["pending"] = None
        row = await self._conditional(hk, row, cp, next_cp)
        return (
            hydrate(row, row.get("metadata", {}).get("gamma", {}), hk=hk),
            now,
        )

    def _check_cap_claim(
        self, cp: dict, new_mint: int, cap: Optional[dict], now: DepositState
    ):
        balance = pallet_units(now.stored, "balance")
        if new_mint > 0 and cap is None:
            # Existing entire uncapped chain balance was accepted, never partly unclaimed.
            if balance > new_mint + cp["due_allowance_units"]:
                raise Ineligible("untouched eligible remainder unproven")
        elif new_mint == 0 and cap is not None:
            allowance = (
                cap["bucket_units"]
                + cap["cap_units"]
                * max(0, now.height - cap["fed_at_block"])
                // 7200
            )
            if (
                allowance - cp["due_allowance_units"] < 0
                or cap_spendable(now.stored, now.height) - balance != 0
            ):
                if balance > cp["due_allowance_units"]:
                    raise Pending(
                        "cap refill/settlement difference requires manual floor proof"
                    )

    async def _conditional(
        self, hk: str, row: dict, expected: dict, new: dict
    ):
        row["metadata"]["gamma"] = copy.deepcopy(expected)
        if new.get("pending"):
            self.follow.add(hk)
        elif not new.get("delta_units"):
            self.follow.discard(hk)
        if self.store is None:
            return await self.gateway.conditional_transition(
                hk, copy.deepcopy(row), copy.deepcopy(new)
            )
        return await self.store.conditional_transition(
            hk, copy.deepcopy(row), copy.deepcopy(new)
        )

    async def plan_spend(
        self, hk: str, row: dict, cp: dict, now: DepositState
    ):
        authorized = min(
            cp["delta_units"] + cp.get("due_allowance_units", 0),
            cap_spendable(now.stored, now.height),
        )
        if 0 < authorized < 1_000_000_000:
            self.follow.add(hk)
            raise Pending(
                "await sufficient cap refill for the chain's minimum spend", 12
            )
        if authorized <= 0:
            if authorized < 0:
                raise Pending("pending revision with no newly owned amount")
            if pallet_units(now.stored, "balance") > 0:
                self.follow.add(hk)
            else:
                self.follow.discard(hk)
            return
        if authorized > pallet_units(now.stored, "balance"):
            raise Ineligible("authorize more than Chain deposit")
        ref = SettlementRef(
            block_number=now.height,
            block_hash=now.block_hash,
            event_index=-1,
            reference=settlement_reference(90, hk, now.block_hash, authorized),
            hotkey_ss58=hk,
            netuid=90,
            amount_units=authorized,
        )
        ref.validate_identity(hk)
        if ref.reference in {
            r["reference"].lower() for r in cp["receipt_ids"]
        }:
            raise Pending("reference reused")
        expected = copy.deepcopy(cp)
        next_cp = copy.deepcopy(cp)
        next_cp["pending"] = {
            "reference": ref.model_dump(),
            "intake_height": now.height,
            "planning_hash": now.block_hash,
            "attempts": 1,
            "parent_units": now.stored["balance"],
            "expected_checkpoint": expected,
        }
        await self._conditional(hk, row, cp, next_cp)
        row = await self._row(hk)
        cp = hydrate(row, row.get("metadata", {}).get("gamma", {}), hk=hk)
        if cp.get("pending") != next_cp["pending"]:
            raise StateConflict("spend intent was not durably stored")
        self.follow.discard(hk)
        if self.signer is None:
            raise Pending("configured signer/preflight paused", 12)
        from .chain import PendingReceipt

        try:
            await self.chain.execute_spend(
                hk, authorized, ref.reference, self.signer
            )
        except PendingReceipt as exc:
            self.follow.add(hk)
            raise Pending(
                "spend_final_credit_pending; exact-intent lookup (never resubmit)",
                12,
            ) from exc
        except (ConnectionError, asyncio.TimeoutError) as exc:
            self.follow.add(hk)
            raise Pending(
                "spend_final_credit_pending; exact-intent lookup", 12
            ) from exc
        row = await self._row(hk)
        cp = hydrate(row, row.get("metadata", {}).get("gamma", {}), hk=hk)
        await self.recover(hk, row)

    async def recover(self, hk: str, row: dict):
        cp = hydrate(row, row.get("metadata", {}).get("gamma", {}), hk=hk)
        pending = cp.get("pending")
        if pending is None:
            return
        pending_ref = SettlementRef.model_validate(pending["reference"])
        found = await self.chain.find_receipt(
            hk,
            pending_ref.reference,
            pending_ref.amount_units,
            pending["intake_height"],
            cp["observation_coldkey"],
        )
        if found is None:
            if await self.chain.find_skipped(
                hk,
                pending_ref.reference,
                pending_ref.amount_units,
                pending["intake_height"],
            ):
                next_cp = copy.deepcopy(cp)
                next_cp["pending"] = None
                next_cp["delta_units"] = 0
                next_cp["due_allowance_units"] = cp["delta_units"] + cp.get(
                    "due_allowance_units", 0
                )
                next_cp["due_observation_height"] = cp["observation_height"]
                next_cp["due_cap"] = cp.get("cap")
                rejected = await self._conditional(hk, row, cp, next_cp)
                if rejected["metadata"]["gamma"] != next_cp:
                    raise Pending(
                        "skipped intent checkpoint not read back exactly"
                    )
                self.follow.add(hk)
                raise Pending(
                    "chain skipped exact spend; retained mint for gated refill planning",
                    12,
                )
            self.follow.add(hk)
            raise Pending(
                "original spend uncertain; bounded chain search (never resubmit)",
                12,
            )
        if (
            found.coldkey_ss58 is None
            or found.coldkey_ss58 != cp["observation_coldkey"]
        ):
            raise Ineligible(
                "settlement coldkey differs from observed identity; pause"
            )
        ref = SettlementRef(
            block_number=found.block_number,
            event_index=found.event_index,
            block_hash=found.block_hash,
            reference=found.reference,
            hotkey_ss58=hk,
            netuid=found.netuid,
            amount_units=found.amount_units,
        )
        ref.validate_identity(hk)
        if ref.block_number < pending["intake_height"]:
            raise Ineligible("receipt predates fenced pending intent")
        if pending_ref.reference != ref.reference:
            raise Ineligible("chain reference autopsy mismatch")
        before, after = await self.chain.raw_at(
            hk, ref.block_number - 1
        ), await self.chain.raw_at(hk, ref.block_number)
        if before - after != ref.amount_units:
            raise Ineligible("chain storage delta infringed")
        if ref.reference in {
            r["reference"].lower() for r in cp["receipt_ids"]
        }:
            raise Pending("duplicate receipt marker; fail closed")
        target = exact_money(row["max_budget"]) + ref.amount_units
        next_cp = {
            k: copy.deepcopy(v) for k, v in cp.items() if k != "pending"
        }
        next_cp.update(
            {
                "pending": None,
                "due_allowance_units": max(
                    0,
                    cp["delta_units"]
                    + cp.get("due_allowance_units", 0)
                    - ref.amount_units,
                ),
                "due_observation_height": ref.block_number,
                "due_cap": cp.get("cap"),
                "delta_units": 0,
                "receipt_ids": [*cp["receipt_ids"], ref.model_dump()],
                "total_settled_units": int(cp.get("total_settled_units", 0))
                + ref.amount_units,
                "observation_height": ref.block_number,
                "observation_hash": ref.block_hash,
                "last_spent_height": ref.block_number,
                "last_spent_amount": ref.amount_units,
                "last_spent_reference": ref.reference,
                "accepted_kind": "settled",
                "cap": await self.current_cap(hk),
            }
        )
        if self.store is None:
            credited = await self.gateway.credit_and_checkpoint(
                hk, row, ref, target, next_cp
            )
        else:
            credited = await self.store.credit_and_checkpoint(
                hk, cp, ref, target, next_cp
            )
        readback = await self._row(hk)
        if exact_money(readback["max_budget"]) != target:
            raise Pending("not exact atomic funded readback")
        validate_identity(readback, hk, row["token_id"])
        if readback["metadata"]["gamma"] != next_cp:
            raise Pending("chain proof not atomically checkpointed")
        if remaining_units(readback) < 0:
            raise Pending("remaining native credit negative")
        self.follow.discard(hk)

    async def finish(self, hk: str) -> PublicResult:
        row = await self._row(hk)
        cp = row.get("metadata", {}).get("gamma") or {}
        if row["key_alias"] != cp["observation_coldkey"] + "-" + hk.lower():
            raise Pending(
                "exact-hotkey key_alias must preserve the chain-observed funding coldkey; pause",
                12,
            )
        validate_identity(row, hk, row["token_id"])
        if cp.get("pending"):
            return pending(hk, "spend_final_credit_pending", 12)
        available = remaining_units(row)
        return PublicResult(
            status="funded" if available > 0 else "pending",
            reason=(
                None
                if available > 0
                else "await new eligible Gamma or bounded refill"
            ),
            token_id=row["token_id"],
            max_budget=str(amount(row)),
            spend=str(row.get("spend", 0)),
            remaining_credit=str(Decimal(available) / 10**9),
            reconciliation_reference=cp.get("last_spent_reference"),
        )


def pending(hotkey: str, reason: str, wait: int = 6) -> PublicResult:
    return PublicResult(
        status="pending", reason=reason, retry_after_seconds=wait
    )
