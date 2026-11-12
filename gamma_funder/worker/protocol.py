"""SN90 Gamma protocol: canonical integers, references, signed claim wire types."""

from __future__ import annotations

import hashlib
from bittensor_core import ss58_decode
from decimal import Decimal, InvalidOperation
from typing import Literal

import bittensor as bt
from bittensor.settings import FINNEY_GENESIS_HASH
from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field

GENESIS = FINNEY_GENESIS_HASH
GAMMA_UNITS = 10**9


def units_to_gamma(value: int) -> str:
    if type(value) is not int or not 0 < value <= 2**64 - 1:
        raise ValueError("positive uint64 Gamma units required")
    return format(Decimal(value) / GAMMA_UNITS, "f")


def gamma_to_units(value) -> int:
    """Current SDK amount_tao_to_u64 convention for user Gamma amounts."""
    if isinstance(value, bool):
        raise ValueError("invalid Gamma amount")
    try:
        if isinstance(value, (int, str, Decimal)):
            if (
                isinstance(value, int)
                and 0 <= value <= 2**64 - 1
                and not isinstance(value, str)
            ):
                return value
            result = Decimal(str(value).removesuffix(" gamma")) * GAMMA_UNITS
        else:
            result = (
                Decimal(str(bt.intents._money.gamma_amount(value)))
                * GAMMA_UNITS
            )
        if result != int(result) or not 0 <= int(result) <= 2**64 - 1:
            raise ValueError()
        return int(result)
    except (bt.BittensorError, InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid exact Gamma amount") from exc


def currency_to_units(value: str) -> int:
    if not isinstance(value, str) or not value.endswith(" gamma"):
        raise ValueError("SDK Gamma currency required")
    return gamma_to_units(value)


def ss58_address(value: str) -> str:
    """Verify Base58Check decode and SS58 checksum for a Substrate account."""
    raw = ss58_decode(value)
    if len(raw) != 32:
        raise ValueError("invalid SS58 account ID")
    return value


def settlement_reference(
    netuid: int, hotkey_ss58: str, block_hash: str, amount_units: int
) -> str:
    if netuid != 90:
        raise ValueError("only SN90")
    ss58_address(hotkey_ss58)
    units_to_gamma(amount_units)
    try:
        if (
            len(bytes.fromhex(block_hash.removeprefix("0x"))) != 32
            or block_hash != block_hash.lower()
        ):
            raise ValueError()
    except ValueError as exc:
        raise ValueError("canonical lowercase block hash required") from exc
    return (
        "0x"
        + hashlib.sha256(
            f"kubetee-sn90-settlement-v1\0{GENESIS}\0{netuid}\0{hotkey_ss58}\0"
            f"{block_hash}\0{amount_units}".encode()
        ).hexdigest()
    )


class SettlementRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_number: int = Field(ge=1)
    block_hash: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    event_index: int = Field(ge=-1)
    reference: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    hotkey_ss58: str
    netuid: int = Field(default=90)
    amount_units: int = Field(gt=0)

    @property
    def event_id(self):
        return f"{self.block_hash}:{self.event_index}"

    def validate_identity(self, hotkey: str) -> None:
        if (
            self.hotkey_ss58 != hotkey
            or self.netuid != 90
            or self.amount_units <= 0
        ):
            raise ValueError("wrong settlement hotkey")
        # Emitted at the settlement height; it cannot equal the planning hash.


class ProveReconcile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    network: Literal["finney"] = "finney"
    genesis_hash: Literal[GENESIS] = GENESIS
    netuid: Literal[90] = 90
    hotkey_ss58: str
    action: Literal["claim", "regenerate", "status"]
    verified_challenge_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicResult(BaseModel):
    status: Literal["pending", "ineligible", "funded", "retryable_error"]
    reason: str | None = None
    retry_after_seconds: int = 6
    token_id: str | None = None
    max_budget: str | None = None
    spend: str | None = None
    remaining_credit: str | None = None
    reconciliation_reference: str | None = None
    job_id: str | None = None
    correlation_id: str | None = None


class ReservationRequest(BaseModel):
    """Private worker request: alias is always chain-observed, not signed text."""

    model_config = ConfigDict(extra="forbid")
    network: Literal["finney"] = "finney"
    genesis_hash: Literal[GENESIS] = GENESIS
    netuid: int = Field(default=90)
    hotkey_ss58: str
    checkpoint: dict
    key_alias: str = Field(min_length=1, max_length=255)
    target_permissions: dict | None = None


class CreditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    network: Literal["finney"] = "finney"
    genesis_hash: Literal[GENESIS] = GENESIS
    netuid: int = Field(default=90)
    hotkey_ss58: str
    token_id: str
    settlement: SettlementRef
    expected_checkpoint: dict | None
    amount_units: int = Field(gt=0)


def internal_router(processor) -> APIRouter:
    router = APIRouter()

    @router.post("/internal/v1/reconcile", response_model=PublicResult)
    async def reconcile(
        body: ProveReconcile, x_kubetee_worker_proof: str = Header("")
    ):
        await processor.authenticate(x_kubetee_worker_proof)
        return await processor.request(body)

    @router.get("/internal/v1/ready")
    async def ready(x_kubetee_worker_proof: str = Header("")):
        await processor.authenticate(x_kubetee_worker_proof)
        return await processor.ready()

    return router
