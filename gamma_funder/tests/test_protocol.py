from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
import bittensor as bt
from worker.protocol import (
    settlement_reference,
    SettlementRef,
    units_to_gamma,
    gamma_to_units,
    CreditRequest,
)
from decimal import Decimal

from worker.management import ManagementError, amount, remaining

HK = "5C62Ck4UrFPiBtoCmeSrgF7x9yv9mn38446dhCpsi2mLHiFT"
H = "0x" + "22" * 32


def test_reference_exact_and_bind():
    reference = settlement_reference(90, HK, H, 10**9)
    assert (
        reference
        == "0x671141613134e98cde60c6ec4a95d1127b961c8cf3aa76074fab6781b546690e"
    )
    receipt = SettlementRef(
        block_number=3,
        block_hash=H,
        event_index=1,
        reference=reference,
        netuid=90,
        hotkey_ss58=HK,
        amount_units=10**9,
    )
    assert receipt.event_id == f"{H}:1"
    with pytest.raises(ValueError):
        settlement_reference(89, HK, H, 1)
    with pytest.raises(ValueError):
        settlement_reference(90, "invalid", H, 1)
    with pytest.raises(ValueError):
        receipt.model_copy(
            update={
                "hotkey_ss58": "5FzVQ8vH4nfFocVvpL4fVZGzSVaPMFFFGNfPCdY6P5puxy"
            }
        ).validate_identity(HK)


def test_units_are_integer_native_exact():
    assert units_to_gamma(1) == "0.000000001"
    assert units_to_gamma(10**9) == "1"
    assert gamma_to_units("0.1 gamma") == 100_000_000
    assert gamma_to_units(1) == 1
    for x in [0, -1, 2**64]:
        pytest.raises(ValueError, units_to_gamma, x)


def test_key_credit_is_never_spend_floored():
    row = {"max_budget": "8", "spend": "5.25"}
    assert amount(row) == 8
    assert remaining(row).as_tuple().exponent == -2
    row = {"max_budget": "11.50", "spend": "12.75"}
    assert remaining(row) == 0
    # Real LiteLLM usage is a float meter, not 1e-9 Gamma units.
    row = {"max_budget": 1.5, "spend": 0.30000000000000004}
    assert amount(row) == Decimal("1.5")
    assert remaining(row) == Decimal("1.19999999999999996")
    for spend in ("nan", "-1", "inf", None):
        with pytest.raises(ManagementError):
            remaining({"max_budget": "1", "spend": spend})
    with pytest.raises(ManagementError):
        amount({"max_budget": "0.0000000001", "spend": "0"})


def test_challenge_version_only_required_for_update():
    with pytest.raises(ValueError):
        CreditRequest(
            token_id="x",
            hotkey_ss58=HK,
            amount_units=1,
            expected_checkpoint=None,
            settlement={
                "height": 1,
                "block_hash": H,
                "event_index": 1,
                "reference": settlement_reference(90, HK, H, 1),
                "amount_units": 1,
            },
        )
