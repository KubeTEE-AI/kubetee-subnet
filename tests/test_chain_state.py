"""Unit tests for scripts/chain_state.py real-chain query helpers (Layer 1 of pyramid).

All tests use injected fake subtensor objects - no real chain, no HTTP. These
functions replace the previously-hardcoded placeholder output in
print_subnet_stats.py and the untrusted regex-parsed ownership assumption in
setup_single_node.py: every result here must trace back to a queried value or
an explicit error, never a baked-in string.

Run:
  cd repos/subnet/kubetee-subnet
  python -m pytest tests/test_chain_state.py -q --tb=line
"""

import importlib.util
import sys
from pathlib import Path

_this_dir = Path(__file__).parent
_root = _this_dir.parent
_script_path = _root / "scripts" / "chain_state.py"

_spec = importlib.util.spec_from_file_location("chain_state_under_test", _script_path)
_chain_state = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _chain_state
_spec.loader.exec_module(_chain_state)

query_subnet_ownership = _chain_state.query_subnet_ownership
query_wallet_stake = _chain_state.query_wallet_stake


class _FakeSubnetInfo:
    def __init__(self, owner_ss58):
        self.owner_ss58 = owner_ss58


class _FakeBalance:
    def __init__(self, tao):
        self.tao = tao


class FakeSubtensor:
    def __init__(self, exists=True, owner_ss58=None, stake_tao=0.0,
                 raise_on_stake=None, raise_on_info=None):
        self._exists = exists
        self._owner_ss58 = owner_ss58
        self._stake_tao = stake_tao
        self._raise_on_stake = raise_on_stake
        self._raise_on_info = raise_on_info

    def subnet_exists(self, netuid):
        return self._exists

    def get_subnet_info(self, netuid):
        if self._raise_on_info:
            raise self._raise_on_info
        return _FakeSubnetInfo(self._owner_ss58)

    def get_stake(self, coldkey_ss58, hotkey_ss58, netuid):
        if self._raise_on_stake:
            raise self._raise_on_stake
        return _FakeBalance(self._stake_tao)


def test_query_subnet_ownership_owned():
    fake = FakeSubtensor(exists=True, owner_ss58="5OWNER")
    result = query_subnet_ownership(
        netuid=1, our_coldkey_ss58="5OWNER", chain_endpoint="ws://ignored", subtensor=fake
    )
    assert result == {"exists": True, "owner_ss58": "5OWNER", "owned_by_us": True, "error": None}


def test_query_subnet_ownership_not_owned():
    fake = FakeSubtensor(exists=True, owner_ss58="5SOMEONEELSE")
    result = query_subnet_ownership(
        netuid=1, our_coldkey_ss58="5OWNER", chain_endpoint="ws://ignored", subtensor=fake
    )
    assert result["exists"] is True
    assert result["owner_ss58"] == "5SOMEONEELSE"
    assert result["owned_by_us"] is False
    assert result["error"] is None


def test_query_subnet_ownership_missing_subnet():
    fake = FakeSubtensor(exists=False)
    result = query_subnet_ownership(
        netuid=99, our_coldkey_ss58="5OWNER", chain_endpoint="ws://ignored", subtensor=fake
    )
    assert result == {"exists": False, "owner_ss58": None, "owned_by_us": False, "error": None}


def test_query_subnet_ownership_query_error_is_reported_not_swallowed():
    fake = FakeSubtensor(exists=True, raise_on_info=RuntimeError("HTTP 429"))
    result = query_subnet_ownership(
        netuid=1, our_coldkey_ss58="5OWNER", chain_endpoint="ws://ignored", subtensor=fake
    )
    assert result["owned_by_us"] is False
    assert result["error"] == "HTTP 429"


def test_query_wallet_stake_success():
    fake = FakeSubtensor(stake_tao=12.5)
    result = query_wallet_stake(
        netuid=1, coldkey_ss58="5A", hotkey_ss58="5A", chain_endpoint="ws://ignored", subtensor=fake
    )
    assert result == {"stake_tao": 12.5, "error": None}


def test_query_wallet_stake_error_is_reported_not_swallowed():
    fake = FakeSubtensor(raise_on_stake=RuntimeError("HTTP 429"))
    result = query_wallet_stake(
        netuid=1, coldkey_ss58="5A", hotkey_ss58="5A", chain_endpoint="ws://ignored", subtensor=fake
    )
    assert result["stake_tao"] is None
    assert result["error"] == "HTTP 429"
