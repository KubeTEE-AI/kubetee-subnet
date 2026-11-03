"""infrastructure_validation: fail-closed binary readiness policy."""

from datetime import datetime, timedelta, timezone

from infrastructure_validation import node_posture, validate_miner

HOTKEY = "5EHotkeyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def _ago(seconds: float = 30.0) -> str:
    """An RFC3339 heartbeat timestamp `seconds` in the past."""
    return (
        (datetime.now(timezone.utc) - timedelta(seconds=seconds))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _labels(role_flags, extra=None):
    labels = {}
    for role in role_flags:
        labels[f"node-role.kubernetes.io/{role}"] = ""
    labels.update(extra or {})
    return labels


def _node(
    cpu,
    mem,
    roles,
    labels=None,
    ready=True,
    schedulable=True,
    heartbeat_age=30.0,
):
    base = _labels(roles, labels or {})
    ready_cond = {"type": "Ready", "status": "True" if ready else "False"}
    if heartbeat_age is not None:
        ready_cond["lastHeartbeatTime"] = _ago(heartbeat_age)
    return {
        "labels": base,
        "conditions": [ready_cond],
        "capacity": {"cpu": str(cpu), "memory": mem},
        "unschedulable": not schedulable,
    }


def _gpu_node(cls="H200"):
    labels = {
        "nvidia.com/gpu.workload.config": "vm-passthrough",
        "nvidia.com/gpu.model": cls,
        "kubetee.ai/runtime": "kata-qemu-nvidia-gpu-tdx",
    }
    node = _node(96, "1500Gi", ["worker"], labels)
    return node


def _healthy_cluster(hotkey=HOTKEY):
    cluster = {"id": "c-1", "labels": {"kubetee.ai/hotkey": hotkey}}
    cp = [
        _node(96, "1500Gi", ["etcd", "control-plane", "worker"])
        for _ in range(5)
    ]
    gpu = [_gpu_node() for _ in range(2)]
    nodes = {cluster["id"]: cp + gpu}
    return [cluster], nodes


def _cid(cluster):
    return cluster["id"]


def test_parse_numeric_posture():
    node = _node(96, "1500Gi", ["worker"], {"nvidia.com/gpu.model": "H200"})
    p = node_posture(node)
    assert p.cpu_cores == 96
    assert p.memory_gib >= 1400
    assert p.ready and p.schedulable


def test_healthy_cluster_passes():
    clusters, nodes = _healthy_cluster()
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert verdict.ready, verdict.reasons


def test_banned_cluster_fails():
    clusters, nodes = _healthy_cluster()
    clusters[0]["labels"]["kubetee.ai/ban"] = "true"
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert not verdict.ready
    assert any("banned" in r for r in verdict.reasons)


def test_no_cluster_for_hotkey_fails():
    clusters, nodes = _healthy_cluster()
    verdict = validate_miner(
        "5EOtherHotkeyBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB", clusters, nodes, _cid
    )
    assert not verdict.ready


def test_two_clusters_one_hotkey_is_ambiguous():
    clusters, nodes = _healthy_cluster()
    clusters.append({"id": "c-2", "labels": {"kubetee.ai/hotkey": HOTKEY}})
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert not verdict.ready
    assert any("ambiguous" in r for r in verdict.reasons)


def test_no_gpu_worker_fails():
    clusters, nodes = _healthy_cluster()
    nodes[clusters[0]["id"]] = nodes[clusters[0]["id"]][:3]  # drop GPU nodes
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert not verdict.ready
    assert any("8-GPU" in r or "GPU" in r for r in verdict.reasons)


def test_small_cluster_still_passes():
    # No minimum node-count gate: a 3-node cluster (1 combined CP/etcd/
    # worker + 2 GPU workers) is ready if every other gate passes.
    clusters, nodes = _healthy_cluster()
    nodes[clusters[0]["id"]] = [
        _node(96, "1500Gi", ["etcd", "control-plane", "worker"]),
        _gpu_node(),
        _gpu_node(),
    ]
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert verdict.ready, verdict.reasons


def test_single_node_cluster_still_passes():
    # Even a 1-node all-in-one cluster is ready (docs describe the 3-node
    # topology as guidance, not a validator gate).
    clusters, nodes = _healthy_cluster()
    nodes[clusters[0]["id"]] = [
        _node(96, "1500Gi", ["etcd", "control-plane", "worker"]),
    ]
    # A 1-node cluster has no GPU worker → add the GPU class + CC runtime
    # labels so the single node also satisfies the GPU gate.
    nodes[clusters[0]["id"]][0]["labels"].update(
        {
            "nvidia.com/gpu.workload.config": "vm-passthrough",
            "nvidia.com/gpu.model": "H200",
            "kubetee.ai/runtime": "kata-qemu-nvidia-gpu-tdx",
        }
    )
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert verdict.ready, verdict.reasons


def test_gpu_node_without_passthrough_fails():
    clusters, nodes = _healthy_cluster()
    for node in nodes[clusters[0]["id"]]:
        if node["labels"].get("nvidia.com/gpu.model"):
            del node["labels"]["nvidia.com/gpu.workload.config"]
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert not verdict.ready


def test_unschedulable_worker_fails():
    clusters, nodes = _healthy_cluster()
    for node in nodes[clusters[0]["id"]]:
        if node["labels"].get("nvidia.com/gpu.model"):
            # Rancher top-level unschedulable flag
            node["unschedulable"] = True
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert not verdict.ready


# --- freshness gates (na-us-dallas-132 incident, 2026-11-03) ----------------
# A decommissioned node keeps its last `Ready: True` snapshot in Rancher
# forever once the cluster agent disconnects. These pin the gates that stop
# such a frozen snapshot from earning epoch weight.


def test_stale_ready_condition_is_not_ready():
    node = _node(96, "1500Gi", ["worker"], heartbeat_age=3600)
    p = node_posture(node)
    assert not p.ready
    assert p.stale
    assert p.ready_age_seconds >= 3599


def test_fresh_ready_condition_is_ready():
    node = _node(96, "1500Gi", ["worker"], heartbeat_age=60)
    p = node_posture(node)
    assert p.ready
    assert not p.stale


def test_ready_without_timestamp_fails_closed():
    node = _node(96, "1500Gi", ["worker"])
    del node["conditions"][0]["lastHeartbeatTime"]
    p = node_posture(node)
    assert not p.ready
    assert p.stale


def test_go_style_timestamp_is_parsed():
    # Rancher serialises some conditions as Go time, not RFC3339.
    node = _node(96, "1500Gi", ["worker"])
    node["conditions"][0][
        "lastHeartbeatTime"
    ] = "2026-11-03 10:36:55 +0000 UTC"
    p = node_posture(node)
    assert p.ready_age_seconds is not None
    assert p.stale  # 2026-11-03 is well past the 15 min window


def test_decommissioned_cluster_scores_zero():
    """Full replay of the incident: cluster disconnected, node frozen Ready."""
    clusters, nodes = _healthy_cluster()
    cid = clusters[0]["id"]
    # Every node frozen >15 min ago and the cluster reports Ready=False.
    for node in nodes[cid]:
        node["conditions"][0]["lastHeartbeatTime"] = _ago(3400)
    clusters[0]["conditions"] = [
        {
            "type": "Ready",
            "status": "False",
            "reason": "Disconnected",
            "message": "Cluster agent is not connected",
        }
    ]
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert not verdict.ready
    joined = "; ".join(verdict.reasons)
    assert "stale heartbeat" in joined
    assert "Cluster agent is not connected" in joined


def test_disconnected_cluster_fails_even_with_fresh_nodes():
    """Cluster-level Ready=False is disqualifying on its own."""
    clusters, nodes = _healthy_cluster()
    clusters[0]["conditions"] = [
        {"type": "Ready", "status": "False", "reason": "Disconnected"}
    ]
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert not verdict.ready
    assert any(
        "Connected" in r or "Disconnected" in r for r in verdict.reasons
    )


def test_cluster_without_ready_condition_still_scores():
    """Older Rancher payloads omit the cluster Ready condition — don't regress."""
    clusters, nodes = _healthy_cluster()
    clusters[0].pop("conditions", None)
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert verdict.ready, verdict.reasons


def test_duplicate_ready_conditions_use_newest_heartbeat():
    """Rancher's v3 payload carries TWO Ready conditions on every node.

    The legacy copy has only a Go-format lastTransitionTime (registration
    time, days old) and no heartbeat; the Norman copy has the real
    lastHeartbeatTime. Reading the first one would mark every healthy node
    stale, so the newest timestamp must win.
    """
    node = _node(96, "1500Gi", ["worker"], heartbeat_age=30)
    node["conditions"] = [
        {
            "type": "Ready",
            "status": "True",
            "reason": "KubeletReady",
            "lastTransitionTime": _ago(5 * 24 * 3600),
        },
        {
            "type": "Ready",
            "status": "True",
            "reason": "KubeletReady",
            "lastHeartbeatTime": _ago(30),
            "lastTransitionTime": _ago(5 * 24 * 3600),
        },
    ]
    p = node_posture(node)
    assert p.ready
    assert not p.stale
    assert p.ready_age_seconds < 120


def test_duplicate_ready_conditions_both_stale_is_stale():
    """Same duplicate shape, but the heartbeat itself is old → dead."""
    node = _node(96, "1500Gi", ["worker"], heartbeat_age=3600)
    node["conditions"] = [
        {
            "type": "Ready",
            "status": "True",
            "lastTransitionTime": _ago(5 * 24 * 3600),
        },
        {"type": "Ready", "status": "True", "lastHeartbeatTime": _ago(3600)},
    ]
    p = node_posture(node)
    assert not p.ready
    assert p.stale
