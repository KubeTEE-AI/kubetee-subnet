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

from __future__ import annotations

import copy
import json
import logging
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from validator import (
    BasicValidator,
    ConfigError,
    ValidatorConfig,
    load_config,
    main,
)
from infrastructure_validation import HOTKEY_LABEL, ValidationProfile
from rancher_client import ErrorCategory, RancherClient, RancherError
from reconciliation import ReconciliationEngine
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
    "KUBETEE_OWNER_HOTKEY": OWNER,
    "KUBETEE_VALIDATOR_HOTKEY": VALIDATOR,
    "RANCHER_URL": "https://rancher.example.test",
    "RANCHER_BEARER_TOKEN": TOKEN,
    "KUBETEE_CHAIN_NETWORK": "finney",
    "KUBETEE_VALIDATION_PROFILE": "debug",
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
    def __init__(self, neurons: list[FakeNeuron], block: int = 100):
        self.neurons = neurons
        self.block = block


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
    ):
        self._neurons = neurons
        self._metagraph_errors = list(metagraph_errors or [])
        self.calls = calls if calls is not None else []

    def metagraph(self, netuid: int):
        self.calls.append("metagraph")
        if self._metagraph_errors:
            error = self._metagraph_errors.pop(0)
            if error is not None:
                raise error
        return FakeMetagraph(
            [
                FakeNeuron(n["uid"], n["hotkey"], n["coldkey"])
                for n in self._neurons
            ]
        )


class FakeStakingNamespace:
    """Mimics bt.staking v11 namespace."""

    def get(self, coldkey, hotkey, netuid):
        return _FakeBalance(0.0)


class FakeResult:
    """Mimics the result of subtensor.execute(intent) in v11."""

    def __init__(self, success: bool, message: str = "ok"):
        self.is_success = success
        self._message = message

    def __str__(self) -> str:
        return self._message


class FakeSubtensor:
    def __init__(
        self,
        neurons: list[dict],
        set_weights_results=None,
        metagraph_errors=None,
        calls: list | None = None,
    ):
        self.subnets = FakeSubnetsNamespace(
            neurons, metagraph_errors=metagraph_errors, calls=calls
        )
        self.staking = FakeStakingNamespace()
        self.hyperparameters = object()
        self.set_weights_calls: list[dict] = []
        self._set_weights_results = list(set_weights_results or [])
        self.calls = calls if calls is not None else []

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
            success, message = raw
            return FakeResult(success, message)
        return FakeResult(True, "ok")


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
            "uuid": "uuid-bob",
            "state": "active",
            "transitioning": "no",
            "labels": {
                "kubetee.ai/binding-id": "binding-bob",
                HOTKEY_LABEL: BOB,
                "kubetee.ai/coldkey": BOB_COLDKEY,
                "kubetee.ai/provider-id": "provider-bob",
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
    assert config.miner_share == 0.10
    assert config.poll_seconds == 60.0
    assert config.max_consecutive_skips == 10
    assert config.reconcile_min_cycles == 3
    assert config.reconcile_min_seconds == 900.0
    assert config.wallet_name == "alice"
    assert config.owner_hotkey == OWNER
    assert config.validator_hotkey == VALIDATOR
    assert config.chain_network == "finney"
    assert config.validation_profile is ValidationProfile.DEBUG


@pytest.mark.parametrize(
    "missing",
    [
        "RANCHER_URL",
        "RANCHER_BEARER_TOKEN",
        "KUBETEE_OWNER_HOTKEY",
        "KUBETEE_VALIDATOR_HOTKEY",
        "KUBETEE_CHAIN_NETWORK",
        "KUBETEE_VALIDATION_PROFILE",
    ],
)
def test_missing_static_config_refuses_to_start(missing):
    env = make_env(**{missing: None})
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(env)
    assert missing in str(excinfo.value)
    assert TOKEN not in str(excinfo.value)


@pytest.mark.parametrize("share", ["1.5", "-0.1", "abc", "nan", "inf"])
def test_invalid_share_refuses_to_start(share):
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(KUBETEE_MINER_SHARE=share))
    assert "KUBETEE_MINER_SHARE" in str(excinfo.value)


def test_empty_tunables_fall_back_to_pinned_defaults():
    """Compose passes tunables through as ${VAR:-}; an empty value means
    'not configured' and takes the plan-pinned default. Credentials and
    hotkeys never do this - empty is missing there (D14)."""
    config = ValidatorConfig.from_env(
        make_env(
            KUBETEE_MINER_SHARE="",
            KUBETEE_POLL_SECONDS="",
            KUBETEE_MAX_CONSECUTIVE_SKIPS="",
        )
    )
    assert config.miner_share == 0.10
    assert config.poll_seconds == 60.0
    assert config.max_consecutive_skips == 10


@pytest.mark.parametrize("poll", ["59", "0", "-5", "junk"])
def test_poll_interval_below_minimum_refuses_to_start(poll):
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(KUBETEE_POLL_SECONDS=poll))
    assert "KUBETEE_POLL_SECONDS" in str(excinfo.value)


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


def test_equal_owner_and_validator_hotkeys_refuse_to_start():
    with pytest.raises(ConfigError):
        ValidatorConfig.from_env(make_env(KUBETEE_VALIDATOR_HOTKEY=OWNER))


@pytest.mark.parametrize(
    "url", ["http://insecure.example", "not-a-url", "ftp://x"]
)
def test_non_https_rancher_url_refuses_to_start(url):
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(RANCHER_URL=url))
    assert "RANCHER_URL" in str(excinfo.value)


@pytest.mark.parametrize("profile", ["", "DEBUG", "staging"])
def test_invalid_validation_profile_refuses_to_start(profile):
    with pytest.raises(ConfigError) as excinfo:
        ValidatorConfig.from_env(make_env(KUBETEE_VALIDATION_PROFILE=profile))
    assert "KUBETEE_VALIDATION_PROFILE" in str(excinfo.value)


def test_validation_profile_ignores_outer_whitespace_only():
    config = ValidatorConfig.from_env(
        make_env(KUBETEE_VALIDATION_PROFILE=" production ")
    )
    assert config.validation_profile is ValidationProfile.PRODUCTION


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
    assert "KUBETEE_OWNER_HOTKEY" in str(cause)
    assert "KUBETEE_CHAIN_NETWORK" in str(cause)
    assert "KUBETEE_VALIDATION_PROFILE" in str(cause)


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


def test_degenerate_share_zero_reproduces_owner_only_weights():
    """Migrated owner-validator expectation: share x score = 0 keeps 100%
    owner weight with explicit zeros for everyone else."""
    clusters, nodes = active_bob_cluster()
    config = ValidatorConfig.from_env(make_env(KUBETEE_MINER_SHARE="0"))
    validator, subtensor, *_ = build_validator(
        config=config,
        rancher=FakeRancher(clusters=clusters, nodes_by_cluster=nodes),
    )

    assert validator.run_cycle() == "weights_set"
    call = subtensor.set_weights_calls[0]
    assert call["uids"] == [0, 1, 2]
    assert call["weights"] == [1.0, 0.0, 0.0]


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

    neurons, block = validator._read_neurons(subtensor)

    assert block == 100
    assert neurons[2] == {
        "uid": 2,
        "hotkey": BOB,
        "coldkey": BOB_COLDKEY,
    }


def test_invalid_metagraph_suppresses_rancher_and_reconciliation_actions():
    duplicate = neurons_triad() + [
        {"uid": 3, "hotkey": BOB, "coldkey": BOB_COLDKEY}
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


@pytest.mark.parametrize("mutation", ["pending", "coldkey_mismatch"])
def test_complete_binding_failure_scores_only_that_miner_zero(mutation):
    clusters, nodes = active_bob_cluster()
    if mutation == "pending":
        clusters[0]["labels"]["kubetee.ai/binding-status"] = "PENDING"
    else:
        clusters[0]["labels"]["kubetee.ai/coldkey"] = "5WrongColdkey"
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
    carol_cluster["labels"]["kubetee.ai/binding-status"] = "PENDING"
    carol_cluster["annotations"]["kubetee.ai/enrollment-uid"] = "3"
    clusters.append(carol_cluster)
    nodes["c-carol"] = [
        {
            "id": "c-carol:node-1",
            "clusterId": "c-carol",
            "state": "active",
            "transitioning": "no",
        }
    ]
    snapshot = neurons_triad() + [
        {"uid": 3, "hotkey": CAROL, "coldkey": CAROL_COLDKEY}
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
    reconciler = FakeReconciler(error=RuntimeError("unexpected bug"))
    sleep, sleep_calls = stop_after(3)
    validator, _subtensor, _, _, _, _ = build_validator(
        reconciler=reconciler, sleep=sleep
    )

    with (
        caplog.at_level(logging.ERROR, logger="basic_validator"),
        pytest.raises(_StopLoop),
    ):
        validator.run_forever()

    assert len(sleep_calls) == 3
    assert "unexpected cycle error" in caplog.text
    assert "RuntimeError" in caplog.text


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


def test_set_weights_rejection_log_is_redacted(caplog):
    """AC5: even if a rendered chain error somehow embeds the credential, the
    process boundary strips it before logging."""
    subtensor = FakeSubtensor(
        neurons_triad(),
        set_weights_results=[(False, f"rejected; ctx={TOKEN}")],
    )
    validator, *_ = build_validator(subtensor=subtensor)

    with caplog.at_level(logging.DEBUG, logger="basic_validator"):
        assert validator.run_cycle() == "weights_rejected"

    assert "rejected" in caplog.text
    assert TOKEN not in caplog.text


def test_reconciliation_suppression_log_is_redacted(caplog):
    """AC5: the unauthorized reconciliation suppression path (spec 4.2a) logs
    its evidence through the process boundary without token or bodies."""
    gone = "5GoneHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEa"
    cluster = {
        "id": "c-gone",
        "uuid": "uuid-gone",
        "state": "active",
        # Reconciliation's label migration is covered in Task 4.
        "labels": {"kubetee.ai/miner-hotkey": gone},
    }
    list_body = json.dumps({"data": [cluster], "pagination": {"limit": -1}})
    get_body = json.dumps(cluster)
    client = RancherClient(
        "https://rancher.example.test",
        TOKEN,
        transport=ScriptedTransport(
            {
                ("GET", "/v3/clusters?limit=-1"): (200, list_body),
                ("GET", "/v3/nodes"): (
                    200,
                    json.dumps({"data": [], "pagination": {"limit": -1}}),
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
    assert "denied-body" not in caplog.text
