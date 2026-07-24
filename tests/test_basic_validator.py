"""g004 V6: basic validator process assembly (TDD, red first).

Replaces the retired owner-validator test module (D8): the connection-reuse regression
(HTTP 429 lesson, AC6) and the owner-only weight expectations migrate here
against the new module. New coverage per plan V6:

- D14 fail-fast startup: every static config error (share, poll interval,
  max skips, reconcile params, hotkeys, RANCHER_*) refuses to start with a
  clear error that names the variable and never echoes the token.
- D14 liveness corollary: a runtime Rancher outage, a rejected set_weights,
  and an injected unexpected in-cycle exception each degrade to skip/backoff
  and the loop demonstrably continues - the process never exits.
- Cycle order per spec 4.2: metagraph -> Rancher enumeration ->
  reconciliation -> scoring -> weights -> log + metrics.
- AC5 process-boundary log capture: Rancher error path, set_weights
  rejection, reconciliation suppression - no token/credential/body ever
  appears in captured logs, including rendered exceptions.

No test here imports real bittensor: the module defers that import to
main(), and every chain seam is injected.
"""

# Protocol fakes intentionally accept unused arguments, and these tests probe
# private cycle boundaries to verify fail-closed ordering.
# pylint: disable=unused-argument,protected-access

from __future__ import annotations

import copy
import json
import logging
import pathlib
import sys

import pytest
from bittensor.result import ExtrinsicResult

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from infrastructure_validation import (
    BINDING_ID_LABEL,
    BINDING_STATUS_LABEL,
    COLDKEY_LABEL,
    ENROLLMENT_UID_ANNOTATION,
    GENERATION_LABEL,
    HOTKEY_LABEL,
    NETUID_LABEL,
    NETWORK_LABEL,
    ORIGIN_FP_PREFIX_LABEL,
    PROVIDER_ID_LABEL,
    ValidationProfile,
)
from rancher_client import ErrorCategory, RancherClient, RancherError
from reconciliation import ReconciliationEngine
from validator import (
    BasicValidator,
    ConfigError,
    ValidatorConfig,
    _log_reconciliation_evidence,
    load_config,
    main,
)
import validator as validator_module
from validator_metrics import ValidatorMetrics

OWNER = "5OwnerHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE"
VALIDATOR = "5ValidatorHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE"
BOB = "5BobHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEab"
CAROL = "5CarolHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE"
OWNER_COLDKEY = "5OwnerColdkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAK"
VALIDATOR_COLDKEY = "5ValidatorColdkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFA"
BOB_COLDKEY = "5BobColdkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEa"
CAROL_COLDKEY = "5CarolColdkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFA"
TOKEN = "token-fake12345:pretendsecretvalue"

BASE_ENV = {
    "KUBETEE_VALIDATOR_HOTKEY": VALIDATOR,
    "RANCHER_URL": "https://rancher.example.test",
    "RANCHER_BEARER_TOKEN": TOKEN,
    "KUBETEE_CHAIN_NETWORK": "finney",
    "KUBETEE_VALIDATION_PROFILE": "debug",
    # Scoring v2: cycle tests exercise scoring/weights directly; the
    # probation gate has its own dedicated tests.
    "KUBETEE_PROBATION_CYCLES": "0",
    # Scoring v3: pin the conversion so a 1-node debug miner's target is
    # 1 node x $2/h (H100 card) x 1.2h = 2.4 alpha, and bucket 24 makes the
    # dynamic share exactly 0.1 -> historical [0.9, 0, 0.1] expectations hold.
    "KUBETEE_USD_PER_ALPHA_OVERRIDE": "1.0",
    "KUBETEE_MINER_BUCKET_ALPHA_OVERRIDE": "24",
    # Pinned TEST card (cheapest class $2 drives the debug node price);
    # the production default card is asserted in its own tests.
    "KUBETEE_GPU_USD_PRICES": "H100=2.00,H200=2.34,B200=4.34,B300=5.34",
}


def make_env(**overrides) -> dict:
    env = dict(BASE_ENV)
    env.update(overrides)
    return {k: v for k, v in env.items() if v is not None}


# ---------------------------------------------------------------------------
# fakes (no bittensor anywhere)
# ---------------------------------------------------------------------------


class _StopLoop(BaseException):
    """Stops run_forever from tests; BaseException so the liveness guard
    (which must catch only Exception) can never swallow it."""


class FakeNeuron:
    def __init__(self, uid: int, hotkey: str, coldkey: str):
        self.uid = uid
        self.hotkey = hotkey
        self.coldkey = coldkey


class FakeMetagraph:
    def __init__(
        self,
        neurons: list[FakeNeuron],
        block: int = 100,
        owner_hotkey: str | None = OWNER,
    ):
        self.neurons = neurons
        self.block = block
        self.owner_hotkey = owner_hotkey


class _FakeBalance:
    def __init__(self, tao: float = 0.0):
        self.tao = tao


class FakeSubnetsNamespace:
    """Mimics subtensor.subnets in v11."""

    def __init__(
        self,
        neurons: list[dict],
        metagraph_errors=None,
        calls: list | None = None,
        owner_hotkey: str | None = OWNER,
    ):
        self._neurons = neurons
        self._metagraph_errors = list(metagraph_errors or [])
        self.calls = calls if calls is not None else []
        self._owner_hotkey = owner_hotkey

    def metagraph(self, netuid: int, block: int | None = None):
        self.calls.append("metagraph")
        if self._metagraph_errors:
            error = self._metagraph_errors.pop(0)
            if error is not None:
                raise error
        return FakeMetagraph(
            [
                FakeNeuron(n["uid"], n["hotkey"], n["coldkey"])
                for n in self._neurons
            ],
            block=100 if block is None else block,
            owner_hotkey=self._owner_hotkey,
        )


class FakeStakingNamespace:
    """Mimics bt.staking v11 namespace."""

    def get(self, coldkey, hotkey, netuid):
        return _FakeBalance(0.0)


class FakeSubtensor:
    def __init__(
        self,
        neurons: list[dict],
        set_weights_results=None,
        metagraph_errors=None,
        calls: list | None = None,
        owner_hotkey: str | None = OWNER,
    ):
        self.subnets = FakeSubnetsNamespace(
            neurons,
            metagraph_errors=metagraph_errors,
            calls=calls,
            owner_hotkey=owner_hotkey,
        )
        self.staking = FakeStakingNamespace()
        self.hyperparameters = object()
        self.set_weights_calls: list[dict] = []
        self._set_weights_results = list(set_weights_results or [])
        self.calls = calls if calls is not None else []
        self._next_block = 100

    def block(self) -> int:
        block = self._next_block
        self._next_block += 1
        return block

    def execute(self, intent, wallet):
        self.calls.append("set_weights")
        self.set_weights_calls.append(
            {
                "wallet": wallet,
                "netuid": intent.netuid,
                "uids": intent.uids,
                "weights": intent.weights,
            }
        )
        if self._set_weights_results:
            raw = self._set_weights_results.pop(0)
            if isinstance(raw, Exception):
                raise raw
            if isinstance(raw, ExtrinsicResult):
                return raw
            success, message = raw
            return ExtrinsicResult(success=success, message=message)
        return ExtrinsicResult(success=True, message="ok")


class FakeRancher:
    def __init__(
        self,
        clusters: list[dict] | None = None,
        nodes_by_cluster: dict[str, list[dict]] | None = None,
        list_error: Exception | None = None,
        node_errors: dict[str, Exception] | None = None,
        calls: list | None = None,
    ):
        self.clusters = clusters or []
        self.nodes_by_cluster = nodes_by_cluster or {}
        self.list_error = list_error
        self.node_errors = node_errors or {}
        self.calls = calls if calls is not None else []

    def list_clusters(self) -> list[dict]:
        self.calls.append("list_clusters")
        if self.list_error is not None:
            raise self.list_error
        return self.clusters

    def list_nodes(self, cluster_id: str) -> list[dict]:
        self.calls.append("list_nodes")
        if cluster_id in self.node_errors:
            raise self.node_errors[cluster_id]
        return self.nodes_by_cluster.get(cluster_id, [])


class FakeReconciler:
    def __init__(
        self, calls: list | None = None, error: Exception | None = None
    ):
        self.calls = calls if calls is not None else []
        self.run_args: list[dict] = []
        self.error = error

    def run_cycle(
        self, registered_hotkeys, clusters, metagraph_block, refresh
    ):
        self.calls.append("reconcile")
        self.run_args.append(
            {
                "registered": registered_hotkeys,
                "clusters": clusters,
                "block": metagraph_block,
            }
        )
        if self.error is not None:
            raise self.error


def neurons_triad() -> list[dict]:
    return [
        {"uid": 0, "hotkey": OWNER, "coldkey": OWNER_COLDKEY},
        {"uid": 1, "hotkey": VALIDATOR, "coldkey": VALIDATOR_COLDKEY},
        {"uid": 2, "hotkey": BOB, "coldkey": BOB_COLDKEY},
    ]


def active_bob_cluster() -> tuple[list[dict], dict[str, list[dict]]]:
    clusters = [
        {
            "id": "c-bob",
            "uuid": "00000000-0000-4000-8000-000000000002",
            "state": "active",
            "transitioning": "no",
            "labels": {
                "kubetee.ai/binding-id": "binding-bob",
                HOTKEY_LABEL: BOB,
                "kubetee.ai/coldkey": BOB_COLDKEY,
                "kubetee.ai/provider-id": "00000000-0000-4000-8000-000000000002",
                "kubetee.ai/binding-status": "ENROLLED",
                "kubetee.ai/generation": "1",
                "kubetee.ai/netuid": "1",
                "kubetee.ai/network": "finney",
                "kubetee.ai/origin-fp-prefix": "a" * 63,
            },
            "annotations": {"kubetee.ai/enrollment-uid": "2"},
        }
    ]
    nodes = {
        "c-bob": [
            {
                "id": "c-bob:node-1",
                "clusterId": "c-bob",
                "state": "active",
                "transitioning": "no",
            }
        ]
    }
    return clusters, nodes


def build_validator(
    config: ValidatorConfig | None = None,
    subtensor: FakeSubtensor | None = None,
    rancher: FakeRancher | None = None,
    reconciler: FakeReconciler | None = None,
    metrics: ValidatorMetrics | None = None,
    sleep=None,
    factory_calls: list | None = None,
):
    config = config or ValidatorConfig.from_env(make_env())
    subtensor = (
        subtensor if subtensor is not None else FakeSubtensor(neurons_triad())
    )
    rancher = rancher if rancher is not None else FakeRancher()
    reconciler = reconciler if reconciler is not None else FakeReconciler()
    metrics = metrics or ValidatorMetrics(
        max_consecutive_skips=config.max_consecutive_skips
    )
    factory_calls = factory_calls if factory_calls is not None else []

    def factory():
        factory_calls.append("subtensor")
        return subtensor

    validator = BasicValidator(
        config=config,
        subtensor_factory=factory,
        wallet=object(),
        rancher=rancher,
        metrics=metrics,
        reconciler=reconciler,
        sleep=sleep or (lambda seconds: None),
    )
    return validator, subtensor, rancher, reconciler, metrics, factory_calls


def stop_after(n: int, record: list | None = None):
    calls = record if record is not None else []

    def fake_sleep(seconds):
        calls.append(seconds)
        if len(calls) >= n:
            raise _StopLoop()

    return fake_sleep, calls


def sample(metrics: ValidatorMetrics, name: str, **labels) -> float:
    return metrics.registry.get_sample_value(name, labels or None) or 0.0


# ---------------------------------------------------------------------------
# D14 fail-fast startup configuration
# ---------------------------------------------------------------------------


def test_from_env_happy_path_pins_plan_defaults():
    config = ValidatorConfig.from_env(make_env())
    assert config.payout_window_hours == 1.2
    assert config.price_divergence_max == 0.10
    assert config.poll_seconds == 60.0
    assert config.max_consecutive_skips == 10
    assert config.reconcile_min_cycles == 3
    assert config.reconcile_min_seconds == 900.0
    assert config.wallet_name == "alice"
    assert config.validator_hotkey == VALIDATOR
    assert config.chain_network == "finney"
    assert config.validation_profile is ValidationProfile.DEBUG


@pytest.mark.parametrize("profile", [None, ""])
def test_missing_validation_profile_defaults_to_production(profile):
    config = ValidatorConfig.from_env(
        make_env(
            KUBETEE_VALIDATION_PROFILE=profile,
            BT_NETWORK="finney",
            BT_WALLET="validator",
            BT_WALLET_HOTKEY="default",
            KUBETEE_SUBNET_NETUID="90",
        )
    )

    assert config.validation_profile is ValidationProfile.PRODUCTION
    assert config.poll_seconds == 60.0


def test_owner_hotkey_is_resolved_from_selected_metagraph():
    config = ValidatorConfig.from_env(make_env())
    subtensor = FakeSubtensor(neurons_triad(), owner_hotkey=OWNER)
    validator, subtensor, _, _, _, _ = build_validator(
        config=config, subtensor=subtensor
    )

    assert validator.run_cycle() == "weights_set"
    assert subtensor.set_weights_calls[0]["weights"] == [1.0, 0.0, 0.0]


def test_debug_main_runs_local_bootstrap_with_redacted_subprocess(monkeypatch):
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed.update(kwargs)
        return object()

    monkeypatch.setattr(validator_module.subprocess, "run", fake_run)
    env = make_env(
        BT_NETWORK="ws://chain:9944",
        KUBETEE_OWNER_WALLET="owner",
    )
    config = ValidatorConfig.from_env(env)

    validator_module._bootstrap_if_debug(config, env)

    command = observed["command"]
    assert command[0] == sys.executable
    assert command[1:3] == ["-u", str(validator_module._SETUP_SCRIPT)]
    assert command[3:] == [
        "--netuid",
        "1",
        "--owner-wallet",
        "owner",
        "--chain-endpoint",
        "ws://chain:9944",
    ]
    assert observed["check"] is True
    assert observed["capture_output"] is True
    assert observed["text"] is True
    assert observed["env"] == env


def test_production_main_skips_local_bootstrap(monkeypatch):
    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        validator_module, "_run_local_bootstrap", fail_if_called
    )
    env = make_env(
        KUBETEE_VALIDATION_PROFILE="production",
        BT_NETWORK="finney",
        BT_WALLET="validator",
        BT_WALLET_HOTKEY="default",
        KUBETEE_SUBNET_NETUID="90",
    )
    config = ValidatorConfig.from_env(env)

    validator_module._bootstrap_if_debug(config, env)

    assert called is False


@pytest.mark.parametrize(
    "missing",
    [
        "RANCHER_URL",
        "RANCHER_BEARER_TOKEN",
        "KUBETEE_VALIDATOR_HOTKEY",
        "KUBETEE_CHAIN_NETWORK",
    ],
)
def test_missing_static_config_refuses_to_start(missing):
    env = make_env(**{missing: None})
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(env)
    assert missing in str(excinfo.value)
    assert TOKEN not in str(excinfo.value)


@pytest.mark.parametrize("value", ["-0.1", "abc", "nan", "inf", "0"])
def test_invalid_price_override_refuses_to_start(value):
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(
            make_env(KUBETEE_USD_PER_ALPHA_OVERRIDE=value)
        )
    assert "KUBETEE_USD_PER_ALPHA_OVERRIDE" in str(excinfo.value)


def test_missing_price_source_refuses_to_start():
    """No override and no taostats key -> the validator cannot price."""
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(KUBETEE_USD_PER_ALPHA_OVERRIDE=None))
    assert "TAOSTATS_API_KEY" in str(excinfo.value)


def test_invalid_usd_card_refuses_to_start():
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(KUBETEE_GPU_USD_PRICES="H100=zero"))
    assert "KUBETEE_GPU_USD_PRICES" in str(excinfo.value)


def test_empty_tunables_fall_back_to_pinned_defaults():
    """Compose passes tunables through as ${VAR:-}; an empty value means
    'not configured' and takes the plan-pinned default. Credentials and
    hotkeys never do this - empty is missing there (D14)."""
    config = ValidatorConfig.from_env(
        make_env(
            KUBETEE_POLL_SECONDS="",
            KUBETEE_MAX_CONSECUTIVE_SKIPS="",
            KUBETEE_PAYOUT_WINDOW_HOURS="",
        )
    )
    assert config.payout_window_hours == 1.2
    assert config.poll_seconds == 60.0
    assert config.max_consecutive_skips == 10


def test_debug_profile_allows_five_second_poll_interval():
    """Debug UAT may use the approved five-second cadence."""
    config = ValidatorConfig.from_env(make_env(KUBETEE_POLL_SECONDS="5"))
    assert config.poll_seconds == 5.0


def test_debug_profile_keeps_sixty_second_default_poll_interval():
    """An unset cadence keeps the fixed production-safe default."""
    config = ValidatorConfig.from_env(make_env(KUBETEE_POLL_SECONDS=None))
    assert config.poll_seconds == 60.0


@pytest.mark.parametrize(
    "poll", ["4.999", "0", "-5", "junk", "nan", "inf", "-inf"]
)
def test_debug_profile_rejects_invalid_poll_intervals(poll):
    """Debug may lower the floor, but never bypass numeric validation."""
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(KUBETEE_POLL_SECONDS=poll))
    assert "KUBETEE_POLL_SECONDS" in str(excinfo.value)
    assert TOKEN not in str(excinfo.value)


@pytest.mark.parametrize("poll", ["59.999", "5", "0", "-5"])
def test_production_profile_rejects_poll_intervals_below_sixty_seconds(poll):
    """Production retains the original sixty-second lower bound."""
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(
            make_env(
                KUBETEE_VALIDATION_PROFILE="production",
                KUBETEE_POLL_SECONDS=poll,
                BT_NETWORK="finney",
                BT_WALLET="validator",
                BT_WALLET_HOTKEY="default",
                KUBETEE_SUBNET_NETUID="90",
            )
        )
    assert "KUBETEE_POLL_SECONDS" in str(excinfo.value)
    assert TOKEN not in str(excinfo.value)


def test_production_profile_allows_sixty_second_poll_interval():
    """The production boundary value remains valid."""
    config = ValidatorConfig.from_env(
        make_env(
            KUBETEE_VALIDATION_PROFILE="production",
            KUBETEE_POLL_SECONDS="60",
            BT_NETWORK="finney",
            BT_WALLET="validator",
            BT_WALLET_HOTKEY="default",
            KUBETEE_SUBNET_NETUID="90",
        )
    )
    assert config.poll_seconds == 60.0


@pytest.mark.parametrize("profile", ["staging"])
def test_invalid_profile_never_unlocks_debug_poll_interval(profile):
    """Only a parsed debug enum may unlock the UAT cadence."""
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(
            make_env(
                KUBETEE_VALIDATION_PROFILE=profile,
                KUBETEE_POLL_SECONDS="5",
            )
        )
    error = str(excinfo.value)
    assert "KUBETEE_VALIDATION_PROFILE" in error
    assert "KUBETEE_POLL_SECONDS" in error
    assert TOKEN not in error


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("KUBETEE_MAX_CONSECUTIVE_SKIPS", "0"),
        ("KUBETEE_MAX_CONSECUTIVE_SKIPS", "x"),
        ("KUBETEE_RECONCILE_MIN_CYCLES", "0"),
        ("KUBETEE_RECONCILE_MIN_SECONDS", "-1"),
        ("KUBETEE_SUBNET_NETUID", "no"),
        ("KUBETEE_METRICS_PORT", "0"),
        ("KUBETEE_METRICS_PORT", "70000"),
    ],
)
def test_invalid_numeric_config_refuses_to_start(var, value):
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(**{var: value}))
    assert var in str(excinfo.value)


@pytest.mark.parametrize(
    "url", ["http://insecure.example", "not-a-url", "ftp://x"]
)
def test_non_https_rancher_url_refuses_to_start(url):
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(RANCHER_URL=url))
    assert "RANCHER_URL" in str(excinfo.value)


@pytest.mark.parametrize(
    "url",
    [
        "https://rancher.example/v3",
        "https://rancher.example?scope=all",
        "https://rancher.example#fragment",
        "https://user:embedded-secret@rancher.example",
    ],
)
def test_rancher_url_must_be_an_origin_without_credentials(url):
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(RANCHER_URL=url))
    assert "RANCHER_URL" in str(excinfo.value)
    assert "embedded-secret" not in str(excinfo.value)


@pytest.mark.parametrize("profile", ["DEBUG", "staging"])
def test_invalid_validation_profile_refuses_to_start(profile):
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(KUBETEE_VALIDATION_PROFILE=profile))
    assert "KUBETEE_VALIDATION_PROFILE" in str(excinfo.value)


def test_validation_profile_ignores_outer_whitespace_only():
    config = ValidatorConfig.from_env(
        make_env(
            KUBETEE_VALIDATION_PROFILE=" production ",
            BT_NETWORK="finney",
            BT_WALLET="validator",
            BT_WALLET_HOTKEY="default",
            KUBETEE_SUBNET_NETUID="90",
        )
    )
    assert config.validation_profile is ValidationProfile.PRODUCTION


@pytest.mark.parametrize(
    "missing",
    ["BT_NETWORK", "BT_WALLET", "BT_WALLET_HOTKEY", "KUBETEE_SUBNET_NETUID"],
)
def test_production_profile_requires_explicit_chain_and_wallet(missing):
    env = make_env(
        KUBETEE_VALIDATION_PROFILE="production",
        BT_NETWORK="finney",
        BT_WALLET="validator",
        BT_WALLET_HOTKEY="default",
        KUBETEE_SUBNET_NETUID="90",
    )
    env.pop(missing)

    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(env)

    assert missing in str(excinfo.value)


def test_netuid_file_overrides_env(tmp_path):
    netuid_file = tmp_path / "netuid"
    netuid_file.write_text("7\n")
    config = load_config(
        make_env(
            KUBETEE_SUBNET_NETUID="1", KUBETEE_NETUID_FILE=str(netuid_file)
        )
    )
    assert config.netuid == 7


def test_main_refuses_to_start_without_credentials():
    """D14 startup half of AC9(c): missing RANCHER_* is a clear config error,
    exit - never a skip loop. Reaches SystemExit before any bittensor import.

    Asserts on the ConfigError chained onto SystemExit instead of captured
    logs: in the full CI suite bittensor's import-time logging side effects
    break root-level caplog capture, and the refusal contract is the exit
    code plus the error naming every missing variable."""
    with pytest.raises(SystemExit) as excinfo:
        main(env={})
    assert excinfo.value.code == 2
    cause = excinfo.value.__cause__
    assert isinstance(cause, ConfigError)
    assert "RANCHER_URL" in str(cause)
    assert "RANCHER_BEARER_TOKEN" in str(cause)
    assert "KUBETEE_CHAIN_NETWORK" in str(cause)
    assert "KUBETEE_VALIDATION_PROFILE" not in str(cause)


# ---------------------------------------------------------------------------
# migrated owner-validator expectations (D8) + AC6 connection reuse
# ---------------------------------------------------------------------------


def test_loop_reuses_single_injected_connection():
    """Migrated HTTP 429 regression (AC6): healthy cycles never construct a
    second chain connection; the factory runs exactly once per process."""
    sleep, sleep_calls = stop_after(3)
    validator, subtensor, _, _, _, factory_calls = build_validator(sleep=sleep)

    with pytest.raises(_StopLoop):
        validator.run_forever()

    assert factory_calls == ["subtensor"]
    assert len(subtensor.set_weights_calls) == 3
    assert sleep_calls == [60.0, 60.0, 60.0]


def test_owner_only_mode_when_no_miners_registered():
    """No discovered miners -> 100% owner weight (today's recycle behavior)."""
    subtensor = FakeSubtensor(
        [
            {"uid": 0, "hotkey": OWNER, "coldkey": OWNER_COLDKEY},
            {
                "uid": 1,
                "hotkey": VALIDATOR,
                "coldkey": VALIDATOR_COLDKEY,
            },
        ]
    )
    validator, *_ = build_validator(subtensor=subtensor)

    outcome = validator.run_cycle()

    assert outcome == "weights_set"
    call = subtensor.set_weights_calls[0]
    assert call["uids"] == [0, 1]
    assert call["weights"] == [1.0, 0.0]


def test_healthy_miner_gets_share_and_owner_gets_rest():
    clusters, nodes = active_bob_cluster()
    validator, subtensor, _, _, metrics, _ = build_validator(
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes)
    )

    assert validator.run_cycle() == "weights_set"
    call = subtensor.set_weights_calls[0]
    assert call["netuid"] == 1
    assert call["uids"] == [0, 1, 2]
    assert call["weights"] == pytest.approx([0.9, 0.0, 0.1])
    assert sample(metrics, "kubetee_set_weights_total", result="success") == 1
    assert sample(metrics, "kubetee_miners_discovered") == 1
    assert sample(metrics, "kubetee_miners_scoring") == 1
    assert sample(metrics, "kubetee_validation_status", status="eligible") == 1
    assert sample(metrics, "kubetee_validation_reason", reason="eligible") == 1


def test_metagraph_coldkey_reaches_validator_snapshot():
    validator, subtensor, *_ = build_validator()

    neurons, block, owner_hotkey = validator._read_neurons(subtensor)

    assert block == 100
    assert owner_hotkey == OWNER
    assert neurons[2] == {
        "uid": 2,
        "hotkey": BOB,
        "coldkey": BOB_COLDKEY,
    }


def test_invalid_metagraph_suppresses_rancher_and_reconciliation_actions():
    duplicate = [
        *neurons_triad(),
        {"uid": 3, "hotkey": BOB, "coldkey": BOB_COLDKEY},
    ]
    rancher = FakeRancher()
    reconciler = FakeReconciler()
    validator, subtensor, *_ = build_validator(
        subtensor=FakeSubtensor(duplicate),
        rancher=rancher,
        reconciler=reconciler,
    )

    assert validator.run_cycle() == "skip"

    assert subtensor.set_weights_calls == []
    assert rancher.calls == []
    assert reconciler.run_args[0]["registered"] is None
    assert reconciler.run_args[0]["clusters"] is None


def test_missing_raw_metagraph_identity_is_not_stringified_into_valid_data():
    snapshot = neurons_triad()
    snapshot[2]["coldkey"] = None
    rancher = FakeRancher()
    reconciler = FakeReconciler()
    validator, *_ = build_validator(
        subtensor=FakeSubtensor(snapshot),
        rancher=rancher,
        reconciler=reconciler,
    )

    assert validator.run_cycle() == "skip"
    assert rancher.calls == []
    assert reconciler.run_args[0]["registered"] is None


@pytest.mark.parametrize("raw_uid", ["2", 2.9])
def test_non_integral_raw_metagraph_uid_skips_before_rancher(raw_uid):
    snapshot = neurons_triad()
    snapshot[2]["uid"] = raw_uid
    rancher = FakeRancher()
    reconciler = FakeReconciler()
    validator, subtensor, *_ = build_validator(
        subtensor=FakeSubtensor(snapshot),
        rancher=rancher,
        reconciler=reconciler,
    )

    assert validator.run_cycle() == "skip"
    assert subtensor.set_weights_calls == []
    assert rancher.calls == []
    assert reconciler.run_args[0]["registered"] is None


def test_reconciliation_refresh_rejects_invalid_metagraph_identity():
    duplicate = [
        *neurons_triad(),
        {"uid": 3, "hotkey": BOB, "coldkey": BOB_COLDKEY},
    ]
    validator, *_ = build_validator(subtensor=FakeSubtensor(duplicate))
    validator._ensure_subtensor()

    assert validator._refresh_registered() is None


def test_missing_metagraph_block_skips_before_rancher():
    subtensor = FakeSubtensor(neurons_triad())
    read_metagraph = subtensor.subnets.metagraph

    def without_block(netuid, block=None):
        metagraph = read_metagraph(netuid, block=block)
        metagraph.block = None
        return metagraph

    subtensor.subnets.metagraph = without_block
    rancher = FakeRancher()
    validator, *_ = build_validator(subtensor=subtensor, rancher=rancher)

    assert validator.run_cycle() == "skip"
    assert rancher.calls == []


def test_repeated_metagraph_block_skips_the_later_cycle():
    class StaticBlockSubtensor(FakeSubtensor):
        def block(self):
            return 100

    clusters, nodes = active_bob_cluster()
    rancher = FakeRancher(clusters=clusters, nodes_by_cluster=nodes)
    validator, subtensor, *_ = build_validator(
        subtensor=StaticBlockSubtensor(neurons_triad()),
        rancher=rancher,
    )

    assert validator.run_cycle() == "weights_set"
    assert validator.run_cycle() == "skip"
    assert len(subtensor.set_weights_calls) == 1
    assert rancher.calls.count("list_clusters") == 1


def test_reconciliation_refresh_must_not_precede_cycle_block():
    class StaticBlockSubtensor(FakeSubtensor):
        def block(self):
            return 100

    validator, *_ = build_validator(
        subtensor=StaticBlockSubtensor(neurons_triad())
    )
    validator._ensure_subtensor()

    assert validator._refresh_registered(101) is None


@pytest.mark.parametrize("mutation", ["cluster_inactive", "no_nodes"])
def test_complete_binding_failure_scores_only_that_miner_zero(mutation):
    clusters, nodes = active_bob_cluster()
    if mutation == "cluster_inactive":
        clusters[0]["state"] = "unavailable"
    else:
        nodes["c-bob"] = []
    validator, subtensor, *_ = build_validator(
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes)
    )

    assert validator.run_cycle() == "weights_set"

    assert subtensor.set_weights_calls[0]["weights"] == [1.0, 0.0, 0.0]


def test_node_fetch_error_skips_whole_cycle_without_zeroing_miner():
    clusters, nodes = active_bob_cluster()
    rancher = FakeRancher(
        clusters=clusters,
        nodes_by_cluster=nodes,
        node_errors={
            "c-bob": RancherError(ErrorCategory.TRANSPORT, "node read failed")
        },
    )
    validator, subtensor, _, reconciler, metrics, _ = build_validator(
        rancher=rancher
    )

    assert validator.run_cycle() == "skip"

    assert subtensor.set_weights_calls == []
    assert reconciler.run_args[0]["clusters"] is None
    assert (
        sample(
            metrics,
            "kubetee_cycles_skipped_total",
            reason="rancher_unavailable",
        )
        == 1
    )


def test_two_miners_can_receive_different_complete_verdicts():
    clusters, nodes = active_bob_cluster()
    carol_cluster = copy.deepcopy(clusters[0])
    carol_cluster["id"] = "c-carol"
    carol_cluster["labels"]["kubetee.ai/binding-id"] = "binding-carol"
    carol_cluster["labels"][HOTKEY_LABEL] = CAROL
    carol_cluster["labels"]["kubetee.ai/coldkey"] = CAROL_COLDKEY
    carol_cluster["annotations"]["kubetee.ai/enrollment-uid"] = "3"
    clusters.append(carol_cluster)
    # Carol's cluster has no ready node inventory -> she scores zero via
    # NODE_INVENTORY_EMPTY while bob stays eligible (formerly Carol failed via
    # a PENDING binding-status, which is no longer a scoring input).
    nodes["c-carol"] = []
    snapshot = [
        *neurons_triad(),
        {"uid": 3, "hotkey": CAROL, "coldkey": CAROL_COLDKEY},
    ]
    validator, subtensor, *_ = build_validator(
        subtensor=FakeSubtensor(snapshot),
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes),
    )

    assert validator.run_cycle() == "weights_set"

    assert subtensor.set_weights_calls[0]["weights"] == pytest.approx(
        [0.9, 0.0, 0.1, 0.0]
    )


def test_registered_miner_without_cluster_scores_zero():
    """D10: Rancher reachable but no labeled cluster -> that miner scores 0."""
    validator, subtensor, _, _, metrics, _ = build_validator(
        rancher=FakeRancher(clusters=[])
    )

    assert validator.run_cycle() == "weights_set"
    call = subtensor.set_weights_calls[0]
    assert call["uids"] == [0, 1, 2]
    assert call["weights"] == [1.0, 0.0, 0.0]
    assert (
        sample(metrics, "kubetee_validation_status", status="suspended") == 1
    )
    assert (
        sample(
            metrics,
            "kubetee_validation_reason",
            reason="cluster_missing",
        )
        == 1
    )


def test_malformed_cluster_labels_score_zero_without_escaping_cycle():
    rancher = FakeRancher(
        clusters=[
            {
                "id": "c-malformed",
                "state": "active",
                "transitioning": "no",
                "labels": "not-a-mapping",
            }
        ]
    )
    validator, subtensor, _, _, metrics, _ = build_validator(rancher=rancher)

    assert validator.run_cycle() == "weights_set"

    assert subtensor.set_weights_calls[0]["weights"] == [1.0, 0.0, 0.0]
    assert (
        sample(
            metrics,
            "kubetee_validation_reason",
            reason="cluster_missing",
        )
        == 1
    )


def test_validation_logs_only_aggregate_reasons(caplog):
    clusters, nodes = active_bob_cluster()
    validator, *_ = build_validator(
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes)
    )

    with caplog.at_level(logging.INFO, logger="basic_validator"):
        assert validator.run_cycle() == "weights_set"

    assert "validation_reasons={'eligible': 1}" in caplog.text
    assert "binding-bob" not in caplog.text
    assert "kubetee.ai/enrollment-uid" not in caplog.text
    assert "a" * 63 not in caplog.text
    assert TOKEN not in caplog.text


# ---------------------------------------------------------------------------
# cycle order per spec 4.2
# ---------------------------------------------------------------------------


def test_cycle_order_metagraph_enumeration_reconciliation_weights():
    calls: list[str] = []
    clusters, nodes = active_bob_cluster()
    subtensor = FakeSubtensor(neurons_triad(), calls=calls)
    rancher = FakeRancher(
        clusters=clusters, nodes_by_cluster=nodes, calls=calls
    )
    reconciler = FakeReconciler(calls=calls)
    validator, *_ = build_validator(
        subtensor=subtensor, rancher=rancher, reconciler=reconciler
    )

    validator.run_cycle()

    assert calls == [
        "metagraph",
        "list_clusters",
        "list_nodes",
        "reconcile",
        "set_weights",
    ]
    assert reconciler.run_args[0]["registered"] == {OWNER, VALIDATOR, BOB}
    assert reconciler.run_args[0]["clusters"] == clusters


# ---------------------------------------------------------------------------
# fail-closed skips + D14 liveness corollary (the process never exits)
# ---------------------------------------------------------------------------


def test_metagraph_failure_skips_weights_and_loop_continues():
    subtensor = FakeSubtensor(
        neurons_triad(),
        metagraph_errors=[RuntimeError("ws down")] * 3,
    )
    sleep, sleep_calls = stop_after(3)
    validator, _, _, reconciler, metrics, _ = build_validator(
        subtensor=subtensor, sleep=sleep
    )

    with pytest.raises(_StopLoop):
        validator.run_forever()

    assert len(sleep_calls) == 3
    assert subtensor.set_weights_calls == []
    assert metrics.consecutive_skips == 3
    assert reconciler.run_args[0]["registered"] is None


def test_runtime_rancher_outage_skips_and_never_exits():
    """D14 liveness path 1 + D10: outage -> skip weights, count the error,
    suppress reconciliation, keep looping. Never score 0 for our outage."""
    rancher = FakeRancher(
        list_error=RancherError(ErrorCategory.TRANSPORT, "connect timeout")
    )
    sleep, sleep_calls = stop_after(3)
    validator, subtensor, _, reconciler, metrics, _ = build_validator(
        rancher=rancher, sleep=sleep
    )

    with pytest.raises(_StopLoop):
        validator.run_forever()

    assert len(sleep_calls) == 3
    assert subtensor.set_weights_calls == []
    assert (
        sample(metrics, "kubetee_rancher_errors_total", category="transport")
        == 3
    )
    assert (
        sample(
            metrics,
            "kubetee_cycles_skipped_total",
            reason="rancher_unavailable",
        )
        == 3
    )
    assert all(args["clusters"] is None for args in reconciler.run_args)
    assert all(
        args["registered"] == {OWNER, VALIDATOR, BOB}
        for args in reconciler.run_args
    )


def test_typed_extrinsic_result_success_records_accepted_weight():
    """The pinned SDK result's success field is the accepted-chain verdict."""
    subtensor = FakeSubtensor(
        neurons_triad(),
        set_weights_results=[ExtrinsicResult(success=True, message="ok")],
    )
    validator, _, _, _, metrics, _ = build_validator(subtensor=subtensor)

    assert validator.run_cycle() == "weights_set"
    assert sample(metrics, "kubetee_set_weights_total", result="success") == 1
    assert sample(metrics, "kubetee_set_weights_total", result="failure") == 0


def test_typed_extrinsic_result_rejection_records_failed_weight():
    """A typed rejected result is not confused with a raised submission."""
    subtensor = FakeSubtensor(
        neurons_triad(),
        set_weights_results=[
            ExtrinsicResult(success=False, message="rejected")
        ],
    )
    validator, _, _, _, metrics, _ = build_validator(subtensor=subtensor)

    assert validator.run_cycle() == "weights_rejected"
    assert sample(metrics, "kubetee_set_weights_total", result="success") == 0
    assert sample(metrics, "kubetee_set_weights_total", result="failure") == 1


def test_rejected_set_weights_is_honest_and_loop_continues(caplog):
    """D14 liveness path 2: chain rejection -> failure metric, redacted log,
    no success claim, loop continues."""
    subtensor = FakeSubtensor(
        neurons_triad(),
        set_weights_results=[(False, "no validator permit")] * 3,
    )
    sleep, sleep_calls = stop_after(3)
    validator, _, _, _, metrics, _ = build_validator(
        subtensor=subtensor, sleep=sleep
    )

    with (
        caplog.at_level(logging.INFO, logger="basic_validator"),
        pytest.raises(_StopLoop),
    ):
        validator.run_forever()

    assert len(sleep_calls) == 3
    assert sample(metrics, "kubetee_set_weights_total", result="failure") == 3
    assert sample(metrics, "kubetee_set_weights_total", result="success") == 0
    assert "accepted" not in caplog.text.lower()


def test_unexpected_in_cycle_exception_never_exits(caplog):
    """D14 liveness path 3: an injected unexpected exception degrades to
    backoff and the loop continues - only operator signals stop the process."""
    config = ValidatorConfig.from_env(
        make_env(KUBETEE_MAX_CONSECUTIVE_SKIPS="2")
    )
    hostile_marker = "ATTACKER-CONTROLLED-UNEXPECTED-ERROR"
    reconciler = FakeReconciler(error=RuntimeError(hostile_marker))
    sleep, sleep_calls = stop_after(3)
    validator, _subtensor, _, _, metrics, _ = build_validator(
        config=config,
        reconciler=reconciler,
        sleep=sleep,
    )

    with (
        caplog.at_level(logging.ERROR, logger="basic_validator"),
        pytest.raises(_StopLoop),
    ):
        validator.run_forever()

    assert len(sleep_calls) == 3
    assert "unexpected cycle error" in caplog.text
    assert hostile_marker not in caplog.text
    assert (
        sample(
            metrics,
            "kubetee_cycles_skipped_total",
            reason="unexpected_runtime",
        )
        == 3
    )
    assert metrics.consecutive_skips == 3
    assert metrics.degraded is True


def test_set_weights_transport_exception_recreates_connection_once():
    """Sessions are recreated only after a transport failure (bounded by the
    poll backoff), never per iteration."""
    subtensor = FakeSubtensor(
        neurons_triad(),
        set_weights_results=[RuntimeError("broken pipe"), (True, "ok")],
    )
    sleep, _ = stop_after(2)
    validator, _, _, _, metrics, factory_calls = build_validator(
        subtensor=subtensor, sleep=sleep
    )

    with pytest.raises(_StopLoop):
        validator.run_forever()

    assert factory_calls == ["subtensor", "subtensor"]
    assert sample(metrics, "kubetee_set_weights_total", result="failure") == 1
    assert sample(metrics, "kubetee_set_weights_total", result="success") == 1


def test_degraded_mode_entered_and_cleared(caplog):
    """AC13 logic wiring: consecutive skips beyond the max flag degraded mode
    loudly; a recovered scoring cycle clears it. No weights are auto-zeroed
    while degraded (no set_weights call happens at all)."""
    config = ValidatorConfig.from_env(
        make_env(KUBETEE_MAX_CONSECUTIVE_SKIPS="2")
    )
    rancher = FakeRancher(
        list_error=RancherError(ErrorCategory.TRANSPORT, "outage")
    )
    validator, subtensor, _, _, metrics, _ = build_validator(
        config=config, rancher=rancher
    )

    with caplog.at_level(logging.CRITICAL, logger="basic_validator"):
        for _ in range(3):
            assert validator.run_cycle() == "skip"

    assert metrics.degraded is True
    assert "degraded" in caplog.text.lower()
    assert subtensor.set_weights_calls == []

    rancher.list_error = None
    assert validator.run_cycle() == "weights_set"
    assert metrics.degraded is False


# ---------------------------------------------------------------------------
# AC5 process-boundary log redaction
# ---------------------------------------------------------------------------


class ScriptedTransport:
    """Fake transport for a real RancherClient: routes by (method, path)."""

    def __init__(self, routes: dict, default=(500, "upstream-error-body")):
        self.routes = routes
        self.default = default

    def request(self, method, url, headers, timeout):
        for (m, fragment), result in self.routes.items():
            if m == method and fragment in url:
                if isinstance(result, Exception):
                    raise result
                return result
        return self.default


def test_rancher_error_path_logs_no_token_or_body(caplog):
    """AC5: a Rancher auth failure whose upstream body carries the token must
    render into logs without the token or the body."""
    body = json.dumps(
        {"message": "denied", "echo": TOKEN, "marker": "RAWBODY"}
    )
    client = RancherClient(
        "https://rancher.example.test",
        TOKEN,
        transport=ScriptedTransport({("GET", "/v3/clusters"): (401, body)}),
    )
    validator, subtensor, _, _, metrics, _ = build_validator(rancher=client)

    with caplog.at_level(logging.DEBUG, logger="basic_validator"):
        assert validator.run_cycle() == "skip"

    assert subtensor.set_weights_calls == []
    assert (
        sample(metrics, "kubetee_rancher_errors_total", category="auth") == 1
    )
    assert TOKEN not in caplog.text
    assert "RAWBODY" not in caplog.text


def test_rancher_error_detail_is_fixed_field_not_remote_text(caplog):
    hostile_marker = "ATTACKER-CONTROLLED-RANCHER-ERROR"
    rancher = FakeRancher(
        list_error=RancherError(ErrorCategory.TRANSPORT, hostile_marker)
    )
    validator, *_ = build_validator(rancher=rancher)

    with caplog.at_level(logging.DEBUG, logger="basic_validator"):
        assert validator.run_cycle() == "skip"

    assert "reason=rancher_unavailable" in caplog.text
    assert "detail=rancher_transport_failure" in caplog.text
    assert hostile_marker not in caplog.text


def test_set_weights_rejection_log_is_redacted(caplog):
    """AC5: even if a rendered chain error somehow embeds the credential, the
    process boundary strips it before logging."""
    hostile_marker = f"ATTACKER-CONTROLLED-REJECTION-{TOKEN}"
    subtensor = FakeSubtensor(
        neurons_triad(),
        set_weights_results=[(False, hostile_marker)],
    )
    validator, *_ = build_validator(subtensor=subtensor)

    with caplog.at_level(logging.DEBUG, logger="basic_validator"):
        assert validator.run_cycle() == "weights_rejected"

    assert "set_weights rejected by chain" in caplog.text
    assert hostile_marker not in caplog.text
    assert TOKEN not in caplog.text


def test_reconciliation_suppression_log_is_redacted(caplog):
    """AC5: the unauthorized reconciliation suppression path (spec 4.2a) logs
    its evidence through the process boundary without token or bodies."""
    gone = "5GoneHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEa"
    cluster = {
        "id": "c-gone",
        "type": "cluster",
        "uuid": "00000000-0000-4000-8000-000000000099",
        "state": "active",
        "labels": {
            BINDING_ID_LABEL: "binding-gone",
            HOTKEY_LABEL: gone,
            COLDKEY_LABEL: "5GoneColdkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFA",
            PROVIDER_ID_LABEL: "00000000-0000-4000-8000-000000000099",
            BINDING_STATUS_LABEL: "ENROLLED",
            GENERATION_LABEL: "1",
            NETUID_LABEL: "1",
            NETWORK_LABEL: "finney",
            ORIGIN_FP_PREFIX_LABEL: "a" * 63,
        },
        "annotations": {ENROLLMENT_UID_ANNOTATION: "99"},
    }
    list_body = json.dumps(
        {
            "type": "collection",
            "resourceType": "cluster",
            "data": [cluster],
            "pagination": {"limit": -1, "total": 1},
        }
    )
    get_body = json.dumps(cluster)
    client = RancherClient(
        "https://rancher.example.test",
        TOKEN,
        transport=ScriptedTransport(
            {
                ("GET", "/v3/clusters?limit=-1"): (200, list_body),
                ("GET", "/v3/nodes"): (
                    200,
                    json.dumps(
                        {
                            "type": "collection",
                            "resourceType": "node",
                            "data": [],
                            "pagination": {"limit": -1, "total": 0},
                        }
                    ),
                ),
                ("GET", "/v3/clusters/c-gone"): (200, get_body),
                ("DELETE", "/v3/clusters/c-gone"): (
                    401,
                    "denied-body " + TOKEN,
                ),
            }
        ),
    )
    metrics = ValidatorMetrics(max_consecutive_skips=10)
    log = logging.getLogger("basic_validator")
    engine = ReconciliationEngine(
        client,
        metrics,
        expected_netuid=1,
        min_cycles=1,
        min_seconds=0.0,
        evidence_sink=lambda event: log.info(
            "reconciliation evidence: %s", event
        ),
    )
    validator, _subtensor, _, _, _, _ = build_validator(
        rancher=client, reconciler=engine, metrics=metrics
    )

    with caplog.at_level(logging.DEBUG, logger="basic_validator"):
        outcome = validator.run_cycle()

    assert outcome == "weights_set"  # scoring path unaffected by suppression
    assert (
        sample(
            metrics,
            "kubetee_reconciliation_suppressed_total",
            reason="unauthorized_operator_action_required",
        )
        == 1
    )
    assert "operator action required" in caplog.text
    assert TOKEN not in caplog.text


def test_reconciliation_audit_logger_uses_only_allowlisted_fields(caplog):
    event = {
        "event": "reconciliation_deletion",
        "correlation_id": "audit-1",
        "cluster_id": "c-gone",
        "absence_cycles": 3,
        "metagraph_blocks": [100, 101, 102],
        "response_class": "deleted-204",
        "detail": None,
        "raw_evidence": TOKEN,
    }

    with caplog.at_level(logging.INFO, logger="basic_validator"):
        _log_reconciliation_evidence(event)

    assert "reconciliation_deletion" in caplog.text
    assert "c-gone" in caplog.text
    assert "[100, 101, 102]" in caplog.text
    assert "deleted-204" in caplog.text
    assert TOKEN not in caplog.text
    assert "denied-body" not in caplog.text


def test_debug_evidence_logs_labels_reasons_and_never_secrets(caplog):
    """DEBUG evidence: cluster kubetee.ai/* labels and per-miner verdict
    reasons are visible at DEBUG, and bearer-token material never appears."""
    clusters = [
        {
            "id": "c-bob",
            "name": "miner-cluster",
            "state": "active",
            "internal": False,
            "labels": {
                "kubetee.ai/hotkey": "hot-bob",
                "kubetee.ai/binding-status": "ENROLLED",
                "unrelated": "ignored",
            },
        },
        "malformed-entry",
    ]
    verdict = validator_module.validate_miner(
        {"hotkey": "hot-bob", "coldkey": "cold-bob", "uid": 2},
        [],
        {},
        validator_module.InfrastructurePolicy.for_profile(
            validator_module.ValidationProfile.DEBUG
        ),
    )
    with caplog.at_level(logging.DEBUG, logger="basic_validator"):
        validator_module._log_cluster_debug_evidence(clusters)
        validator_module._log_verdict_debug_evidence(
            ["hot-bob"],
            {
                "hot-bob": {
                    "hotkey": "hot-bob",
                    "coldkey": "cold-bob",
                    "uid": 2,
                }
            },
            {"hot-bob": verdict},
            {},
        )
    assert "kubetee.ai/hotkey" in caplog.text
    assert "hot-bob" in caplog.text
    assert "reason=cluster_missing" in caplog.text
    assert "uid=2" in caplog.text
    assert '"unrelated": "ignored"' in caplog.text
    assert "token" not in caplog.text.lower()


# ---------------------------------------------------------------------------
# Two-label contract (hotkey + ban) end-to-end through a full cycle.
# ---------------------------------------------------------------------------


def test_two_label_contract_hotkey_only_cluster_scores():
    """The write->read seam: a cluster carrying ONLY kubetee.ai/hotkey (no
    canonical binding) + a ready node scores its miner in a real cycle."""
    clusters, nodes = active_bob_cluster()
    clusters[0]["labels"] = {HOTKEY_LABEL: BOB}
    clusters[0].pop("annotations", None)
    validator, subtensor, *_ = build_validator(
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes)
    )

    assert validator.run_cycle() == "weights_set"

    assert subtensor.set_weights_calls[0]["weights"] == pytest.approx(
        [0.9, 0.0, 0.1]
    )


def test_banned_hotkey_only_cluster_scores_zero_in_cycle():
    """kubetee.ai/ban=true on the miner's cluster -> that miner scores 0."""
    clusters, nodes = active_bob_cluster()
    clusters[0]["labels"] = {HOTKEY_LABEL: BOB, "kubetee.ai/ban": "true"}
    clusters[0].pop("annotations", None)
    validator, subtensor, *_ = build_validator(
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes)
    )

    assert validator.run_cycle() == "weights_set"

    assert subtensor.set_weights_calls[0]["weights"] == [1.0, 0.0, 0.0]


def test_alias_labeled_cluster_gets_nodes_fetched_and_scores():
    """Regression: _fetch_miner_nodes must match the cluster with the same
    canonicalized (miner- alias aware) hotkey lookup the scorer uses;
    a cluster labeled only kubetee.ai/miner-hotkey previously never had its
    nodes fetched -> node_inventory_empty despite a healthy inventory."""
    clusters, nodes = active_bob_cluster()
    clusters[0]["labels"] = {"kubetee.ai/miner-hotkey": BOB}
    clusters[0].pop("annotations", None)
    validator, subtensor, *_ = build_validator(
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes)
    )

    assert validator.run_cycle() == "weights_set"

    assert subtensor.set_weights_calls[0]["weights"] == pytest.approx(
        [0.9, 0.0, 0.1]
    )


# ---------------------------------------------------------------------------
# Scoring v2: probation gate, capacity-proportional weights, metrics.
# ---------------------------------------------------------------------------


def _gpu_node_for(cluster_id, index, product="NVIDIA-H100-80GB-HBM3"):
    return {
        "id": f"{cluster_id}:node-{index}",
        "clusterId": cluster_id,
        "state": "active",
        "transitioning": "no",
        "capacity": {"nvidia.com/gpu": "8"},
        "labels": {"nvidia.com/gpu.product": product},
    }


def test_probation_gates_first_cycles_then_earns():
    config = ValidatorConfig.from_env(make_env(KUBETEE_PROBATION_CYCLES="2"))
    clusters, nodes = active_bob_cluster()
    validator, subtensor, *_ = build_validator(
        config=config,
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes),
    )
    for _ in range(3):
        assert validator.run_cycle() == "weights_set"
    weights = [c["weights"] for c in subtensor.set_weights_calls]
    # 2 gated cycles (owner-only), then bob earns.
    assert weights[0] == [1.0, 0.0, 0.0]
    assert weights[1] == [1.0, 0.0, 0.0]
    assert weights[2] == pytest.approx([0.9, 0.0, 0.1])


def test_failure_during_probation_resets_gate():
    config = ValidatorConfig.from_env(make_env(KUBETEE_PROBATION_CYCLES="1"))
    clusters, nodes = active_bob_cluster()
    rancher = FakeRancher(clusters=clusters, nodes_by_cluster=nodes)
    validator, subtensor, *_ = build_validator(config=config, rancher=rancher)

    assert validator.run_cycle() == "weights_set"  # gated (k=1)
    clusters[0]["labels"]["kubetee.ai/ban"] = "true"  # fail a cycle
    assert validator.run_cycle() == "weights_set"  # reset to k=0
    del clusters[0]["labels"]["kubetee.ai/ban"]
    assert validator.run_cycle() == "weights_set"  # k=1 again
    assert validator.run_cycle() == "weights_set"  # earns now
    weights = [c["weights"] for c in subtensor.set_weights_calls]
    assert weights[2] == [1.0, 0.0, 0.0]
    assert weights[3] == pytest.approx([0.9, 0.0, 0.1])


def test_weights_proportional_to_gpu_capacity():
    """Two earning miners, one with B200s (2.17x H100): weights split
    proportionally to gpus x class weight in the production profile."""
    # Debug-profile capacity (node count) keeps the fixtures small while
    # still proving proportional splitting end to end.
    config = ValidatorConfig.from_env(make_env())
    clusters, nodes = active_bob_cluster()
    carol_cluster = copy.deepcopy(clusters[0])
    carol_cluster["id"] = "c-carol"
    carol_cluster["labels"] = {HOTKEY_LABEL: CAROL}
    clusters.append(carol_cluster)
    # debug capacity = node count: bob 1 node, carol 3 nodes -> 1:3 split
    nodes["c-carol"] = [
        {
            "id": f"c-carol:n{i}",
            "clusterId": "c-carol",
            "state": "active",
            "transitioning": "no",
        }
        for i in range(3)
    ]
    snapshot = [
        *neurons_triad(),
        {"uid": 3, "hotkey": CAROL, "coldkey": CAROL_COLDKEY},
    ]
    validator, subtensor, *_ = build_validator(
        config=config,
        subtensor=FakeSubtensor(snapshot),
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes),
    )
    assert validator.run_cycle() == "weights_set"
    weights = subtensor.set_weights_calls[0]["weights"]
    # v3 dynamic share: bob 1 node -> 2.4 alpha, carol 3 nodes -> 7.2 alpha;
    # sum 9.6 over bucket 24 -> share 0.4 split 1:3 -> 0.1 / 0.3, owner 0.6.
    assert weights == pytest.approx([0.6, 0.0, 0.1, 0.3])


def test_miner_scoring_metrics_exposed():
    clusters, nodes = active_bob_cluster()
    validator, _, _, _, metrics, _ = build_validator(
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes)
    )
    assert validator.run_cycle() == "weights_set"
    text = metrics.exposition().decode()
    assert 'kubetee_miner_state{cluster_id="c-bob",hotkey="' in text
    assert "kubetee_miner_score{" in text
    assert "kubetee_miner_weight{" in text
    assert "kubetee_scoring_earning_miners 1.0" in text
    assert 'reason="eligible"' in text


# ---------------------------------------------------------------------------
# Scoring v3: USD-priced weights.
# ---------------------------------------------------------------------------


def test_token_price_doubling_halves_miner_weight():
    """Same hardware, same USD target: alpha price x2 => weight /2."""
    clusters, nodes = active_bob_cluster()
    config = ValidatorConfig.from_env(
        make_env(KUBETEE_USD_PER_ALPHA_OVERRIDE="2.0")
    )
    validator, subtensor, *_ = build_validator(
        config=config,
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes),
    )
    assert validator.run_cycle() == "weights_set"
    assert subtensor.set_weights_calls[0]["weights"] == pytest.approx(
        [0.95, 0.0, 0.05]
    )


def test_bucket_smaller_than_targets_caps_share_pro_rata():
    """Token crash: targets exceed the bucket => share caps at 1.0 and the
    owner gets explicit zero (all emissions to miners, pro-rata)."""
    clusters, nodes = active_bob_cluster()
    config = ValidatorConfig.from_env(
        make_env(KUBETEE_MINER_BUCKET_ALPHA_OVERRIDE="1.0")
    )
    validator, subtensor, *_ = build_validator(
        config=config,
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes),
    )
    assert validator.run_cycle() == "weights_set"
    weights = subtensor.set_weights_calls[0]["weights"]
    assert weights == pytest.approx([0.0, 0.0, 1.0])
    assert sum(weights) == pytest.approx(1.0)


def test_price_feed_failure_skips_cycle_and_freezes_state():
    from price_feed import PriceFeedError

    config = ValidatorConfig.from_env(make_env(KUBETEE_PROBATION_CYCLES="5"))
    clusters, nodes = active_bob_cluster()
    validator, subtensor, _, _, metrics, _ = build_validator(
        config=config,
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes),
    )
    # two healthy cycles advance probation to k=2
    assert validator.run_cycle() == "weights_set"
    assert validator.run_cycle() == "weights_set"

    def broken_provider():
        raise PriceFeedError("feed down")

    validator._price_provider = broken_provider
    assert validator.run_cycle() == "skip"
    assert subtensor.set_weights_calls[-1]["weights"] == [1.0, 0.0, 0.0]
    text = metrics.exposition().decode()
    assert 'reason="price_unavailable"' in text
    # freeze: probation counter did not reset; two more healthy cycles
    # continue from k=2 (needs 5 -> still gated), proving no reset happened.
    validator._price_provider = validator._build_price_provider(config)
    assert validator.run_cycle() == "weights_set"  # k=3
    st = json_probation(metrics)
    assert st == 3


def json_probation(metrics) -> int:
    for line in metrics.exposition().decode().splitlines():
        if line.startswith("kubetee_miner_probation_cycles{"):
            return int(float(line.rsplit(" ", 1)[1]))
    return -1


def test_divergent_feed_price_skips_cycle():
    clusters, nodes = active_bob_cluster()
    validator, subtensor, *_ = build_validator(
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes)
    )
    from price_feed import PriceQuote

    validator._price_provider = lambda: PriceQuote(
        tao_usd=192.0, alpha_tao=0.02, usd_per_alpha=3.84, fetched_at=0.0
    )
    validator._chain_alpha_tao = lambda subtensor: 0.0067  # feed 3x off
    assert validator.run_cycle() == "skip"
    assert subtensor.set_weights_calls == []


def test_default_usd_card_is_the_owner_decision():
    """Owner card 2026-07-24: H200 $3.50, B200 $6.50, B300 $8.00 per
    GPU-hour. H100 deliberately absent -> earns $0 (fail-closed)."""
    env = make_env()
    env.pop("KUBETEE_GPU_USD_PRICES")
    config = ValidatorConfig.from_env(env)
    assert config.gpu_usd_prices == {
        "H200": 3.50,
        "B200": 6.50,
        "B300": 8.00,
    }
    assert "H100" not in config.gpu_usd_prices
