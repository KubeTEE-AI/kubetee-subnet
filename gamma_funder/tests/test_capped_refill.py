# Synthetic cap-refill safety only; no deployment readiness claim.
from decimal import Decimal

import pytest

from fixtures import HK, NativeStore, SyntheticChain
from worker.reconciler import Pending, Reconciler
from worker.events import EventStream, ObservationDispatcher
from worker.management import Management
from worker.service import WorkerService
from test_reconciler_init import intake


@pytest.mark.asyncio
async def test_refill_revisits_spend_without_claiming_allowance_as_credit():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(240_000_000_000)
    chain.advance("GammaDepositDailySpendCapSet", cap=120_000_000_000)
    chain.advance()
    await intake(chain, store)
    r = Reconciler(chain, None, store, signer=object())
    await r.reconcile(HK)
    assert len(store.row["metadata"]["gamma"]["receipt_ids"]) == 1
    for _ in range(7200):
        chain.advance()
    await r.reconcile(HK)
    assert store.row["max_budget"] == "240.0"
    assert chain.submitted[-1]["amount"] == 120_000_000_000
    assert len(chain.submitted) == 2
    assert len(store.row["metadata"]["gamma"]["receipt_ids"]) == 2
    for _ in range(7200):
        chain.advance()
    await r.remind(HK)
    assert len(chain.submitted) == 2
    assert len(store.row["metadata"]["gamma"]["receipt_ids"]) == 2
    assert Decimal(store.row["max_budget"]) == 240


@pytest.mark.asyncio
async def test_cap_rejection_recovers_only_exact_prior_spend_without_retry():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(120_000_000_000)
    chain.advance("GammaDepositDailySpendCapSet", cap=120_000_000_000)
    chain.advance()
    await intake(chain, store)
    r = Reconciler(chain, None, store, signer=object(), max_backfill=8000)
    await r.reconcile(HK)
    assert store.row["max_budget"] == "120.0"
    chain.mint(120_000_000_000)
    for _ in range(60):
        chain.advance()
    chain.reject_next_spend = True
    with pytest.raises(Pending, match="exact-intent lookup"):
        await r.reconcile(HK)
    assert store.row["max_budget"] == "120.0"
    pending = store.row["metadata"]["gamma"]["pending"]
    first_reference = store.row["metadata"]["gamma"]["last_spent_reference"]
    attempt = chain.submitted[-1]
    assert attempt["reference"] == pending["reference"]["reference"]
    assert 1_000_000_000 <= attempt["amount"] < 120_000_000_000
    # The fixture's actual finalized execution already emitted GammaSpendSkipped.
    # Its definitive rejection permits no resubmit in the same bounded pass.
    with pytest.raises(Pending, match="retained mint"):
        await r.reconcile(HK)
    assert len(chain.submitted) == 2
    assert chain.submitted[-1] == attempt
    assert (
        store.row["metadata"]["gamma"]["last_spent_reference"]
        == first_reference
    )
    # No GammaSpent receipt => no credit, and refill is allowed to plan a later intent.
    assert store.credits == 1
    for _ in range(7200):
        chain.advance()
    await r.remind(HK)
    assert len(chain.submitted) == 3
    assert chain.submitted[-1]["reference"] != attempt["reference"]
    assert len(store.row["metadata"]["gamma"]["receipt_ids"]) == 2
    assert store.credits == 2


@pytest.mark.asyncio
async def test_cap_pause_raise_and_removal_keep_only_actual_mint_claims():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(240_000_000_000)
    chain.advance("GammaDepositDailySpendCapSet", cap=120_000_000_000)
    chain.advance()
    await intake(chain, store)
    r = Reconciler(chain, None, store, signer=object(), max_backfill=50_000)
    await r.reconcile(HK)
    assert store.row["max_budget"] == "120.0"
    chain.advance("GammaDepositDailySpendCapSet", cap=0)
    await r.reconcile(HK)
    assert store.row["max_budget"] == "120.0"
    assert len(chain.submitted) == 1
    for _ in range(7200):
        chain.advance()
    # Pallet raises out of a zero cap: absence of a cap is full, zero is paused.
    chain.advance("GammaDepositDailySpendCapSet", cap=240_000_000_000)
    await r.reconcile(HK)
    assert store.row["max_budget"] == "240.0"
    chain.mint(1_000_000_000)
    chain.advance("GammaDepositDailySpendCapSet", cap=0)
    for _ in range(60):
        chain.advance()
    await r.reconcile(HK)
    assert store.row["max_budget"] == "240.0"
    chain.advance("GammaDepositDailySpendCapSet", cap=1_000_000_000)
    await r.reconcile(HK)
    assert store.row["max_budget"] == "241.0"
    chain.mint(1_000_000_000)
    chain.advance("GammaDepositDailySpendCapSet", cap=None)
    await r.reconcile(HK)
    assert store.row["max_budget"] == "242.0"
    assert store.credits == 4
    await r.reconcile(HK)
    assert store.credits == 4
    assert len(chain.submitted) == 4


@pytest.mark.asyncio
async def test_synthetic_mint_inventory_and_durable_pending_lease():
    # Cross-check intake dollar exactness; settled accounting only uses budget
    # increment, never synthetic request reserves or a spend floor.
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(12_500_000_000)
    native = Management(store, "https://native.invalid", "synthetic")
    reconciler = Reconciler(chain, native, None, signer=object())
    service = WorkerService(
        chain,
        chain.finalized_snapshot,
        reconciler,
        certificate_fingerprint="a" * 64,
    )
    events = EventStream(ObservationDispatcher(service, reconciler))
    root, rows = await chain.events(chain.current)
    assert await events.dispatch_decoded(chain.current, root, rows) == 1
    assert Decimal(store.row["max_budget"]) == Decimal("12.5")
    assert len(chain.submitted) == 1
