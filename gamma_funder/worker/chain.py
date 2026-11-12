"""Finalized Bittensor 11.3.2 queries; no public wallet or free-form extrinsic."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import bittensor as bt

from .protocol import GENESIS, units_to_gamma


class ChainError(RuntimeError): pass
class PendingReceipt(ChainError): pass


@dataclass(frozen=True)
class FiscalReceipt:
    block_number: int
    event_index: int
    block_hash: str
    reference: str
    hotkey_ss58: str
    netuid: int
    amount_units: int
    coldkey_ss58: Optional[str] = None


def event_parts(entry: Any):
    record = entry.value if hasattr(entry, "value") else entry
    if not isinstance(record, dict): return None, None, None, None
    event = record.get("event", record)
    if not isinstance(event, dict): return None, None, None, None
    return (event.get("module_id", event.get("pallet")),
            event.get("event_id", event.get("name")),
            event.get("attributes", event.get("data")),
            record.get("extrinsic_idx"))


def pallet_units(attrs: dict, field: str = "amount") -> int:
    value = attrs.get(field)
    if type(value) is not int or not 0 <= value <= 2**64 - 1:
        raise ChainError("foreign Gamma event amount/currency; refusing to infer float money")
    return value


def raw_reference(value) -> Optional[str]:
    if isinstance(value, str) and len(value.removeprefix("0x")) == 64:
        return "0x" + value.removeprefix("0x").lower()
    try: value = bytes(value)
    except (TypeError, ValueError): return None
    return "0x" + value.hex() if len(value) == 32 else None


def matching_events(events: list, hotkey: str, netuid: int = 90):
    for index, entry in enumerate(events):
        pallet, name, attrs, extrinsic_idx = event_parts(entry)
        if pallet != "SubtensorModule" or not isinstance(attrs, dict): continue
        moved_to_hotkey = name == "GammaMoved" and attrs.get("destination_hotkey") == hotkey
        if (attrs.get("hotkey") == hotkey or moved_to_hotkey) and str(attrs.get("netuid")) == str(netuid):
            yield index if extrinsic_idx is None else extrinsic_idx, name, attrs


class GammaChain:
    def __init__(self, client, *, real_spender: str, delegate: str | None,
                 service_url="https://llm.kubetee.ai", max_backfill=7200,
                 max_fee=None, genesis_hash=GENESIS):
        if not real_spender: raise ValueError("real spender required")
        self.client, self.real_spender = client, real_spender
        self.delegate = delegate if delegate is not None else real_spender
        self.service_url, self.max_backfill, self.max_fee = service_url, max_backfill, max_fee
        self.genesis_hash = genesis_hash.lower()
        self.follow: set[str] = set()

    async def _hash_for_height(self, h: int) -> str:
        if not 1 <= h <= await self.client.finalized_block(): raise PendingReceipt("not finalized")
        value = await self.client._substrate.block_hash(h)
        if not isinstance(value, str) or len(value.removeprefix("0x")) != 64: raise PendingReceipt("no block hash")
        return value.lower()

    async def _snapshot(self, h=None):
        final, h = await self.client.finalized_block(), h
        h = final if h is None else h
        if not 1 <= h <= final: raise PendingReceipt("unfinalized snapshot")
        return await self.client.at(h), h

    async def genesis(self): return str(await self.client._substrate.block_hash(0)).lower()

    async def preflight(self):
        if await self.genesis() != self.genesis_hash: raise ChainError("non-Finney chain")
        snap, _ = await self._snapshot()
        enabled, enabled90, services, oracle = await asyncio.gather(
            snap.query(bt.storage.SubtensorModule.GammaEnabled),
            snap.query(bt.storage.SubtensorModule.SubnetGammaEnabled, [90]),
            snap.query_map(bt.storage.SubtensorModule.Services, [90]),
            snap.read("tao_usd_price"),
        )
        project = None
        proxies = []
        if self.delegate != self.real_spender:
            project, proxies = await asyncio.gather(
                snap.query(bt.storage.System.Account, [self.delegate]),
                snap.query(bt.storage.Proxy.Proxies, [self.real_spender]),
            )
        if not enabled or not enabled90: raise ChainError("Gamma/SN90 not enabled")
        if not any(svc.get("url") == self.service_url and str(svc.get("spender")) == self.real_spender for _hk, svc in services):
            raise ChainError("service registration spender mismatch")
        if not isinstance(oracle, dict) or not oracle.get("oracle") or oracle.get("blocks_since_last_feed") is None or oracle["blocks_since_last_feed"]>300:
            raise ChainError("absent/stale Finney oracle")
        if self.delegate != self.real_spender:
            if int((project or {}).get("data", {}).get("free", 0)) <= 0: raise ChainError("proxy delegate fee balance is zero")
            rows = (proxies or [])[0] if isinstance(proxies, (list, tuple)) and len(proxies) == 2 else proxies
            if not any(str(p.get("delegate")) == self.delegate and str(p.get("proxy_type")) == "GammaSpend" and int(p.get("delay", -1)) == 0 for p in rows or []):
                raise ChainError("GammaSpend proxy not valid")

    async def finalized_snapshot(self, hotkey: str):
        height = await self.client.finalized_block()
        snap, height = await self._snapshot(height)
        row = await snap.query(bt.storage.SubtensorModule.GammaDeposits, [90, hotkey])
        block_hash = await self._hash_for_height(height)
        if height > await self.client.finalized_block(): raise PendingReceipt("snapshot no longer finalized")
        return height, block_hash, row

    async def deposit_at(self, hotkey: str, height: int) -> Optional[dict]:
        snap, _ = await self._snapshot(height)
        return await snap.query(bt.storage.SubtensorModule.GammaDeposits, [90, hotkey])

    async def raw_at(self, hotkey: str, h: int) -> int:
        row = await self.deposit_at(hotkey, h)
        return 0 if row is None else pallet_units(row, "balance")

    async def events(self, height: int):
        block_hash = await self._hash_for_height(height)
        result = await self.client._substrate.events(block_hash)
        if block_hash != await self._hash_for_height(height): raise PendingReceipt("read not stable")
        return block_hash, result

    async def find_receipt(self, hotkey: str, reference: str, amount_units: int, first=1,
                           coldkey: Optional[str] = None) -> Optional[FiscalReceipt]:
        final, first = await self.client.finalized_block(), max(1, first)
        if final - first >= self.max_backfill: return None
        for height in range(first, final + 1):
            block_hash, events = await self.events(height)
            for index, name, a in matching_events(events, hotkey):
                observed_coldkey = a.get("coldkey")
                if (name == "GammaSpent" and str(a.get("spender")) == self.real_spender and raw_reference(a.get("reference")) == reference.lower() and pallet_units(a) == amount_units
                    and observed_coldkey is not None and (coldkey is None or observed_coldkey == coldkey)
                    and await self.raw_at(hotkey, height - 1) - await self.raw_at(hotkey, height) == amount_units):
                    return FiscalReceipt(height, index, block_hash, reference.lower(), hotkey, 90, amount_units, observed_coldkey)
        return None

    async def execute_spend(self, hotkey: str, units: int, reference: str, signer):
        if not raw_reference(reference) == reference or type(signer) is type(None): raise ChainError("incomplete exact spend intent")
        policy = bt.intents.plan.Policy(allowed_netuids=[90], max_fee_tao="0" if self.max_fee is None else str(self.max_fee), max_spend_tao="0", allow_raw_calls=False)
        if Decimal(policy.max_fee_tao.tao) <= 0: raise ChainError("explicit positive service fee cap required")
        intent = bt.SpendGamma(netuid=90, spends=[{"hotkey_ss58": hotkey, "amount_gamma": units_to_gamma(units), "reference": reference}])
        delegation = {"proxy_for": self.real_spender, "proxy_type": "GammaSpend"} if self.delegate != self.real_spender else {}
        preview = await self.client.plan(intent, signer, policy=policy, **delegation, shielded=False)
        assert preview.args == {'netuid': 90, 'spends': [{'hotkey_ss58': hotkey, 'amount_gamma': units_to_gamma(units), 'reference': reference}]}
        assert not preview.violations and preview.fee is not None
        result = await self.client.execute(
            intent, signer, **delegation, shielded=False,
            wait_for_inclusion=True, wait_for_finalization=True, policy=policy, retries=0,
        )
        if not result.success or not result.block_hash or not result.extrinsic_id: raise PendingReceipt("no known standardized receipt")
        height = int(str(result.extrinsic_id).split("-", 1)[0])
        if await self._hash_for_height(height) != result.block_hash.lower(): raise PendingReceipt("wrong finality")
        _hash, events = await self.events(height)
        found = [(index, name, attrs) for index, name, attrs in matching_events(events, hotkey) if raw_reference(attrs.get("reference")) == reference.lower()]
        if len(found) != 1 or found[0][1] != "GammaSpent" or pallet_units(found[0][2]) != units:
            raise PendingReceipt("settlement not exact or was capped; no automatic resubmit")
