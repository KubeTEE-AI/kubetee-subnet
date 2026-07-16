#!/usr/bin/env python3
"""
Validator container entrypoint for the KubeTEE single-node testing pyramid.

Behavior requested:
  1. First run btcli-powered setup (register subnet, fund, start emissions, set hypers for conviction + recycle).
  2. Once the setup script exits, run the owner validator (which sets weights 1.0 to TARGET_UID).

This makes the validator container self-bootstrapping for local compose testing:
  docker compose up -d --build
  # then watch http://localhost:8080 (dozzle)

The setup is the same script used from host, but now invoked from inside with the compose-internal
chain address (ws://chain:9944) by default.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time


def main() -> None:
    role = os.getenv("ROLE", "validator").lower()
    if role == "miner":
        # Stub miner in compose profiles: just stay alive for now.
        print("[entrypoint] ROLE=miner -> stub (sleeping)")
        while True:
            time.sleep(3600)

    netuid = os.getenv("KUBETEE_SUBNET_NETUID", "1")
    owner_wallet = os.getenv("BT_WALLET", "owner")
    chain_endpoint = os.getenv("BT_NETWORK", "ws://chain:9944")

    print("=== KubeTEE Validator Container Entrypoint ===")
    print(f"  role={role}")
    print(f"  chain_endpoint={chain_endpoint}")
    print(f"  netuid={netuid}")
    print(f"  owner_wallet={owner_wallet}")
    print("  Phase 1: (deterministic accounts) register subnet if not exists + stake + start emissions + set conviction/recycle hypers (btcli)")
    print("  Phase 2: owner validator (set weights 1.0 for recycle observation)")

    # Run the setup script (it is idempotent-ish and uses check=False on most steps)
    setup_cmd = [
        sys.executable, "-u",
        "scripts/setup_single_node.py",
        "--netuid", str(netuid),
        "--owner-wallet", owner_wallet,
        "--chain-endpoint", chain_endpoint,
    ]

    print(f"\n$ {' '.join(setup_cmd)}")
    setup_proc = subprocess.run(setup_cmd, env=os.environ.copy())

    if setup_proc.returncode == 0:
        print("\n=== Setup script exited successfully ===")
    else:
        print(f"\n=== Setup script exited with code {setup_proc.returncode} ===")
        print("Continuing to validator anyway (setup steps are best-effort with --yes; inspect dozzle logs).")

    # If setup wrote a .kubetee_netuid file (because create allocated a different netuid that we own),
    # use it for the validator phase so TARGET_UID etc. match the subnet we actually control.
    netuid_file = "/app/.kubetee_netuid"
    if os.path.exists(netuid_file):
        try:
            with open(netuid_file) as f:
                actual = f.read().strip()
            if actual and actual != os.getenv("KUBETEE_SUBNET_NETUID"):
                os.environ["KUBETEE_SUBNET_NETUID"] = actual
                print(f"  Using netuid from setup: {actual} (overriding env)")
        except Exception as e:
            print(f"  Warning reading netuid file: {e}")

    print("\n=== Phase 2: starting owner validator ===")
    # Exec the validator so it becomes PID 1 / receives signals cleanly
    # (matches original CMD intent)
    validator_cmd = [sys.executable, "scripts/owner_validator.py"]
    print(f"$ {' '.join(validator_cmd)}")
    os.execv(sys.executable, validator_cmd)


if __name__ == "__main__":
    main()
