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
from types import SimpleNamespace

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


class _RegistrationNeuron:
    def __init__(self, uid, hotkey, coldkey):
        self.uid = uid
        self.hotkey = hotkey
        self.coldkey = coldkey


def _install_registration_sdk(monkeypatch, metagraphs, *, head=17):
    """Install a synthetic SDK that records the exact head-pinned read shape."""
    calls = {"wallet": [], "subtensor": [], "block": 0, "metagraph": []}

    class FakeWallet:
        def __init__(self, name, hotkey):
            calls["wallet"].append((name, hotkey))
            self.hotkey = SimpleNamespace(ss58_address="5HOT")
            self.coldkeypub = SimpleNamespace(ss58_address="5COLD")

    class FakeSubtensor:
        def __init__(self, network):
            calls["subtensor"].append(network)
            self.subnets = SimpleNamespace(metagraph=self.metagraph)

        def block(self):
            calls["block"] += 1
            return head

        def metagraph(self, netuid, block):
            calls["metagraph"].append((netuid, block))
            return metagraphs.pop(0)

    monkeypatch.setattr(
        _setup, "bt", SimpleNamespace(Wallet=FakeWallet, Subtensor=FakeSubtensor)
    )
    return calls


def _registration_metagraph(neurons, block=17):
    return SimpleNamespace(neurons=neurons, block=block)


def _assert_fixed_registration_error(error):
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert str(error.value) == "unable to verify neuron registration"


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


def test_registration_plan_has_no_legacy_per_wallet_stake_amounts():
    """Readiness stakes only alice after ownership verification, not the triad."""
    assert all("stake" not in entry for entry in registration_plan())


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

    assert len(calls) == 2
    assert all(kwargs["dry_run"] is True for _, kwargs in calls)


def test_main_dry_run_is_private_fixed_output_and_performs_no_operations(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_single_node.py",
            "--dry-run",
            "--netuid",
            "42",
            "--owner-wallet",
            "owner-must-not-appear",
            "--chain-endpoint",
            "ws://chain.example:9944",
        ],
    )
    def forbidden(*_args, **_kwargs):
        raise AssertionError("dry-run must not execute setup work")

    for name in (
        "wait_for_chain",
        "ensure_dev_wallet",
        "fund_from_alice",
        "create_subnet_if_needed",
        "register_neuron",
        "get_wallet_coldkey_ss58",
        "start_emissions",
        "add_stake",
        "set_conviction_and_recycle",
    ):
        monkeypatch.setattr(_setup, name, forbidden)
    monkeypatch.setattr(_setup.time, "sleep", forbidden)
    monkeypatch.setattr(_setup.chain_state, "query_subnet_ownership", forbidden)
    monkeypatch.setattr(_setup.subprocess, "run", forbidden)
    monkeypatch.setattr(
        _setup,
        "bt",
        SimpleNamespace(Subtensor=forbidden, Wallet=forbidden),
    )

    _setup.main()

    assert capsys.readouterr().out == (
        "[DRY-RUN] local readiness setup would be executed\n"
        "[DRY-RUN] subnet activation would be executed\n"
        "[DRY-RUN] validator stake would be executed\n"
    )


def test_registration_state_reads_one_head_pinned_metagraph_for_exact_identity(
    monkeypatch,
):
    calls = _install_registration_sdk(
        monkeypatch,
        [_registration_metagraph([_RegistrationNeuron(3, "5HOT", "5COLD")])],
    )

    assert _setup._registration_is_present(42, "owner", "default", "ws://chain")
    assert calls == {
        "wallet": [("owner", "default")],
        "subtensor": ["ws://chain"],
        "block": 1,
        "metagraph": [(42, 17)],
    }


@pytest.mark.parametrize(
    "metagraph",
    [
        _registration_metagraph([_RegistrationNeuron(True, "5HOT", "5COLD")]),
        _registration_metagraph([_RegistrationNeuron(-1, "5HOT", "5COLD")]),
        _registration_metagraph([_RegistrationNeuron("3", "5HOT", "5COLD")]),
        _registration_metagraph([_RegistrationNeuron(3, "5HOT", "5OTHER")]),
        _registration_metagraph(
            [
                _RegistrationNeuron(3, "5HOT", "5COLD"),
                _RegistrationNeuron(4, "5HOT", "5COLD"),
            ]
        ),
        _registration_metagraph([SimpleNamespace(uid=3, hotkey="5HOT")]),
        _registration_metagraph("not-neurons"),
        _registration_metagraph([_RegistrationNeuron(3, "5HOT", "5COLD")], block=18),
    ],
)
def test_registration_state_fails_closed_for_malformed_or_ambiguous_identity(
    monkeypatch, metagraph
):
    _install_registration_sdk(monkeypatch, [metagraph])

    with pytest.raises(RuntimeError) as error:
        _setup._registration_is_present(42, "owner", "default", "ws://chain")

    _assert_fixed_registration_error(error)


@pytest.mark.parametrize("head", [True, -1, "17"])
def test_registration_state_fails_closed_for_invalid_chain_head(monkeypatch, head):
    _install_registration_sdk(monkeypatch, [], head=head)

    with pytest.raises(RuntimeError) as error:
        _setup._registration_is_present(42, "owner", "default", "ws://chain")

    _assert_fixed_registration_error(error)


def test_registration_state_fails_closed_for_wallet_failure(monkeypatch):
    class ExplodingWallet:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("hostile wallet detail")

    monkeypatch.setattr(_setup, "bt", SimpleNamespace(Wallet=ExplodingWallet))

    with pytest.raises(RuntimeError) as error:
        _setup._registration_is_present(42, "owner", "default", "ws://chain")

    _assert_fixed_registration_error(error)


def test_registration_state_fails_closed_for_sdk_failure(monkeypatch):
    class FakeWallet:
        hotkey = SimpleNamespace(ss58_address="5HOT")
        coldkeypub = SimpleNamespace(ss58_address="5COLD")

        def __init__(self, *_args, **_kwargs):
            pass

    class ExplodingSubtensor:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("hostile SDK detail")

    monkeypatch.setattr(
        _setup,
        "bt",
        SimpleNamespace(Wallet=FakeWallet, Subtensor=ExplodingSubtensor),
    )

    with pytest.raises(RuntimeError) as error:
        _setup._registration_is_present(42, "owner", "default", "ws://chain")

    _assert_fixed_registration_error(error)


def test_register_neuron_skips_subprocess_for_exact_preexisting_identity(monkeypatch):
    calls = _install_registration_sdk(
        monkeypatch,
        [_registration_metagraph([_RegistrationNeuron(3, "5HOT", "5COLD")])],
    )

    def subprocess_must_not_run(*_args, **_kwargs):
        raise AssertionError("present identity must not register again")

    monkeypatch.setattr(_setup.subprocess, "run", subprocess_must_not_run)

    _setup.register_neuron(42, "owner", chain_endpoint="ws://chain")

    assert calls["metagraph"] == [(42, 17)]


@pytest.mark.parametrize("as_validator", [True, False])
def test_register_neuron_uses_exact_checked_btcli_v11_command_then_live_postcondition(
    monkeypatch, as_validator
):
    _install_registration_sdk(
        monkeypatch,
        [
            _registration_metagraph([]),
            _registration_metagraph([_RegistrationNeuron(3, "5HOT", "5COLD")]),
        ],
    )
    calls = []

    def capture_run(args, **kwargs):
        calls.append((args, kwargs))
        return _setup.subprocess.CompletedProcess(args, 0, stdout="ignored", stderr="ignored")

    monkeypatch.setattr(_setup.subprocess, "run", capture_run)

    _setup.register_neuron(
        42,
        "owner",
        "default",
        as_validator=as_validator,
        chain_endpoint="ws://chain.example:9944",
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
                "owner",
                "--wallet-hotkey",
                "default",
                "--network",
                "ws://chain.example:9944",
                "--yes",
            ],
            {"check": True, "capture_output": True, "text": True, "shell": False},
        )
    ]


@pytest.mark.parametrize(
    "failure",
    [
        _setup.subprocess.CalledProcessError(1, ["btcli"], output="hostile", stderr="detail"),
        RuntimeError("hostile command detail"),
    ],
)
def test_register_neuron_normalizes_command_failure_without_output_or_chain(
    monkeypatch, capsys, failure
):
    _install_registration_sdk(monkeypatch, [_registration_metagraph([])])

    def failing_subprocess_run(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(_setup.subprocess, "run", failing_subprocess_run)

    with pytest.raises(RuntimeError, match=r"^neuron registration failed$") as error:
        _setup.register_neuron(42, "owner", chain_endpoint="ws://chain")

    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    output = capsys.readouterr()
    assert "hostile" not in output.out
    assert "hostile" not in output.err


def test_register_neuron_requires_exact_live_postcondition(monkeypatch):
    _install_registration_sdk(
        monkeypatch,
        [_registration_metagraph([]), _registration_metagraph([])],
    )
    monkeypatch.setattr(
        _setup.subprocess,
        "run",
        lambda args, **_kwargs: _setup.subprocess.CompletedProcess(args, 0),
    )

    with pytest.raises(
        RuntimeError, match=r"^neuron registration postcondition failed$"
    ) as error:
        _setup.register_neuron(42, "owner", chain_endpoint="ws://chain")

    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_register_neuron_dry_run_avoids_sdk_and_subprocess_and_identity_output(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        _setup,
        "bt",
        SimpleNamespace(
            Wallet=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
            Subtensor=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
        ),
    )
    monkeypatch.setattr(
        _setup.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )

    _setup.register_neuron(
        42, "identity-must-not-appear", "secret-hotkey", dry_run=True
    )

    assert capsys.readouterr().out == "[DRY-RUN] registration command would be executed\n"


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
    events = []
    regenerated = []
    commands = []

    def fake_regenerate(key_kind, name, seed, hotkey="default", dry_run=False):
        events.append(("regenerate", dry_run))
        regenerated.append((key_kind, name, seed, hotkey, dry_run))

    def fake_get_wallet_coldkey_ss58(name, hotkey="default", dry_run=False):
        events.append(("resolve-destination", dry_run))
        return "5DEST"

    def fake_run(args, **kwargs):
        events.append(("transfer", kwargs["dry_run"]))
        commands.append((args, kwargs))

    monkeypatch.setattr(_setup, "_regenerate_wallet_key", fake_regenerate)
    monkeypatch.setattr(_setup, "get_wallet_coldkey_ss58", fake_get_wallet_coldkey_ss58)
    monkeypatch.setattr(_setup, "run", fake_run)

    _setup.fund_from_alice(
        "owner", amount=5000, chain_endpoint="ws://chain:9944", dry_run=True
    )

    assert events == [
        ("regenerate", True),
        ("resolve-destination", True),
        ("transfer", True),
    ]
    assert regenerated == [("coldkey", "alice", _setup.DEV_ALICE_SEED, "default", True)]
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
            ],
            {"check": True, "dry_run": True},
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


class _SnapshotSubnet:
    def __init__(self, netuid):
        self.netuid = netuid


def _install_snapshot_subtensor(monkeypatch, snapshots):
    calls = []

    class FakeSubtensor:
        def __init__(self, network):
            calls.append(network)
            self.subnets = SimpleNamespace(subnets=lambda: snapshots.pop(0))

    monkeypatch.setattr(_setup, "bt", SimpleNamespace(Subtensor=FakeSubtensor))
    return calls


def test_create_subnet_resolves_exact_new_live_netuid_not_cli_text(
    monkeypatch, capsys
):
    snapshots = [
        [_SnapshotSubnet(0), _SnapshotSubnet(1)],
        [_SnapshotSubnet(0), _SnapshotSubnet(1), _SnapshotSubnet(2)],
    ]
    sdk_calls = _install_snapshot_subtensor(monkeypatch, snapshots)
    calls = []

    def fake_subprocess_run(args, **kwargs):
        calls.append((args, kwargs))
        return _setup.subprocess.CompletedProcess(
            args, 0, stdout="success: netuid 999", stderr="netuid 999"
        )

    monkeypatch.setattr(_setup.subprocess, "run", fake_subprocess_run)

    assert _setup.create_subnet_if_needed(
        1, "owner", "ws://chain.example:9944"
    ) == 2
    assert sdk_calls == ["ws://chain.example:9944", "ws://chain.example:9944"]
    assert calls == [
        (
            [
                "btcli",
                "subnet",
                "create",
                "--wallet",
                "owner",
                "--wallet-hotkey",
                "default",
                "--network",
                "ws://chain.example:9944",
                "--yes",
                "--json",
            ],
            {
                "check": True,
                "capture_output": True,
                "text": True,
                "shell": False,
            },
        )
    ]
    output = capsys.readouterr()
    assert "999" not in output.out
    assert "999" not in output.err


@pytest.mark.parametrize(
    "failure",
    [
        _setup.subprocess.CalledProcessError(
            1, ["btcli"], output="hostile stdout", stderr="hostile stderr"
        ),
        RuntimeError("hostile upstream error"),
    ],
)
def test_create_subnet_normalizes_cli_failure_without_output_or_chain(
    monkeypatch, capsys, failure
):
    _install_snapshot_subtensor(monkeypatch, [[_SnapshotSubnet(0), _SnapshotSubnet(1)]])

    def failing_subprocess_run(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(_setup.subprocess, "run", failing_subprocess_run)

    with pytest.raises(RuntimeError, match=r"^subnet creation failed$") as error:
        _setup.create_subnet_if_needed(1, "owner")

    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    output = capsys.readouterr()
    assert "hostile" not in output.out
    assert "hostile" not in output.err
    assert "hostile" not in str(error.value)


@pytest.mark.parametrize(
    "snapshots, error_message",
    [
        (
            [
                [_SnapshotSubnet(0), _SnapshotSubnet(1)],
                [_SnapshotSubnet(0), _SnapshotSubnet(1)],
            ],
            "subnet creation did not yield exactly one new netuid",
        ),
        (
            [
                [_SnapshotSubnet(0), _SnapshotSubnet(1)],
                [_SnapshotSubnet(0), _SnapshotSubnet(1), _SnapshotSubnet(2), _SnapshotSubnet(3)],
            ],
            "subnet creation did not yield exactly one new netuid",
        ),
        ([[_SnapshotSubnet(0), _SnapshotSubnet(True)]], "invalid subnet netuid snapshot"),
        ([[_SnapshotSubnet(0), _SnapshotSubnet(-1)]], "invalid subnet netuid snapshot"),
        ([[_SnapshotSubnet(0), _SnapshotSubnet("2")]], "invalid subnet netuid snapshot"),
        ([[_SnapshotSubnet(0), _SnapshotSubnet(0)]], "invalid subnet netuid snapshot"),
    ],
)
def test_create_subnet_fails_closed_for_invalid_or_ambiguous_live_postconditions(
    monkeypatch, snapshots, error_message
):
    _install_snapshot_subtensor(monkeypatch, snapshots)

    def successful_subprocess_run(args, **_kwargs):
        return _setup.subprocess.CompletedProcess(args, 0, stdout="success")

    monkeypatch.setattr(_setup.subprocess, "run", successful_subprocess_run)

    with pytest.raises(RuntimeError, match=rf"^{error_message}$") as error:
        _setup.create_subnet_if_needed(1, "owner")

    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_snapshot_subnet_netuids_normalizes_sdk_failure_without_chain(monkeypatch):
    class FakeSubtensor:
        def __init__(self, network):
            self.subnets = SimpleNamespace(
                subnets=lambda: (_ for _ in ()).throw(RuntimeError("hostile sdk error"))
            )

    monkeypatch.setattr(_setup, "bt", SimpleNamespace(Subtensor=FakeSubtensor))

    with pytest.raises(RuntimeError, match=r"^unable to snapshot subnet netuids$") as error:
        _setup._snapshot_subnet_netuids("ws://chain.example:9944")

    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "hostile" not in str(error.value)


def test_create_subnet_dry_run_skips_sdk_and_subprocess_and_returns_preview(
    monkeypatch, capsys
):
    def must_not_construct_subtensor(*_args, **_kwargs):
        raise AssertionError("dry-run must not query the chain")

    def must_not_run_subprocess(*_args, **_kwargs):
        raise AssertionError("dry-run must not create a subnet")

    monkeypatch.setattr(
        _setup, "bt", SimpleNamespace(Subtensor=must_not_construct_subtensor)
    )
    monkeypatch.setattr(_setup.subprocess, "run", must_not_run_subprocess)

    assert _setup.create_subnet_if_needed(41, "owner", dry_run=True) == 41
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""


def test_start_emissions_uses_checked_direct_v11_activation_command(
    monkeypatch, capsys
):
    calls = []

    def capture_run(args, **kwargs):
        calls.append((args, kwargs))
        return _setup.subprocess.CompletedProcess(
            args, 0, stdout="discarded stdout", stderr="discarded stderr"
        )

    monkeypatch.setattr(_setup.subprocess, "run", capture_run)

    _setup.start_emissions(42, "owner", "ws://chain.example:9944")

    assert calls == [
        (
            [
                "btcli",
                "sudo",
                "start",
                "--netuid",
                "42",
                "--wallet",
                "owner",
                "--wallet-hotkey",
                "default",
                "--network",
                "ws://chain.example:9944",
                "--yes",
                "--no-mev-shield",
            ],
            {"check": True, "capture_output": True, "text": True, "shell": False},
        )
    ]
    captured = capsys.readouterr()
    assert "discarded stdout" not in captured.out
    assert "discarded stderr" not in captured.out


def test_add_stake_uses_checked_direct_alice_validator_command(monkeypatch, capsys):
    calls = []

    def capture_run(args, **kwargs):
        calls.append((args, kwargs))
        return _setup.subprocess.CompletedProcess(
            args, 0, stdout="discarded stdout", stderr="discarded stderr"
        )

    monkeypatch.setattr(_setup.subprocess, "run", capture_run)

    _setup.add_stake(42, "alice", 1, "ws://chain.example:9944")

    assert calls == [
        (
            [
                "btcli",
                "stake",
                "add",
                "--netuid",
                "42",
                "--wallet",
                "alice",
                "--wallet-hotkey",
                "default",
                "--amount-tao",
                "1",
                "--network",
                "ws://chain.example:9944",
                "--yes",
                "--no-mev-shield",
            ],
            {"check": True, "capture_output": True, "text": True, "shell": False},
        )
    ]
    captured = capsys.readouterr()
    assert "discarded stdout" not in captured.out
    assert "discarded stderr" not in captured.out


@pytest.mark.parametrize(
    ("helper", "args", "error_message"),
    [
        (
            _setup.start_emissions,
            (42, "owner", "ws://chain.example:9944"),
            "subnet activation failed",
        ),
        (
            _setup.add_stake,
            (42, "alice", 1, "ws://chain.example:9944"),
            "validator stake failed",
        ),
    ],
)
def test_local_readiness_helpers_normalize_ordinary_command_failures(
    monkeypatch, capsys, helper, args, error_message
):
    def fail(*_args, **_kwargs):
        raise _setup.subprocess.CalledProcessError(
            1, ["btcli"], output="hostile stdout", stderr="hostile stderr"
        )

    monkeypatch.setattr(_setup.subprocess, "run", fail)

    with pytest.raises(RuntimeError, match=rf"^{error_message}$") as error:
        helper(*args)

    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    output = capsys.readouterr()
    assert "hostile" not in output.out
    assert "hostile" not in output.err


@pytest.mark.parametrize(
    ("helper", "args", "preview"),
    [
        (
            _setup.start_emissions,
            (42, "owner-must-not-appear", "ws://chain.example:9944"),
            "[DRY-RUN] subnet activation would be executed\n",
        ),
        (
            _setup.add_stake,
            (42, "alice-must-not-appear", 1, "ws://chain.example:9944"),
            "[DRY-RUN] validator stake would be executed\n",
        ),
    ],
)
def test_local_readiness_helpers_dry_run_is_private_and_does_not_execute(
    monkeypatch, capsys, helper, args, preview
):
    monkeypatch.setattr(
        _setup.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("dry-run must not execute subprocess")
        ),
    )
    monkeypatch.setattr(
        _setup,
        "bt",
        SimpleNamespace(
            Subtensor=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("dry-run must not query SDK")
            )
        ),
    )

    helper(*args, dry_run=True)

    assert capsys.readouterr().out == preview


class _StatusFile:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def write(self, _value):
        return None


def _stub_setup_main(monkeypatch, ownership, events):
    monkeypatch.setattr(sys, "argv", ["setup_single_node.py"])
    monkeypatch.setattr(_setup, "wait_for_chain", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        _setup, "ensure_dev_wallet", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(_setup, "fund_from_alice", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(_setup.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        _setup, "create_subnet_if_needed", lambda *_args, **_kwargs: 42
    )
    monkeypatch.setattr(
        _setup,
        "register_neuron",
        lambda _netuid, wallet, *_args, **_kwargs: events.append(
            ("registration", wallet)
        ),
    )
    monkeypatch.setattr(
        _setup,
        "add_stake",
        lambda netuid, wallet, amount=1, chain_endpoint="", **_kwargs: events.append(
            ("stake", netuid, wallet, amount, chain_endpoint)
        ),
    )
    monkeypatch.setattr(
        _setup,
        "get_wallet_coldkey_ss58",
        lambda *_args, **_kwargs: "5OWNER",
    )
    monkeypatch.setattr(
        _setup.chain_state,
        "query_subnet_ownership",
        lambda *_args, **_kwargs: ownership,
    )
    monkeypatch.setattr(
        _setup,
        "start_emissions",
        lambda netuid, owner, endpoint, **_kwargs: events.append(
            ("activation", netuid, owner, endpoint)
        ),
    )
    monkeypatch.setattr(
        _setup,
        "set_conviction_and_recycle",
        lambda *_args, **_kwargs: events.append(("hyperparameters",)),
    )
    monkeypatch.setattr(_setup, "open", lambda *_args, **_kwargs: _StatusFile(), raising=False)


def test_main_activates_then_stakes_only_alice_after_exact_triad_registration(
    monkeypatch
):
    events = []
    _stub_setup_main(
        monkeypatch,
        {"exists": True, "owner_ss58": "5OWNER", "owned_by_us": True, "error": None},
        events,
    )

    _setup.main()

    assert [event for event in events if event[0] == "registration"] == [
        ("registration", "owner"),
        ("registration", "alice"),
        ("registration", "bob"),
    ]
    readiness = [
        event for event in events if event[0] in {"activation", "stake"}
    ]
    assert readiness == [
        ("activation", 42, "owner", "ws://127.0.0.1:9944"),
        ("stake", 42, "alice", 1, "ws://127.0.0.1:9944"),
    ]


@pytest.mark.parametrize(
    "ownership",
    [
        {"exists": None, "owner_ss58": None, "owned_by_us": False, "error": "rpc"},
        {"exists": False, "owner_ss58": None, "owned_by_us": False, "error": None},
        {"exists": True, "owner_ss58": "5OTHER", "owned_by_us": False, "error": None},
    ],
)
def test_main_fails_closed_for_every_negative_ownership_decision(
    monkeypatch, ownership
):
    events = []
    _stub_setup_main(monkeypatch, ownership, events)

    with pytest.raises(
        RuntimeError, match=r"^subnet ownership verification failed$"
    ) as error:
        _setup.main()

    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert [event for event in events if event[0] in {"activation", "stake"}] == []
