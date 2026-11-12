"""Finalized synthetic event/storage history; never an alternative credit ledger."""

from __future__ import annotations

import copy
import hashlib
from worker.chain import (
    FiscalReceipt,
    PendingReceipt,
    event_parts,
    pallet_units,
)
from worker.management import ManagementError, StateConflict, exact_money
from worker.protocol import GENESIS, SettlementRef
from worker.reconciler import DepositState, base_checkpoint

HK = "5C62Ck4UrFPiBtoCmeSrgF7x9yv9mn38446dhCpsi2mLHiFT"
REAL = "5C7LYpP2ZH3tpKbvVvwiVe54AapxErdPBbvkYhe6y9ZBkqWt"
COLD = "5C8etthaGJi5SkQeEDSaK32ABBjkhwDeK9ksQCTLEGM3EH14"
ALIEN = "5FzVQ8vH4nfFocVvpL4fVZGzSVaPMFFFGNfPCdY6P5puxy"


def event(name, **kw):
    return {
        "event": {
            "module_id": "SubtensorModule",
            "event_id": name,
            "attributes": {"netuid": 90, **kw},
        }
    }


class SyntheticChain:
    def __init__(self):
        self.HK = HK
        self.current = 0
        self.blocks = {0: {"events": [], "row": None}}
        self.real_spender, self.service_url, self.max_backfill = (
            REAL,
            "https://llm.kubetee.ai",
            7200,
        )
        self.submitted = []
        self.disconnect: bool | None = False
        self.client = self

    async def finalized_block(self):
        return self.current

    def advance(self, name=None, **a):
        row = copy.deepcopy(self.blocks[self.current]["row"])
        if name == "GammaMinted" and a.get("hotkey", self.HK) == self.HK:
            row = row or {
                "balance": 0,
                "coldkey": COLD,
                "spender": REAL,
                "daily_spend_cap": None,
                "hotkey": self.HK,
            }
            row.update(
                {
                    "balance": row["balance"] + a["gamma"],
                    "coldkey": a["coldkey"],
                    "spender": a["spender"],
                }
            )
        elif (
            name == "GammaSpent" and a["hotkey"] == self.HK and row is not None
        ):
            row["balance"] -= a["amount"]
            if row["balance"] == 0:
                row = None
        elif name == "GammaMoved":
            if a.get("origin_hotkey") == self.HK:
                row["balance"] -= a["amount"]
            if a.get("destination_hotkey") == self.HK:
                row = row or {
                    "balance": 0,
                    "coldkey": COLD,
                    "spender": REAL,
                    "daily_spend_cap": None,
                    "hotkey": HK,
                }
                row["balance"] += a["amount"]
        elif (
            name == "GammaDepositSpenderSet"
            and a.get("hotkey", self.HK) == self.HK
            and row is not None
        ):
            row["spender"] = a["spender"]
        elif name == "GammaDepositDailySpendCapSet" and row is not None:
            row["daily_spend_cap"] = (
                None
                if a.get("cap") is None
                else {
                    "cap": a["cap"],
                    "bucket": [
                        a.get("bucket", 0),
                        a.get("fed_at", self.current + 1),
                    ],
                }
            )
        elif name == "GammaDepositClosed":
            row = None
        self.current += 1
        self.blocks[self.current] = {
            "events": [] if name is None else [event(name, **a)],
            "row": row,
        }

    def mint(self, value, hk=None, coldkey=COLD, spender=REAL):
        hk = hk or self.HK
        self.advance(
            "GammaMinted",
            hotkey=hk,
            coldkey=coldkey,
            spender=spender,
            gamma=value,
            daily_spend_cap=None,
        )

    def finalized(self):
        n = self.current
        return DepositState(
            n, f"0x{n:064x}", copy.deepcopy(self.blocks[n]["row"])
        )

    async def _hash_for_height(self, n):
        if not 1 <= n <= self.current:
            raise AssertionError("not finalized")
        return f"0x{n:064x}"

    async def finalized_snapshot(self, hk):
        state = self.finalized()
        return state.height, state.block_hash, state.stored

    async def deposit_at(self, hk, n):
        return copy.deepcopy(self.blocks[n]["row"])

    async def deposit(self, hk):
        return await self.deposit_at(hk, self.current)

    async def raw_at(self, hk, n):
        return self.blocks[n]["row"]["balance"] if self.blocks[n]["row"] else 0

    async def events(self, n):
        return await self._hash_for_height(n), copy.deepcopy(
            self.blocks[n]["events"]
        )

    async def execute_spend(self, hk, amount, reference, signer):
        balance = self.blocks[self.current]["row"]["balance"]
        success = 0 < amount <= balance and amount >= 1_000_000_000
        attrs = {
            "hotkey": hk,
            "coldkey": COLD,
            "spender": REAL,
            "amount": amount,
            "reference": list(bytes.fromhex(reference.removeprefix("0x"))),
        }
        if not success:
            skip_errors = {
                "ProtocolCannotSpend": "ProtocolCannotSpend",
                "InvalidAmount": "InvalidAmount",
                "DepositBelowMinimum": "DepositBelowMinimum",
                "SpendAmountAboveDailyAllowance": "SpendAmountAboveDailyAllowance",
            }
            attrs["reason"] = "SpendAmountAboveDailyAllowance"
        self.advance("GammaSpent" if success else "GammaSpendSkipped", **attrs)
        self.submitted.append(
            {
                "amount": amount,
                "hotkey": hk,
                "reference": reference,
                "height": self.current,
            }
        )
        if self.disconnect:
            self.disconnect = False
            raise ConnectionError(
                "response missing after SDK receipt may have emitted"
            )
        if not success:
            raise PendingReceipt("GammaSpendSkipped; no matching receipt")

    async def find_receipt(self, hk, reference, amount, first=1, coldkey=None):
        if self.current - max(first, 1) >= self.max_backfill:
            return None
        for n in range(max(first, 1), self.current + 1):
            for idx, entry in enumerate(self.blocks[n]["events"]):
                p, name, a, extrinsic = event_parts(entry)
                compare = "0x" + bytes(a.get("reference", b"")).hex()
                if (
                    p == "SubtensorModule"
                    and name == "GammaSpent"
                    and a["hotkey"] == hk
                    and a["coldkey"] == coldkey
                    and a["spender"] == REAL
                    and a["amount"] == amount
                    and compare == reference
                ):
                    if (
                        self.blocks[n]["row"]["balance"]
                        if self.blocks[n]["row"]
                        else 0
                    ) + amount != self.blocks[n - 1]["row"]["balance"]:
                        return None
                    return FiscalReceipt(
                        n,
                        idx,
                        f"0x{n:064x}",
                        reference,
                        hk,
                        90,
                        amount,
                        a["coldkey"],
                    )
        return None


class NativeStore:
    """Native exact-H fixture, compare-and-swap keyed checkpoint; no receipt DB."""

    def __init__(self, hk=HK):
        self.hk, self.row, self.last_version = hk, None, 0
        self.credits = 0
        self.fence = 0
        self.interrupt = False
        self.fail_credit_once = False

    async def key(self, hk, copy_ok=False):
        return copy.deepcopy(self.row) if hk == self.hk else None

    async def gamma_identities(self):
        if self.row is None:
            return []
        return [
            {
                "metadata": {
                    "gamma": copy.deepcopy(self.row["metadata"]["gamma"])
                }
            }
        ]

    def serialize_row(self):
        import json
        from datetime import datetime, timezone

        self.last_version += 1
        return {
            "token_id": self.row["token_id"],
            "version": f"2026-11-12T00:00:{self.last_version:02d}+00:00",
            "max_budget": self.row["max_budget"],
            "spend": self.row["spend"],
            "key_alias": self.row["key_alias"],
            "models": self.row["models"],
            "team_id": self.row["team_id"],
            "object_permission": self.row["object_permission"],
            "metadata": json.loads(json.dumps(self.row["metadata"])),
            "blocked": False,
        }

    async def observe_fresh_event(
        self, hk: str, state: DepositState, *, quality: str
    ):
        assert quality in {"minted_pending", "donor", "delegated"}
        if self.row is not None:
            assert (
                self.row["metadata"]["gamma"]["observation_height"]
                == state.height
            )
            return self.row
        self.row = {
            "token_id": hashlib.sha256(b"synthetic-key").hexdigest(),
            "key_alias": state.stored["coldkey"] + "-" + hk.lower(),
            "max_budget": "0",
            "spend": "0",
            "models": ["selected-model"],
            "team_id": "native-grant",
            "object_permission": {"mcp_servers": ["firecrawl"]},
            "metadata": {
                "gamma_network": "finney",
                "gamma_netuid": 90,
                "gamma_hotkey": self.hk,
                "gamma": base_checkpoint(state, quality=quality),
            },
            "version": 1,
        }
        return copy.deepcopy(self.row)

    async def reserve(self, hk, cp):
        assert self.row is None
        self.row = {
            "token_id": hashlib.sha256(b"synthetic-key").hexdigest(),
            "key_alias": cp["observation_coldkey"] + "-" + hk.lower(),
            "max_budget": "0",
            "spend": "0",
            "models": ["selected-model"],
            "team_id": "native-grant",
            "object_permission": {"mcp_servers": ["firecrawl"]},
            "metadata": {
                "gamma_network": "finney",
                "gamma_netuid": 90,
                "gamma_hotkey": hk,
                "gamma": cp,
            },
            "version": 1,
        }
        return copy.deepcopy(self.row)

    async def conditional_transition(self, hk, row, next_cp):
        assert hk == self.hk
        observed = copy.deepcopy(row["metadata"]["gamma"])
        if self.row["metadata"]["gamma"] != observed:
            raise StateConflict("expected checkpoint differs")
        if (
            next_cp.get("pending")
            and self.row["metadata"]["gamma"]
            != next_cp["pending"]["expected_checkpoint"]
        ):
            raise StateConflict("pending checkpoint unfenced")
        if self.row.get("spend") != row.get("spend") or self.row.get(
            "max_budget"
        ) != row.get("max_budget"):
            raise StateConflict("native usage changed; retry at actual spend")
        if self.interrupt:
            self.interrupt = False
            raise ManagementError("transport interrupted before CAS")
        self.row["metadata"]["gamma"] = copy.deepcopy(next_cp)
        self.row["version"] += 1
        result = copy.deepcopy(self.row)
        row.clear()
        row.update(copy.deepcopy(self.row))
        return result

    async def credit_and_checkpoint(
        self, hk, expected_checkpoint, ref, target_units, cp
    ):
        assert hk == self.hk and ref.hotkey_ss58 == self.hk
        if self.row["metadata"]["gamma"] != expected_checkpoint:
            raise StateConflict("receipt without exact protected intent")
        if self.row.get("spend", "0") != self.row.get("spend", "0"):
            pass
        if self.row["metadata"]["gamma"] == cp:
            return copy.deepcopy(self.row)
        if self.fail_credit_once:
            self.fail_credit_once = False
            raise ManagementError(
                "response interruption before conditional transaction commit"
            )
        planned = self.row["metadata"]["gamma"]["pending"]["reference"]
        assert {
            key: planned[key]
            for key in ("hotkey_ss58", "netuid", "amount_units", "reference")
        } == {
            key: ref.model_dump()[key]
            for key in ("hotkey_ss58", "netuid", "amount_units", "reference")
        }
        assert (
            exact_money(self.row["max_budget"]) + ref.amount_units
            == target_units
        )
        self.row["max_budget"] = str(target_units / 10**9)
        self.row["metadata"]["gamma"] = copy.deepcopy(cp)
        self.row["version"] += 1
        self.credits += 1
        return copy.deepcopy(self.row)

    async def request(self, method, url, **kwargs):
        # Mirror a real Scoped httpx transport's query encoding.
        from urllib.parse import urlencode

        query = kwargs.pop("params", None)
        if query:
            url += ("&" if "?" in url else "?") + urlencode(query)
        return await self.management_request(method, url, **kwargs)

    async def management_request(self, method, url, **kwargs):
        from types import SimpleNamespace
        from urllib.parse import urlparse, parse_qs
        from worker.protocol import GENESIS

        params = kwargs.get("json")
        if params is None:
            # FastAPI supplies named scalar query parameters, not parse_qs lists.
            params = {
                name: values[0]
                for name, values in parse_qs(urlparse(url).query).items()
            }
        if (
            params.get("network") != "finney"
            or params.get("genesis_hash") != GENESIS
        ):
            raise ManagementError("wrong network")
        hotkey = (
            kwargs.get("json", {}).get("hotkey_ss58")
            if kwargs.get("json")
            else parse_qs(urlparse(url).query)["hotkey_ss58"][0]
        )
        path = urlparse(url).path
        if method == "GET" and path == "/internal/v1/gamma/key":
            row = await self.key(hotkey)
            return {
                "exists": row is not None,
                "row": None if row is None else self.serialize_row(),
            }
        if method == "POST":
            previous = params.get("previous_max_budget")
            native = await self.key(hotkey)
            if (
                native is not None
                and previous is not None
                and native["max_budget"] != previous
            ):
                return {"status_code": 409, "text": "stale row"}
            if path == "/internal/v1/gamma/key/reservation":
                await self.reserve(hotkey, params["checkpoint"])
            elif path == "/internal/v1/gamma/checkpoint":
                await self.conditional_transition(
                    hotkey, native, params["checkpoint"]
                )
            elif path == "/internal/v1/gamma/credit":
                await self.credit_and_checkpoint(
                    hotkey,
                    params["previous_checkpoint"],
                    SettlementRef.model_validate(
                        {
                            key: value
                            for key, value in params["settlement"].items()
                            if key != "observation_hash"
                        }
                    ),
                    exact_money(params["target_max_budget"]),
                    params["expected_checkpoint"],
                )
            return {"row": self.serialize_row()}
        raise AssertionError(f"unsupported management request {method} {url}")

    async def create_duplicate_row(self):
        raise AssertionError("only exact-H unique native identity")
