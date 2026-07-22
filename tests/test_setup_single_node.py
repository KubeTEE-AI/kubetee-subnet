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

import pytest

_this_dir = Path(__file__).parent
_root = _this_dir.parent
_scripts_dir = _root / "scripts"
_script_path = _scripts_dir / "setup_single_node.py"

# setup_single_node.py does `import chain_state` (sibling module, resolved via
# sys.path[0] when run as `python scripts/setup_single_node.py`) - replicate
# that for the importlib-by-path load used in tests.
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

_spec = importlib.util.spec_from_file_location(
    "setup_single_node_under_test", _script_path
)
_setup = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _setup
_spec.loader.exec_module(_setup)

decide_owner_actions = _setup.decide_owner_actions
registration_plan = _setup.registration_plan


def test_registration_plan_is_owner_alice_bob_triad():
    """g004 D7: owner (recycle target) registers first for a stable UID,
    then alice (validator, signs set_weights), then bob (miner)."""
    plan = registration_plan("owner")
    assert [entry["wallet"] for entry in plan] == ["owner", "alice", "bob"]
    assert [entry["role"] for entry in plan] == ["owner", "validator", "miner"]
    assert [entry["validator"] for entry in plan] == [True, True, False]
    seeds = [entry["seed"] for entry in plan]
    assert (
        len(set(seeds)) == 3
    ), "triad seeds must be distinct pinned dev seeds"


def test_legacy_miner_wallet_is_retired():
    """D7: the sample 'miner' wallet and its pinned dev seed are gone; bob
    (new pinned dev seed) is the miner."""
    assert not any(name.startswith("DEV_MINER") for name in dir(_setup))
    assert all(entry["wallet"] != "miner" for entry in registration_plan())
    assert _setup.DEV_BOB_SEED.startswith("0x")
    assert len(_setup.DEV_BOB_SEED) == 66  # 0x + 32 bytes hex
    int(_setup.DEV_BOB_SEED[2:], 16)  # must parse as hex


def test_decide_owner_actions_proceeds_when_owned():
    ownership = {
        "exists": True,
        "owner_ss58": "5OWNER",
        "owned_by_us": True,
        "error": None,
    }
    decision = decide_owner_actions(ownership)
    assert decision["proceed"] is True


def test_decide_owner_actions_skips_when_owned_by_someone_else():
    """This is the exact scenario from the SubtokenDisabled/bootstrap-key bug:
    create failed, netuid 1 exists, but it's owned by a different key."""
    ownership = {
        "exists": True,
        "owner_ss58": "5BOOTSTRAPKEY",
        "owned_by_us": False,
        "error": None,
    }
    decision = decide_owner_actions(ownership)
    assert decision["proceed"] is False
    assert "5BOOTSTRAPKEY" in decision["reason"]


def test_decide_owner_actions_skips_when_netuid_missing():
    ownership = {
        "exists": False,
        "owner_ss58": None,
        "owned_by_us": False,
        "error": None,
    }
    decision = decide_owner_actions(ownership)
    assert decision["proceed"] is False


def test_decide_owner_actions_fails_closed_on_query_error():
    """A query error (e.g. HTTP 429) must never be treated as implicit ownership."""
    ownership = {
        "exists": None,
        "owner_ss58": None,
        "owned_by_us": False,
        "error": "HTTP 429",
    }
    decision = decide_owner_actions(ownership)
    assert decision["proceed"] is False
    assert "HTTP 429" in decision["reason"]


def test_dry_run_prints_commands_and_returns_success():
    """Dry-run mode should print [DRY-RUN] prefixed commands and not execute them."""
    result = _setup.run(["echo", "should_not_run"], dry_run=True)
    assert result.returncode == 0
    assert result.args == ["echo", "should_not_run"]


def test_dry_run_does_not_execute_commands():
    """A command that would fail normally should succeed in dry-run mode."""
    result = _setup.run(["/nonexistent/command"], dry_run=True)
    assert result.returncode == 0
    assert result.args == ["/nonexistent/command"]


def test_command_helpers_propagate_dry_run(monkeypatch):
    calls = []

    def capture_run(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(_setup, "run", capture_run)

    _setup.register_neuron(1, "alice", dry_run=True)
    _setup.start_emissions(1, "owner", dry_run=True)
    _setup.add_stake(1, "alice", dry_run=True)
    _setup.set_conviction_and_recycle(1, "owner", dry_run=True)

    assert len(calls) == 5
    assert all(kwargs["dry_run"] is True for _, kwargs in calls)


@pytest.mark.parametrize("as_validator", [True, False])
def test_register_neuron_uses_fail_closed_btcli_v11_command(monkeypatch, as_validator):
    calls = []

    def capture_run(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(_setup, "run", capture_run)

    _setup.register_neuron(
        42,
        "test-wallet",
        "test-hotkey",
        as_validator=as_validator,
        chain_endpoint="ws://chain.example:9944",
        dry_run=True,
    )

    assert calls == [
        (
            [
                "btcli",
                "subnet",
                "register",
                "--netuid",
                "42",
                "--wallet",
                "test-wallet",
                "--wallet-hotkey",
                "test-hotkey",
                "--network",
                "ws://chain.example:9944",
                "--yes",
            ],
            {"check": True, "dry_run": True},
        )
    ]


@pytest.mark.parametrize(
    ("key_kind", "subcommand", "key_kind_options"),
    [
        ("coldkey", "regen-coldkey", ["--no-password"]),
        ("hotkey", "regen-hotkey", []),
    ],
)
def test_regenerate_wallet_key_uses_direct_v11_arguments_and_redacts_output(
    monkeypatch, capsys, key_kind, subcommand, key_kind_options
):
    """Wallet regeneration must be a direct btcli v11 invocation, never a shell."""
    seed = "seed-must-not-be-logged"
    calls = []

    def fake_subprocess_run(args, **kwargs):
        calls.append((args, kwargs))
        return _setup.subprocess.CompletedProcess(
            args, 0, stdout=f"stdout: {seed}", stderr=f"stderr: {seed}"
        )

    monkeypatch.setattr(_setup.subprocess, "run", fake_subprocess_run)

    _setup._regenerate_wallet_key(key_kind, "owner", seed)

    assert calls == [
        (
            [
                "btcli",
                "wallet",
                subcommand,
                "--wallet",
                "owner",
                "--wallet-hotkey",
                "default",
                "--wallet-path",
                str(Path.home() / ".bittensor" / "wallets"),
                "--seed",
                seed,
                *key_kind_options,
                "--overwrite",
                "--quiet",
            ],
            {"capture_output": True, "text": True, "shell": False},
        )
    ]
    captured = capsys.readouterr()
    assert seed not in captured.out
    assert seed not in captured.err


def test_regenerate_wallet_key_dry_run_never_executes_or_prints_seed(monkeypatch, capsys):
    seed = "seed-must-not-be-logged"

    def subprocess_must_not_run(*_args, **_kwargs):
        raise AssertionError("dry-run must not invoke subprocess.run")

    monkeypatch.setattr(_setup.subprocess, "run", subprocess_must_not_run)

    _setup._regenerate_wallet_key("coldkey", "owner", seed, dry_run=True)

    output = capsys.readouterr().out
    assert "<redacted-seed>" in output
    assert seed not in output


def test_regenerate_wallet_key_fails_closed_without_leaking_captured_seed(monkeypatch, capsys):
    seed = "seed-must-not-be-logged"

    def failing_subprocess_run(args, **_kwargs):
        return _setup.subprocess.CompletedProcess(
            args, 1, stdout=f"stdout: {seed}", stderr=f"stderr: {seed}"
        )

    monkeypatch.setattr(_setup.subprocess, "run", failing_subprocess_run)

    with pytest.raises(RuntimeError, match=r"^coldkey regeneration failed$") as error:
        _setup._regenerate_wallet_key("coldkey", "owner", seed)

    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    captured = capsys.readouterr()
    assert seed not in captured.out
    assert seed not in captured.err
    assert seed not in str(error.value)


def test_regenerate_wallet_key_normalizes_subprocess_errors_without_leaking_seed(
    monkeypatch, capsys
):
    seed = "seed-must-not-be-logged"

    def exploding_subprocess_run(*_args, **_kwargs):
        raise _setup.subprocess.SubprocessError(f"subprocess detail: {seed}")

    monkeypatch.setattr(_setup.subprocess, "run", exploding_subprocess_run)

    with pytest.raises(RuntimeError, match=r"^hotkey regeneration failed$") as error:
        _setup._regenerate_wallet_key("hotkey", "owner", seed)

    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    captured = capsys.readouterr()
    assert seed not in captured.out
    assert seed not in captured.err
    assert seed not in str(error.value)


def test_regenerate_wallet_key_normalizes_ordinary_errors_without_leaking_seed(
    monkeypatch, capsys
):
    seed = "seed-must-not-be-logged"

    def exploding_subprocess_run(*_args, **_kwargs):
        raise RuntimeError(f"hostile upstream marker: {seed}")

    monkeypatch.setattr(_setup.subprocess, "run", exploding_subprocess_run)

    with pytest.raises(RuntimeError, match=r"^hotkey regeneration failed$") as error:
        _setup._regenerate_wallet_key("hotkey", "owner", seed)

    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    captured = capsys.readouterr()
    assert seed not in captured.out
    assert seed not in captured.err
    assert seed not in str(error.value)


def test_ensure_dev_wallet_regenerates_coldkey_then_hotkey(monkeypatch):
    regenerated = []

    def fake_regenerate(key_kind, name, seed, hotkey="default", dry_run=False):
        regenerated.append((key_kind, name, seed, hotkey, dry_run))

    monkeypatch.setattr(_setup, "_regenerate_wallet_key", fake_regenerate)

    _setup.ensure_dev_wallet("owner", _setup.DEV_OWNER_SEED, dry_run=True)

    assert regenerated == [
        ("coldkey", "owner", _setup.DEV_OWNER_SEED, "default", True),
        ("hotkey", "owner", _setup.DEV_OWNER_SEED, "default", True),
    ]


def test_fund_from_alice_reuses_fail_closed_coldkey_regeneration(monkeypatch):
    regenerated = []
    commands = []

    def fake_regenerate(key_kind, name, seed, hotkey="default", dry_run=False):
        regenerated.append((key_kind, name, seed, hotkey, dry_run))

    monkeypatch.setattr(_setup, "_regenerate_wallet_key", fake_regenerate)
    monkeypatch.setattr(_setup, "get_wallet_coldkey_ss58", lambda *_args, **_kwargs: "5DEST")
    monkeypatch.setattr(_setup, "run", lambda args, **kwargs: commands.append((args, kwargs)))

    _setup.fund_from_alice("owner", amount=5000, chain_endpoint="ws://chain:9944")

    assert regenerated == [("coldkey", "alice", _setup.DEV_ALICE_SEED, "default", False)]
    assert commands == [
        (
            [
                "btcli",
                "wallet",
                "transfer",
                "--dest",
                "5DEST",
                "--amount",
                "5000",
                "--wallet",
                "alice",
                "--wallet-hotkey",
                "default",
                "--network",
                "ws://chain:9944",
                "--yes",
                "--allow-death",
            ],
            {"check": False, "dry_run": False},
        )
    ]


def test_wallet_regeneration_source_has_no_obsolete_flag_or_shell_pipeline():
    source = _script_path.read_text(encoding="utf-8")
    assert "--no-use-password" not in source
    assert "yes y | btcli wallet regen" not in source
    assert '"sh", "-c"' not in source


def test_dockerfile_healthcheck_curls_metrics_with_a_timeout():
    dockerfile = (_root / "Dockerfile").read_text(encoding="utf-8")
    assert "curl --fail --silent --show-error --max-time" in dockerfile
    assert "http://127.0.0.1:9100/metrics" in dockerfile
    assert 'python -c "import bittensor' not in dockerfile
