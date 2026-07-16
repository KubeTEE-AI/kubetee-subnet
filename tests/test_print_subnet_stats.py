"""Unit tests for scripts/print_subnet_stats.py.

Regression coverage for the original bug: the Stake / Subnet overview /
Conviction sections were hardcoded placeholder strings printed unconditionally,
never derived from a real chain query. These tests prove build_report() only
ever reports queried values (via injected fake subtensor + wallet ss58s) and
that format_report() never emits the old baked-in failure text when the real
state is actually successful.

Run:
  cd repos/subnet/kubetee-subnet
  python -m pytest tests/test_print_subnet_stats.py -q --tb=line
"""

import importlib.util
import sys
from pathlib import Path

_this_dir = Path(__file__).parent
_root = _this_dir.parent
_scripts_dir = _root / "scripts"
_script_path = _scripts_dir / "print_subnet_stats.py"

if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

_spec = importlib.util.spec_from_file_location("print_subnet_stats_under_test", _script_path)
_stats = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _stats
_spec.loader.exec_module(_stats)

build_report = _stats.build_report
format_report = _stats.format_report


def test_default_wallets_are_bob_and_owner_not_signing_wallet(monkeypatch):
    """g004 D7: the default miner wallet is bob (legacy 'miner' retired) and
    the owner default never follows BT_WALLET (that is alice, the validator
    signing wallet in compose)."""
    monkeypatch.setenv("BT_WALLET", "alice")
    monkeypatch.delenv("KUBETEE_OWNER_WALLET", raising=False)
    parser = _stats.build_arg_parser()
    assert parser.get_default("miner_wallet") == "bob"
    assert parser.get_default("owner_wallet") == "owner"

# Old hardcoded strings the buggy version printed unconditionally - must never
# appear again once the real state contradicts them.
_OLD_HARDCODED_STAKE_TEXT = "no stake found (or setup stake failed due to ownership)"
_OLD_HARDCODED_OVERVIEW_TEXT = "owner is bootstrap key (not our owner wallet)"
_OLD_HARDCODED_CONVICTION_TEXT = "sudo failed - not owner"


class _FakeSubnetInfo:
    def __init__(self, owner_ss58):
        self.owner_ss58 = owner_ss58


class _FakeHyperparams:
    tempo = 99
    owner_cut_auto_lock_enabled = True
    min_burn = 1
    max_burn = 2
    immunity_period = 3
    activity_cutoff = 4
    recycle_or_burn = "Recycle"


class _FakeBalance:
    def __init__(self, tao):
        self.tao = tao


class FakeSubtensor:
    def __init__(self, owner_ss58="5OWNER", stake_by_coldkey=None, hyperparams=None):
        self._owner_ss58 = owner_ss58
        self._stake_by_coldkey = stake_by_coldkey or {}
        self._hyperparams = hyperparams if hyperparams is not None else _FakeHyperparams()

    def subnet_exists(self, netuid):
        return True

    def get_subnet_info(self, netuid):
        return _FakeSubnetInfo(self._owner_ss58)

    def get_subnet_hyperparameters(self, netuid):
        return self._hyperparams

    def get_stake(self, coldkey_ss58, hotkey_ss58, netuid):
        return _FakeBalance(self._stake_by_coldkey.get(coldkey_ss58, 0.0))


def _wallets(owner_ss58="5OWNER", miner_ss58="5MINER"):
    return {
        "owner": {"coldkey_ss58": owner_ss58, "hotkey_ss58": owner_ss58},
        "miner": {"coldkey_ss58": miner_ss58, "hotkey_ss58": miner_ss58},
    }


def test_build_report_reflects_real_owned_state_with_stake():
    fake = FakeSubtensor(owner_ss58="5OWNER", stake_by_coldkey={"5OWNER": 200.0, "5MINER": 50.0})
    report = build_report(netuid=1, chain_endpoint="ws://ignored", wallets=_wallets(), subtensor=fake)

    assert report["ownership"]["owned_by_us"] is True
    assert report["ownership"]["owner_ss58"] == "5OWNER"
    assert report["stake"]["owner"]["stake_tao"] == 200.0
    assert report["stake"]["miner"]["stake_tao"] == 50.0
    assert report["hyperparameters"]["owner_cut_auto_lock_enabled"] is True
    assert report["hyperparameters"]["recycle_or_burn"] == "Recycle"


def test_build_report_reflects_real_not_owned_state():
    fake = FakeSubtensor(owner_ss58="5BOOTSTRAPKEY", stake_by_coldkey={})
    report = build_report(netuid=1, chain_endpoint="ws://ignored", wallets=_wallets(), subtensor=fake)

    assert report["ownership"]["owned_by_us"] is False
    assert report["ownership"]["owner_ss58"] == "5BOOTSTRAPKEY"
    assert report["stake"]["owner"]["stake_tao"] == 0.0


def test_build_report_reports_unresolved_wallet_honestly():
    fake = FakeSubtensor()
    wallets = {"owner": None, "miner": {"coldkey_ss58": "5MINER", "hotkey_ss58": "5MINER"}}
    report = build_report(netuid=1, chain_endpoint="ws://ignored", wallets=wallets, subtensor=fake)

    assert report["ownership"]["error"]
    assert report["stake"]["owner"]["error"]


def test_format_report_omits_old_hardcoded_text_when_state_is_actually_good():
    fake = FakeSubtensor(owner_ss58="5OWNER", stake_by_coldkey={"5OWNER": 200.0, "5MINER": 50.0})
    report = build_report(netuid=1, chain_endpoint="ws://ignored", wallets=_wallets(), subtensor=fake)
    text = format_report(report)

    assert _OLD_HARDCODED_STAKE_TEXT not in text
    assert _OLD_HARDCODED_OVERVIEW_TEXT not in text
    assert _OLD_HARDCODED_CONVICTION_TEXT not in text
    assert "200.0" in text
    assert "50.0" in text
    assert "5OWNER" in text


def test_format_report_shows_real_failure_when_actually_not_owned():
    fake = FakeSubtensor(owner_ss58="5BOOTSTRAPKEY", stake_by_coldkey={})
    report = build_report(netuid=1, chain_endpoint="ws://ignored", wallets=_wallets(), subtensor=fake)
    text = format_report(report)

    assert "5BOOTSTRAPKEY" in text
    assert "5OWNER" in text  # our wallet ss58 shown for comparison
