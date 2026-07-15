"""Unit tests for the ownership-decision logic in scripts/setup_single_node.py.

Regression coverage for the bug where create_subnet_if_needed's regex-parsed
btcli output was trusted as proof of ownership: a failed `btcli subnet
create` (e.g. SubtokenDisabled) fell through to "use the requested netuid
anyway" and the script then blindly attempted owner-only sudo operations
(start_emissions, conviction/recycle hypers) against a netuid it did not
own, forever, in a retry loop - producing the HTTP 429 connection storm.

decide_owner_actions() is the pure decision point extracted from that flow:
given a real query_subnet_ownership() result, it decides whether owner-only
operations are safe to attempt at all. No hardcoded "proceed" bias.

Run:
  cd repos/subnet/kubetee-subnet
  python -m pytest tests/test_setup_single_node.py -q --tb=line
"""

import importlib.util
import sys
from pathlib import Path

_this_dir = Path(__file__).parent
_root = _this_dir.parent
_scripts_dir = _root / "scripts"
_script_path = _scripts_dir / "setup_single_node.py"

# setup_single_node.py does `import chain_state` (sibling module, resolved via
# sys.path[0] when run as `python scripts/setup_single_node.py`) - replicate
# that for the importlib-by-path load used in tests.
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

_spec = importlib.util.spec_from_file_location("setup_single_node_under_test", _script_path)
_setup = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _setup
_spec.loader.exec_module(_setup)

decide_owner_actions = _setup.decide_owner_actions


def test_decide_owner_actions_proceeds_when_owned():
    ownership = {"exists": True, "owner_ss58": "5OWNER", "owned_by_us": True, "error": None}
    decision = decide_owner_actions(ownership)
    assert decision["proceed"] is True


def test_decide_owner_actions_skips_when_owned_by_someone_else():
    """This is the exact scenario from the SubtokenDisabled/bootstrap-key bug:
    create failed, netuid 1 exists, but it's owned by a different key."""
    ownership = {"exists": True, "owner_ss58": "5BOOTSTRAPKEY", "owned_by_us": False, "error": None}
    decision = decide_owner_actions(ownership)
    assert decision["proceed"] is False
    assert "5BOOTSTRAPKEY" in decision["reason"]


def test_decide_owner_actions_skips_when_netuid_missing():
    ownership = {"exists": False, "owner_ss58": None, "owned_by_us": False, "error": None}
    decision = decide_owner_actions(ownership)
    assert decision["proceed"] is False


def test_decide_owner_actions_fails_closed_on_query_error():
    """A query error (e.g. HTTP 429) must never be treated as implicit ownership."""
    ownership = {"exists": None, "owner_ss58": None, "owned_by_us": False, "error": "HTTP 429"}
    decision = decide_owner_actions(ownership)
    assert decision["proceed"] is False
    assert "HTTP 429" in decision["reason"]
