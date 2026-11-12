from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

import copy
from decimal import Decimal


import pytest
from worker.reconciler import Ineligible, Pending, Reconciler
from worker.management import exact_money
from fixtures import ALIEN, HK, NativeStore, SyntheticChain
from worker.chain import ChainError


async def intake(chain, store, quality="minted_pending"):
    return await store.observe_fresh_event(
        getattr(chain, "HK", store.hk), chain.finalized(), quality=quality
    )


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
    assert (
        store.row["key_alias"]
        == store.row["metadata"]["gamma"]["observation_coldkey"]
        + "-"
        + store.row["metadata"]["gamma_hotkey"].lower()
    )
    cp = store.row["metadata"]["gamma"]
    assert cp["delta_units"] == 2_000_000_000


@pytest.mark.asyncio
async def test_cross_coldkey_settlement_receipt_never_grants_credit():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(1_000_000_000)
    await intake(chain, store)
    original = chain.execute_spend

    async def foreign_coldkey(hk, amount, reference, signer):
        await original(hk, amount, reference, signer)
        chain.blocks[chain.current]["events"][0]["event"]["attributes"][
            "coldkey"
        ] = ALIEN

    chain.execute_spend = foreign_coldkey
    with pytest.raises(Pending, match="lookup|never resubmit"):
        await worker(chain, store).reconcile(HK)
    with pytest.raises(Pending, match="never resubmit"):
        await worker(chain, store).reconcile(HK)
    assert store.credits == 0 and store.row["max_budget"] == "0"


@pytest.mark.asyncio
async def test_moved_event_is_matched_at_destination_hotkey():
    chain, store = SyntheticChain(), NativeStore()
    chain.advance(
        "GammaMoved",
        coldkey="5C8etthaGJi5SkQeEDSaK32ABBjkhwDeK9ksQCTLEGM3EH14",
        origin_hotkey="5FzVQ8vH4nfFocVvpL4fVZGzSVaPMFFFGNfPCdY6P5puxy",
        destination_hotkey=HK,
        amount=1_000_000_000,
    )
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
    assert (
        store.row["key_alias"]
        == store.row["metadata"]["gamma"]["observation_coldkey"]
        + "-"
        + store.row["metadata"]["gamma_hotkey"].lower()
    )
    assert store.row["metadata"]["gamma_hotkey"] == HK
    with pytest.raises(Pending, match="pause"):
        store.row["key_alias"] = ALIEN
        await Reconciler(chain, None, store, signer=None).reconcile(HK)


@pytest.mark.asyncio
async def test_one_coldkey_funds_two_real_same_length_hotkeys_independently():
    second_hotkey = "5E7G3rNBsLkneUmrDAhYUo1KRu2MrTMXivYX5vbWLcMUn3de"
    assert len(second_hotkey) == len(HK) == 48

    async def funded_identity(hotkey, units):
        chain = SyntheticChain()
        chain.HK = hotkey
        chain.mint(units, hk=hotkey)
        store = NativeStore(hotkey)
        await intake(chain, store)
        await worker(chain, store).reconcile(hotkey)
        return chain, store

    first_chain, first_store = await funded_identity(HK, 1_000_000_000)
    second_chain, second_store = await funded_identity(
        second_hotkey, 2_000_000_000
    )
    for hotkey, units, chain, store in (
        (HK, 1_000_000_000, first_chain, first_store),
        (second_hotkey, 2_000_000_000, second_chain, second_store),
    ):
        expected_alias = (
            store.row["metadata"]["gamma"]["observation_coldkey"]
            + "-"
            + hotkey.lower()
        )
        assert store.row["metadata"]["gamma_hotkey"] == hotkey
        assert store.row["key_alias"] == expected_alias
        assert store.row["max_budget"] == str(units / 1_000_000_000)
        assert len(chain.submitted) == 1
        assert store.credits == 1
        result = await worker(chain, store).reconcile(hotkey)
        assert (
            result.reconciliation_reference
            == store.row["metadata"]["gamma"]["last_spent_reference"]
        )

    # The two synthetic identities share a coldkey but not credentials or credit.
    assert first_store.row["key_alias"] != second_store.row["key_alias"]
    assert second_hotkey not in first_store.row["key_alias"]


@pytest.mark.asyncio
async def test_exact_burn_added_once_and_readback_keeps_grants():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(1_000_000_000)
    await intake(chain, store)
    result = await worker(chain, store).reconcile(HK)
    assert result.status == "funded"
    assert (
        len(chain.submitted) == 1
        and chain.submitted[0]["amount"] == 1_000_000_000
    )
    assert store.credits == 1
    assert exact_money(store.row["max_budget"]) == 1_000_000_000
    assert store.row["models"] == ["selected-model"]
    assert store.row["team_id"] == "native-grant"
    assert store.row["object_permission"]["mcp_servers"] == ["firecrawl"]
    assert store.row["metadata"]["gamma"]["pending"] is None
    assert (
        store.row["metadata"]["gamma"]["total_settled_units"] == 1_000_000_000
    )
    assert store.row["metadata"]["gamma"]["delta_units"] == 0


@pytest.mark.asyncio
async def test_no_spend_recovery_still_uses_exact_receipt_and_never_submits():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(1_000_000_000)
    await intake(chain, store)
    chain.disconnect = True
    with pytest.raises(Pending, match="exact-intent lookup"):
        await worker(chain, store).reconcile(HK)
    chain.spend_enabled = False  # Production chained transport enforces this.
    recovered = Reconciler(chain, None, store, signer=None)
    result = await recovered.reconcile(HK)
    assert result.status == "funded"
    assert len(chain.submitted) == 1 and store.credits == 1
    # Transport-gate is exercised separately; this fixture models receipt lookups only.
    assert recovered.signer is None and chain.spend_enabled is False
    assert len(chain.submitted) == 1


@pytest.mark.asyncio
async def test_below_chain_minimum_never_submits_and_never_fabricates_receipt():
    chain, store = SyntheticChain(), NativeStore()
    chain.mint(5)
    await intake(chain, store)
    r = worker(chain, store)
    with pytest.raises(Pending, match="minimum spend"):
        await r.reconcile(HK)
    assert len(chain.submitted) == 0 and store.credits == 0
    assert store.row["max_budget"] == "0"


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
    with pytest.raises(Pending, match="minimum spend"):
        await worker(chain, store).reconcile(HK)
    assert len(chain.submitted) == 0 and store.credits == 0
    with pytest.raises(Pending, match="minimum spend"):
        await worker(chain, store).reconcile(HK)
    assert len(chain.submitted) == 0 and store.credits == 0
