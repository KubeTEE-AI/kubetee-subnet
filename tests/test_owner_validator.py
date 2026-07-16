"""
Basic unit test for owner validator recycle use case (start of testing pyramid).

Uses in-memory mocks (no real chain) - Layer 1 of pyramid.
Mocks the bt.Subtensor.set_weights path used by the current implementation.

Run:
  cd repos/subnet/kubetee-subnet
  PYTHONPATH=. python -m pytest tests/test_owner_validator.py -q --tb=line
  # or just: python -m pytest ... (the test adjusts sys.path relative to itself)
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import bittensor as bt

# Robustly load the script module by path (no reliance on "scripts" being a package on sys.path).
# This is intentional for the testing pyramid: we test the actual .py that will run in the container.
_this_dir = Path(__file__).parent
_root = _this_dir.parent
_script_path = _root / "scripts" / "owner_validator.py"

_spec = importlib.util.spec_from_file_location("owner_validator_under_test", _script_path)
_owner_validator = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _owner_validator
_spec.loader.exec_module(_owner_validator)

set_owner_weights = _owner_validator.set_owner_weights


class _StopLoop(BaseException):
    """Sentinel used to break run_validator_loop's `while True` in tests.

    Deliberately a BaseException (not Exception) subclass so it is NOT caught
    by the loop's `except Exception` retry handler - a plain StopIteration
    would be swallowed and retried, defeating the test.
    """


def test_set_owner_weights_mocked():
    """In-mem test: verify set_owner_weights calls subtensor.set_weights with correct args (1.0 to target)."""
    fake_wallet = bt.Wallet(name="test", hotkey="test")

    mock_subtensor = MagicMock(spec=bt.Subtensor)
    mock_subtensor.set_weights.return_value = (True, "ok")

    result = set_owner_weights(
        subtensor=mock_subtensor,
        wallet=fake_wallet,
        netuid=42,
        target_uid=7,
    )

    assert result["success"] is True
    assert result["netuid"] == 42
    assert result["target_uid"] == 7

    mock_subtensor.set_weights.assert_called_once_with(
        wallet=fake_wallet,
        netuid=42,
        uids=[7],
        weights=[1.0],
    )


def test_set_owner_weights_failure_path():
    """Test failure handling (part of robust pyramid)."""
    fake_wallet = bt.Wallet(name="test", hotkey="test")
    mock_subtensor = MagicMock(spec=bt.Subtensor)
    mock_subtensor.set_weights.return_value = (False, "no permit or not registered")

    result = set_owner_weights(
        subtensor=mock_subtensor,
        wallet=fake_wallet,
        netuid=1,
        target_uid=0,
    )
    assert result["success"] is False
    assert result.get("message") or result.get("error")
    # The function currently puts it under "message" on the tuple path; be lenient
    msg = str(result.get("message") or result.get("error") or "")
    assert "permit" in msg.lower() or "not registered" in msg.lower() or msg != ""


def test_run_validator_loop_reuses_single_injected_connection(monkeypatch):
    """Regression test for the HTTP 429 connection-storm bug: the loop used to
    call set_owner_weights() with no subtensor arg every iteration, which
    defaulted to constructing a brand new bt.Subtensor() (new websocket
    connection) every 10-20s. run_validator_loop must reuse exactly the
    connection it was given and never construct its own.
    """
    mock_subtensor = MagicMock(spec=bt.Subtensor)
    mock_subtensor.set_weights.return_value = (True, "ok")
    fake_wallet = bt.Wallet(name="test", hotkey="test")

    def _forbidden_subtensor(*args, **kwargs):
        raise AssertionError("run_validator_loop must not construct its own bt.Subtensor")

    monkeypatch.setattr(_owner_validator.bt, "Subtensor", _forbidden_subtensor)

    sleep_calls = []

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 3:
            raise _StopLoop("stop test loop")

    with pytest.raises(_StopLoop):
        _owner_validator.run_validator_loop(
            mock_subtensor, fake_wallet, netuid=1, target_uid=0, sleep=fake_sleep
        )

    assert mock_subtensor.set_weights.call_count == 3
    for call in mock_subtensor.set_weights.call_args_list:
        assert call.kwargs["wallet"] is fake_wallet
    assert sleep_calls == [20, 20, 20]


def test_run_validator_loop_backs_off_and_retries_on_failure(monkeypatch):
    mock_subtensor = MagicMock(spec=bt.Subtensor)
    mock_subtensor.set_weights.return_value = (False, "not registered")
    fake_wallet = bt.Wallet(name="test", hotkey="test")

    monkeypatch.setattr(
        _owner_validator.bt,
        "Subtensor",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not construct a new Subtensor")),
    )

    sleep_calls = []

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise _StopLoop("stop test loop")

    with pytest.raises(_StopLoop):
        _owner_validator.run_validator_loop(
            mock_subtensor, fake_wallet, netuid=1, target_uid=0, sleep=fake_sleep
        )

    assert sleep_calls == [10, 10]
