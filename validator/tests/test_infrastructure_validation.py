"""infrastructure_validation: fail-closed binary readiness policy."""

from infrastructure_validation import node_posture, validate_miner

HOTKEY = "5EHotkeyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def _labels(role_flags, extra=None):
    labels = {}
    for role in role_flags:
        labels[f"node-role.kubernetes.io/{role}"] = ""
    labels.update(extra or {})
    return labels


def _node(cpu, mem, roles, labels=None, ready=True, schedulable=True):
    base = _labels(roles, labels or {})
    return {
        "labels": base,
        "conditions": [
            {"type": "Ready", "status": "True" if ready else "False"}
        ],
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
        _node(32, "128Gi", ["etcd", "control-plane", "worker"])
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


def test_below_minimum_nodes_fails():
    clusters, nodes = _healthy_cluster()
    # 6 nodes: drop one GPU worker from the 5+2 shape -> below the 7 minimum
    nodes[clusters[0]["id"]] = nodes[clusters[0]["id"]][:-1]
    verdict = validate_miner(HOTKEY, clusters, nodes, _cid)
    assert not verdict.ready
    assert any("7 minimum" in r for r in verdict.reasons)


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
