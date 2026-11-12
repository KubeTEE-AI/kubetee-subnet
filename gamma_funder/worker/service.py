"""Separate worker HTTP boundary; reconciliation creates no sk or budget directly."""
from __future__ import annotations

import hashlib
import hmac
import re
import base64
import logging
from decimal import Decimal, InvalidOperation

LOG = logging.getLogger(__name__)
from typing import Any

from cryptography import x509

from fastapi import HTTPException
from pydantic import ValidationError

from .management import ManagementError, StateConflict, remaining
from .chain import ChainError, PendingReceipt
from .protocol import PublicResult, ProveReconcile
from .reconciler import DepositState, Ineligible, Pending, Reconciler, base_checkpoint


class WorkerService:
    """Sole chain-reconciliation caller, with no native raw-key capability."""
    def __init__(self, chain: Any, fresh_checkpoint: Any, reconciler: Reconciler, *,
                 certificate_fingerprint: str, ready: bool = True):
        if chain is None or fresh_checkpoint is None or reconciler is None:
            raise ValueError("explicit chain, finalized-observation, and reconciler required")
        if not re.fullmatch(r"[0-9a-f]{64}", certificate_fingerprint.lower()):
            raise ValueError("explicit gateway mTLS certificate fingerprint required")
        self.certificate_fingerprint = certificate_fingerprint.lower()
        self.chain, self.fresh_checkpoint, self.reconciler = chain, fresh_checkpoint, reconciler
        self.is_ready = ready  # Kubelet cannot access mTLS; gateway probes only.

    async def authenticate(self, proof: str) -> None:
        try:
            der = base64.b64decode(proof, validate=True)
            certificate = x509.load_der_x509_certificate(der)
            certificate.not_valid_after_utc  # trust path is terminated by mTLS sidecar
        except (ValueError, TypeError) as error:
            raise HTTPException(403, "invalid caller certificate") from error
        if not hmac.compare_digest(hashlib.sha256(der).hexdigest(), self.certificate_fingerprint):
            raise HTTPException(403, "caller not authorized for chain reconciliation")

    async def ready(self) -> dict[str, bool]:
        return {"ready": self.is_ready}

    async def request(self, body: ProveReconcile) -> PublicResult:
        hotkey = body.hotkey_ss58
        ss58_address(hotkey)
        if not self.is_ready:
            return PublicResult(status="retryable_error", reason="worker_unavailable", retry_after_seconds=6)
        try:
            await self.reconciler.prepare_observation(hotkey)
            result = await self.reconciler.reconcile(hotkey)
            return public_result(result, hotkey)
        except StateConflict:
            return pending_public("concurrent native row transition")
        except Pending as error:
            if body.action in ("claim", "regenerate"):
                existing = await self.reconciler._row(hotkey)
                checkpoint = (existing or {}).get("metadata", {}).get("gamma") or {}
                if existing is not None and existing.get("max_budget") and checkpoint.get("last_spent_reference"):
                    return PublicResult(status="funded", token_id=existing["token_id"],
                        max_budget=str(Decimal(str(existing["max_budget"])).normalize()), spend=str(existing["spend"]),
                        remaining_credit=str(remaining(existing)),
                        reconciliation_reference=checkpoint["last_spent_reference"])
            return pending_public(str(error))
        except Ineligible as error:
            return PublicResult(status="ineligible", reason="ineligible finalized service deposit")
        except (ManagementError, ChainError, ConnectionError, TimeoutError, OSError,
                InvalidOperation, KeyError, TypeError, ValidationError, ValueError):
            LOG.exception("Finalized chain reconciliation or native management rejected request")
            raise HTTPException(503, {"status": "retryable_error"})


def pending_public(reason: str) -> PublicResult:
    """Only expose reasons allowed by the gateway's public reasoning vocabulary.

    Internal diagnostic reasons stay in the private worker log, never become a
    malformed public contract that the gateway would replace with HTTP 503.
    """
    if reason == "service unavailable":
        return PublicResult(status="retryable_error", reason="service_unavailable", retry_after_seconds=6)
    return PublicResult(status="pending", reason="spend_final_credit_pending", retry_after_seconds=6)


def public_result(result: Any, hotkey: str) -> PublicResult:
    if isinstance(result, PublicResult):
        return result
    if isinstance(result, dict):
        return PublicResult.model_validate(result)
    raise TypeError("native worker result is not public")


def ss58_address(hotkey: str) -> None:
    from bittensor_core import ss58_decode
    try:
        if len(ss58_decode(hotkey)) != 32:
            raise ValueError()
    except (TypeError, ValueError) as error:
        raise HTTPException(422, {"status": "ineligible", "reason": "invalid_hotkey"}) from error
