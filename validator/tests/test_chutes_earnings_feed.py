"""Chutes display metrics vs reference input behavior; no network."""

from pathlib import Path
import importlib.util
import json
import sys

import pytest

import chutes_earnings_feed as feed


class _Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class _Client:
    def __init__(self, get=None):
        self.getter = get
        self.calls = []

    def get(self, url, headers, timeout):
        self.calls.append((url, headers, timeout))
        return _Response(
            self.getter(url, headers, timeout) if self.getter else {}
        )


@pytest.fixture(scope="session")
def captured_input():
    directory = Path(__file__).parent / "fixtures" / "chutes-reference"
    return {
        name: json.loads((directory / f"{name}.json").read_text())
        for name in ("nodes", "stats", "catalog", "rewards")
    }


def reference_rows(inputs):
    """The original script, not an independent copy of our rate formula."""
    path = Path(__file__).parents[2] / "docs" / "miner_revenue.py"
    spec = importlib.util.spec_from_file_location("miner_revenue_ref", path)
    reference = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reference
    spec.loader.exec_module(reference)
    nodes = inputs["nodes"]
    catalog = {x["chute_id"]: x for x in inputs["catalog"]["items"]}
    names = {
        n["chute"]["chute_id"]: n["chute"].get("name", "")
        for data in nodes.values()
        for n in data["provisioned"]
        if (n.get("chute") or {}).get("chute_id")
    }
    miners = reference.process_nodes_data(nodes, catalog)
    reference.process_per_chute_stats(miners, inputs["stats"], names, catalog)
    reference.attribute_compute_by_gpu_type(miners)
    reference.process_taostats_data(miners, inputs["rewards"]["data"])
    miners = reference.filter_tee_miners(miners, True)
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
