from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))

import copy
from decimal import Decimal


import pytest
from worker.reconciler import Ineligible, Pending, Reconciler
from worker.management import exact_money
from fixtures import ALIEN, HK, NativeStore, SyntheticChain


async def intake(chain, store, quality="minted_pending"):
    return await store.observe_fresh_event(HK, chain.finalized(), quality=quality)


def worker(chain, store, **kw):
    return Reconciler(chain, None, store, signer=object(), **kw)


@pytest.mark.asyncio
async def test_paused_observation_never_credits_or_spends():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(2_000_000_000)
    await intake(chain, store)
    r = Reconciler(chain, None, store, signer=None)
    with pytest.raises(Pending, match="paused"):
        await r.reconcile(HK)
    assert chain.submitted == [] and store.row["max_budget"] == "0"
    assert store.row["key_alias"] == store.row["metadata"]["gamma"]["observation_coldkey"]
    cp = store.row["metadata"]["gamma"]
    assert cp["delta_units"] == 2_000_000_000


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_cross_coldkey_settlement_receipt_never_grants_credit():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(1_000_000_000)
    await intake(chain, store)
    original = chain.execute_spend

    async def foreign_coldkey(hk, amount, reference, signer):
        await original(hk, amount, reference, signer)
        chain.blocks[chain.current]["events"][0]["event"]["attributes"]["coldkey"] = ALIEN

    chain.execute_spend = foreign_coldkey
    with pytest.raises(Pending, match="lookup|never resubmit"):
        await worker(chain, store).reconcile(HK)
    with pytest.raises(Pending, match="never resubmit"):
        await worker(chain, store).reconcile(HK)
    assert store.credits == 0 and store.row["max_budget"] == "0"


@pytest.mark.asyncio
async def test_moved_event_is_matched_at_destination_hotkey():
    chain, store = SyntheticChain(), NativeStore()
    chain.advance("GammaMoved", coldkey="5C8etthaGJi5SkQeEDSaK32ABBjkhwDeK9ksQCTLEGM3EH14",
                  origin_hotkey="5FzVQ8vH4nfFocVvpL4fVZGzSVaPMFFFGNfPCdY6P5puxy",
                  destination_hotkey=HK, amount=1_000_000_000)
    await intake(chain, store, quality="donor")
    chain.advance()
    await worker(chain, store).reconcile(HK)
    assert store.row["max_budget"] == "1.0"
    assert store.credits == 1


@pytest.mark.asyncio
async def test_coldkey_is_fast_alias_but_hotkey_is_identity():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(1_000_000_000)
    await intake(chain, store)
    result = await worker(chain, store).reconcile(HK)
    assert result.status == "funded"
    assert store.row["key_alias"] == store.row["metadata"]["gamma"]["observation_coldkey"]
    assert store.row["metadata"]["gamma_hotkey"] == HK
    with pytest.raises(Pending, match="migrates"):
        store.row["key_alias"] = ALIEN
        await Reconciler(chain, None, store, signer=None).reconcile(HK)


@pytest.mark.asyncio
async def test_exact_burn_added_once_and_readback_keeps_grants():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(1_000_000_000)
    await intake(chain, store)
    result = await worker(chain, store).reconcile(HK)
    assert result.status == "funded"
    assert len(chain.submitted) == 1 and chain.submitted[0]["amount"] == 1_000_000_000
    assert store.credits == 1
    assert exact_money(store.row["max_budget"]) == 1_000_000_000
    assert store.row["models"] == ["selected-model"]
    assert store.row["team_id"] == "native-grant"
    assert store.row["object_permission"]["mcp_servers"] == ["firecrawl"]
    assert store.row["metadata"]["gamma"]["pending"] is None
    assert store.row["metadata"]["gamma"]["total_settled_units"] == 1_000_000_000
    assert store.row["metadata"]["gamma"]["delta_units"] == 0


@pytest.mark.asyncio
async def test_crash_after_final_spend_recovery_does_not_resubmit_or_double_credit():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(1_000_000_000)
    await intake(chain, store)
    chain.disconnect = True
    with pytest.raises(Pending, match="exact-intent lookup"):
        await worker(chain, store).reconcile(HK)
    assert len(chain.submitted) == 1 and store.credits == 0
    assert store.row["metadata"]["gamma"]["pending"]
    # Same process applies, then independent fresh worker observes exact receipt.
    first = await worker(chain, store).reconcile(HK)
    second = await worker(chain, store).reconcile(HK)
    assert first.status == second.status == "funded"
    assert len(chain.submitted) == 1 and store.credits == 1
    assert store.row["max_budget"] == "1.0"
    assert exact_money(store.row["max_budget"]) == 1_000_000_000


@pytest.mark.asyncio
async def test_pre_spend_checkpoint_transport_failure_credits_once_with_bounded_reminder():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(3_000_000_000)
    chain.advance()
    await intake(chain, store)
    r = worker(chain, store)
    store.interrupt = True
    with pytest.raises(Exception, match="interrupted before CAS"):
        await r.reconcile(HK)
    assert chain.submitted == [] and store.credits == 0
    assert HK in r.follow  # Reaper retries the bounded exact-H reconciliation.
    await r.reconcile(HK)
    assert store.credits == 1 and len(chain.submitted) == 1
    await r.reconcile(HK)
    assert store.credits == 1 and len(chain.submitted) == 1


@pytest.mark.asyncio
async def test_cap_reminder_recovers_checkpoint_failure_before_execution():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(1_000_000_000)
    await intake(chain, store)
    r = worker(chain, store)
    await r.reconcile(HK)
    chain.mint(1_000_000_000)
    store.interrupt = True
    with pytest.raises(Exception, match="interrupted before CAS"):
        await r.reconcile(HK)
    assert len(chain.submitted) == 1 and HK in r.follow
    await r.reconcile(HK)
    assert store.row["max_budget"] == "2.0"
    assert exact_money(store.row["max_budget"]) == 2_000_000_000
    assert len(chain.submitted) == 2


@pytest.mark.asyncio
async def test_spend_skipped_means_zero_credit_and_never_same_claim_again():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(5)
    await intake(chain, store)
    with pytest.raises(Pending, match="exact-intent lookup"):
        await worker(chain, store).reconcile(HK)
    assert len(chain.submitted) == 1 and store.credits == 0
    with pytest.raises(Pending, match="never resubmit"):
        await worker(chain, store).reconcile(HK)
    assert len(chain.submitted) == 1 and store.credits == 0
