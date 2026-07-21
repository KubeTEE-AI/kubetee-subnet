#!/usr/bin/env python3
"""KubeTEE basic validator (g004 V6, spec 4.2) - replaces the owner validator.

One validator loop, one chain connection, one Rancher session (HTTP 429
lesson, AC6). Cycle order per spec 4.2: metagraph -> Rancher enumeration ->
reconciliation -> scoring -> weights -> log + metrics.

Startup vs runtime failure contract (D14):
- ALL static configuration is validated fail-fast at startup - a missing or
  malformed value (share, poll interval, max skips, reconcile params, owner
  and validator hotkeys, RANCHER_URL/RANCHER_BEARER_TOKEN) refuses to start
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

import dataclasses
import logging
import math
import os
import pathlib
import time
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

from miner_scoring import (
    MINER_LABEL,
    CycleConfig,
    SkipCycle,
    SkipReason,
    decide_cycle,
    score_miner,
    validate_share,
)
from prometheus_client import start_http_server
from rancher_client import RancherClient, RancherError
from reconciliation import ReconciliationEngine
from validator_metrics import ValidatorMetrics

_LOG = logging.getLogger("basic_validator")

DEFAULT_NETWORK = "ws://chain:9944"
DEFAULT_WALLET = "alice"  # the validator signing identity (D7)
DEFAULT_NETUID_FILE = "/app/.kubetee_netuid"
MIN_POLL_SECONDS = 60.0


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
    owner_hotkey: str
    validator_hotkey: str
    rancher_url: str
    rancher_token: str
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

        raw_share = str(env.get("KUBETEE_MINER_SHARE") or "0.10").strip()
        miner_share = 0.10
        try:
            miner_share = validate_share(float(raw_share))
        except ValueError:
            fail("KUBETEE_MINER_SHARE", "must be finite and within [0, 1]")

        poll_seconds = parse_float(
            "KUBETEE_POLL_SECONDS", MIN_POLL_SECONDS, MIN_POLL_SECONDS
        )
        max_skips = parse_int("KUBETEE_MAX_CONSECUTIVE_SKIPS", 10, 1)
        reconcile_cycles = parse_int("KUBETEE_RECONCILE_MIN_CYCLES", 3, 1)
        reconcile_seconds = parse_float("KUBETEE_RECONCILE_MIN_SECONDS", 900.0, 0.0)
        netuid = parse_int("KUBETEE_SUBNET_NETUID", 1, 0)
        metrics_port = parse_int("KUBETEE_METRICS_PORT", 9100, 1, 65535)

        owner_hotkey = require("KUBETEE_OWNER_HOTKEY")
        validator_hotkey = require("KUBETEE_VALIDATOR_HOTKEY")
        if owner_hotkey and validator_hotkey and owner_hotkey == validator_hotkey:
            fail(
                "KUBETEE_VALIDATOR_HOTKEY",
                "must differ from KUBETEE_OWNER_HOTKEY",
            )

        rancher_url = require("RANCHER_URL")
        if rancher_url:
            parts = urlsplit(rancher_url)
            if parts.scheme != "https" or not parts.netloc:
                fail("RANCHER_URL", "must be a https origin")
        rancher_token = require("RANCHER_BEARER_TOKEN")

        if errors:
            raise ConfigError(
                "invalid static configuration: " + "; ".join(errors)
            )

        return cls(
            network=(env.get("BT_NETWORK") or DEFAULT_NETWORK).strip(),
            wallet_name=(env.get("BT_WALLET") or DEFAULT_WALLET).strip(),
            wallet_hotkey=(env.get("BT_WALLET_HOTKEY") or "default").strip(),
            netuid=netuid,
            miner_share=miner_share,
            poll_seconds=poll_seconds,
            max_consecutive_skips=max_skips,
            reconcile_min_cycles=reconcile_cycles,
            reconcile_min_seconds=reconcile_seconds,
            owner_hotkey=owner_hotkey,
            validator_hotkey=validator_hotkey,
            rancher_url=rancher_url,
            rancher_token=rancher_token,
            metrics_port=metrics_port,
            metrics_addr=(env.get("KUBETEE_METRICS_ADDR") or "0.0.0.0").strip(),
        )


def load_config(env: Mapping[str, str] | None = None) -> ValidatorConfig:
    """Resolve config from the environment plus the setup-written netuid file
    (the setup phase records the netuid it actually owns)."""
    data = dict(os.environ if env is None else env)
    path = (data.get("KUBETEE_NETUID_FILE") or DEFAULT_NETUID_FILE).strip()
    try:
        text = pathlib.Path(path).read_text().strip()
    except OSError:
        text = ""
    if text:
        data["KUBETEE_SUBNET_NETUID"] = text
    return ValidatorConfig.from_env(data)


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
        self._cycle_config = CycleConfig(
            owner_hotkey=config.owner_hotkey,
            validator_hotkey=config.validator_hotkey,
            miner_share=config.miner_share,
        )

    # -- redaction (AC5) ------------------------------------------------------

    def _redact(self, text: str) -> str:
        return text.replace(self._config.rancher_token, "<redacted-token>")

    def _render(self, error: BaseException) -> str:
        return self._redact(f"{type(error).__name__}: {error}")

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

    def _read_neurons(self, subtensor) -> tuple[list[dict] | None, object]:
        try:
            meta = subtensor.metagraph(self._config.netuid)
            neurons = [
                {"uid": int(uid), "hotkey": str(hotkey)}
                for uid, hotkey in zip(meta.uids, meta.hotkeys, strict=True)
            ]
            return neurons, getattr(meta, "block", None)
        except Exception as error:  # fail closed; recreate only after failure
            self._chain_dirty = True
            self._log.warning("metagraph read failed: %s", self._render(error))
            return None, None

    def _refresh_registered(self) -> set[str] | None:
        """Fresh metagraph read for the reconciliation pre-delete recheck."""
        if self._subtensor is None:
            return None
        neurons, _ = self._read_neurons(self._subtensor)
        if neurons is None:
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
                and (c.get("labels") or {}).get(MINER_LABEL) == hotkey
            ]
            if len(matches) != 1:
                continue
            cluster_id = matches[0].get("id")
            if not isinstance(cluster_id, str) or not cluster_id:
                continue
            try:
                nodes_by_cluster[cluster_id] = self._rancher.list_nodes(cluster_id)
            except ValueError:
                continue  # invalid id: unfetched -> score 0
        return nodes_by_cluster

    # -- one cycle (spec 4.2 order) --------------------------------------------

    def _record_skip(self, reason: SkipReason, detail: str) -> None:
        entered_degraded = self._metrics.record_skip(reason)
        self._log.warning(
            "cycle skipped set_weights: reason=%s detail=%s consecutive=%d",
            reason.value,
            self._redact(detail),
            self._metrics.consecutive_skips,
        )
        if entered_degraded:
            self._log.critical(
                "DEGRADED MODE entered: %d consecutive skipped cycles exceeded "
                "KUBETEE_MAX_CONSECUTIVE_SKIPS=%d - on-chain weights are stale; "
                "operator intervention required (see SUBNET.md); weights are "
                "never auto-zeroed",
                self._metrics.consecutive_skips,
                self._config.max_consecutive_skips,
            )

    def run_cycle(self) -> str:
        """Run one validation cycle; returns the outcome tag for logs/tests."""
        subtensor = self._ensure_subtensor()

        # 1. metagraph (identity preconditions re-checked every cycle)
        neurons, block = self._read_neurons(subtensor)
        if neurons is None:
            self._reconciler.run_cycle(None, None, None, self._refresh_registered)
            self._record_skip(SkipReason.METAGRAPH_UNAVAILABLE, "metagraph read failed")
            return "skip"
        registered = {n["hotkey"] for n in neurons}
        miners = sorted(
            registered
            - {self._config.owner_hotkey, self._config.validator_hotkey}
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
            self._record_skip(SkipReason.RANCHER_UNAVAILABLE, str(error))
            return "skip"

        # 3. reconciliation (spec 4.2a; requires fresh metagraph + complete
        #    enumeration from this same cycle)
        self._reconciler.run_cycle(
            registered, clusters, block, self._refresh_registered
        )

        # 4. scoring (binary fail-closed) + identity validation
        scores = {
            hotkey: score_miner(hotkey, clusters, nodes_by_cluster)
            for hotkey in miners
        }
        decision = decide_cycle(neurons, scores, self._cycle_config)
        if isinstance(decision, SkipCycle):
            self._record_skip(decision.reason, decision.detail)
            return "skip"

        scoring_count = sum(decision.miner_scores.values())
        self._metrics.record_scoring_result(len(miners), scoring_count)
        self._metrics.record_successful_scoring()

        # 5. weights (signed by alice; success only on chain acceptance)
        uids = sorted(decision.weights)
        weights = [decision.weights[uid] for uid in uids]
        try:
            success, message = subtensor.set_weights(
                wallet=self._wallet,
                netuid=self._config.netuid,
                uids=uids,
                weights=weights,
            )
        except Exception as error:
            self._chain_dirty = True
            self._metrics.record_set_weights(False)
            self._log.warning(
                "set_weights raised, will back off and retry: %s",
                self._render(error),
            )
            return "weights_rejected"

        # 6. log + metrics (honest, redacted)
        self._metrics.record_set_weights(bool(success))
        if success:
            self._log.info(
                "set_weights accepted on chain: netuid=%d miners=%d scoring=%d "
                "scores=%s uids=%s weights=%s",
                self._config.netuid,
                len(miners),
                scoring_count,
                decision.miner_scores,
                uids,
                weights,
            )
            return "weights_set"
        self._log.warning(
            "set_weights rejected by chain (no success claimed): %s",
            self._redact(str(message)),
        )
        return "weights_rejected"

    def run_forever(self) -> None:
        """D14 liveness corollary: no runtime error may terminate the loop.
        Only operator signals (BaseException path) stop the process."""
        self._log.info(
            "basic validator started: netuid=%d poll=%gs share=%g "
            "max_consecutive_skips=%d rancher=%s",
            self._config.netuid,
            self._config.poll_seconds,
            self._config.miner_share,
            self._config.max_consecutive_skips,
            urlsplit(self._config.rancher_url).netloc,
        )
        while True:
            try:
                self.run_cycle()
            except Exception as error:  # never exit on a runtime error (D14)
                self._log.error(
                    "unexpected cycle error (loop continues): %s",
                    self._render(error),
                )
            self._sleep(self._config.poll_seconds)


def main(env: Mapping[str, str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        config = load_config(env)
    except ConfigError as error:
        _LOG.error("refusing to start: %s", error)
        raise SystemExit(2) from error

    # Lazy import: unit tests (and hosts without the SDK) never import
    # real bittensor; only the live process pays this cost.
    import bittensor as bt

    # bittensor's import reconfigures global logging to Warning, which would
    # mute the cycle-evidence INFO lines that AC5/AC9 assert on. Give our
    # logger its own handler and stop propagation so nothing upstream can
    # silence it.
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    _LOG.handlers.clear()
    _LOG.addHandler(handler)
    _LOG.setLevel(logging.INFO)
    _LOG.propagate = False

    wallet = bt.Wallet(name=config.wallet_name, hotkey=config.wallet_hotkey)
    metrics = ValidatorMetrics(max_consecutive_skips=config.max_consecutive_skips)
    # Compose keeps this port off the host network (AC11: compose-internal).
    start_http_server(
        config.metrics_port, addr=config.metrics_addr, registry=metrics.registry
    )
    client = RancherClient(config.rancher_url, config.rancher_token)

    def evidence_sink(event: dict) -> None:
        _LOG.info(
            "reconciliation evidence: event=%(event)s correlation_id=%(correlation_id)s",
            {"event": event.get("event"), "correlation_id": event.get("correlation_id"), **event},
        )

    reconciler = ReconciliationEngine(
        client,
        metrics,
        min_cycles=config.reconcile_min_cycles,
        min_seconds=config.reconcile_min_seconds,
        evidence_sink=evidence_sink,
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
