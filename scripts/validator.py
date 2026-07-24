#!/usr/bin/env python3
"""KubeTEE basic validator (g004 V6, spec 4.2) - replaces the owner validator.

One validator loop, one chain connection, one Rancher session (HTTP 429
lesson, AC6). Cycle order per spec 4.2: metagraph -> Rancher enumeration ->
reconciliation -> scoring -> weights -> log + metrics.

Startup vs runtime failure contract (D14):
- ALL static configuration is validated fail-fast at startup - a missing or
  malformed value (share, poll interval, max skips, reconcile params, the
  validator hotkey, RANCHER_URL/RANCHER_BEARER_TOKEN) refuses to start
  with a clear error naming the variable, never echoing a secret.
- Once started the process NEVER exits on a runtime error: Rancher outages,
  rejected set_weights, and unexpected in-cycle exceptions all degrade to
  the skip/backoff paths and the loop continues. Only operator signals
  (SIGTERM/SIGINT, compose down) stop it.

Weights are signed by alice (BT_WALLET, D7); success is claimed only on
chain acceptance. Rancher runtime unavailability skips set_weights for the
cycle (D10) - our own observability outage must never zero a miner. Logs are
structured and redacted: the bearer token and upstream bodies never appear,
including inside rendered exceptions (AC5).

bittensor is imported lazily inside main() so the unit suite (and any host
without the SDK) exercises everything through injected seams.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import math
import os
import pathlib
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from numbers import Integral
from urllib.parse import urlsplit

from dotenv import load_dotenv
from loguru import logger

from infrastructure_validation import (
    HOTKEY_LABEL,
    InfrastructurePolicy,
    ValidationProfile,
    canonicalize_kubetee_keys,
    validate_miner,
)
from logging_setup import configure_logging
from miner_scoring import (
    CycleConfig,
    SkipCycle,
    SkipReason,
    decide_cycle,
    validate_share,
)
from prometheus_client import start_http_server
from rancher_client import (
    ErrorCategory,
    RancherClient,
    RancherError,
    normalize_https_origin,
)
from reconciliation import ReconciliationEngine
from validator_metrics import ValidatorMetrics

# Loguru module logger; tests bridge it back into the stdlib
# "basic_validator" logger via tests/conftest.py so caplog keeps working.
_LOG = logger

DEFAULT_NETWORK = "ws://chain:9944"
DEFAULT_WALLET = "alice"  # the validator signing identity (D7)
DEFAULT_NETUID_FILE = "/app/.kubetee_netuid"
_SETUP_SCRIPT = pathlib.Path(__file__).with_name("setup_single_node.py")
MIN_POLL_SECONDS = 60.0
DEBUG_MIN_POLL_SECONDS = 5.0

_SKIP_DETAILS = {
    SkipReason.METAGRAPH_UNAVAILABLE: "metagraph_read_failed",
    SkipReason.METAGRAPH_STALE: "metagraph_block_not_advanced",
    SkipReason.OWNER_UNRESOLVED: "owner_hotkey_unresolved",
    SkipReason.IDENTITY_VIOLATION: "metagraph_identity_violation",
    SkipReason.UNEXPECTED_RUNTIME: "unexpected_runtime_error",
}
_RANCHER_SKIP_DETAILS = {
    ErrorCategory.TRANSPORT: "rancher_transport_failure",
    ErrorCategory.AUTH: "rancher_auth_failure",
    ErrorCategory.MALFORMED: "rancher_malformed_response",
    ErrorCategory.INCOMPLETE: "rancher_incomplete_enumeration",
}


def _log_reconciliation_evidence(event: dict) -> None:
    """Emit only the fixed audit fields approved for destructive actions."""
    _LOG.info(
        "reconciliation evidence",
        extra={
            "event": event.get("event"),
            "correlation_id": event.get("correlation_id"),
            "cluster_id": event.get("cluster_id"),
            "absence_cycles": event.get("absence_cycles"),
            "metagraph_blocks": event.get("metagraph_blocks"),
            "response_class": event.get("response_class"),
            "detail": event.get("detail"),
        },
    )


def _log_cluster_debug_evidence(clusters: list) -> None:
    """DEBUG-only enumeration evidence: the complete cluster label map (as
    JSON) and readiness state per cluster. Never bearer tokens or raw
    upstream bodies (AC5); labels are operator-authored cluster metadata."""
    _LOG.debug(
        "rancher enumeration complete", extra={"clusters": len(clusters)}
    )
    for cluster in clusters:
        if not isinstance(cluster, dict):
            _LOG.debug(
                "cluster entry malformed",
                extra={"entry_type": type(cluster).__name__},
            )
            continue
        labels = cluster.get("labels")
        labels_json = (
            json.dumps(labels, sort_keys=True, default=str)
            if isinstance(labels, dict)
            else None
        )
        _LOG.debug(
            "cluster evidence",
            extra={
                "cluster_id": cluster.get("id"),
                "name": cluster.get("name"),
                "state": cluster.get("state"),
                "internal": cluster.get("internal"),
                "labels": labels_json,
            },
        )


def _log_verdict_debug_evidence(
    miners: list,
    neurons_by_hotkey: dict,
    verdicts: dict,
    nodes_by_cluster: dict,
) -> None:
    """DEBUG-only per-miner verdict evidence: which reason fired and what
    the miner's chain identity and node inventory looked like."""
    for hotkey in miners:
        neuron = neurons_by_hotkey.get(hotkey, {})
        verdict = verdicts.get(hotkey)
        cluster_id = getattr(verdict, "cluster_id", None)
        nodes = nodes_by_cluster.get(cluster_id)
        _LOG.debug(
            "miner verdict",
            extra={
                "hotkey": hotkey,
                "uid": neuron.get("uid"),
                "coldkey": neuron.get("coldkey"),
                "status": getattr(
                    getattr(verdict, "status", None), "value", None
                ),
                "reason": getattr(
                    getattr(verdict, "reason", None), "value", None
                ),
                "cluster_id": cluster_id,
                "node_count": len(nodes) if isinstance(nodes, list) else None,
            },
        )


class ConfigError(ValueError):
    """A static configuration error: refuse to start (D14)."""


@dataclasses.dataclass(frozen=True)
class ValidatorConfig:
    """Static per-process configuration, validated fail-fast (D12/D14)."""

    network: str
    wallet_name: str
    wallet_hotkey: str
    netuid: int
    miner_share: float
    poll_seconds: float
    max_consecutive_skips: int
    reconcile_min_cycles: int
    reconcile_min_seconds: float
    validator_hotkey: str
    chain_network: str
    validation_profile: ValidationProfile
    rancher_url: str
    rancher_token: str
    rancher_ca_file: str | None
    metrics_port: int
    metrics_addr: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ValidatorConfig:
        """Build config from the environment, collecting EVERY error so the
        operator sees the full list in one refusal. Values of secret-bearing
        variables are never echoed."""
        errors: list[str] = []

        def fail(name: str, why: str) -> None:
            errors.append(f"{name} {why}")

        def require(name: str) -> str:
            value = (env.get(name) or "").strip()
            if not value:
                fail(name, "is required (missing or empty)")
            return value

        def parse_float(name: str, default: float, minimum: float) -> float:
            raw = str(env.get(name) or "").strip()
            if not raw:
                return default
            try:
                value = float(raw)
            except ValueError:
                fail(name, "must be a number")
                return default
            if not math.isfinite(value) or value < minimum:
                fail(name, f"must be finite and >= {minimum:g}")
                return default
            return value

        def parse_int(
            name: str, default: int, minimum: int, maximum: int | None = None
        ) -> int:
            raw = str(env.get(name) or "").strip()
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError:
                fail(name, "must be an integer")
                return default
            if value < minimum or (maximum is not None and value > maximum):
                bound = (
                    f"between {minimum} and {maximum}"
                    if maximum is not None
                    else f">= {minimum}"
                )
                fail(name, f"must be {bound}")
                return default
            return value

        profile_raw = (
            str(env.get("KUBETEE_VALIDATION_PROFILE") or "").strip()
            or ValidationProfile.PRODUCTION.value
        )
        validation_profile = ValidationProfile.PRODUCTION
        try:
            validation_profile = ValidationProfile(profile_raw)
        except ValueError:
            fail(
                "KUBETEE_VALIDATION_PROFILE",
                "must be production or debug",
            )

        raw_share = str(env.get("KUBETEE_MINER_SHARE") or "0.10").strip()
        miner_share = 0.10
        try:
            miner_share = validate_share(float(raw_share))
        except ValueError:
            fail("KUBETEE_MINER_SHARE", "must be finite and within [0, 1]")

        poll_seconds = parse_float(
            "KUBETEE_POLL_SECONDS",
            MIN_POLL_SECONDS,
            (
                DEBUG_MIN_POLL_SECONDS
                if validation_profile is ValidationProfile.DEBUG
                else MIN_POLL_SECONDS
            ),
        )
        max_skips = parse_int("KUBETEE_MAX_CONSECUTIVE_SKIPS", 10, 1)
        reconcile_cycles = parse_int("KUBETEE_RECONCILE_MIN_CYCLES", 3, 1)
        reconcile_seconds = parse_float(
            "KUBETEE_RECONCILE_MIN_SECONDS", 900.0, 0.0
        )
        netuid = parse_int("KUBETEE_SUBNET_NETUID", 1, 0)
        metrics_port = parse_int("KUBETEE_METRICS_PORT", 9100, 1, 65535)

        validator_hotkey = require("KUBETEE_VALIDATOR_HOTKEY")

        chain_network = require("KUBETEE_CHAIN_NETWORK")

        network = (env.get("BT_NETWORK") or DEFAULT_NETWORK).strip()
        wallet_name = (env.get("BT_WALLET") or DEFAULT_WALLET).strip()
        wallet_hotkey = (env.get("BT_WALLET_HOTKEY") or "default").strip()
        if validation_profile is ValidationProfile.PRODUCTION and (
            profile_raw == ValidationProfile.PRODUCTION.value
        ):
            network = require("BT_NETWORK")
            wallet_name = require("BT_WALLET")
            wallet_hotkey = require("BT_WALLET_HOTKEY")
            require("KUBETEE_SUBNET_NETUID")

        rancher_url = require("RANCHER_URL")
        if rancher_url:
            try:
                rancher_url = normalize_https_origin(rancher_url)
            except ValueError:
                fail("RANCHER_URL", "must be a https origin")
        rancher_token = require("RANCHER_BEARER_TOKEN")
        rancher_ca_file = (env.get("RANCHER_CA_FILE") or "").strip() or None

        if errors:
            raise ConfigError(
                "invalid static configuration: " + "; ".join(errors)
            )

        return cls(
            network=network,
            wallet_name=wallet_name,
            wallet_hotkey=wallet_hotkey,
            netuid=netuid,
            miner_share=miner_share,
            poll_seconds=poll_seconds,
            max_consecutive_skips=max_skips,
            reconcile_min_cycles=reconcile_cycles,
            reconcile_min_seconds=reconcile_seconds,
            validator_hotkey=validator_hotkey,
            chain_network=chain_network,
            validation_profile=validation_profile,
            rancher_url=rancher_url,
            rancher_token=rancher_token,
            rancher_ca_file=rancher_ca_file,
            metrics_port=metrics_port,
            metrics_addr=(
                env.get("KUBETEE_METRICS_ADDR") or "0.0.0.0"
            ).strip(),
        )


def load_config(env: Mapping[str, str] | None = None) -> ValidatorConfig:
    """Resolve config from the environment plus the setup-written netuid file
    (the setup phase records the netuid it actually owns)."""
    data = dict(os.environ if env is None else env)
    path = (data.get("KUBETEE_NETUID_FILE") or DEFAULT_NETUID_FILE).strip()
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if text:
        data["KUBETEE_SUBNET_NETUID"] = text
    return ValidatorConfig.from_env(data)


def _run_local_bootstrap(env: Mapping[str, str], netuid: int) -> None:
    """Run the disposable local-chain setup without exposing its output."""
    runtime_env = dict(env)
    setup_cmd = [
        sys.executable,
        "-u",
        str(_SETUP_SCRIPT),
        "--netuid",
        str(netuid),
        "--owner-wallet",
        runtime_env.get("KUBETEE_OWNER_WALLET", "owner"),
        "--chain-endpoint",
        runtime_env.get("BT_NETWORK", DEFAULT_NETWORK),
    ]
    try:
        subprocess.run(
            setup_cmd,
            check=True,
            env=runtime_env,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        # Debug-only path with pinned public dev seeds; setup_single_node
        # redacts seed-bearing command echoes, so its failure output is safe
        # to surface for diagnosis.
        _LOG.opt(exception=True).error(
            "validator bootstrap failed",
            extra={
                "returncode": error.returncode,
                "stdout_tail": (error.stdout or "")[-2000:],
                "stderr_tail": (error.stderr or "")[-2000:],
            },
        )
        raise SystemExit(1) from None
    except OSError:
        _LOG.opt(exception=True).error(
            "validator bootstrap failed to launch",
            extra={"command": setup_cmd},
        )
        raise SystemExit(1) from None


def _bootstrap_if_debug(
    config: ValidatorConfig, env: Mapping[str, str]
) -> None:
    """Bootstrap only the disposable debug/local validator environment."""
    if config.validation_profile is ValidationProfile.DEBUG:
        _run_local_bootstrap(env, config.netuid)


class BasicValidator:
    """The validator loop. Every boundary (chain, Rancher, metrics, clock)
    is injected; the loop owns no secrets besides the redaction pattern."""

    def __init__(
        self,
        config: ValidatorConfig,
        subtensor_factory: Callable[[], object],
        wallet: object,
        rancher,
        metrics: ValidatorMetrics,
        reconciler: ReconciliationEngine,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._subtensor_factory = subtensor_factory
        self._wallet = wallet
        self._rancher = rancher
        self._metrics = metrics
        self._reconciler = reconciler
        self._sleep = sleep
        self._log = _LOG
        self._subtensor = None
        self._chain_dirty = False
        self._last_metagraph_block: int | None = None
        self._validator_hotkey = config.validator_hotkey
        self._miner_share = config.miner_share
        self._infrastructure_policy = InfrastructurePolicy.for_profile(
            config.validation_profile
        )

    # -- chain session (AC6: one connection, recreated only after failure) -----

    def _ensure_subtensor(self):
        if self._subtensor is None or self._chain_dirty:
            if self._chain_dirty:
                self._log.warning(
                    "recreating chain connection after transport failure"
                )
            self._subtensor = self._subtensor_factory()
            self._chain_dirty = False
        return self._subtensor

    def _read_neurons(
        self, subtensor
    ) -> tuple[list[dict] | None, int | None, str | None]:
        try:
            head = subtensor.block()
            if isinstance(head, bool) or not isinstance(head, int) or head < 0:
                raise ValueError("chain head block is invalid")
            meta = subtensor.subnets.metagraph(
                self._config.netuid,
                block=head,
            )
            neurons = []
            for neuron in meta.neurons:
                raw_uid = getattr(neuron, "uid", None)
                if isinstance(raw_uid, bool) or not isinstance(
                    raw_uid, Integral
                ):
                    uid = raw_uid
                else:
                    uid = int(raw_uid)
                neurons.append(
                    {
                        "uid": uid,
                        "hotkey": getattr(neuron, "hotkey", None),
                        "coldkey": getattr(neuron, "coldkey", None),
                    }
                )
            block = getattr(meta, "block", None)
            if (
                isinstance(block, bool)
                or not isinstance(block, int)
                or block != head
            ):
                raise ValueError("metagraph is not pinned to the chain head")
            owner_hotkey = getattr(meta, "owner_hotkey", None)
            if not isinstance(owner_hotkey, str) or not owner_hotkey.strip():
                return neurons, block, None
            return neurons, block, owner_hotkey.strip()
        # The injected chain SDK does not expose one stable transport exception.
        # pylint: disable-next=broad-exception-caught
        except Exception:  # fail closed; never reflect remote exception text
            self._chain_dirty = True
            self._log.warning("metagraph read failed")
            return None, None, None

    def _cycle_config(self, owner_hotkey: str | None) -> CycleConfig | None:
        """Build cycle identity config from the chain-derived owner key."""
        if not isinstance(owner_hotkey, str) or not owner_hotkey.strip():
            return None
        try:
            return CycleConfig(
                owner_hotkey=owner_hotkey,
                validator_hotkey=self._validator_hotkey,
                miner_share=self._miner_share,
            )
        except ValueError:
            return None

    def _refresh_registered(
        self, minimum_block: int | None = None
    ) -> set[str] | None:
        """Fresh metagraph read for the reconciliation pre-delete recheck."""
        if self._subtensor is None:
            return None
        neurons, block, owner_hotkey = self._read_neurons(self._subtensor)
        if neurons is None or block is None or owner_hotkey is None:
            return None
        if minimum_block is not None and block < minimum_block:
            return None
        cycle_config = self._cycle_config(owner_hotkey)
        if cycle_config is None:
            return None
        identity_check = decide_cycle(neurons, {}, cycle_config)
        if isinstance(identity_check, SkipCycle):
            return None
        return {n["hotkey"] for n in neurons}

    # -- Rancher enumeration (spec 4.2 step 2) ---------------------------------

    def _fetch_miner_nodes(
        self, clusters: list[dict], miners: list[str]
    ) -> dict[str, list[dict]]:
        """Fetch nodes for each miner's uniquely labeled cluster. A Rancher
        failure propagates (whole-cycle skip); a malformed cluster id simply
        stays unfetched and scores 0 (fail closed)."""
        nodes_by_cluster: dict[str, list[dict]] = {}
        for hotkey in miners:
            matches = [
                c
                for c in clusters
                if isinstance(c, dict)
                and isinstance(c.get("labels"), dict)
                and canonicalize_kubetee_keys(c["labels"]).get(HOTKEY_LABEL)
                == hotkey
            ]
            if len(matches) != 1:
                continue
            cluster_id = matches[0].get("id")
            if not isinstance(cluster_id, str) or not cluster_id:
                continue
            try:
                nodes_by_cluster[cluster_id] = self._rancher.list_nodes(
                    cluster_id
                )
            except ValueError:
                continue  # invalid id: unfetched -> score 0
        return nodes_by_cluster

    # -- one cycle (spec 4.2 order) --------------------------------------------

    def _record_skip(
        self,
        reason: SkipReason,
        rancher_category: ErrorCategory | None = None,
    ) -> None:
        if reason is SkipReason.RANCHER_UNAVAILABLE:
            detail = _RANCHER_SKIP_DETAILS.get(
                rancher_category,
                "rancher_unknown_failure",
            )
        else:
            detail = _SKIP_DETAILS.get(reason, "unspecified_skip")
        entered_degraded = self._metrics.record_skip(reason)
        self._metrics.record_cycle_outcome("skip")
        self._log.warning(
            "cycle skipped set_weights",
            extra={
                "reason": reason.value,
                "detail": detail,
                "consecutive": self._metrics.consecutive_skips,
            },
        )
        if entered_degraded:
            self._log.critical(
                "DEGRADED MODE entered: consecutive skipped cycles exceeded "
                "KUBETEE_MAX_CONSECUTIVE_SKIPS - on-chain weights are stale; "
                "operator intervention required (see SUBNET.md); weights are "
                "never auto-zeroed",
                extra={
                    "consecutive": self._metrics.consecutive_skips,
                    "max_consecutive_skips": (
                        self._config.max_consecutive_skips
                    ),
                },
            )

    def run_cycle(self) -> str:
        """Run one validation cycle; returns the outcome tag for logs/tests."""
        subtensor = self._ensure_subtensor()

        # 1. metagraph (identity preconditions re-checked every cycle)
        neurons, block, owner_hotkey = self._read_neurons(subtensor)
        if neurons is None:
            self._reconciler.run_cycle(
                None, None, None, self._refresh_registered
            )
            self._record_skip(SkipReason.METAGRAPH_UNAVAILABLE)
            return "skip"
        cycle_config = self._cycle_config(owner_hotkey)
        if cycle_config is None:
            self._reconciler.run_cycle(
                None,
                None,
                block,
                self._refresh_registered,
            )
            self._record_skip(SkipReason.OWNER_UNRESOLVED)
            return "skip"
        identity_check = decide_cycle(neurons, {}, cycle_config)
        if isinstance(identity_check, SkipCycle):
            self._reconciler.run_cycle(
                None,
                None,
                block,
                self._refresh_registered,
            )
            self._record_skip(identity_check.reason)
            return "skip"
        if block is None or (
            self._last_metagraph_block is not None
            and block <= self._last_metagraph_block
        ):
            self._reconciler.run_cycle(
                None,
                None,
                block,
                self._refresh_registered,
            )
            self._record_skip(SkipReason.METAGRAPH_STALE)
            return "skip"
        self._last_metagraph_block = block
        registered = {n["hotkey"] for n in neurons}
        miners = sorted(
            registered - {owner_hotkey, self._config.validator_hotkey}
        )

        # 2. Rancher enumeration (complete pagination inside the client)
        try:
            clusters = self._rancher.list_clusters()
            nodes_by_cluster = self._fetch_miner_nodes(clusters, miners)
        except RancherError as error:
            # D10/D14: runtime outage -> skip weights, never crash, never
            # score 0 for our own outage; reconciliation is suppressed.
            self._metrics.record_rancher_error(error.category)
            self._reconciler.run_cycle(
                registered, None, block, self._refresh_registered
            )
            self._record_skip(SkipReason.RANCHER_UNAVAILABLE, error.category)
            return "skip"

        _log_cluster_debug_evidence(clusters)

        # 3. reconciliation (spec 4.2a; requires fresh metagraph + complete
        #    enumeration from this same cycle)
        self._reconciler.run_cycle(
            registered, clusters, block, self._refresh_registered
        )

        # 4. infrastructure validation (binary fail-closed) + identity checks
        neurons_by_hotkey = {neuron["hotkey"]: neuron for neuron in neurons}
        verdicts = {
            hotkey: validate_miner(
                neurons_by_hotkey[hotkey],
                clusters,
                nodes_by_cluster,
                self._infrastructure_policy,
            )
            for hotkey in miners
        }
        _log_verdict_debug_evidence(
            miners, neurons_by_hotkey, verdicts, nodes_by_cluster
        )
        scores = {
            hotkey: verdict.score for hotkey, verdict in verdicts.items()
        }
        decision = decide_cycle(neurons, scores, cycle_config)
        if isinstance(decision, SkipCycle):
            self._record_skip(decision.reason)
            return "skip"

        self._metrics.record_validation_results(tuple(verdicts.values()))
        reason_counts = collections.Counter(
            verdict.reason.value for verdict in verdicts.values()
        )
        validation_reasons = dict(sorted(reason_counts.items()))
        scoring_count = sum(decision.miner_scores.values())
        self._metrics.record_scoring_result(len(miners), scoring_count)
        self._metrics.record_successful_scoring()

        # 5. weights (signed by alice; success only on chain acceptance)
        uids = sorted(decision.weights)
        weights = [decision.weights[uid] for uid in uids]
        try:
            from bittensor.intents.weights import SetWeights

            intent = SetWeights(
                netuid=self._config.netuid, uids=uids, weights=weights
            )
            result = subtensor.execute(intent, wallet=self._wallet)
            success = result.success
        # Bittensor can surface transport and submission failures from plugins.
        # pylint: disable-next=broad-exception-caught
        except Exception:
            self._chain_dirty = True
            self._metrics.record_set_weights(False)
            self._log.warning("set_weights raised; will back off and retry")
            self._metrics.record_cycle_outcome("weights_rejected")
            return "weights_rejected"

        # 6. log + metrics (honest, redacted)
        self._metrics.record_set_weights(bool(success))
        if success:
            self._log.info(
                "set_weights accepted on chain",
                extra={
                    "netuid": self._config.netuid,
                    "miners": len(miners),
                    "scoring": scoring_count,
                    "validation_reasons": validation_reasons,
                    "uids": uids,
                    "weights": weights,
                },
            )
            self._metrics.record_cycle_outcome("weights_set")
            return "weights_set"
        self._log.warning("set_weights rejected by chain; no success claimed")
        self._metrics.record_cycle_outcome("weights_rejected")
        return "weights_rejected"

    def run_forever(self) -> None:
        """D14 liveness corollary: no runtime error may terminate the loop.
        Only operator signals (BaseException path) stop the process."""
        self._log.info(
            "basic validator started",
            extra={
                "netuid": self._config.netuid,
                "chain_network": self._config.chain_network,
                "profile": self._config.validation_profile.value,
                "poll_seconds": self._config.poll_seconds,
                "miner_share": self._config.miner_share,
                "max_consecutive_skips": self._config.max_consecutive_skips,
                "rancher": urlsplit(self._config.rancher_url).netloc,
            },
        )
        while True:
            try:
                self.run_cycle()
            # The process liveness contract intentionally guards every cycle.
            # pylint: disable-next=broad-exception-caught
            except Exception:  # never exit on a runtime error (D14)
                self._log.error("unexpected cycle error; loop continues")
                self._record_skip(SkipReason.UNEXPECTED_RUNTIME)
            self._sleep(self._config.poll_seconds)


def main(env: Mapping[str, str] | None = None) -> None:
    if env is None:
        # Host/PyCharm runs: pick up the repo-root .env regardless of the
        # process working directory (compose injects the same variables via
        # its environment: block). Never overrides real env.
        load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")
    runtime_env = dict(os.environ if env is None else env)
    # Configure the shared ml-pipeline sink format before the first log line
    # (config refusal included). bittensor's later import reconfigures global
    # stdlib logging only; loguru keeps its own sinks, so the cycle-evidence
    # INFO lines (AC5/AC9) cannot be muted.
    configure_logging(level=runtime_env.get("LOG_LEVEL", "INFO"))
    try:
        config = load_config(runtime_env)
        _bootstrap_if_debug(config, runtime_env)
        # setup_single_node.py writes the netuid actually owned by the local
        # process; reload so the validator and reconciliation use that value.
        config = load_config(runtime_env)
    except ConfigError as error:
        _LOG.error("refusing to start: {}", error)
        raise SystemExit(2) from error

    # Lazy import: unit tests (and hosts without the SDK) never import
    # real bittensor; only the live process pays this cost.
    import bittensor as bt

    wallet = bt.Wallet(name=config.wallet_name, hotkey=config.wallet_hotkey)
    metrics = ValidatorMetrics(
        max_consecutive_skips=config.max_consecutive_skips
    )
    # Compose keeps this port off the host network (AC11: compose-internal).
    start_http_server(
        config.metrics_port,
        addr=config.metrics_addr,
        registry=metrics.registry,
    )
    client = RancherClient(
        config.rancher_url,
        config.rancher_token,
        ca_file=config.rancher_ca_file,
    )

    reconciler = ReconciliationEngine(
        client,
        metrics,
        expected_netuid=config.netuid,
        min_cycles=config.reconcile_min_cycles,
        min_seconds=config.reconcile_min_seconds,
        evidence_sink=_log_reconciliation_evidence,
    )
    validator = BasicValidator(
        config=config,
        subtensor_factory=lambda: bt.Subtensor(network=config.network),
        wallet=wallet,
        rancher=client,
        metrics=metrics,
        reconciler=reconciler,
    )
    validator.run_forever()


if __name__ == "__main__":
    main()
