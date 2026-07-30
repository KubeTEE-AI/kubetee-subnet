"""Live, READ-ONLY Finney smoke check.

Connects to Finney, reads the real SN90 metagraph, and enumerates Rancher
clusters/nodes. It never signs and never sets weights. Run before the first
weight-setting run:
    python -m validator.scripts.smoke_finney
(reads SUBNET_NETUID / RANCHER_URL / RANCHER_BEARER_TOKEN from env)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chain_state import ChainState
from config import ConfigError, load_config
from rancher_client import RancherClient, RancherEvidenceError, hotkey_of


def main() -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    print(
        f"network={cfg.network} endpoint={cfg.endpoint or '(default)'} netuid={cfg.netuid}"
    )

    chain = ChainState(cfg.network, cfg.endpoint, cfg.hotkey_seed)
    try:
        miners = chain.metagraph(cfg.netuid)
    except Exception as exc:  # noqa: BLE001
        print(f"metagraph read FAILED: {exc}", file=sys.stderr)
        return 1
    our_hotkey = chain.hotkey_ss58
    print(f"metagraph: {len(miners)} neurons; our hotkey={our_hotkey}")
    if miners:
        print(
            f"  first uids: {[(m.uid, m.hotkey[:10], m.is_validator) for m in miners[:5]]}"
        )

    rancher = RancherClient(cfg)
    try:
        clusters = rancher.list_clusters()
    except RancherEvidenceError as exc:
        print(f"rancher enumerate FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"rancher: {len(clusters)} clusters")
    for cluster in clusters[:10]:
        hk = hotkey_of(cluster) or "(unlabeled)"
        try:
            nodes = rancher.list_nodes(rancher.cluster_id(cluster))
            count = len(nodes)
        except RancherEvidenceError:
            count = -1
        print(
            f"  cluster={rancher.cluster_id(cluster)} hotkey={hk} nodes={count}"
        )

    print("smoke OK (read-only; no chain writes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
