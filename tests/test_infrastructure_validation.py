"""Infrastructure-ready policy and verdict evaluation tests."""

from __future__ import annotations

import copy
import pathlib
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from infrastructure_validation import (
    InfrastructurePolicy,
    ValidationProfile,
    ValidationReason,
    ValidationStatus,
    ValidationVerdict,
    canonicalize_kubetee_keys,
    parse_cpu_cores,
    parse_memory_bytes,
    validate_miner,
)

HOTKEY = "5MinerHotkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE"
COLDKEY = "5MinerColdkeyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAK"
NETWORK = "finney"
NETUID = 90
UID = 42


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8", Decimal("8")),
        ("8000m", Decimal("8")),
        (8, Decimal("8")),
        ("7.5", Decimal("7.5")),
        ("0.5", Decimal("0.5")),
        ("-1", None),
        ("nan", None),
        ("8x", None),
        ("9" * 64, None),
        ("9" * 5000, None),
        (True, None),
    ],
)
def test_parse_cpu_cores(raw, expected):
    assert parse_cpu_cores(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("16Gi", 16 * 2**30),
        ("16384Mi", 16 * 2**30),
        ("16777216Ki", 16 * 2**30),
        ("16G", 16_000_000_000),
        (str(16 * 2**30), 16 * 2**30),
        ("1.5Gi", 3 * 2**29),
        ("-1Gi", None),
        ("NaN", None),
        ("16watts", None),
        ("9" * 62 + "Gi", None),
        ("9" * 5000 + "Gi", None),
        (False, None),
    ],
)
def test_parse_memory_bytes(raw, expected):
    assert parse_memory_bytes(raw) == expected


def test_profiles_are_exact_and_debug_is_not_a_fallback():
    production = InfrastructurePolicy.for_profile(ValidationProfile.PRODUCTION)
    debug = InfrastructurePolicy.for_profile(ValidationProfile.DEBUG)

    assert (
        production.min_etcd,
        production.min_control_plane,
        production.min_workers,
    ) == (3, 3, 1)
    assert production.min_gpu_workers == 1
    assert production.required_runtime_handler == ("kata-qemu-nvidia-gpu-tdx")
    assert debug.min_workers == 0
    assert debug.min_gpu_workers == 0
    assert debug.required_runtime_handler is None

    with pytest.raises(TypeError):
        InfrastructurePolicy.for_profile("debug")


def test_verdict_score_is_binary_and_status_driven():
    eligible = ValidationVerdict(
        ValidationStatus.ELIGIBLE,
        ValidationReason.ELIGIBLE,
        "c-miner",
    )
    suspended = ValidationVerdict(
        ValidationStatus.SUSPENDED,
        ValidationReason.CLUSTER_MISSING,
    )

    assert eligible.score == 1
    assert suspended.score == 0


def _ready_conditions() -> list[dict]:
    return [
        {"type": "Ready", "status": "True"},
        {"type": "MemoryPressure", "status": "False"},
        {"type": "DiskPressure", "status": "False"},
        {"type": "PIDPressure", "status": "False"},
        {"type": "NetworkUnavailable", "status": "False"},
    ]


def _valid_cluster() -> dict:
    return {
        "id": "c-miner",
        "uuid": "00000000-0000-4000-8000-000000000042",
        "state": "active",
        "transitioning": "no",
        "conditions": [{"type": "Ready", "status": "True"}],
        "labels": {
            "kubetee.ai/binding-id": "binding-miner-42",
            "kubetee.ai/hotkey": HOTKEY,
            "kubetee.ai/coldkey": COLDKEY,
            "kubetee.ai/provider-id": "00000000-0000-4000-8000-000000000042",
            "kubetee.ai/binding-status": "ENROLLED",
            "kubetee.ai/generation": "1",
            "kubetee.ai/netuid": str(NETUID),
            "kubetee.ai/network": NETWORK,
            "kubetee.ai/origin-fp-prefix": "a" * 63,
        },
        "annotations": {"kubetee.ai/enrollment-uid": str(UID)},
    }


def _valid_node(index: int, product: str = "NVIDIA-H100-80GB-HBM3") -> dict:
    return {
        "id": f"c-miner:node-{index}",
        "clusterId": "c-miner",
        "state": "active",
        "transitioning": "no",
        "conditions": _ready_conditions(),
        "etcd": True,
        "controlPlane": True,
        "worker": True,
        "unschedulable": False,
        "capacity": {
            "cpu": "8",
            "memory": "16Gi",
            "nvidia.com/gpu": "8",
        },
        "allocatable": {"nvidia.com/gpu": "8"},
        "labels": {
            "nvidia.com/gpu.product": product,
            "nvidia.com/gpu.workload.config": "vm-passthrough",
        },
        "runtimeHandlers": [{"name": "kata-qemu-nvidia-gpu-tdx"}],
    }


def valid_production_inventory() -> (
    tuple[dict, list[dict], dict[str, list[dict]]]
):
    neuron = {"uid": UID, "hotkey": HOTKEY, "coldkey": COLDKEY}
    clusters = [_valid_cluster()]
    nodes = {"c-miner": [_valid_node(index) for index in range(1, 4)]}
    return neuron, clusters, nodes


def _apply_mutation(
    mutation: str,
    clusters: list[dict],
    nodes_by_cluster: dict[str, list[dict]],
) -> None:
    cluster = clusters[0]
    nodes = nodes_by_cluster["c-miner"]
    if mutation == "remove_cluster":
        clusters.clear()
    elif mutation == "duplicate_hotkey_cluster":
        duplicate = copy.deepcopy(cluster)
        duplicate["id"] = "c-duplicate"
        duplicate["labels"]["kubetee.ai/binding-id"] = "binding-duplicate"
        clusters.append(duplicate)
    elif mutation == "management_cluster":
        cluster["id"] = "local"
    elif mutation == "internal_cluster":
        cluster["internal"] = True
    elif mutation == "cluster_inactive":
        cluster["state"] = "unavailable"
    elif mutation == "cluster_ready_missing":
        cluster["conditions"] = []
    elif mutation == "remove_nodes":
        nodes.clear()
    elif mutation == "node_inactive":
        nodes[0]["state"] = "unavailable"
    elif mutation == "node_wrong_cluster":
        nodes[0]["clusterId"] = "c-other"
    elif mutation == "duplicate_node_id":
        nodes.append(copy.deepcopy(nodes[0]))
    elif mutation == "malformed_node_id":
        nodes[0]["id"] = "c-miner:../node"
    elif mutation == "node_pressure":
        nodes[0]["conditions"][1]["status"] = "True"
    elif mutation == "two_etcd_nodes":
        nodes[0]["etcd"] = False
    elif mutation == "all_workers_cordoned":
        for node in nodes:
            node["unschedulable"] = True
    elif mutation == "seven_cpu_cores":
        nodes[0]["capacity"]["cpu"] = "7"
    elif mutation == "fifteen_gib":
        nodes[0]["capacity"]["memory"] = "15Gi"
    elif mutation == "seven_gpus":
        nodes[0]["capacity"]["nvidia.com/gpu"] = "7"
        nodes[0]["allocatable"]["nvidia.com/gpu"] = "7"
    elif mutation == "gpu_on_non_worker":
        nodes[0]["worker"] = False
    elif mutation == "passthrough_missing":
        del nodes[0]["labels"]["nvidia.com/gpu.workload.config"]
    elif mutation == "a100_product":
        nodes[0]["labels"]["nvidia.com/gpu.product"] = "NVIDIA-A100-SXM4"
    elif mutation == "runtime_handler_missing":
        nodes[0]["runtimeHandlers"] = [{"name": "runc"}]
    else:
        raise AssertionError(f"unhandled mutation: {mutation}")


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("remove_cluster", ValidationReason.CLUSTER_MISSING),
        ("duplicate_hotkey_cluster", ValidationReason.CLUSTER_AMBIGUOUS),
        ("management_cluster", ValidationReason.BINDING_METADATA_INVALID),
        ("internal_cluster", ValidationReason.BINDING_METADATA_INVALID),
        ("cluster_inactive", ValidationReason.CLUSTER_NOT_READY),
        ("cluster_ready_missing", ValidationReason.CLUSTER_NOT_READY),
        ("remove_nodes", ValidationReason.NODE_INVENTORY_EMPTY),
        ("node_inactive", ValidationReason.NODE_NOT_READY),
        ("node_wrong_cluster", ValidationReason.NODE_NOT_READY),
        ("duplicate_node_id", ValidationReason.NODE_NOT_READY),
        ("malformed_node_id", ValidationReason.NODE_NOT_READY),
        ("node_pressure", ValidationReason.NODE_NOT_READY),
        ("two_etcd_nodes", ValidationReason.TOPOLOGY_INSUFFICIENT),
        ("all_workers_cordoned", ValidationReason.TOPOLOGY_INSUFFICIENT),
        ("seven_cpu_cores", ValidationReason.NODE_CAPACITY_INSUFFICIENT),
        ("fifteen_gib", ValidationReason.NODE_CAPACITY_INSUFFICIENT),
        ("seven_gpus", ValidationReason.GPU_INVENTORY_INVALID),
        ("gpu_on_non_worker", ValidationReason.GPU_INVENTORY_INVALID),
        ("passthrough_missing", ValidationReason.GPU_INVENTORY_INVALID),
        ("a100_product", ValidationReason.GPU_MODEL_UNSUPPORTED),
        ("runtime_handler_missing", ValidationReason.RUNTIME_HANDLER_MISSING),
    ],
)
def test_production_first_failure_is_deterministic(mutation, reason):
    neuron, clusters, nodes = valid_production_inventory()
    _apply_mutation(mutation, clusters, nodes)

    verdict = validate_miner(
        neuron,
        clusters,
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.PRODUCTION),
    )

    assert verdict.status is ValidationStatus.SUSPENDED
    assert verdict.reason is reason
    assert verdict.score == 0


def test_valid_production_inventory_is_eligible():
    neuron, clusters, nodes = valid_production_inventory()

    verdict = validate_miner(
        neuron,
        clusters,
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.PRODUCTION),
    )

    assert verdict == ValidationVerdict(
        ValidationStatus.ELIGIBLE,
        ValidationReason.ELIGIBLE,
        "c-miner",
    )


@pytest.mark.parametrize(
    "product",
    [
        "NVIDIA-H100-80GB-HBM3",
        "NVIDIA H200 141GB",
        "NVIDIA-B200-SXM",
        "B300-SXM6",
    ],
)
def test_supported_gpu_product_tokens_are_eligible(product):
    neuron, clusters, nodes = valid_production_inventory()
    for node in nodes["c-miner"]:
        node["labels"]["nvidia.com/gpu.product"] = product

    verdict = validate_miner(
        neuron,
        clusters,
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.PRODUCTION),
    )

    assert verdict.status is ValidationStatus.ELIGIBLE


def test_gpu_product_substrings_do_not_pass_token_matching():
    neuron, clusters, nodes = valid_production_inventory()
    for node in nodes["c-miner"]:
        node["labels"]["nvidia.com/gpu.product"] = "NOTH1000"

    verdict = validate_miner(
        neuron,
        clusters,
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.PRODUCTION),
    )

    assert verdict.reason is ValidationReason.GPU_MODEL_UNSUPPORTED


def test_gpu_product_with_multiple_model_markers_is_malformed():
    neuron, clusters, nodes = valid_production_inventory()
    nodes["c-miner"][0]["labels"]["nvidia.com/gpu.product"] = "H100-H200"

    verdict = validate_miner(
        neuron,
        clusters,
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.PRODUCTION),
    )

    assert verdict.reason is ValidationReason.GPU_MODEL_UNSUPPORTED


def test_mixed_supported_gpu_models_are_not_a_uniform_inventory():
    neuron, clusters, nodes = valid_production_inventory()
    nodes["c-miner"][1]["labels"][
        "nvidia.com/gpu.product"
    ] = "NVIDIA-H200-141GB"

    verdict = validate_miner(
        neuron,
        clusters,
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.PRODUCTION),
    )

    assert verdict.reason is ValidationReason.GPU_MODEL_UNSUPPORTED


def test_binding_is_hotkey_only():
    """The scoring binding is the hotkey alone: a cluster carrying ONLY
    kubetee.ai/hotkey (no coldkey, binding-id, provider-id, generation,
    netuid, network, origin-fp-prefix, ENROLLED sentinel, or enrollment-uid
    annotation) is ELIGIBLE in debug."""
    neuron = {"uid": UID, "hotkey": HOTKEY, "coldkey": COLDKEY}
    minimal = {
        "id": "c-miner",
        "state": "active",
        "transitioning": "no",
        "labels": {
            "kubetee.ai/hotkey": HOTKEY,
        },
    }
    nodes = {
        "c-miner": [
            {
                "id": "c-miner:n1",
                "clusterId": "c-miner",
                "state": "active",
                "transitioning": "no",
            }
        ]
    }
    verdict = validate_miner(
        neuron,
        [minimal],
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.DEBUG),
    )
    assert verdict.status is ValidationStatus.ELIGIBLE
    assert verdict.reason is ValidationReason.ELIGIBLE


def test_dropped_binding_fields_no_longer_suspend():
    """Mutating the retired binding fields (netuid/network/uid/binding-id/
    provider-id/generation/origin-fp-prefix/binding-status) must NOT change a
    debug ELIGIBLE verdict now that they are not part of the binding."""
    neuron = {"uid": UID, "hotkey": HOTKEY, "coldkey": COLDKEY}
    cluster = _valid_cluster()
    cluster["labels"]["kubetee.ai/netuid"] = "9999"
    cluster["labels"]["kubetee.ai/network"] = "some-other-network"
    cluster["labels"]["kubetee.ai/binding-status"] = "PENDING"
    cluster["labels"]["kubetee.ai/provider-id"] = "not-a-uuid"
    cluster["labels"]["kubetee.ai/origin-fp-prefix"] = "too-short"
    del cluster["labels"]["kubetee.ai/binding-id"]
    del cluster["annotations"]["kubetee.ai/enrollment-uid"]
    nodes = {
        "c-miner": [
            {
                "id": "c-miner:n1",
                "clusterId": "c-miner",
                "state": "active",
                "transitioning": "no",
            }
        ]
    }
    verdict = validate_miner(
        neuron,
        [cluster],
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.DEBUG),
    )
    assert verdict.status is ValidationStatus.ELIGIBLE


def test_oversized_gpu_count_is_invalid_instead_of_raising():
    neuron, clusters, nodes = valid_production_inventory()
    nodes["c-miner"][0]["capacity"]["nvidia.com/gpu"] = "9" * 5000

    verdict = validate_miner(
        neuron,
        clusters,
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.PRODUCTION),
    )

    assert verdict.reason is ValidationReason.GPU_INVENTORY_INVALID


def test_debug_accepts_one_active_node_without_production_fields():
    neuron = {"uid": UID, "hotkey": HOTKEY, "coldkey": COLDKEY}
    cluster = _valid_cluster()
    cluster.pop("conditions")
    nodes = {
        "c-miner": [
            {
                "id": "c-miner:debug",
                "clusterId": "c-miner",
                "state": "active",
                "transitioning": "no",
            }
        ]
    }

    verdict = validate_miner(
        neuron,
        [cluster],
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.DEBUG),
    )

    assert verdict.status is ValidationStatus.ELIGIBLE


# ---------------------------------------------------------------------------
# kubetee.ai/miner-<x> prefix tolerance: accept both the canonical
# kubetee.ai/<x> and the kubetee.ai/miner-<x> alias.
# ---------------------------------------------------------------------------


def test_canonicalize_exposes_miner_alias_as_canonical():
    out = canonicalize_kubetee_keys(
        {"kubetee.ai/miner-hotkey": "H", "kubetee.ai/miner-coldkey": "C"}
    )
    assert out["kubetee.ai/hotkey"] == "H"
    assert out["kubetee.ai/coldkey"] == "C"
    # original alias key is preserved too
    assert out["kubetee.ai/miner-hotkey"] == "H"


def test_canonicalize_canonical_key_wins_over_alias():
    out = canonicalize_kubetee_keys(
        {"kubetee.ai/hotkey": "REAL", "kubetee.ai/miner-hotkey": "ALIAS"}
    )
    assert out["kubetee.ai/hotkey"] == "REAL"


def test_canonicalize_passes_through_unrelated_and_non_kubetee_keys():
    out = canonicalize_kubetee_keys(
        {"environment": "staging", "kubetee.ai/city": "oakland"}
    )
    assert out == {"environment": "staging", "kubetee.ai/city": "oakland"}


def test_canonicalize_non_dict_is_empty_fail_closed():
    assert canonicalize_kubetee_keys(None) == {}
    assert canonicalize_kubetee_keys("nope") == {}


def _miner_prefixed(cluster: dict) -> dict:
    """Rewrite the identity labels of a valid cluster to the miner- alias."""
    labels = cluster["labels"]
    for canonical in ("kubetee.ai/hotkey", "kubetee.ai/coldkey"):
        suffix = canonical[len("kubetee.ai/") :]
        labels["kubetee.ai/miner-" + suffix] = labels.pop(canonical)
    return cluster


def test_validate_miner_accepts_miner_prefixed_identity_labels():
    """A cluster carrying kubetee.ai/miner-hotkey / miner-coldkey (rest
    canonical) still selects and validates as ELIGIBLE in debug."""
    neuron, clusters, nodes = valid_production_inventory()
    _miner_prefixed(clusters[0])
    verdict = validate_miner(
        neuron,
        clusters,
        nodes,
        InfrastructurePolicy.for_profile(ValidationProfile.DEBUG),
    )
    assert verdict.status is ValidationStatus.ELIGIBLE
    assert verdict.reason is ValidationReason.ELIGIBLE


# ---------------------------------------------------------------------------
# kubetee.ai/ban: operator soft safety switch -> score 0.
# ---------------------------------------------------------------------------


def _hotkey_only_cluster(ban: str | None = None) -> dict:
    labels = {"kubetee.ai/hotkey": HOTKEY}
    if ban is not None:
        labels["kubetee.ai/ban"] = ban
    return {
        "id": "c-miner",
        "state": "active",
        "transitioning": "no",
        "labels": labels,
    }


def _one_active_node() -> dict:
    return {
        "c-miner": [
            {
                "id": "c-miner:n1",
                "clusterId": "c-miner",
                "state": "active",
                "transitioning": "no",
            }
        ]
    }


def _debug_verdict(cluster: dict):
    return validate_miner(
        {"uid": UID, "hotkey": HOTKEY, "coldkey": COLDKEY},
        [cluster],
        _one_active_node(),
        InfrastructurePolicy.for_profile(ValidationProfile.DEBUG),
    )


def test_ban_true_scores_zero():
    verdict = _debug_verdict(_hotkey_only_cluster(ban="true"))
    assert verdict.status is ValidationStatus.SUSPENDED
    assert verdict.reason is ValidationReason.BANNED
    assert verdict.score == 0


def test_ban_false_is_eligible():
    verdict = _debug_verdict(_hotkey_only_cluster(ban="false"))
    assert verdict.status is ValidationStatus.ELIGIBLE


def test_ban_absent_is_eligible():
    verdict = _debug_verdict(_hotkey_only_cluster(ban=None))
    assert verdict.status is ValidationStatus.ELIGIBLE


def test_ban_non_true_value_is_eligible():
    verdict = _debug_verdict(_hotkey_only_cluster(ban="1"))
    assert verdict.status is ValidationStatus.ELIGIBLE


def test_miner_ban_alias_is_honored():
    cluster = _hotkey_only_cluster()
    cluster["labels"]["kubetee.ai/miner-ban"] = "true"
    verdict = _debug_verdict(cluster)
    assert verdict.reason is ValidationReason.BANNED
