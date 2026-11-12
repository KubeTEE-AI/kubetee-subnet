"""Finalized Gamma triggers feeding the sole exact-hotkey reconciler.

Nothing here mints keys, supplies amounts, or records an alternative ledger.
An event is an observation; live storage and exact receipts remain authoritative.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .chain import ChainError, event_parts

LOG = logging.getLogger(__name__)
TRIGGERS = {"GammaMinted", "GammaMoved", "GammaDepositSpenderSet"}
RETRYABLE_ERRORS = (ChainError, ConnectionError, TimeoutError, OSError)


def decoded_records(rows: Any):
    if rows is None:
        return []
    if isinstance(rows, dict) and any(
        name in rows for name in ("records", "events")
    ):
        rows = rows.get("records", rows.get("events", []))
    return [row.to_dict() if hasattr(row, "to_dict") else row for row in rows]


def event_header(header: Any) -> int:
    return int(header["number"] if isinstance(header, dict) else header.number)


def relevant_events(reconciler: Any, hotkey: str | None = None):
    """Only current-chain events initiate monitoring; no remote identity trust."""
    chain = reconciler.chain
    return chain, chain.real_spender


class ObservationDispatcher:
    """Bounded exact-H work, with process cleanup on listener shutdown.

    A call joins an already running hotkey rather than double spending it.
    Pending results are explicitly left to the next event/restart/recovery
    reminder and are never acknowledged as settled credit by this dispatcher.
    """

    def __init__(self, service, reconciler):
        self.service = service
        self.reconciler = reconciler
        self.tasks: dict[str, asyncio.Task] = {}
        self.results: dict[str, bool] = {}
        self.max_queue = 512

    async def observation(self, hotkey: str, identifier: str):
        if len(self.tasks) >= self.max_queue:
            LOG.warning(
                "Gamma observation queue saturated; exact-H retry remains pending"
            )
            return False
        previous = self.tasks.get(hotkey)
        if previous is not None:
            return await previous
        return await self._run(hotkey)

    async def _run(self, hotkey: str):
        from .protocol import ProveReconcile

        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Gamma observation requires an event loop")
        self.tasks[hotkey] = task
        try:
            result = await self.service.request(
                ProveReconcile(
                    hotkey_ss58=hotkey,
                    action="status",
                    verified_challenge_digest="0" * 64,
                )
            )
            if result.status in {"funded", "ineligible"}:
                return True
            # Native pending intent, live zero-budget reservation, and chain
            # exact-H state remain durable; this is not a false credit commit.
            self.reconciler.follow.add(hotkey)
            return True
        except Exception:
            LOG.warning(
                "Finalized Gamma observation failed; retry remains due",
                exc_info=True,
            )
            self.reconciler.follow.add(hotkey)
            return False
        finally:
            self.tasks.pop(hotkey, None)

    async def reconcile(self, hotkey: str):
        return await self.observation(hotkey, "manual")

    async def run_reminders(self, *, interval: float = 30.0) -> None:
        """Retry only exact known hotkeys already queued by native events/CAS.

        Pending receipt lookup can credit a proved burn. No account map scan,
        fabricated spend delta, implicit client identity, or speculative signer
        delegation exists. No new spend is required to complete recovery.
        """
        if self.reconciler.signer is None and not self.reconciler.follow:
            return
        while True:
            for hotkey in tuple(self.reconciler.follow):
                try:
                    result = await self.reconciler.reconcile(hotkey)
                    if result.status in {"funded", "ineligible"}:
                        self.reconciler.follow.discard(hotkey)
                except Exception:
                    LOG.warning(
                        "Exact-H pending receipt reminder deferred",
                        exc_info=True,
                    )
            # No general account-map walk. Exact follow entries can reflect a
            # native pending spend or a previously checkpointed capped balance.
            for hotkey in tuple(self.reconciler.follow):
                try:
                    await self.reconciler.remind(hotkey)
                except Exception:
                    LOG.warning(
                        "Exact-H capped allowance reminder deferred",
                        exc_info=True,
                    )
            await asyncio.sleep(interval)

    async def close(self):
        tasks = set(self.tasks.values())
        current = asyncio.current_task()
        tasks.discard(current)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def automatic_status(awaitable):
    try:
        await awaitable
        return True
    except Exception:
        LOG.warning("Finalized Gamma observation failed", exc_info=True)
        return False


class EventStream:
    """Bounded block-hash/event-position deduplication, not a receipt store."""

    def __init__(self, client, *, retain: int = 8192):
        self.client = client
        self.next_head: int | None = None
        self.dispatch = client.observation
        self.dispatcher = client
        self.retain = retain
        self._keys: set[str] = set()
        self._order: list[str] = []

    async def dispatch_decoded(
        self, height: int, block_hash: str, rows: Any, *, startup: bool = False
    ) -> int:
        root = "0x" + block_hash.removeprefix("0x").lower()
        if len(root) != 66 or any(
            c not in "0123456789abcdef" for c in root[2:]
        ):
            raise ChainError("invalid finalized Gamma block hash")
        count = 0
        for position, entry in enumerate(decoded_records(rows)):
            pallet, name, attrs, _ = event_parts(entry)
            if (
                name not in TRIGGERS
                or pallet not in ("SubtensorModule", "Subtensor")
                or not isinstance(attrs, dict)
                or str(attrs.get("netuid")) != "90"
            ):
                continue
            hotkey = (
                attrs.get("destination_hotkey")
                if name == "GammaMoved"
                else attrs.get("hotkey")
            )
            if not isinstance(hotkey, str) or not hotkey:
                continue
            key = root + "-" + str(position)
            if key in self._keys:
                continue
            reconciler = getattr(self.client, "reconciler", None)
            if reconciler is not None:
                # A move has no spender. Storage proof is authoritative;
                # moved-to rows are established by their first mint, never
                # created from an unauthenticated move alone.
                if (
                    name == "GammaMoved"
                    and await reconciler._row(hotkey) is None
                ):
                    continue
                if (
                    name != "GammaMoved"
                    and attrs.get("spender") != reconciler.chain.real_spender
                ):
                    continue
                if (
                    name != "GammaMinted"
                    and await reconciler._row(hotkey) is None
                ):
                    continue
            if not await self.dispatch(hotkey, key):
                raise ChainError(
                    "finalized Gamma observation not acknowledged"
                )
            # Atomically commit dedup only after the authoritative outcome.
            self._keys.add(key)
            self._order.append(key)
            if len(self._order) > self.retain:
                self._keys.remove(self._order.pop(0))
            count += 1
        return count

    async def replay(self, chain: Any, first: int, last: int):
        # Native checkpoint dedup remains authoritative even if this bounded
        # process-local cache is gone. Startup reservations are not new spends.
        for height in range(max(1, first), last + 1):
            root, rows = await asyncio.shield(chain.events(height))
            await asyncio.sleep(0)
            await self.dispatch_decoded(height, root, rows, startup=True)
        self.next_head = last + 1


async def replay_history(chain: Any, events: EventStream):
    head = await chain.client.finalized_block()
    events.next_head = max(1, head - getattr(chain, "max_backfill", 7200) + 1)
    await events.replay(chain, events.next_head, head)


async def run_monitor(
    chain: Any, events: EventStream, *, retries: int | None = None
):
    """Recover transport gaps without silently skipping finalized heights."""
    failures = 0
    while retries is None or failures < retries:
        failures += 1
        try:
            async for header in chain.client.blocks(finalized=True):
                height = event_header(header)
                if events.next_head is None:
                    raise ChainError(
                        "startup replay must complete before subscription"
                    )
                if height < events.next_head:
                    continue
                await events.replay(chain, events.next_head, height)
                failures = 0
        except RETRYABLE_ERRORS:
            LOG.warning(
                "Finalized Gamma subscription interrupted; resuming",
                exc_info=True,
            )
            await asyncio.sleep(1)
    raise RuntimeError(
        "finalized head subscription exceeded configured retries"
    )
