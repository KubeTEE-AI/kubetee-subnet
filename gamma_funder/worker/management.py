"""Native LiteLLM management adapter; no worker database, no SQL budget update."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .protocol import GENESIS, CreditRequest


class ManagementError(RuntimeError):
    pass


class StateConflict(ManagementError):
    pass


@dataclass(frozen=True)
class CreditMarker:
    settlement: CreditRequest
    accepted: bool


def exact_money(value: Any) -> int:
    if isinstance(value, bool):
        raise ManagementError("invalid flag")
    try:
        result = Decimal(str(value)) * 10**9
        if result < 0 or result != int(result):
            raise ArithmeticError()
        return int(result)
    except (ArithmeticError, InvalidOperation, ValueError, TypeError) as exc:
        raise ManagementError(
            "native money is not exact Gamma base units"
        ) from exc


def amount(row: dict, field: str = "max_budget") -> Decimal:
    """Decimal string for display only; internal amounts remain integers."""
    if field == "max_budget":
        return Decimal(exact_money(row.get("max_budget", "0"))) / 10**9
    return Decimal(str(row.get("spend", "0")))


def remaining(row) -> Decimal:
    return max(Decimal(0), remaining_units(row) / Decimal(10**9))


def remaining_units(row) -> int:
    return max(
        0,
        exact_money(row.get("max_budget", "0"))
        - exact_money(row.get("spend", "0")),
    )


def validate_identity(row: dict, hotkey: str, token_id: str) -> None:
    if not isinstance(row, dict):
        raise ManagementError("native key row required")
    if row.get("token_id", token_id) != token_id:
        raise ManagementError("wrong token ID")
    md = row.get("metadata")
    if not isinstance(md, dict) or md.get("gamma_hotkey") != hotkey:
        raise ManagementError("key is not exact-H Gamma identity")
    if (
        md.get("gamma_netuid", 90) != 90
        or md.get("gamma_network", "finney") != "finney"
    ):
        raise ManagementError("non-SN90 Gamma identity")
    coldkey = (md.get("gamma") or {}).get("observation_coldkey")
    if not isinstance(coldkey, str) or not coldkey:
        raise ManagementError("chain-verified Gamma funding coldkey absent")
    if row.get("key_alias") != coldkey + "-" + hotkey.lower():
        raise ManagementError(
            "key_alias must match observed GammaDeposits.coldkey and exact hotkey"
        )
    # Never erase/access-widen these existing native grants during credit calls.
    for field in (
        "models",
        "team_id",
        "object_permission",
        "expiry_duration",
        "allowed_models",
    ):
        if field in row:
            copy.deepcopy(row[field])
    for field in ("max_budget", "spend"):
        exact_money(row.get(field, "0"))


class Management:
    def __init__(
        self,
        transport,
        base_url,
        credential: str,
        models: Optional[list[str]] = None,
        mcp_servers: Optional[list[str]] = None,
    ):
        if not credential:
            raise ValueError("private narrow management credential required")
        self.transport, self.base = transport, base_url.rstrip("/")
        # Measured mTLS authenticates the socket, never a static bearer token.
        # Synthetic tests retain their explicitly-requested headers.
        self.mtLS = credential == "mTLS:gamma-reconciler-type22"
        self.headers = (
            {} if self.mtLS else {"Authorization": f"Bearer {credential}"}
        )
        self.models, self.mcp_servers = models, mcp_servers
        if (
            self.mtLS
            and self.base
            != "https://litellm-gateway-mtls.litellm.svc.cluster.local:8443"
        ):
            raise ValueError("mTLS management transport cannot be rebound")

    async def ready(self) -> bool:
        response = await self.transport.get(self.base + "/internal/v1/ready")
        return response.status_code == 200 and response.json() == {
            "ready": True
        }

    async def call(self, method: str, path: str, **kwargs) -> dict:
        if self.mtLS:
            # Never accept an arbitrary caller-supplied identity header.
            headers = self.transport.headers
            kwargs.pop("headers", None)
        else:
            headers = {**self.headers, **kwargs.pop("headers", {})}
        response = await self.transport.request(
            method, self.base + path, headers=headers, **kwargs
        )
        if isinstance(response, dict):
            if response.get("status_code", 200) not in (200, 201, 202):
                raise ManagementError("native management rejected")
            return response.get("json", response)
        if response.status_code not in (200, 201, 202):
            if response.status_code == 409:
                raise StateConflict(response.text[:1000])
            raise ManagementError(
                f"management HTTP {response.status_code}: {response.text[:1000]}"
            )
        return response.json()

    async def hotkeys(self) -> list[str]:
        """Existing native Gamma rows only; never infer money or wallet ownership."""
        data = await self.call("GET", "/internal/v1/gamma/keys")
        keys = data.get("keys")
        if not isinstance(keys, list):
            raise ManagementError(
                "native aggregate key-info missing keys list"
            )
        hotkeys = []
        for row in keys:
            if not isinstance(row, dict) or not isinstance(
                row.get("metadata"), dict
            ):
                continue
            cp = row["metadata"].get("gamma")
            if isinstance(cp, dict) and cp.get("schema") == 1:
                hotkey = cp.get("hotkey_ss58")
                if isinstance(hotkey, str) and hotkey:
                    from .protocol import ss58_address

                    ss58_address(hotkey)
                    hotkeys.append(hotkey)
        if len(set(hotkeys)) != len(hotkeys):
            raise ManagementError(
                "duplicate native Gamma identity in aggregate listing"
            )
        return hotkeys

    def response_row(
        self,
        data: dict,
        hotkey: str,
        previous: Optional[dict] = None,
        checkpoint: Optional[dict] = None,
    ) -> dict:
        if not isinstance(data.get("row"), dict):
            raise ManagementError("native row response missing")
        result = data["row"]
        if not re.fullmatch(r"[0-9a-f]{64}", result.get("token_id", "")):
            raise ManagementError("invalid native hashed-token identity")
        if previous is not None and result["token_id"] != previous["token_id"]:
            raise ManagementError(
                "native row identity changed between credit phases"
            )
        validate_identity(result, hotkey, result["token_id"])
        if (
            checkpoint is not None
            and result["metadata"].get("gamma") != checkpoint
        ):
            raise ManagementError("native checkpoint readback differs")
        return result

    async def reserve(
        self,
        hotkey: str,
        checkpoint: dict,
        target_permissions: Optional[dict] = None,
    ) -> dict:
        if not isinstance(checkpoint.get("observation_coldkey"), str):
            raise ManagementError(
                "chain-verified funding coldkey required for key_alias"
            )
        data = await self.call(
            "POST",
            "/internal/v1/gamma/key/reservation",
            json={
                "network": "finney",
                "genesis_hash": GENESIS,
                "netuid": 90,
                "hotkey_ss58": hotkey,
                "checkpoint": checkpoint,
                # Alias from verified GammaDeposits.coldkey, never from claimant.
                "key_alias": checkpoint["observation_coldkey"]
                + "-"
                + hotkey.lower(),
                "target_permissions": target_permissions
                or (
                    None
                    if self.models is None and self.mcp_servers is None
                    else {
                        "models": self.models,
                        "mcp_servers": self.mcp_servers,
                    }
                ),
            },
        )
        return self.response_row(data, hotkey)

    async def info(self, hotkey: str) -> Optional[dict]:
        data = await self.call(
            "GET",
            "/internal/v1/gamma/key",
            params={
                "network": "finney",
                "genesis_hash": GENESIS,
                "netuid": 90,
                "hotkey_ss58": hotkey,
            },
        )
        if data.get("exists") is True and data.get("row") is None:
            raise ManagementError("native key row missing")
        if data.get("exists") is False or data.get("row") is None:
            return None
        return self.response_row(data, hotkey)

    async def conditional_transition(
        self, hotkey: str, row: dict, checkpoint: dict
    ) -> dict:
        data = await self.call(
            "POST",
            "/internal/v1/gamma/checkpoint",
            json={
                "network": "finney",
                "genesis_hash": GENESIS,
                "netuid": 90,
                "hotkey_ss58": hotkey,
                "token_id": row["token_id"],
                "row_version": row.get("version"),
                "expected_checkpoint": (row.get("metadata") or {}).get(
                    "gamma"
                ),
                "checkpoint": checkpoint,
                "previous_max_budget": row.get("max_budget"),
                "previous_spend": row.get("spend"),
            },
        )
        if data.get("conflict"):
            raise StateConflict(
                data.get("reason", "native row version changed")
            )
        if exact_money(
            self.response_row(data, hotkey, row, checkpoint)["max_budget"]
        ) != exact_money(row["max_budget"]):
            raise ManagementError("non-credit changed money")
        return self.response_row(data, hotkey, row, checkpoint)

    async def issue(
        self, hotkey: str, action: str, verification_digest: str
    ) -> dict:
        if action not in ("claim", "regenerate"):
            raise ManagementError("unsupported native key action")
        if not re.fullmatch(r"[0-9a-f]{64}", verification_digest):
            raise ManagementError("invalid signed-challenge digest")
        data = await self.call(
            "POST",
            "/internal/v1/gamma/key/issue",
            json={
                "network": "finney",
                "genesis_hash": GENESIS,
                "netuid": 90,
                "hotkey_ss58": hotkey,
                "action": action,
                "verification_digest": verification_digest,
            },
        )
        if data.get("status") == "pending":
            raise StateConflict(
                data.get("error", "native key activation pending")
            )
        if data.get("status") != "provisioned":
            raise ManagementError("native key activation not definitive")
        if not isinstance(data.get("api_key"), str) or not data[
            "api_key"
        ].startswith("sk-"):
            raise ManagementError(
                "native key secret absent from protected response"
            )
        current = await self.info(hotkey)
        if current is None:
            raise ManagementError("native identity absent after key issuance")
        for field in ("max_budget", "spend"):
            if exact_money(data.get(field)) != exact_money(current.get(field)):
                raise ManagementError("native issuance money readback failed")
        checkpoint = current["metadata"].get("gamma") or {}
        if data.get("reconciliation_reference") != checkpoint.get(
            "last_spent_reference"
        ):
            raise ManagementError("native issuance settlement readback failed")
        return {
            **data,
            "token_id": current["token_id"],
            "version": current.get("version"),
            "metadata": current["metadata"],
        }

    async def credit_and_checkpoint(
        self,
        hotkey: str,
        row: dict,
        settlement,
        target_units: int,
        checkpoint: dict,
    ) -> dict:
        pending = ((row.get("metadata") or {}).get("gamma") or {}).get(
            "pending"
        ) or {}
        observation_hash = pending.get("planning_hash")
        if not re.fullmatch(r"0x[0-9a-f]{64}", observation_hash or ""):
            raise StateConflict(
                "settlement intent has no protected observation hash"
            )
        data = await self.call(
            "POST",
            "/internal/v1/gamma/credit",
            json={
                "network": "finney",
                "genesis_hash": GENESIS,
                "netuid": 90,
                "hotkey_ss58": hotkey,
                "token_id": row["token_id"],
                "row_version": row.get("version"),
                "previous_checkpoint": (row.get("metadata") or {}).get(
                    "gamma"
                ),
                "previous_max_budget": row.get("max_budget"),
                "previous_spend": row.get("spend"),
                "settlement": {
                    **settlement.model_dump(),
                    "observation_hash": observation_hash,
                },
                "expected_checkpoint": checkpoint,
                "target_max_budget": format(
                    Decimal(target_units) / 10**9, "f"
                ),
                "amount_units": settlement.amount_units,
            },
        )
        if data.get("conflict"):
            raise StateConflict(data.get("reason", "credit version changed"))
        if (
            exact_money(
                self.response_row(data, hotkey, row, checkpoint)["max_budget"]
            )
            != target_units
        ):
            raise ManagementError("native exact-budget readback differs")
        return self.response_row(data, hotkey, row, checkpoint)
