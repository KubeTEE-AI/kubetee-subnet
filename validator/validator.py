"""KubeTEE subnet-owner validator: epoch loop.

Per cycle: metagraph -> Rancher enumerate -> price feeds -> readiness ->
proportional USD-per-epoch weight split -> set_weights once per chain epoch.
The subnet-owner also publishes the public dashboard to Hippius S3.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
import threading
import time
import traceback

import validator_metrics as metrics
import dashboard as _dashboard
from chain_state import ChainState
from config import Config, ConfigError, load_config
from hippius_store import (
    DEFAULT_CARD_KEY,
    DEFAULT_PAYOUT_KEY,
    HippiusError,
    HippiusStore,
    fetch_published_payout,
)
from infrastructure_validation import node_posture, validate_miner
from miner_scoring import MinerInput, compute_weights
from price_card import build_price_card, require_card, resolve_card
from price_feed import PriceFeed, PriceFeedError
from rancher_client import RancherClient, RancherEvidenceError, hotkey_of
from targon_payout_feed import TargonPayoutFeed

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-7s %(message)s",
)
log = logging.getLogger("kubetee-validator")


def load_validated_config() -> Config:
    try:
        return load_config()
    except ConfigError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        sys.exit(2)


class Validator:
    def __init__(
        self, config: Config, dry_run: bool, once: bool = False
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self.once = once
        self.chain = ChainState(
            config.network, config.endpoint, config.hotkey_seed
        )
        # Reader-mode: when RANCHER_BEARER_TOKEN is empty, the client signs
        # each request with the validator hotkey (proxy path). The keypair
        # is the same one used for set_weights — no new key material.
        self.rancher = RancherClient(
            config,
            keypair=None if config.rancher_token else self.chain.keypair,
        )
        self.price_feed = PriceFeed(config, chain_state=self.chain)
        self.targon = TargonPayoutFeed(config)
        self.hippius: HippiusStore | None = None
        if config.is_publisher:
            self.hippius = HippiusStore(
                config.hippius_access_key, config.hippius_secret_key
            )
        self._last_card: dict[str, float] | None = None
        self._last_submitted_epoch = -1
        self._last_set_block: int | None = None
        self._last_targon_payout: dict[str, float] = {}

    def _first_cycle(self) -> bool:
        return self._last_card is None

    def run_cycle(self) -> None:
        cfg = self.config

        miners = self.chain.metagraph(cfg.netuid)
        log.info("metagraph: %d neurons", len(miners))

        try:
            clusters = self.rancher.list_clusters()
            nodes_by_cluster = {
                self.rancher.cluster_id(c): self.rancher.list_nodes(
                    self.rancher.cluster_id(c)
                )
                for c in clusters
            }
        except RancherEvidenceError as exc:
            log.warning("skip cycle: rancher evidence outage: %s", exc)
            metrics.record_skip("rancher")
            return

        card, card_source = self._resolve_card()
        try:
            require_card(card_source, self._first_cycle())
        except Exception as exc:
            log.error("%s", exc)
            if self.hippius is None:
                raise
        self._last_card = card

        effective_card, pricing_source, targon_age = self._targon_card()
        log.info(
            "card[%s/%s]=%s",
            card_source,
            pricing_source,
            effective_card,
        )

        # Price feed: live Taostats (cached on 429) + chain, else S3 snapshot.
        published_payout = fetch_published_payout()
        if published_payout:
            self.price_feed.seed_from_published(published_payout)
        tao_usd_fb: float | None = None
        alpha_to_tao_fb: float | None = None
        try:
            usd_per_alpha = self.price_feed.usd_per_alpha()
        except PriceFeedError as exc:
            # Fallback: try the owner's last-known price snapshot from S3
            # (payout.json carries tao_usd + alpha_to_tao). This lets a reader
            # validator keep scoring for one cycle when Taostats is down,
            # instead of skipping indefinitely and leaving stale weights.
            fallback = self._fallback_usd_per_alpha()
            if fallback is None:
                log.warning(
                    "skip cycle: price feed unavailable: %s (no S3 fallback)",
                    exc,
                )
                metrics.record_skip("price_feed")
                return
            usd_per_alpha, tao_usd_fb, alpha_to_tao_fb = fallback
            log.warning(
                "price feed down (%s) — using S3 fallback "
                "usd_per_alpha=%.6g tao_usd=%.2f alpha_to_tao=%.6g",
                exc,
                usd_per_alpha,
                tao_usd_fb,
                alpha_to_tao_fb,
            )
        log.info("usd_per_alpha=%.6g", usd_per_alpha)

        # Read on-chain emissions (alpha tokens paid per UID last epoch)
        chain_emissions = self.chain.emissions()
        if chain_emissions:
            for uid, em in sorted(chain_emissions.items()):
                if em > 0:
                    log.info(
                        "chain emission: UID %d = %.4f alpha/epoch", uid, em
                    )

        # Compute the emission pool (Targon-style): the total USD value of
        # alpha the subnet mints for miners per epoch, from on-chain data.
        # If the price feed was down and we used the S3 fallback, reuse that
        # tao_usd (don't re-fetch — it would fail again).
        if tao_usd_fb is not None:
            tao_usd = tao_usd_fb
        else:
            try:
                tao_usd = self.price_feed.tao_usd()
            except PriceFeedError:
                tao_usd = 0.0
        emission_pool_usd = self.chain.emission_pool_usd(tao_usd)
        log.info(
            "emission pool: $%.2f USD/epoch (alpha_out=%.4f TAO/blk, moving_price=%.8f, tao_usd=%.2f)",
            emission_pool_usd,
            self.chain.alpha_out_emission(),
            self.chain.moving_price(),
            tao_usd,
        )

        # Publish the payout snapshot (owner only) with the price fields
        # included, so reader validators can fall back to them when Taostats
        # is down. Deferred from _targon_card because tao_usd + alpha_to_tao
        # are only known here.
        if self.hippius is not None and self._last_targon_payout:
            alpha_to_tao_now = self.chain.spot_price() or None
            self._publish_payout(
                self._last_targon_payout,
                tao_usd=(
                    tao_usd if tao_usd > 0 else self.price_feed.last_tao_usd
                ),
                alpha_to_tao=(
                    alpha_to_tao_now
                    if alpha_to_tao_now and alpha_to_tao_now > 0
                    else None
                ),
            )

        registered_hotkeys = {m.hotkey for m in miners}
        metagraph_clusters = [
            c for c in clusters if hotkey_of(c) in registered_hotkeys
        ]
        orphans = len(clusters) - len(metagraph_clusters)
        if orphans:
            log.info("dropping %d unbound/spoofed labeled clusters", orphans)

        inputs: list[MinerInput] = []
        for miner in miners:
            verdict = validate_miner(
                miner.hotkey,
                metagraph_clusters,
                nodes_by_cluster,
                self.rancher.cluster_id,
            )
            if not verdict.ready and miner.uid == cfg.owner_miner_uid:
                log.info(
                    "owner staging miner uid=%d override: NOT ready -> ready",
                    miner.uid,
                )
                verdict = dataclasses.replace(verdict, ready=True)
            include_tdx_non_cc = miner.uid == cfg.owner_miner_uid
            gpu_class, workers, breakdown = self._miner_gpu_posture(
                miner.hotkey,
                clusters,
                nodes_by_cluster,
                verdict.ready,
                include_tdx_non_cc=include_tdx_non_cc,
            )
            if verdict.ready:
                log.info(
                    "miner uid=%d ready: %s",
                    miner.uid,
                    ", ".join(
                        f"{count}x {klass} GPU"
                        for klass, count in sorted(breakdown.items())
                    )
                    or "no qualifying GPUs",
                )
            else:
                log.info(
                    "miner uid=%d NOT ready: %s",
                    miner.uid,
                    "; ".join(verdict.reasons),
                )
            # Cluster display name for the dashboard: the Rancher cluster
            # that carried this miner's kubetee.ai/hotkey binding.
            cluster_name = None
            bound = [
                c for c in metagraph_clusters if hotkey_of(c) == miner.hotkey
            ]
            if bound:
                cluster_name = bound[0].get("name")
            inputs.append(
                MinerInput(
                    uid=miner.uid,
                    hotkey=miner.hotkey,
                    ready=verdict.ready,
                    gpu_class=gpu_class,
                    gpu_workers=workers,
                    gpu_breakdown=tuple(sorted(breakdown.items())),
                    total_qualifying_workers=sum(breakdown.values()),
                    cluster_name=cluster_name,
                )
            )

        tempo = self._tempo_from_chain()
        hours_per_epoch = (tempo * 12) / 3600.0
        try:
            scores = compute_weights(
                inputs,
                effective_card,
                usd_per_alpha,
                hours_per_epoch,
                cfg.owner_uid,
                emission_pool_usd,
            )
        except ValueError as exc:
            log.warning("skip cycle: scoring error: %s", exc)
            metrics.record_skip("scoring")
            return
        weights = scores.weights

        usd = scores.miner_usd
        total_earned = sum(usd.values())
        owner_usd = max(0.0, emission_pool_usd - total_earned)
        total_pool = emission_pool_usd
        parts = []
        for uid, amount in sorted(usd.items()):
            alpha_amount = amount / usd_per_alpha
            share = scores.miner_shares.get(uid, 0.0) * 100
            parts.append(
                f"uid={uid} ${amount:,.2f} -> {alpha_amount:,.4f} alpha ({share:.1f}%)"
            )
        log.info("miner payout: %s", "; ".join(parts) or "(none)")
        log.info(
            "total pool this epoch: $%s USD (miner earned $%s "
            "+ Recycled $%s)",
            f"{total_pool:,.2f}",
            f"{total_earned:,.2f}",
            f"{owner_usd:,.2f}",
        )

        fleet_gpus: dict[str, int] = {}
        for inp in inputs:
            if inp.ready:
                for klass, count in inp.gpu_breakdown or (
                    (inp.gpu_class, inp.gpu_workers) if inp.gpu_class else ()
                ):
                    fleet_gpus[str(klass)] = fleet_gpus.get(
                        str(klass), 0
                    ) + int(count)
        if fleet_gpus:
            log.info(
                "GPU inventory this cycle: %s",
                ", ".join(
                    f"{count}x {klass}"
                    for klass, count in sorted(fleet_gpus.items())
                ),
            )
        log.info(
            "weights: earning=%d recycled=%.4f %s",
            sum(1 for i in inputs if i.ready),
            scores.owner_weight,
            {u: round(w, 4) for u, w in sorted(weights.items())},
        )
        if not weights:
            log.warning("skip cycle: no weight vector produced")
            metrics.record_skip("scoring")
            return

        weights = self._pad_to_metagraph(weights, miners)
        if self.dry_run:
            log.info("dry-run: would set_weights on %d uids", len(weights))
        else:
            self._set_weights_once_per_epoch(weights)

        metrics.record_cycle(
            earning=sum(1 for i in inputs if i.ready),
            weights=weights,
            owner_weight=scores.owner_weight,
            usd_per_alpha=usd_per_alpha,
            effective_card=effective_card,
            pricing_source=pricing_source,
            card_source=card_source,
            targon_age_seconds=targon_age,
        )

        if self.hippius is not None:
            snapshot = {
                "epoch": self._current_epoch_from_chain(),
                "block": self._epoch(),
                "tempo": tempo,
                "hours_per_epoch": hours_per_epoch,
                "usd_per_alpha": usd_per_alpha,
                "card": card,
                "effective_card": effective_card,
                "targon_payout": self._last_targon_payout or {},
                "chain_emissions": chain_emissions,
                "pricing_source": pricing_source,
                "card_source": card_source,
                "miner_usd": round(total_earned, 2),
                "owner_usd": round(owner_usd, 2),
                "total_pool_usd": round(total_pool, 2),
                "fleet_gpus": fleet_gpus,
                "miners": [
                    {
                        "uid": inp.uid,
                        "cluster_name": inp.cluster_name,
                        "ready": bool(inp.ready),
                        "gpus": [
                            list(x) for x in sorted(inp.gpu_breakdown or ())
                        ],
                        "usd": round(
                            sum(
                                effective_card.get(k, 0.0) * int(c)
                                for k, c in sorted(inp.gpu_breakdown or ())
                            )
                            * hours_per_epoch,
                            2,
                        ),
                        "alpha": round(
                            (
                                sum(
                                    effective_card.get(k, 0.0) * int(c)
                                    for k, c in sorted(inp.gpu_breakdown or ())
                                )
                                * hours_per_epoch
                                / usd_per_alpha
                                if usd_per_alpha > 0
                                else 0.0
                            ),
                            4,
                        ),
                        "share": round(
                            (
                                sum(
                                    effective_card.get(k, 0.0) * int(c)
                                    for k, c in sorted(inp.gpu_breakdown or ())
                                )
                                * hours_per_epoch
                                / total_pool
                                * 100
                                if total_pool > 0
                                else 0.0
                            ),
                            1,
                        ),
                    }
                    for inp in inputs
                    if inp.ready
                ],
            }
            try:
                _dashboard.publish_dashboard(self.hippius, snapshot)
            except Exception as exc:  # noqa: BLE001
                log.warning("dashboard publish failed: %s", exc)

    def _resolve_card(self) -> tuple[dict[str, float], str]:
        if self.hippius is not None:
            card = self.targon.card()
            self._publish_card(card)
            return card, "published"
        return resolve_card(self._read_published_card, self._last_card)

    def _read_published_card(self) -> dict | None:
        store = self.hippius or HippiusStore("", "")
        return store.get_json(DEFAULT_CARD_KEY)

    def _fallback_usd_per_alpha(self) -> tuple[float, float, float] | None:
        """S3 fallback for the price feed: read the owner's last payout.json.

        Returns (usd_per_alpha, tao_usd, alpha_to_tao) from the published
        snapshot, or None if the snapshot is unavailable / missing the
        price fields. Used when the live Taostats feed is down — one cycle
        stale, strictly better than skipping and leaving stale weights.
        """
        published = fetch_published_payout()
        if published:
            self.price_feed.seed_from_published(published)
        tao_usd = self.price_feed.last_tao_usd
        if tao_usd is None and published:
            tao_usd = self.price_feed.tao_usd_from_published(published)
        alpha_to_tao_raw = (
            published.get("alpha_to_tao")
            if isinstance(published, dict)
            else None
        )
        alpha_to_tao = (
            float(alpha_to_tao_raw)
            if isinstance(alpha_to_tao_raw, (int, float))
            and alpha_to_tao_raw > 0
            else None
        )
        if alpha_to_tao is None:
            spot = self.chain.spot_price()
            alpha_to_tao = spot if spot and spot > 0 else None
        if tao_usd is None or alpha_to_tao is None:
            return None
        return (
            float(tao_usd) * float(alpha_to_tao),
            float(tao_usd),
            float(alpha_to_tao),
        )

    def _publish_card(self, card: dict[str, float]) -> None:
        if self.dry_run:
            log.info("dry-run: skip publish price-card %s", card)
            return
        try:
            self.hippius.put_json(
                DEFAULT_CARD_KEY,
                build_price_card(epoch=self._epoch(), usd_per_gpu_hour=card),
            )
            metrics.record_publish("price-card", True)
        except HippiusError as exc:
            metrics.record_publish("price-card", False)
            log.warning("publish price-card failed: %s", exc)

    def _targon_card(self) -> tuple[dict[str, float], str, float]:
        per_card, pricing_source = self.targon.resolve_per_card_usd()
        self._last_targon_payout = per_card
        # NOTE: payout publish is deferred to run_cycle after tao_usd +
        # alpha_to_tao are known (they're included in the snapshot so
        # readers can fall back to them when Taostats is down).
        effective, _ = self.targon.effective_card()
        return effective, pricing_source, 0.0

    def _publish_payout(
        self,
        per_card: dict[str, float],
        tao_usd: float | None = None,
        alpha_to_tao: float | None = None,
    ) -> None:
        if self.dry_run:
            log.info("dry-run: skip publish payout %s", per_card)
            return
        payload: dict = {
            "epoch": self._epoch(),
            "per_card_usd": {k: float(v) for k, v in per_card.items()},
            "published_at": time.time(),
            "source": "https://stats.targon.com/api/miners",
            "version": 1,
        }
        # Include the price snapshot so reader validators can fall back to
        # these when Taostats is down (one cycle stale, strictly better than
        # skipping and leaving stale weights on chain indefinitely).
        if tao_usd is not None and tao_usd > 0:
            payload["tao_usd"] = float(tao_usd)
        if alpha_to_tao is not None and alpha_to_tao > 0:
            payload["alpha_to_tao"] = float(alpha_to_tao)
        try:
            self.hippius.put_json(DEFAULT_PAYOUT_KEY, payload)
            metrics.record_publish("payout", True)
        except HippiusError as exc:
            metrics.record_publish("payout", False)
            log.warning("publish payout failed: %s", exc)

    def _miner_gpu_breakdown(
        self,
        hotkey: str,
        clusters,
        nodes_by_cluster,
        include_tdx_non_cc: bool = False,
    ) -> dict[str, int]:
        """{gpu_class: total GPU count}, summed per qualifying node per class."""
        bound = [c for c in clusters if hotkey_of(c) == hotkey]
        if not bound:
            return {}
        cid = self.rancher.cluster_id(bound[0])
        breakdown: dict[str, int] = {}
        for node in nodes_by_cluster.get(cid, []):
            p = node_posture(node)
            if not (p.ready and p.schedulable and p.gpu_class):
                continue
            labels = node.get("labels") or {}
            raw = labels.get("nvidia.com/gpu.count")
            if raw is None:
                count = 8
            else:
                try:
                    count = max(0, int(str(raw)))
                except (TypeError, ValueError):
                    count = 0
            if count < 8:
                continue
            cc_ok = p.vm_passthrough and p.kata_confidential_runtime
            if cc_ok:
                breakdown[p.gpu_class] = breakdown.get(p.gpu_class, 0) + count
                continue
            if include_tdx_non_cc and (
                labels.get("intel.feature.node.kubernetes.io/tdx") == "true"
                or labels.get(
                    "feature.node.kubernetes.io/cpu-security.tdx.enabled"
                )
                == "true"
                or "tdx" in (labels.get("nvidia.com/cc.mode", "").lower())
                or labels.get("katacontainers.io/kata-runtime") == "true"
            ):
                breakdown[p.gpu_class] = breakdown.get(p.gpu_class, 0) + count
        return breakdown

    def _miner_gpu_posture(
        self,
        hotkey: str,
        clusters,
        nodes_by_cluster,
        ready: bool,
        include_tdx_non_cc: bool = False,
    ) -> tuple[str | None, int, dict[str, int]]:
        """Dominant (highest-value) gpu class + its GPU count + per-class counts."""
        if not ready:
            return None, 0, {}
        breakdown = self._miner_gpu_breakdown(
            hotkey,
            clusters,
            nodes_by_cluster,
            include_tdx_non_cc=include_tdx_non_cc,
        )
        if not breakdown:
            return None, 0, breakdown
        order = {"B300": 3, "B200": 2, "H200": 1, "H100": 0}
        dominant = max(
            breakdown, key=lambda k: (breakdown[k], order.get(k, -1))
        )
        return dominant, breakdown[dominant], breakdown

    def _pad_to_metagraph(
        self, weights: dict[int, float], miners
    ) -> dict[int, float]:
        return {m.uid: weights.get(m.uid, 0.0) for m in miners}

    def _epoch(self) -> int:
        try:
            return int(self.chain._subtensor.block)
        except Exception:  # noqa: BLE001
            return 0

    def _epoch_progress(self) -> tuple[int, int, int] | None:
        try:
            return self.chain.epoch_progress(self.config.netuid)
        except Exception:  # noqa: BLE001
            return None

    def _tempo_from_chain(self) -> int:
        progress = self._epoch_progress()
        if progress and progress[0]:
            return int(progress[0])
        return 360

    def _current_epoch_from_chain(self) -> int:
        tempo = self._tempo_from_chain()
        block = self._epoch()
        return block // tempo if tempo > 0 else 0

    def _set_weights_once_per_epoch(self, weights: dict[int, float]) -> None:
        tempo = self._tempo_from_chain()
        block = self._epoch()
        current_epoch = block // tempo
        if self._last_submitted_epoch >= current_epoch:
            log.info(
                "epoch %d: already attempted this epoch; not submitting",
                current_epoch,
            )
            return

        # Wait for the chain's weights_rate_limit cooldown before attempting.
        rate_limit = 100
        try:
            rl = self.chain.weights_rate_limit(self.config.netuid)
            if rl is not None:
                rate_limit = rl
        except Exception:
            pass

        blocks_since = block - (self._last_set_block or 0)
        if self._last_set_block is not None and blocks_since < rate_limit:
            remaining = rate_limit - blocks_since
            log.info(
                "epoch %d: cooldown %d/%d blocks (wait %d more ~%ds); skipping",
                current_epoch,
                blocks_since,
                rate_limit,
                remaining,
                remaining * 12,
            )
            return

        try:
            log.info(
                "epoch %d boundary (block=%d tempo=%d rate_limit=%d) -> set_weights",
                current_epoch,
                block,
                tempo,
                rate_limit,
            )
            self.chain.set_weights(self.config.netuid, weights)
            self._last_submitted_epoch = current_epoch
            self._last_set_block = block
            log.info(
                "set_weights OK (epoch %d, block %d)", current_epoch, block
            )
        except Exception as exc:
            # Do NOT advance _last_submitted_epoch on rejection: the next cycle
            # should retry within the same epoch if the rate limit allows.
            log.warning(
                "set_weights rejected for epoch %d (will retry): %s",
                current_epoch,
                exc,
            )
            metrics.record_skip("set_weights")

    def _log_chain_hyperparams(self) -> None:
        hyperparams = self.chain.hyperparams(self.config.netuid)
        if not hyperparams:
            log.info("hyperparams: not available")
            return
        for name, value in sorted(hyperparams.items()):
            log.info("hyperparameter %-32s = %s", name, value)

    def run_forever(self) -> None:
        log.info(
            "validator start netuid=%d network=%s endpoint=%s publisher=%s dry_run=%s owner_uid=%d",
            self.config.netuid,
            self.config.network,
            self.chain.endpoint,
            self.config.is_publisher,
            self.dry_run,
            self.config.owner_uid,
        )
        self._log_chain_hyperparams()
        if self.hippius is not None:
            log.info("publishing startup banner to dashboard")
            _, pricing_source = self.targon.resolve_per_card_usd()
            try:
                _dashboard.publish_dashboard(
                    self.hippius,
                    {
                        "epoch": 0,
                        "block": 0,
                        "tempo": 360,
                        "usd_per_alpha": 0.0,
                        "card": self.targon.card(),
                        "effective_card": {},
                        "targon_payout": {},
                        "pricing_source": pricing_source,
                        "card_source": "starting",
                        "miner_usd": 0.0,
                        "owner_usd": 0.0,
                        "total_pool_usd": 0.0,
                        "fleet_gpus": {},
                        "miners": [],
                    },
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("startup dashboard publish failed: %s", exc)
        while True:
            started = time.monotonic()
            try:
                self.run_cycle()
            except KeyboardInterrupt:
                raise
            except Exception:  # noqa: BLE001
                log.error(
                    "unexpected cycle error:\n%s", traceback.format_exc()
                )
                metrics.record_skip("unexpected")
            if self.once:
                log.info("--once: single cycle done")
                return
            elapsed = time.monotonic() - started
            time.sleep(max(0.0, self.config.cycle_seconds - elapsed))


def main() -> int:
    config = load_validated_config()
    dry_run = os.environ.get("DRY_RUN", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    once = os.environ.get("ONCE", "").strip().lower() in {"1", "true", "yes"}
    if config.is_publisher and not config.hippius_secret_key:
        print(
            "ERROR publisher needs KUBETEE_HIPPIUS_SECRET_KEY", file=sys.stderr
        )
        return 2
    metrics.start_metrics_server(config.metrics_port)

    # Start the hotkey-authenticated Rancher proxy on the subnet-owner
    # instance only (RANCHER_URL + RANCHER_BEARER_TOKEN both set). Reader
    # validators skip this entirely — they point RANCHER_URL at the proxy.
    if config.rancher_url and config.rancher_token:
        import rancher_proxy

        proxy_chain = ChainState(
            config.network, config.endpoint, config.hotkey_seed
        )
        proxy_rancher = RancherClient(
            config
        )  # owner path — token set, no keypair needed
        proxy_port = int(os.environ.get("KUBETEE_PROXY_PORT", "9101"))
        threading.Thread(
            target=rancher_proxy.start_proxy_server,
            args=(proxy_port, proxy_chain, proxy_rancher, config.netuid, log),
            daemon=True,
        ).start()
        log.info("rancher proxy started on port %d", proxy_port)

    Validator(config, dry_run=dry_run, once=once).run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
