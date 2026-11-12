"""Event-to-settlement coverage with no external RPC or signing capability."""

import asyncio

import pytest

from fixtures import HK, REAL, NativeStore, SyntheticChain
from worker.chain import ChainError
from worker.events import EventStream, ObservationDispatcher, run_monitor
from worker.management import Management, exact_money
from worker.reconciler import Reconciler
from worker.service import WorkerService
from bittensor.client import BlockHeader
from test_runtime import lease_synthetic


class LiveLease:
    async def acquire(self, hotkey):
        await asyncio.sleep(0)
        return True

    async def release(self, hotkey):
        await asyncio.sleep(0)


COLD = "5C8etthaGJi5SkQeEDSaK32ABBjkhwDeK9ksQCTLEGM3EH14"
ALIEN = "5FzVQ8vH4nfFocVvpL4fVZGzSVaPMFFFGNfPCdY6P5puxy"


@pytest.mark.asyncio
async def test_finalized_mint_reserves_settles_adds_exact_credit_and_dedupes():
    chain, native = SyntheticChain(), NativeStore()
    chain.mint(10_000_000_000)
    management = Management(native, "https://native.invalid", "synthetic")
    reconciler = Reconciler(
        chain, management, None, signer=object(), lease=LiveLease()
    )
    service = WorkerService(
        chain,
        chain.finalized_snapshot,
        reconciler,
        certificate_fingerprint="a" * 64,
    )
    dispatcher = ObservationDispatcher(service, reconciler)
    stream = EventStream(dispatcher)
    root, rows = await chain.events(chain.current)
    assert await stream.dispatch_decoded(chain.current, root, rows) == 1
    assert native.row["key_alias"] == COLD
    assert exact_money(native.row["max_budget"]) == 10_000_000_000
    assert native.credits == 1 and len(chain.submitted) == 1
    assert await stream.dispatch_decoded(chain.current, root, rows) == 0
    assert native.credits == 1 and len(chain.submitted) == 1
    assert reconciler.follow == set() and dispatcher.tasks == {}


@pytest.mark.asyncio
async def test_unsponsored_event_never_creates_virtual_key_identity():
    chain, native = SyntheticChain(), NativeStore()
    chain.advance(
        "GammaMinted",
        hotkey=HK,
        coldkey=COLD,
        spender=ALIEN,
        gamma=3_000_000_000,
        daily_spend_cap=None,
    )
    reconciler = Reconciler(
        chain,
        Management(native, "https://native.invalid", "synthetic"),
        None,
        signer=object(),
        lease=await lease_synthetic(None),
    )
    summary = WorkerService(
        chain,
        chain.finalized_snapshot,
        reconciler,
        certificate_fingerprint="a" * 64,
    )
    stream = EventStream(ObservationDispatcher(summary, reconciler))
    root, rows = await chain.events(chain.current)
    assert await stream.dispatch_decoded(chain.current, root, rows) == 0
    assert native.row is None and native.credits == 0


@pytest.mark.asyncio
async def test_move_without_spender_disputes_no_initial_event_credit():
    """A known row can reconcile a move, with zero credit while spend is off."""
    chain, native = SyntheticChain(), NativeStore()
    chain.mint(0)
    reconciler = Reconciler(
        chain,
        Management(native, "https://native.invalid", "synthetic"),
        None,
        signer=None,
        lease=LiveLease(),
    )
    summary = WorkerService(
        chain,
        chain.finalized_snapshot,
        reconciler,
        certificate_fingerprint="a" * 64,
        ready=False,
    )
    stream = EventStream(ObservationDispatcher(summary, reconciler))
    # An on-chain mint authorizes a zero-credit row, not a move with no spender.
    root, rows = await chain.events(chain.current)
    await summary.reconciler.prepare_observation(HK)
    assert await stream.dispatch_decoded(chain.current, root, rows) == 1
    assert exact_money(native.row["max_budget"]) == 0
    # Finalized storage still proves our service spender and no credit change.
    chain.advance(
        "GammaMoved",
        origin_hotkey=REAL,
        destination_hotkey=HK,
        coldkey=COLD,
        amount=0,
    )
    root, rows = await chain.events(chain.current)
    assert "spender" not in rows[0]["event"]["attributes"]
    assert await stream.dispatch_decoded(chain.current, root, rows) == 1
    assert exact_money(native.row["max_budget"]) == 0
    assert chain.submitted == []


@pytest.mark.asyncio
async def test_disabled_spend_reserves_zero_and_allows_claim_later():
    chain, native = SyntheticChain(), NativeStore()
    chain.mint(3_000_000_000)
    reconciler = Reconciler(
        chain,
        Management(native, "https://native.invalid", "synthetic"),
        None,
        signer=None,
        lease=LiveLease(),
    )
    service = WorkerService(
        chain,
        chain.finalized_snapshot,
        reconciler,
        certificate_fingerprint="a" * 64,
    )
    stream = EventStream(ObservationDispatcher(service, reconciler))
    root, rows = await chain.events(chain.current)
    assert await stream.dispatch_decoded(chain.current, root, rows) == 1
    assert exact_money(native.row["max_budget"]) == 0
    assert chain.submitted == []


@pytest.mark.asyncio
async def test_event_failure_is_not_acknowledged_before_gateway_transitional_recovery():
    chain, native = SyntheticChain(), NativeStore()
    chain.mint(2_000_000_000)
    management = Management(native, "https://native.invalid", "synthetic")
    reconciler = Reconciler(
        chain, management, None, signer=object(), lease=LiveLease()
    )
    service = WorkerService(
        chain,
        chain.finalized_snapshot,
        reconciler,
        certificate_fingerprint="a" * 64,
    )
    original = native.reserve
    attempts = 0

    async def temporary(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("transient synthetic management failure")
        return await original(*args)

    native.reserve = temporary
    stream = EventStream(ObservationDispatcher(service, reconciler))
    root, rows = await chain.events(chain.current)
    with pytest.raises(ChainError, match="not acknowledged"):
        await stream.dispatch_decoded(chain.current, root, rows)
    assert attempts == 1 and native.credits == 0
    assert await stream.dispatch_decoded(chain.current, root, rows) == 1
    assert attempts == 2 and native.credits == 1


@pytest.mark.asyncio
async def test_real_subscription_shape_retries_lost_connection_and_gaps():
    class Client:
        def __init__(self):
            self.calls = 0

        async def blocks(self, *, finalized):
            assert finalized
            self.calls += 1
            if self.calls == 1:
                yield BlockHeader(
                    number=10, parent_hash="0x" + "a" * 64, raw={}
                )
                raise ConnectionError("lost subscription")
            yield {"number": 12, "parentHash": "0x" + "b" * 64}
            raise ConnectionError("terminal")

    chain = SyntheticChain()
    chain.client = Client()
    calls = []
    chain.events = lambda height: calls.append(height) or asyncio.sleep(
        0, result=(f"0x{height:064x}", [])
    )
    stream = EventStream(
        ObservationDispatcher(None, Reconciler(chain, None, None))
    )
    stream.next_head = 8
    with pytest.raises(RuntimeError, match="retries"):
        await run_monitor(chain, stream, retries=2)
    assert calls == [8, 9, 10, 11, 12]


@pytest.mark.asyncio
async def test_start_up_cursor_begins_inside_bounded_history():
    chain = SyntheticChain()
    for _ in range(85):
        chain.advance()
    chain.max_backfill = 12
    stream = EventStream(
        ObservationDispatcher(None, Reconciler(chain, None, None))
    )
    from worker.events import replay_history

    await replay_history(chain, stream)
    assert stream.next_head == 86
