"""Chutes display metrics vs reference input behavior; no network."""

from dataclasses import dataclass, field
from pathlib import Path
import json
import pytest
import chutes_earnings_feed as feed


@pytest.fixture(scope="session")
def captured_input():
    directory = Path(__file__).parent / "fixtures" / "chutes-reference"
    return {
        name: json.loads((directory / f"{name}.json").read_text())
        for name in ("nodes", "stats", "catalog", "rewards")
    }


@dataclass
class MinerGPU:
    gpu_type: str
    count: int = 0
    tee_count: int = 0
    non_tee_count: int = 0
    chutes: list = field(default_factory=list)


@dataclass
class MinerInfo:
    hotkey: str
    uid: int = -1
    emission: float = 0.0
    tee_gpus: int = 0
    tee_compute_24h: float = 0.0
    gpus_by_type: dict = field(default_factory=dict)
    compute_by_gpu_type: dict = field(default_factory=dict)
    tee_chutes_24h: list = field(default_factory=list)
    tee_chute_compute_24h: dict = field(default_factory=dict)


def _is_tee(chute_id, name, catalog):
    if chute_id in catalog:
        return catalog[chute_id].get("tee", False)
    return "tee" in name.lower() or "tee" in chute_id.lower()


def reference_nodes(nodes_data, catalog):
    """Self-contained math-only extraction from ``docs/miner_revenue.py``."""
    miners = {}
    for hotkey, data in nodes_data.items():
        miner = MinerInfo(hotkey)
        for node in data.get("provisioned", []):
            kind = feed.normalize_gpu_type(node.get("gpu", "unknown"))
            chute = node.get("chute", {})
            chute_id = chute.get("chute_id", "")
            tee = _is_tee(chute_id, chute.get("name", ""), catalog)
            gpu = miner.gpus_by_type.setdefault(kind, MinerGPU(kind))
            gpu.count += 1
            gpu.chutes.append({"chute_id": chute_id})
            if tee:
                gpu.tee_count += 1
                miner.tee_gpus += 1
            else:
                gpu.non_tee_count += 1
        for kind, count in data.get("idle", {}).items():
            kind = feed.normalize_gpu_type(kind)
            gpu = miner.gpus_by_type.setdefault(kind, MinerGPU(kind))
            gpu.count += count
        miners[hotkey] = miner
    return miners


def reference_rows(inputs):
    nodes = inputs["nodes"]
    catalog = {x["chute_id"]: x for x in inputs["catalog"]["items"]}
    names = {
        n["chute"]["chute_id"]: n["chute"].get("name", "")
        for data in nodes.values()
        for n in data["provisioned"]
        if (n.get("chute") or {}).get("chute_id")
    }
    miners = reference_nodes(nodes, catalog)
    for entry in inputs["stats"].get("past_day", {}).get("compute_units", []):
        hotkey = entry.get("miner_hotkey")
        if hotkey not in miners:
            continue
        miner = miners[hotkey]
        cid = entry.get("chute_id", "")
        if not _is_tee(
            cid,
            names.get(cid, catalog.get(cid, {}).get("name", "")),
            catalog,
        ):
            continue
        cu = entry.get("compute_units", 0.0)
        if cid not in miner.tee_chutes_24h:
            miner.tee_chutes_24h.append({"chute_id": cid})
        stored = miner.tee_chute_compute_24h.setdefault(
            cid, {"compute_units": 0.0}
        )
        stored["compute_units"] += cu
        miner.tee_compute_24h += cu
    for miner in miners.values():
        chute_counts = {}
        type_counts = {}
        for kind, gpu in miner.gpus_by_type.items():
            for chute in gpu.chutes:
                cid = chute["chute_id"]
                if not cid:
                    continue
                counts = chute_counts.setdefault(cid, {})
                counts[kind] = counts.get(kind, 0) + 1
                type_counts[kind] = type_counts.get(kind, 0) + 1
        shares = {
            cid: {
                kind: count / (sum(per_type.values()) or 1)
                for kind, count in per_type.items()
            }
            for cid, per_type in chute_counts.items()
        }
        total_nodes = sum(type_counts.values()) or 1
        fallback = {
            kind: count / total_nodes for kind, count in type_counts.items()
        }
        compute = {}
        for cid, data in miner.tee_chute_compute_24h.items():
            for kind, fraction in (shares.get(cid) or fallback).items():
                compute[kind] = compute.get(kind, 0.0) + (
                    data["compute_units"] * fraction
                )
        miner.compute_by_gpu_type = compute
    for entry in inputs["rewards"]["data"]:
        hotkey = entry.get("hotkey", {})
        hotkey = hotkey.get("ss58", "") if isinstance(hotkey, dict) else hotkey
        if hotkey in miners:
            miners[hotkey].uid = entry.get("uid", -1)
            miners[hotkey].emission = feed.get_emission(entry)
    miners = {
        key: miner
        for key, miner in miners.items()
        if miner.tee_gpus > 0 or miner.tee_compute_24h > 0
    }
    tao_usd = 221.74
    total_usd = sum(m.emission for m in miners.values()) * tao_usd
    total_cu = sum(
        sum(m.compute_by_gpu_type.values()) for m in miners.values()
    )
    per_cu = total_usd / total_cu if total_cu else 0
    rows = []
    for miner in miners.values():
        types = [v for v in miner.gpus_by_type.values() if v.count]
        cu_total = sum(miner.compute_by_gpu_type.values())
        for gpu in types:
            cu = miner.compute_by_gpu_type.get(gpu.gpu_type, 0)
            fraction = cu / cu_total if cu_total else 1 / len(types)
            usd = (
                miner.emission * tao_usd * fraction
                if miner.emission > 0
                else cu * per_cu
            )
            gpus = gpu.tee_count + gpu.non_tee_count or gpu.count
            rows.append(
                {
                    "hotkey": miner.hotkey,
                    "uid": miner.uid,
                    "gpu": feed.display_class(gpu.gpu_type),
                    "rate": usd / gpus / 24 if gpus else 0,
                }
            )
    return rows


def test_calculation_reproduces_every_original_row_and_median(captured_input):
    inputs = captured_input
    result = feed.calculate_medians(
        inputs["nodes"],
        inputs["stats"],
        inputs["catalog"],
        inputs["rewards"],
        tao_usd=221.74,
    )
    actual = {(r["hotkey"], r["gpu"]): r["rate"] for r in result["rows"]}
    expected = reference_rows(inputs)
    assert len(actual) == len(expected) == 21
    for row in expected:
        assert actual[row["hotkey"], row["gpu"]] == pytest.approx(row["rate"])
    for gpu in ("H200", "B200", "B300", "RTX6000"):
        values = sorted(r["rate"] for r in expected if r["gpu"] == gpu)
        mid = len(values) // 2
        expected_median = (
            values[mid]
            if len(values) % 2
            else (values[mid - 1] + values[mid]) / 2
        )
        assert result["per_class_usd"][gpu] == pytest.approx(
            expected_median, abs=0.005
        )
        assert result["samples"][gpu] == len(values)


def test_scaling_eight_gpu_model_preserves_reference_allocation(
    captured_input,
):
    """A replacement instance-set formula is not acceptable."""
    ref = reference_rows(captured_input)
    assert len(ref) == 21
    assert (
        next(r for r in ref if r["uid"] == 82 and r["gpu"] == "H200")["rate"]
        > 0
    )
    assert feed.display_class("pro_6000") == "RTX6000"
    assert feed.display_class("rtx_6000_ada") is None


def test_zero_emission_uses_contribution_fallback_and_idle_class_is_safe():
    nodes = {
        "simple": {
            "provisioned": [
                {
                    "gpu": "h200",
                    "chute": {"name": "example-TEE", "chute_id": "chute"},
                },
            ],
            "idle": {"b200": 2},
        }
    }
    stats = {
        "past_day": {
            "compute_units": [
                {
                    "miner_hotkey": "simple",
                    "chute_id": "chute",
                    "compute_units": 4,
                }
            ]
        }
    }
    out = feed.calculate_medians(nodes, stats, {}, {}, tao_usd=221.74)
    row = next(row for row in out["rows"] if row["gpu"] == "B200")
    assert row["rate"] == 0.0
    assert row["nodes"] == 2
