"""Pure infrastructure-readiness evaluation for enrolled miner clusters.

This module has no chain, Rancher, metrics, logging, or clock dependencies.
Callers provide one complete metagraph/Rancher snapshot and receive a bounded,
immutable verdict suitable for binary miner scoring.
"""

from __future__ import annotations

import dataclasses
import enum
import re
from decimal import Decimal

HOTKEY_LABEL = "kubetee.ai/hotkey"
COLDKEY_LABEL = "kubetee.ai/coldkey"
BINDING_ID_LABEL = "kubetee.ai/binding-id"
PROVIDER_ID_LABEL = "kubetee.ai/provider-id"
BINDING_STATUS_LABEL = "kubetee.ai/binding-status"
GENERATION_LABEL = "kubetee.ai/generation"
NETUID_LABEL = "kubetee.ai/netuid"
NETWORK_LABEL = "kubetee.ai/network"
ORIGIN_FP_PREFIX_LABEL = "kubetee.ai/origin-fp-prefix"
ENROLLMENT_UID_ANNOTATION = "kubetee.ai/enrollment-uid"

_KUBETEE_NAMESPACE = "kubetee.ai/"
_MINER_ALIAS_PREFIX = "miner-"


def canonicalize_kubetee_keys(mapping: object) -> dict:
    """Return a copy of a Rancher labels/annotations map that also exposes
    every ``kubetee.ai/miner-<suffix>`` key under the canonical
    ``kubetee.ai/<suffix>``.

    Provisioners may label a cluster with either the canonical binding keys
    or a ``miner-``-prefixed alias (e.g. ``kubetee.ai/miner-hotkey``); both
    forms resolve to the same binding field. A canonical key already present
    always wins over an alias. Non-``kubetee.ai/`` keys pass through
    untouched, and a non-dict input yields an empty dict (fail-closed).
    """
    if not isinstance(mapping, dict):
        return {}
    canonical = dict(mapping)
    for key, value in mapping.items():
        if not isinstance(key, str) or not key.startswith(_KUBETEE_NAMESPACE):
            continue
        suffix = key[len(_KUBETEE_NAMESPACE) :]
        if suffix.startswith(_MINER_ALIAS_PREFIX):
            aliased = _KUBETEE_NAMESPACE + suffix[len(_MINER_ALIAS_PREFIX) :]
            canonical.setdefault(aliased, value)
    return canonical


_CPU_QUANTITY = re.compile(r"^((?:0|[1-9][0-9]*)(?:\.[0-9]+)?)(m)?$")
_MEMORY_QUANTITY = re.compile(
    r"^((?:0|[1-9][0-9]*)(?:\.[0-9]+)?)(Ki|Mi|Gi|Ti|K|M|G|T)?$"
)
_MEMORY_FACTORS = {
    None: 1,
    "Ki": 2**10,
    "Mi": 2**20,
    "Gi": 2**30,
    "Ti": 2**40,
    "K": 10**3,
    "M": 10**6,
    "G": 10**9,
    "T": 10**12,
}
_ORIGIN_FP_PREFIX = re.compile(r"^[0-9a-f]{63}$")
_CANONICAL_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_SUPPORTED_GPU = re.compile(r"(?<![A-Z0-9])(H100|H200|B200|B300)(?![A-Z0-9])")
_BASE_TEN_INTEGER = re.compile(r"^(?:0|[1-9][0-9]*)$")
_MAX_INT64 = 2**63 - 1
_MAX_QUANTITY_TEXT = 64
_RANCHER_CLUSTER_ID_PART = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_RANCHER_NODE_ID_PART = r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?"
_RANCHER_NODE_ID = re.compile(
    rf"^{_RANCHER_CLUSTER_ID_PART}:{_RANCHER_NODE_ID_PART}$"
)
_REQUIRED_BINDING_LABELS = (
    BINDING_ID_LABEL,
    HOTKEY_LABEL,
    COLDKEY_LABEL,
    PROVIDER_ID_LABEL,
    BINDING_STATUS_LABEL,
    GENERATION_LABEL,
    NETUID_LABEL,
    NETWORK_LABEL,
    ORIGIN_FP_PREFIX_LABEL,
)
_PRESSURE_CONDITIONS = (
    "MemoryPressure",
    "DiskPressure",
    "PIDPressure",
    "NetworkUnavailable",
)
_CONDITION_ABSENT = object()


class ValidationProfile(enum.Enum):
    """Explicit trust-domain policy profile."""

    PRODUCTION = "production"
    DEBUG = "debug"


class ValidationStatus(enum.Enum):
    """Status produced from one complete evidence snapshot."""

    ELIGIBLE = "eligible"
    SUSPENDED = "suspended"


class ValidationReason(enum.Enum):
    """Stable, bounded reasons for infrastructure validation outcomes."""

    ELIGIBLE = "eligible"
    CLUSTER_MISSING = "cluster_missing"
    CLUSTER_AMBIGUOUS = "cluster_ambiguous"
    BINDING_METADATA_INVALID = "binding_metadata_invalid"
    BINDING_NOT_ENROLLED = "binding_not_enrolled"
    BINDING_IDENTITY_MISMATCH = "binding_identity_mismatch"
    BINDING_DUPLICATE = "binding_duplicate"
    CLUSTER_NOT_READY = "cluster_not_ready"
    NODE_INVENTORY_EMPTY = "node_inventory_empty"
    NODE_NOT_READY = "node_not_ready"
    TOPOLOGY_INSUFFICIENT = "topology_insufficient"
    NODE_CAPACITY_INSUFFICIENT = "node_capacity_insufficient"
    GPU_INVENTORY_INVALID = "gpu_inventory_invalid"
    GPU_MODEL_UNSUPPORTED = "gpu_model_unsupported"
    RUNTIME_HANDLER_MISSING = "runtime_handler_missing"


@dataclasses.dataclass(frozen=True)
class InfrastructurePolicy:
    """Validated constants for one explicit infrastructure profile."""

    profile: ValidationProfile
    require_ready_conditions: bool
    min_etcd: int
    min_control_plane: int
    min_workers: int
    min_gpu_workers: int
    min_cpu_cores: Decimal
    min_memory_bytes: int
    gpus_per_node: int
    required_runtime_handler: str | None

    @classmethod
    def for_profile(cls, profile: ValidationProfile) -> InfrastructurePolicy:
        if not isinstance(profile, ValidationProfile):
            raise TypeError("profile must be a ValidationProfile")
        if profile is ValidationProfile.PRODUCTION:
            return cls(
                profile=profile,
                require_ready_conditions=True,
                min_etcd=3,
                min_control_plane=3,
                min_workers=1,
                min_gpu_workers=1,
                min_cpu_cores=Decimal("8"),
                min_memory_bytes=16 * 2**30,
                gpus_per_node=8,
                required_runtime_handler="kata-qemu-nvidia-gpu-tdx",
            )
        return cls(
            profile=profile,
            require_ready_conditions=False,
            min_etcd=0,
            min_control_plane=0,
            min_workers=0,
            min_gpu_workers=0,
            min_cpu_cores=Decimal("0"),
            min_memory_bytes=0,
            gpus_per_node=0,
            required_runtime_handler=None,
        )


@dataclasses.dataclass(frozen=True)
class ValidationVerdict:
    """One miner's immutable result from a complete evidence snapshot."""

    status: ValidationStatus
    reason: ValidationReason
    cluster_id: str | None = None

    @property
    def score(self) -> int:
        """Map the verdict onto the subnet's existing binary score."""
        return int(self.status is ValidationStatus.ELIGIBLE)


def parse_cpu_cores(value: object) -> Decimal | None:
    """Parse Kubernetes CPU cores/millicores, returning ``None`` on doubt."""
    if isinstance(value, bool):
        return None
    try:
        text = str(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if len(text) > _MAX_QUANTITY_TEXT:
        return None
    match = _CPU_QUANTITY.fullmatch(text)
    if match is None:
        return None
    cores = Decimal(match.group(1))
    cores = cores / 1000 if match.group(2) == "m" else cores
    return cores if cores <= _MAX_INT64 else None


def parse_memory_bytes(value: object) -> int | None:
    """Parse supported Kubernetes memory quantities into whole bytes."""
    if isinstance(value, bool):
        return None
    try:
        text = str(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if len(text) > _MAX_QUANTITY_TEXT:
        return None
    match = _MEMORY_QUANTITY.fullmatch(text)
    if match is None:
        return None
    scaled = Decimal(match.group(1)) * _MEMORY_FACTORS[match.group(2)]
    if scaled > _MAX_INT64 or scaled != scaled.to_integral_value():
        return None
    return int(scaled)


@dataclasses.dataclass(frozen=True)
class _BindingMetadata:
    cluster_id: str
    binding_id: str
    hotkey: str
    coldkey: str
    status: str
    generation: int
    netuid: int
    network: str
    enrollment_uid: int


def _parse_base_ten_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, str):
        return None
    if not _BASE_TEN_INTEGER.fullmatch(value):
        return None
    if len(value) > 19:
        return None
    parsed = int(value)
    return parsed if parsed <= _MAX_INT64 else None


def _binding_metadata(cluster: dict) -> _BindingMetadata | None:
    cluster_id = cluster.get("id")
    labels = cluster.get("labels")
    annotations = cluster.get("annotations")
    if not isinstance(cluster_id, str) or not cluster_id:
        return None
    if not isinstance(labels, dict) or not isinstance(annotations, dict):
        return None
    labels = canonicalize_kubetee_keys(labels)
    annotations = canonicalize_kubetee_keys(annotations)

    values: dict[str, str] = {}
    for key in _REQUIRED_BINDING_LABELS:
        value = labels.get(key)
        if not isinstance(value, str) or not value or len(value) > 63:
            return None
        values[key] = value

    enrollment_uid = _parse_base_ten_integer(
        annotations.get(ENROLLMENT_UID_ANNOTATION)
    )
    generation = _parse_base_ten_integer(values[GENERATION_LABEL])
    netuid = _parse_base_ten_integer(values[NETUID_LABEL])
    if enrollment_uid is None or generation is None or netuid is None:
        return None
    if generation < 1:
        return None
    if not _CANONICAL_UUID.fullmatch(values[PROVIDER_ID_LABEL]):
        return None
    if not _ORIGIN_FP_PREFIX.fullmatch(values[ORIGIN_FP_PREFIX_LABEL]):
        return None

    return _BindingMetadata(
        cluster_id=cluster_id,
        binding_id=values[BINDING_ID_LABEL],
        hotkey=values[HOTKEY_LABEL],
        coldkey=values[COLDKEY_LABEL],
        status=values[BINDING_STATUS_LABEL],
        generation=generation,
        netuid=netuid,
        network=values[NETWORK_LABEL],
        enrollment_uid=enrollment_uid,
    )


def has_canonical_binding_metadata(cluster: object) -> bool:
    """Whether a Rancher object carries the complete canonical binding shape."""
    return isinstance(cluster, dict) and _binding_metadata(cluster) is not None


def _condition_status(conditions: object, name: str):
    if not isinstance(conditions, list):
        return None
    matches = [
        condition
        for condition in conditions
        if isinstance(condition, dict)
        and (condition.get("type") or condition.get("name")) == name
    ]
    if not matches:
        return _CONDITION_ABSENT
    if len(matches) != 1:
        return None
    status = matches[0].get("status")
    if status is True or status == "True":
        return True
    if status is False or status == "False":
        return False
    return None


def _active(obj: object) -> bool:
    return (
        isinstance(obj, dict)
        and obj.get("state") == "active"
        and obj.get("transitioning") == "no"
    )


def _suspended(
    reason: ValidationReason, cluster: dict | None = None
) -> ValidationVerdict:
    cluster_id = cluster.get("id") if isinstance(cluster, dict) else None
    if not isinstance(cluster_id, str):
        cluster_id = None
    return ValidationVerdict(
        ValidationStatus.SUSPENDED,
        reason,
        cluster_id,
    )


def _binding_id_count(binding_id: str, clusters: list[dict]) -> int:
    return sum(
        1
        for cluster in clusters
        if isinstance(cluster, dict)
        and isinstance(cluster.get("labels"), dict)
        and canonicalize_kubetee_keys(cluster["labels"]).get(BINDING_ID_LABEL)
        == binding_id
    )


def _node_ready(
    node: object, cluster_id: str, policy: InfrastructurePolicy
) -> bool:
    if not _active(node):
        return False
    node_id = node.get("id")
    if (
        not isinstance(node_id, str)
        or not _RANCHER_NODE_ID.fullmatch(node_id)
        or node_id.partition(":")[0] != cluster_id
    ):
        return False
    if node.get("clusterId") != cluster_id:
        return False
    if not policy.require_ready_conditions:
        return True
    if _condition_status(node.get("conditions"), "Ready") is not True:
        return False
    for name in _PRESSURE_CONDITIONS:
        status = _condition_status(node.get("conditions"), name)
        if status is None or status is True:
            return False
    return True


def _topology_ready(nodes: list[dict], policy: InfrastructurePolicy) -> bool:
    etcd = sum(node.get("etcd") is True for node in nodes)
    control_plane = sum(node.get("controlPlane") is True for node in nodes)
    workers = sum(
        node.get("worker") is True and node.get("unschedulable") is False
        for node in nodes
    )
    return (
        etcd >= policy.min_etcd
        and control_plane >= policy.min_control_plane
        and workers >= policy.min_workers
    )


def _capacity_ready(nodes: list[dict], policy: InfrastructurePolicy) -> bool:
    for node in nodes:
        capacity = node.get("capacity")
        if not isinstance(capacity, dict):
            return False
        cpu = parse_cpu_cores(capacity.get("cpu"))
        memory = parse_memory_bytes(capacity.get("memory"))
        if cpu is None or cpu < policy.min_cpu_cores:
            return False
        if memory is None or memory < policy.min_memory_bytes:
            return False
    return True


def _parse_resource_count(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= _MAX_INT64 else None
    if not isinstance(value, str) or not _BASE_TEN_INTEGER.fullmatch(value):
        return None
    if len(value) > 19:
        return None
    parsed = int(value)
    return parsed if parsed <= _MAX_INT64 else None


def _gpu_nodes(
    nodes: list[dict], policy: InfrastructurePolicy
) -> tuple[list[dict] | None, ValidationReason | None]:
    gpu_nodes: list[dict] = []
    for node in nodes:
        capacity = node.get("capacity")
        allocatable = node.get("allocatable")
        if not isinstance(capacity, dict):
            return None, ValidationReason.GPU_INVENTORY_INVALID
        if not isinstance(allocatable, dict):
            return None, ValidationReason.GPU_INVENTORY_INVALID

        capacity_raw = capacity.get("nvidia.com/gpu")
        allocatable_raw = allocatable.get("nvidia.com/gpu")
        if capacity_raw is None and allocatable_raw is None:
            continue
        capacity_count = _parse_resource_count(capacity_raw)
        allocatable_count = _parse_resource_count(allocatable_raw)
        if capacity_count is None or allocatable_count is None:
            return None, ValidationReason.GPU_INVENTORY_INVALID
        if capacity_count == 0 and allocatable_count == 0:
            continue
        if (
            capacity_count != policy.gpus_per_node
            or allocatable_count != policy.gpus_per_node
            or node.get("worker") is not True
            or node.get("unschedulable") is not False
        ):
            return None, ValidationReason.GPU_INVENTORY_INVALID
        labels = node.get("labels")
        if (
            not isinstance(labels, dict)
            or labels.get("nvidia.com/gpu.workload.config") != "vm-passthrough"
        ):
            return None, ValidationReason.GPU_INVENTORY_INVALID
        gpu_nodes.append(node)

    if len(gpu_nodes) < policy.min_gpu_workers:
        return None, ValidationReason.GPU_INVENTORY_INVALID
    return gpu_nodes, None


def _gpu_models_supported(nodes: list[dict]) -> bool:
    models: set[str] = set()
    for node in nodes:
        labels = node.get("labels")
        product = (
            labels.get("nvidia.com/gpu.product")
            if isinstance(labels, dict)
            else None
        )
        matches = (
            _SUPPORTED_GPU.findall(product.upper())
            if isinstance(product, str)
            else []
        )
        if len(matches) != 1:
            return False
        models.add(matches[0])
    return len(models) == 1


def _runtime_handler_ready(nodes: list[dict], required: str) -> bool:
    for node in nodes:
        handlers = node.get("runtimeHandlers")
        if not isinstance(handlers, list):
            return False
        names = {
            handler.get("name")
            for handler in handlers
            if isinstance(handler, dict)
            and isinstance(handler.get("name"), str)
        }
        if required not in names:
            return False
    return True


def validate_miner(
    neuron: dict,
    clusters: list[dict],
    nodes_by_cluster: dict[str, list[dict]],
    expected_netuid: int,
    expected_network: str,
    policy: InfrastructurePolicy,
) -> ValidationVerdict:
    """Evaluate one miner against a complete Rancher/metagraph snapshot."""
    if not isinstance(policy, InfrastructurePolicy):
        raise TypeError("policy must be an InfrastructurePolicy")

    hotkey = neuron.get("hotkey") if isinstance(neuron, dict) else None
    matches = [
        cluster
        for cluster in clusters
        if isinstance(cluster, dict)
        and isinstance(cluster.get("labels"), dict)
        and canonicalize_kubetee_keys(cluster["labels"]).get(HOTKEY_LABEL)
        == hotkey
    ]
    if not matches:
        return _suspended(ValidationReason.CLUSTER_MISSING)
    if len(matches) != 1:
        return _suspended(ValidationReason.CLUSTER_AMBIGUOUS)

    cluster = matches[0]
    if cluster.get("id") == "local" or cluster.get("internal") not in (
        None,
        False,
    ):
        return _suspended(ValidationReason.BINDING_METADATA_INVALID, cluster)
    metadata = _binding_metadata(cluster)
    if metadata is None:
        return _suspended(ValidationReason.BINDING_METADATA_INVALID, cluster)
    if metadata.status != "ENROLLED":
        return _suspended(ValidationReason.BINDING_NOT_ENROLLED, cluster)
    if (
        metadata.hotkey != neuron.get("hotkey")
        or metadata.coldkey != neuron.get("coldkey")
        or metadata.enrollment_uid != neuron.get("uid")
        or metadata.netuid != expected_netuid
        or metadata.network != expected_network
    ):
        return _suspended(ValidationReason.BINDING_IDENTITY_MISMATCH, cluster)
    if _binding_id_count(metadata.binding_id, clusters) != 1:
        return _suspended(ValidationReason.BINDING_DUPLICATE, cluster)

    if not _active(cluster):
        return _suspended(ValidationReason.CLUSTER_NOT_READY, cluster)
    if (
        policy.require_ready_conditions
        and _condition_status(cluster.get("conditions"), "Ready") is not True
    ):
        return _suspended(ValidationReason.CLUSTER_NOT_READY, cluster)

    nodes = nodes_by_cluster.get(metadata.cluster_id)
    if not isinstance(nodes, list) or not nodes:
        return _suspended(ValidationReason.NODE_INVENTORY_EMPTY, cluster)
    if not all(
        _node_ready(node, metadata.cluster_id, policy) for node in nodes
    ):
        return _suspended(ValidationReason.NODE_NOT_READY, cluster)
    node_ids = [node["id"] for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        return _suspended(ValidationReason.NODE_NOT_READY, cluster)
    if policy.profile is ValidationProfile.DEBUG:
        return ValidationVerdict(
            ValidationStatus.ELIGIBLE,
            ValidationReason.ELIGIBLE,
            metadata.cluster_id,
        )

    if not _topology_ready(nodes, policy):
        return _suspended(ValidationReason.TOPOLOGY_INSUFFICIENT, cluster)
    if not _capacity_ready(nodes, policy):
        return _suspended(
            ValidationReason.NODE_CAPACITY_INSUFFICIENT,
            cluster,
        )
    gpu_nodes, gpu_error = _gpu_nodes(nodes, policy)
    if gpu_error is not None:
        return _suspended(gpu_error, cluster)
    if not _gpu_models_supported(gpu_nodes):
        return _suspended(ValidationReason.GPU_MODEL_UNSUPPORTED, cluster)
    if (
        policy.required_runtime_handler is not None
        and not _runtime_handler_ready(
            gpu_nodes, policy.required_runtime_handler
        )
    ):
        return _suspended(ValidationReason.RUNTIME_HANDLER_MISSING, cluster)

    return ValidationVerdict(
        ValidationStatus.ELIGIBLE,
        ValidationReason.ELIGIBLE,
        metadata.cluster_id,
    )
