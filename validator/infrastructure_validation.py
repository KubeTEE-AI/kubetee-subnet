"""Pure, fail-closed infrastructure-readiness policy (no I/O).

A miner's verdict is binary: every required signal must pass, else score 0.
The doc contract (docs/NODE-REGISTRATION.md): eligible cluster carries a
`kubetee.ai/hotkey` label matching the miner's registered hotkey (one cluster
per hotkey), is not banned (`kubetee.ai/ban != "true"`), and is Ready with HA
topology, a schedulable worker, >=8 CPU + >=16 GiB per active node, and at
least one schedulable 8-GPU (H100/H200/B200/B300) worker with vm-passthrough
plus a confidential kata runtime handler. Any explicit missing/malformed/
ambiguous/unhealthy evidence is a failure. (A Rancher outage is handled
upstream as a cycle skip, not a per-miner failure.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rancher_client import hotkey_of, is_banned

_GPU_CLASSES = ("H100", "H200", "B200", "B300")
_MIN_CPU_CORES = 8
_MIN_MEM_GIB = 16

_ROLE_KEYWORDS = ("etcd", "control-plane", "worker")


@dataclass(frozen=True)
class Verdict:
    ready: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NodePosture:
    """The posture scoring reads off one Rancher node."""

    ready: bool
    schedulable: bool
    roles: frozenset[str]
    cpu_cores: float
    memory_gib: float
    gpu_class: str | None  # e.g. "H200"; None if not a labeled GPU node
    vm_passthrough: bool
    kata_confidential_runtime: bool


def _gi_to_gib(value: float, unit: str) -> float:
    factors = {
        "Ki": 1 / (1024 * 1024),
        "Mi": 1 / 1024,
        "Gi": 1.0,
        "Ti": 1024.0,
        # Decimal (non-binary) units — treat as binary for k8s quantity parity.
        "G": 1.0,
        "GB": 1.0,
        "M": 1 / 1024,
        "MB": 1 / 1024,
        "K": 1 / (1024 * 1024),
        "KB": 1 / (1024 * 1024),
        # Bare bytes — convert to GiB.
        "B": 1 / (1024**3),
    }
    return value * factors.get(unit, 1.0)


def _parse_memory_gib(raw) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw) / (1024**3)  # assume bytes
    text = str(raw).strip()
    # Check longer suffixes first so "GB" matches before "G", "Mi" before "M".
    for suffix in ("Ki", "Mi", "Gi", "Ti", "GB", "MB", "KB", "G", "M", "K", "B"):
        if text.endswith(suffix):
            try:
                return _gi_to_gib(float(text[: -len(suffix)]), suffix)
            except ValueError:
                return 0.0
    try:
        return float(text) / (1024**3)
    except ValueError:
        return 0.0


def _parse_cpu_cores(raw) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if text.endswith("m"):
        try:
            return float(text[:-1]) / 1000.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _gpu_class_from_labels(labels: dict) -> str | None:
    for klass in _GPU_CLASSES:
        for key, value in labels.items():
            text = f"{key}={value}".upper()
            if klass in text:
                return klass
    return None


def _conditions(node: dict) -> list[dict]:
    """Rancher node conditions: top-level `conditions`, else status.conditions."""
    conds = node.get("conditions") or (node.get("status") or {}).get("conditions") or []
    return [c for c in conds if isinstance(c, dict)]


def node_posture(node: dict) -> NodePosture:
    """Distill a Rancher node object into scoring posture."""
    labels = node.get("labels") or {}
    ready = any(
        c.get("type") == "Ready" and str(c.get("status")) == "True"
        for c in _conditions(node)
    )
    schedulable = not node.get("unschedulable", False)
    roles = frozenset(r for r in _ROLE_KEYWORDS if _has_role(labels, r))
    capacity = node.get("capacity") or (node.get("status") or {}).get("capacity") or {}
    cpu_cores = _parse_cpu_cores(capacity.get("cpu"))
    memory_gib = _parse_memory_gib(capacity.get("memory"))
    return NodePosture(
        ready=ready,
        schedulable=schedulable,
        roles=roles,
        cpu_cores=cpu_cores,
        memory_gib=memory_gib,
        gpu_class=_gpu_class_from_labels(labels),
        vm_passthrough=(
            str(labels.get("nvidia.com/gpu.workload.config", "")).lower()
            == "vm-passthrough"
        ),
        kata_confidential_runtime=_has_confidential_runtime(node),
    )


def _has_role(labels: dict, role: str) -> bool:
    for key, value in labels.items():
        if key == f"node-role.kubernetes.io/{role}" and str(value) in ("", "true"):
            return True
    return False


def _runtime_handlers(node: dict) -> list[str]:
    handlers = node.get("runtimeHandlers") or []
    return [
        str(h["name"]) for h in handlers if isinstance(h, dict) and h.get("name")
    ]


def _has_confidential_runtime(node: dict) -> bool:
    """A confidential Kata handler (TDX / nvidia-gpu-tdx) in node.runtimeHandlers."""
    for name in _runtime_handlers(node):
        low = name.lower()
        if "kata" in low and ("tdx" in low or "nvidia-gpu" in low):
            return True
    labels = node.get("labels") or {}
    for key, value in labels.items():
        text = f"{key}={value}".lower()
        if "kata" in text and ("tdx" in text or "nvidia-gpu" in text):
            return True
    return False


def validate_miner(
    hotkey: str,
    clusters: list[dict],
    nodes_by_cluster: dict[str, list[dict]],
    cluster_id_of,
) -> Verdict:
    """Recompute the binary readiness verdict for one miner hotkey."""
    reasons: list[str] = []

    bound = [c for c in clusters if hotkey_of(c) == hotkey]
    if not bound:
        return Verdict(
            False, (f"no cluster labeled for hotkey {hotkey[:8]}...",)
        )
    if len(bound) > 1:
        reasons.append(f"ambiguous: {len(bound)} clusters bound to one hotkey")
    cluster = bound[0]

    if is_banned(cluster):
        reasons.append("cluster is banned (kubetee.ai/ban=true)")

    cluster_id = cluster_id_of(cluster)
    nodes = nodes_by_cluster.get(cluster_id, [])
    postures = [node_posture(n) for n in nodes]

    active = [p for p in postures if p.ready]
    if not active:
        reasons.append("no Ready nodes")

    etcd = [p for p in active if "etcd" in p.roles]
    control_plane = [p for p in active if "control-plane" in p.roles]
    workers = [p for p in active if "worker" in p.roles]
    # Single-node (all-in-one) clusters are allowed for staging: a node may
    # hold several roles. Production HA requires 3 etcd + 3 control-plane.
    if len(etcd) < 1:
        reasons.append("no etcd node")
    if len(control_plane) < 1:
        reasons.append("no control-plane node")

    for posture in active:
        if posture.cpu_cores < _MIN_CPU_CORES:
            reasons.append(
                f"node cpu {posture.cpu_cores:g} < {_MIN_CPU_CORES}"
            )
        if posture.memory_gib < _MIN_MEM_GIB:
            reasons.append(
                f"node mem {posture.memory_gib:g}Gi < {_MIN_MEM_GIB}Gi"
            )

    sched_workers = [p for p in workers if p.schedulable]
    if not sched_workers:
        reasons.append("no schedulable worker")

    gpu_ok = any(
        p.schedulable
        and p.vm_passthrough
        and p.kata_confidential_runtime
        and p.gpu_class in _GPU_CLASSES
        for p in active
    )
    if not gpu_ok:
        reasons.append(
            "no schedulable 8-GPU (H100/H200/B200/B300) worker with "
            "vm-passthrough + confidential kata runtime"
        )

    return Verdict(ready=not reasons, reasons=tuple(reasons))
