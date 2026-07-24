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

# Protocol fakes retain SDK call signatures even when a case ignores an
# argument.
# pylint: disable=unused-argument

import importlib.util
import sys
from pathlib import Path

_this_dir = Path(__file__).parent
_root = _this_dir.parent
_script_path = _root / "scripts" / "chain_state.py"

_spec = importlib.util.spec_from_file_location(
    "chain_state_under_test", _script_path
)
_chain_state = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _chain_state
_spec.loader.exec_module(_chain_state)

query_subnet_ownership = _chain_state.query_subnet_ownership
query_wallet_stake = _chain_state.query_wallet_stake


class _FakeMetagraph:
    def __init__(self, block, owner_coldkey):
        self.block = block
        self.owner_coldkey = owner_coldkey


class _FakeBalance:
    def __init__(self, tao):
        self.tao = tao


class FakeSubnetsNamespace:
    def __init__(self, metagraph=None, raise_on_metagraph=None):
        self._metagraph = metagraph
        self._raise_on_metagraph = raise_on_metagraph
        self.metagraph_calls = []

    def metagraph(self, netuid, block, commitments):
        self.metagraph_calls.append((netuid, block, commitments))
        if self._raise_on_metagraph:
            raise self._raise_on_metagraph
        return self._metagraph


class FakeStakingNamespace:
    def __init__(self, stake_tao=0.0, raise_on_stake=None):
        self._stake_tao = stake_tao
        self._raise_on_stake = raise_on_stake

    def get(self, coldkey_ss58, hotkey_ss58, netuid):
        if self._raise_on_stake:
            raise self._raise_on_stake
        return _FakeBalance(self._stake_tao)


class FakeSubtensor:
    def __init__(
        self,
        block=41,
        metagraph=None,
        stake_tao=0.0,
        raise_on_stake=None,
        raise_on_metagraph=None,
    ):
        self._block = block
        self.block_calls = 0
        self.subnets = FakeSubnetsNamespace(
            metagraph=metagraph, raise_on_metagraph=raise_on_metagraph
        )
        self.staking = FakeStakingNamespace(
            stake_tao=stake_tao, raise_on_stake=raise_on_stake
        )

    def block(self):
        self.block_calls += 1
        return self._block


def test_query_subnet_ownership_owned():
    fake = FakeSubtensor(
        metagraph=_FakeMetagraph(block=41, owner_coldkey="5OWNER")
    )
    result = query_subnet_ownership(
        netuid=2,
        our_coldkey_ss58="5OWNER",
        chain_endpoint="ws://ignored",
        subtensor=fake,
    )
    assert result == {
        "exists": True,
        "owner_ss58": "5OWNER",
        "owned_by_us": True,
        "error": None,
    }
    assert fake.block_calls == 1
    assert fake.subnets.metagraph_calls == [(2, 41, False)]


def test_query_subnet_ownership_not_owned():
    fake = FakeSubtensor(
        metagraph=_FakeMetagraph(block=41, owner_coldkey="5SOMEONEELSE")
    )
    result = query_subnet_ownership(
        netuid=1,
        our_coldkey_ss58="5OWNER",
        chain_endpoint="ws://ignored",
        subtensor=fake,
    )
    assert result["exists"] is True
    assert result["owner_ss58"] == "5SOMEONEELSE"
    assert result["owned_by_us"] is False
    assert result["error"] is None


def test_query_subnet_ownership_missing_subnet():
    fake = FakeSubtensor(metagraph=None)
    result = query_subnet_ownership(
        netuid=99,
        our_coldkey_ss58="5OWNER",
        chain_endpoint="ws://ignored",
        subtensor=fake,
    )
    assert result == {
        "exists": False,
        "owner_ss58": None,
        "owned_by_us": False,
        "error": None,
    }


def test_query_subnet_ownership_query_error_is_reported_not_swallowed():
    fake = FakeSubtensor(raise_on_metagraph=RuntimeError("HTTP 429"))
    result = query_subnet_ownership(
        netuid=1,
        our_coldkey_ss58="5OWNER",
        chain_endpoint="ws://ignored",
        subtensor=fake,
    )
    assert result["owned_by_us"] is False
    assert result["error"] == "HTTP 429"


def test_query_subnet_ownership_rejects_stale_metagraph():
    fake = FakeSubtensor(
        metagraph=_FakeMetagraph(block=40, owner_coldkey="5OWNER")
    )
    result = query_subnet_ownership(
        netuid=2,
        our_coldkey_ss58="5OWNER",
        chain_endpoint="ws://ignored",
        subtensor=fake,
    )
    assert result == {
        "exists": None,
        "owner_ss58": None,
        "owned_by_us": False,
        "error": "ownership snapshot is not pinned to the requested head",
    }


def test_query_subnet_ownership_rejects_missing_canonical_owner():
    fake = FakeSubtensor(metagraph=_FakeMetagraph(block=41, owner_coldkey=""))
    result = query_subnet_ownership(
        netuid=2,
        our_coldkey_ss58="5OWNER",
        chain_endpoint="ws://ignored",
        subtensor=fake,
    )
    assert result == {
        "exists": None,
        "owner_ss58": None,
        "owned_by_us": False,
        "error": "ownership snapshot has no canonical owner",
    }


def test_query_subnet_ownership_rejects_non_string_canonical_owner():
    fake = FakeSubtensor(
        metagraph=_FakeMetagraph(block=41, owner_coldkey=None)
    )
    result = query_subnet_ownership(
        netuid=2,
        our_coldkey_ss58="5OWNER",
        chain_endpoint="ws://ignored",
        subtensor=fake,
    )
    assert result == {
        "exists": None,
        "owner_ss58": None,
        "owned_by_us": False,
        "error": "ownership snapshot has no canonical owner",
    }


def test_query_wallet_stake_success():
    fake = FakeSubtensor(stake_tao=12.5)
    result = query_wallet_stake(
        netuid=1,
        coldkey_ss58="5A",
        hotkey_ss58="5A",
        chain_endpoint="ws://ignored",
        subtensor=fake,
    )
    assert result == {"stake_tao": 12.5, "unit": "TAO", "error": None}


def test_query_wallet_stake_error_is_reported_not_swallowed():
    fake = FakeSubtensor(raise_on_stake=RuntimeError("HTTP 429"))
    result = query_wallet_stake(
        netuid=1,
        coldkey_ss58="5A",
        hotkey_ss58="5A",
        chain_endpoint="ws://ignored",
        subtensor=fake,
    )
    assert result["stake_tao"] is None
    assert result["error"] == "HTTP 429"


def test_alpha_balance_reports_alpha_units_instead_of_failing():
    """v11 subnet stakes are alpha Balances whose .tao accessor raises;
    the query must report the alpha amount, not a query failure."""

    class _AlphaBalance:
        @property
        def tao(self):
            raise TypeError(
                "This balance is subnet-2 alpha, not TAO. Use .alpha"
            )

        alpha = 42.5

    class _AlphaStaking:
        def get(self, coldkey_ss58, hotkey_ss58, netuid):
            return _AlphaBalance()

    class _AlphaSub:
        staking = _AlphaStaking()

    result = query_wallet_stake(2, "ck", "hk", "ws://x", subtensor=_AlphaSub())
    assert result["error"] is None
    assert result["stake_tao"] == 42.5
    assert result["unit"] == "alpha"
