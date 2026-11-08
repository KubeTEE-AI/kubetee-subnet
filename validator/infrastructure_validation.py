"""Pure, fail-closed infrastructure-readiness policy (no I/O).

A miner's verdict is binary: every required signal must pass, else score 0.
The documented eligibility contract is: eligible cluster carries a
`kubetee.ai/hotkey` label matching the miner's registered hotkey (one cluster
per hotkey), is not banned (`kubetee.ai/ban != "true"`), and has Ready active
nodes with etcd + control-plane + worker roles, >=72 CPU + >=1024 GiB per
active node, and at least one schedulable 8-GPU (H100/H200/B200/B300) worker
with vm-passthrough plus a confidential kata runtime handler. There is NO
minimum node-count gate (removed 2026-10-29 — the 3-node same-GPU-type
topology in the docs is guidance, not a readiness gate). Any explicit
missing/malformed/ambiguous/unhealthy evidence is a failure. (A Rancher
outage is handled upstream as a cycle skip, not a per-miner failure.)

Two freshness gates keep a dead cluster from scoring off frozen evidence
(added 2026-11-03 after na-us-dallas-132 kept earning 13.2% of the epoch
pool for ~40 min after its node was decommissioned):

1. A node counts as Ready only if its Ready condition is younger than
   `_READY_MAX_AGE_SECONDS` (15 min; healthy nodes heartbeat every <5 min).
   A disconnected cluster freezes its node CRs — including `Ready: True` —
   in Rancher forever, so the timestamp is the load-bearing signal.
2. A cluster whose own Ready condition is explicitly False (e.g. "Cluster
   agent is not connected") disqualifies its nodes outright.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from rancher_client import hotkey_of, is_banned

_GPU_CLASSES = ("H100", "H200", "B200", "B300", "RTX6000")
_MIN_CPU_CORES = 72
_MIN_MEM_GIB = 1024

_ROLE_KEYWORDS = ("etcd", "control-plane", "worker")

# A Ready condition carries a kubelet heartbeat. When a cluster's agent
# disconnects (or a node is decommissioned) Rancher stops refreshing the node
# CR but leaves the last snapshot — including `Ready: True` — in place
# forever. Healthy oakland nodes heartbeat every <5 min, so anything older
# than this is treated as dead evidence, not as a live node. Without this
# gate a stopped node keeps scoring: na-us-dallas-132 (tx-b200-16) was
# decommissioned 2026-11-03 11:10Z yet kept earning 13.2% of the epoch pool
# off a Ready condition frozen at 10:36:55Z.
_READY_MAX_AGE_SECONDS = 900.0  # 15 min


def _parse_timestamp(raw) -> datetime | None:
    """Parse a Rancher/k8s condition timestamp; None if absent/unparseable."""
    if not raw:
        return None
    text = str(raw).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        # Rancher sometimes serialises Go's "2026-11-03 10:36:55 +0000 UTC".
        try:
            parsed = datetime.strptime(
                " ".join(text.split()[:2]) + " " + text.split()[-1],
                "%Y-%m-%d %H:%M:%S %Z",
            )
        except (ValueError, IndexError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _condition_timestamp(condition: dict) -> datetime | None:
    """Newest timestamp a condition carries (heartbeat beats transition)."""
    for key in ("lastHeartbeatTime", "lastUpdateTime", "lastTransitionTime"):
        parsed = _parse_timestamp(condition.get(key))
        if parsed is not None:
            return parsed
    return None


def _ready_condition_age(
    node: dict, now: datetime
) -> tuple[bool, float | None]:
    """(has_ready_true, age_seconds) for the node's Ready condition.

    Rancher's v3 node payload carries DUPLICATE Ready conditions: a legacy
    copy with only a Go-format `lastTransitionTime` (the node's registration
    time, days old) and the Norman copy carrying a real `lastHeartbeatTime`.
    Read every Ready/True condition and keep the NEWEST timestamp, otherwise
    the legacy copy's registration time would make a healthy node look stale.
    """
    timestamps = [
        _condition_timestamp(c)
        for c in _conditions(node)
        if c.get("type") == "Ready" and str(c.get("status")) == "True"
    ]
    usable = [t for t in timestamps if t is not None]
    if not timestamps:
        return False, None  # not Ready at all
    if not usable:
        return True, None  # Ready=True but no usable timestamp → fail closed
    return True, (now - max(usable)).total_seconds()


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
    ready_age_seconds: float | None = None  # None when no usable timestamp
    stale: bool = False


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
    for suffix in (
        "Ki",
        "Mi",
        "Gi",
        "Ti",
        "GB",
        "MB",
        "KB",
        "G",
        "M",
        "K",
        "B",
    ):
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
    for key, value in labels.items():
        text = f"{key}={value}".upper()
        for klass in _GPU_CLASSES:
            if klass in text:
                return klass
        if "RTX6000" in text or "RTX-6000" in text or "RTXPRO6000" in text:
            return "RTX6000"
    return None


def _conditions(node: dict) -> list[dict]:
    """Rancher node conditions: top-level `conditions`, else status.conditions."""
    conds = (
        node.get("conditions")
        or (node.get("status") or {}).get("conditions")
        or []
    )
    return [c for c in conds if isinstance(c, dict)]


def node_posture(node: dict, *, now: datetime | None = None) -> NodePosture:
    """Distill a Rancher node object into scoring posture.

    `ready` is FALSE when the Ready condition is older than
    `_READY_MAX_AGE_SECONDS` — a disconnected cluster keeps its last node
    snapshot (including `Ready: True`) in Rancher indefinitely, so a stale
    timestamp means the kubelet stopped reporting, not that the node is up.
    A Ready/True condition with no usable timestamp at all is likewise not
    live evidence and fails closed.
    """
    labels = node.get("labels") or {}
    now = now or datetime.now(timezone.utc)
    has_ready, ready_age = _ready_condition_age(node, now)
    if not has_ready:
        ready, stale = False, False
    elif ready_age is None:
        # Ready=True with no usable timestamp: unverifiable freshness is not
        # evidence of liveness, so fail closed.
        ready, stale = False, True
    elif ready_age > _READY_MAX_AGE_SECONDS:
        ready, stale = False, True
    else:
        ready, stale = True, False
    schedulable = not node.get("unschedulable", False)
    roles = frozenset(r for r in _ROLE_KEYWORDS if _has_role(labels, r))
    capacity = (
        node.get("capacity")
        or (node.get("status") or {}).get("capacity")
        or {}
    )
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
        ready_age_seconds=ready_age,
        stale=stale,
    )


def _has_role(labels: dict, role: str) -> bool:
    for key, value in labels.items():
        if key == f"node-role.kubernetes.io/{role}" and str(value) in (
            "",
            "true",
        ):
            return True
    return False


def _runtime_handlers(node: dict) -> list[str]:
    handlers = node.get("runtimeHandlers") or []
    return [
        str(h["name"])
        for h in handlers
        if isinstance(h, dict) and h.get("name")
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


def _cluster_conditions(cluster: dict) -> list[dict]:
    """Rancher cluster conditions (top-level `conditions`, else status)."""
    conds = (
        cluster.get("conditions")
        or (cluster.get("status") or {}).get("conditions")
        or []
    )
    return [c for c in conds if isinstance(c, dict)]


def _cluster_state(cluster: dict) -> str:
    """Human-readable cluster health for the log/verdict reason."""
    for cond in _cluster_conditions(cluster):
        if cond.get("type") == "Ready" and str(cond.get("status")) != "True":
            message = str(cond.get("message") or cond.get("reason") or "")
            return message or "not ready"
    return "no Ready condition"


def _cluster_healthy(cluster: dict) -> bool:
    """False when Rancher reports the cluster agent/probe as not Ready.

    A disconnected cluster cannot supply live node evidence. Its node CRs
    freeze at the last successful sync, so an explicit `Ready: False` (e.g.
    "Cluster agent is not connected") disqualifies the cluster regardless of
    what those stale node objects still claim.
    """
    for cond in _cluster_conditions(cluster):
        if cond.get("type") == "Ready":
            return str(cond.get("status")) == "True"
    # No Ready condition at all: older Rancher payloads omit it, so fall back
    # to the node evidence rather than failing every cluster.
    return True


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

    if not _cluster_healthy(cluster):
        reasons.append(
            "cluster not Ready/Connected in Rancher "
            f"({_cluster_state(cluster)})"
        )

    active = [p for p in postures if p.ready]
    if not active:
        stale = [p for p in postures if p.stale]
        if stale:
            ages = [
                p.ready_age_seconds
                for p in stale
                if p.ready_age_seconds is not None
            ]
            detail = (
                f"newest {max(ages) / 60:.0f} min old"
                if ages
                else "no usable heartbeat timestamp"
            )
            reasons.append(
                f"no Ready nodes (stale heartbeat: {detail}, "
                f"limit {_READY_MAX_AGE_SECONDS / 60:.0f} min)"
            )
        else:
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
