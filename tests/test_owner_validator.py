"""
Basic unit test for owner validator recycle use case (start of testing pyramid).

Uses in-memory mocks (no real chain, no HTTP) - Layer 1 of pyramid.
Inspired by FDN Memory* harness + in-process scenarios.

Run:
  python -m pytest tests/test_owner_validator.py -q --tb=line
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import bittensor as sub
from bittensor.wallet import Wallet

from scripts.owner_validator import set_owner_weights

class FakeResult:
    def __init__(self, success=True, block_hash="0xabc", error=None):
        self.success = success
        self.block_hash = block_hash
        self.error = error

@pytest.mark.asyncio
async def test_set_owner_weights_mocked(monkeypatch):
    """In-mem test: verify the weight-setting logic calls execute with correct intent."""
    fake_wallet = Wallet(name="test", hotkey="test")

    # Mock client
    mock_client = MagicMock(spec=sub.Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.execute = AsyncMock(return_value=FakeResult(success=True, block_hash="0xdead"))

    result = await set_owner_weights(
        client=mock_client,
        wallet=fake_wallet,
        netuid=42,
        target_uid=7,
    )

    assert result["success"] is True
    assert result["netuid"] == 42
    assert result["target_uid"] == 7

    # Assert the intent was constructed with full weight to target
    call_args = mock_client.execute.call_args
    intent = call_args[0][0]
    assert isinstance(intent, sub.SetWeights)
    assert intent.netuid == 42
    assert intent.weights == {7: 1.0}

@pytest.mark.asyncio
async def test_set_owner_weights_failure_path():
    """Test failure handling (part of robust pyramid)."""
    fake_wallet = Wallet(name="test", hotkey="test")
    mock_client = MagicMock(spec=sub.Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.execute = AsyncMock(return_value=FakeResult(success=False, error="no permit"))

    result = await set_owner_weights(client=mock_client, wallet=fake_wallet, netuid=1, target_uid=0)
    assert result["success"] is False
    assert "permit" in (result["error"] or "").lower() or result["error"] is not None
