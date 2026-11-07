"""Read-only SN64 daily payout medians for the publisher's dashboard.

The proportional attribution and earning-node denominator follow
``docs/miner_revenue.py``. These estimates never affect KubeTEE issuance.
Only the publisher downloads responses, at most once per chain epoch.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import math
import statistics
import time

import httpx

NODES_URL = "https://api.chutes.ai/nodes/?detailed=true"
STATS_URL = "https://api.chutes.ai/miner/stats?per_chute=true"
CATALOG_URL = "https://api.chutes.ai/chutes/?limit=500"
METAGRAPH_URL = (
    "https://api.taostats.io/api/metagraph/latest/v1?netuid=64&limit=1000"
)
CLASS_LABELS = {
    "H100": "H100",
    "H200": "H200",
    "B200": "B200",
    "B300": "B300",
    "Pro 6000": "RTX6000",
}
NORMALIZATION = (
    ("h100_sxm", "H100 SXM"),
    ("h100_pcie", "H100 PCIe"),
    ("a100_sxm", "A100 SXM"),
    ("a100_pcie", "A100 PCIe"),
    ("a100_80g", "A100 80G"),
    ("rtx_6000_ada", "RTX 6000 Ada"),
    ("rtx_4090", "RTX 4090"),
    ("rtx_3090", "RTX 3090"),
    ("pro_6000", "Pro 6000"),
    ("h200", "H200"),
    ("h100", "H100"),
    ("a100", "A100"),
    ("l40s", "L40S"),
    ("l40", "L40"),
    ("b200", "B200"),
)
log = logging.getLogger("validator")


def display_class(gpu_type: str) -> str | None:
    if gpu_type.strip().lower() == "pro_6000":
        return "RTX6000"
    return CLASS_LABELS.get(gpu_type)


def normalize_gpu_type(value: str) -> str:
    lowered = (value or "unknown").lower()
    for key, label in NORMALIZATION:
        if key in lowered:
            return label
    return value.upper()


def _is_tee(chute_id: str, name: str, catalog: dict) -> bool:
    if chute_id in catalog:
        return bool(catalog[chute_id].get("tee", False))
    return "tee" in name.lower() or "tee" in chute_id.lower()


def _hotkey(entry: dict) -> str:
    value = entry.get("hotkey", "")
    return value.get("ss58", "") if isinstance(value, dict) else value


def get_emission(entry: dict) -> float:
    """Match the reference field precedence and rao/TAO scale boundary."""
    value = entry.get("daily_total_rewards_as_tao")
    if value is None:
        value = entry.get("daily_mining_alpha_as_tao")
    if not value:
        value = entry.get("emission", entry.get("daily_emission", 0))
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value):
        return 0.0
    return value / 1e9 if value > 1_000_000 else value


def _new_miner() -> dict:
    return {"gpus": {}, "history": {}, "tee24": 0.0, "current_tee": 0}


def calculate_medians(
    nodes: dict, stats: dict, catalog: dict, metagraph: dict, tao_usd: float
) -> dict:
    """Reproduce the reference's deployed-shares attribution and medians."""
    chutes = {}
    catalog_items = (
        catalog.get("items", [])
        if isinstance(catalog, dict)
        else catalog or []
    )
    for chute in catalog_items:
        if isinstance(chute, dict) and chute.get("chute_id"):
            chutes[chute["chute_id"]] = chute
    miners = {}
    provisioned = nodes.items() if isinstance(nodes, dict) else []
    for hotkey, data in provisioned:
        miner = miners.setdefault(hotkey, _new_miner())
        for node in data.get("provisioned", []):
            kind = normalize_gpu_type(node.get("gpu", "unknown"))
            gpu = miner["gpus"].setdefault(
                kind, {"count": 0, "tee": 0, "non": 0, "chutes": []}
            )
            chute = node.get("chute") or {}
            chute_id = chute.get("chute_id", "")
            tee = _is_tee(chute_id, chute.get("name", ""), chutes)
            gpu["count"] += 1
            gpu["tee" if tee else "non"] += 1
            gpu["chutes"].append(chute_id)
            miner["current_tee"] += int(tee)
        for kind, count in data.get("idle", {}).items():
            if count > 0:
                gpu = miner["gpus"].setdefault(
                    normalize_gpu_type(kind),
                    {"count": 0, "tee": 0, "non": 0, "chutes": []},
                )
                gpu["count"] += count

    names = {}
    for hotkey, data in provisioned:
        if hotkey not in miners:
            continue
        for node in data.get("provisioned", []):
            chute = node.get("chute") or {}
            if chute.get("chute_id"):
                names[chute["chute_id"]] = chute.get("name", "")
    for entry in (stats or {}).get("past_day", {}).get("compute_units", []):
        hotkey, chute_id = entry.get("miner_hotkey"), entry.get("chute_id", "")
        if not hotkey:
            continue
        miner = miners.setdefault(hotkey, _new_miner())
        if _is_tee(
            chute_id,
            names.get(chute_id, chutes.get(chute_id, {}).get("name", "")),
            chutes,
        ):
            cu = entry.get("compute_units", 0.0)
            miner["history"][chute_id] = (
                miner["history"].get(chute_id, 0.0) + cu
            )
            miner["tee24"] += cu

    for miner in miners.values():
        chute_counts, type_counts = {}, {}
        for kind, gpu in miner["gpus"].items():
            for chute_id in gpu["chutes"]:
                if chute_id:
                    counts = chute_counts.setdefault(chute_id, {})
                    counts[kind] = counts.get(kind, 0) + 1
                    type_counts[kind] = type_counts.get(kind, 0) + 1
        total_nodes = sum(type_counts.values()) or 1
        fallback = {
            kind: count / total_nodes for kind, count in type_counts.items()
        }
        for chute_id, cu in miner["history"].items():
            shares = chute_counts.get(chute_id) or fallback
            total = sum(shares.values()) or 1
            for kind, count in shares.items():
                compute = miner.setdefault("compute", {})
                compute[kind] = compute.get(kind, 0.0) + cu * count / total

    tee_hotkeys = {
        hotkey
        for hotkey, miner in miners.items()
        if miner["tee24"] > 0 or miner["current_tee"]
    }
    emissions_usd = sum(
        get_emission(entry) * tao_usd
        for entry in (metagraph or {}).get("data", [])
        if _hotkey(entry) in tee_hotkeys
    )
    fleet_tee_cu = sum(
        sum(miners[hotkey].get("compute", {}).values())
        for hotkey in tee_hotkeys
    )
    rows = []
    rewards = (metagraph or {}).get("data", [])
    rows_rewards = {
        _hotkey(entry): entry for entry in rewards if isinstance(entry, dict)
    }
    for hotkey, miner in miners.items():
        if hotkey not in tee_hotkeys:
            continue
        reward = rows_rewards.get(hotkey, {})
        emission = get_emission(reward)
        gpu_types = [gpu for gpu in miner["gpus"].values() if gpu["count"]]
        cu_total = sum(miner.get("compute", {}).values())
        for kind, gpu in (
            (kind, gpu) for kind, gpu in miner["gpus"].items() if gpu["count"]
        ):
            cu = miner.get("compute", {}).get(kind, 0.0)
            fraction = (
                cu / cu_total
                if cu_total
                else 1 / len(gpu_types) if gpu_types else 0.0
            )
            if emission > 0:
                day_usd = emission * fraction * tao_usd
            elif fleet_tee_cu:
                day_usd = cu * emissions_usd / fleet_tee_cu
            else:
                day_usd = 0.0
            earning_gpus = gpu["tee"] + gpu["non"] or gpu["count"]
            rate = day_usd / earning_gpus / 24 if earning_gpus else 0
            if display_class(kind) and math.isfinite(rate):
                rows.append(
                    {
                        "gpu": display_class(kind),
                        "hotkey": hotkey,
                        "uid": reward.get("uid", 0),
                        "rate": rate,
                        "nodes": earning_gpus,
                        "tee_nodes": gpu["tee"],
                        "non_tee_nodes": gpu["non"],
                        "daily_usd": day_usd,
                    }
                )
    per_class, samples = {}, {}
    for label in CLASS_LABELS.values():
        rates = [row["rate"] for row in rows if row["gpu"] == label]
        if rates:
            per_class[label] = statistics.median(rates)
            samples[label] = len(rates)
    return {
        "rows": rows,
        "per_class_usd": per_class,
        "samples": samples,
        "mode": "median_24h",
    }


class ChutesEarningsFeed:
    """One synchronous, bounded batch per epoch; no background retry loop."""

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(trust_env=False)
        self.executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="chutes-read"
        )
        self.last = None
        self.attempted = None

    def snapshot(self, block: int, tempo: int, tao_usd: float) -> dict | None:
        if block <= 0 or tempo <= 0:
            return dict(self.last) if self.last else None
        bucket = block // tempo
        if self.attempted == bucket:
            return dict(self.last) if self.last else None
        self.attempted = bucket
        try:
            if not math.isfinite(tao_usd) or tao_usd <= 0:
                raise ValueError("TAO/USD unavailable")
            deadline = time.monotonic() + 90
            requests = [
                (NODES_URL, ""),
                (STATS_URL, ""),
                (CATALOG_URL, ""),
                (METAGRAPH_URL, self.api_key),
            ]
            jobs = [
                self.executor.submit(self._get, url, key, deadline)
                for url, key in requests
            ]
            inputs = [
                job.result(timeout=max(0.001, deadline - time.monotonic()))
                for job in jobs
            ]
            metrics = calculate_medians(*inputs, tao_usd)
            self.last = {
                "per_class_usd": metrics["per_class_usd"],
                "samples": metrics["samples"],
                "mode": metrics["mode"],
                "bucket": bucket,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "tao_usd": tao_usd,
                "observation_window": "current_24h",
                "stale": False,
            }
            log.info(
                "Chutes dashboard medians: %s", self.last["per_class_usd"]
            )
        except Exception as exc:
            log.warning(
                "Chutes dashboard epoch %s fetch failed: %s", bucket, exc
            )
        if self.last:
            self.last["stale"] = bucket != self.last["bucket"]
        return dict(self.last) if self.last else None

    def _get(self, url: str, key: str, deadline: float) -> dict:
        # This credential is scoped to Taostats; never send it to Chutes.
        headers = {
            "Accept": "application/json",
            "User-Agent": "kubetee-validator/0.1",
        }
        if key:
            headers["Authorization"] = key
        response = self.client.get(
            url,
            headers=headers,
            timeout=max(0.001, deadline - time.monotonic()),
        )
        response.raise_for_status()
        return response.json()
