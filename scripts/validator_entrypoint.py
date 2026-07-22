#!/usr/bin/env python3
"""Validator container entrypoint for the KubeTEE single-node testing pyramid.

Behavior:
  1. First run btcli-powered setup (register subnet, fund, register the
     owner/alice/bob triad, start emissions, set hypers for conviction +
     recycle).
  2. Only after the setup script succeeds, run the basic validator (g004): alice
     signs set_weights; miners discovered from the metagraph are scored via
     the read-only Rancher v3 API and the weight split is
     KUBETEE_MINER_SHARE to miners / the rest to the owner recycle UID.

This makes the validator container self-bootstrapping for local compose testing:
  docker compose up -d --build
  # then watch http://localhost:8080 (dozzle)

The setup is the same script used from host, but now invoked from inside with the compose-internal
chain address (ws://chain:9944) by default.

Note the wallet split (D7): BT_WALLET (default alice) is the *validator
signing* wallet; the subnet-owner wallet used for setup/sudo stays owner
(KUBETEE_OWNER_WALLET). The basic validator fails fast at startup on any
missing/invalid static configuration, including RANCHER_* (D14).
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
    owner_wallet = os.getenv("KUBETEE_OWNER_WALLET", "owner")
    chain_endpoint = os.getenv("BT_NETWORK", "ws://chain:9944")

    # Essential setup is captured so upstream output can never disclose wallet
    # or chain material through the entrypoint.
    setup_cmd = [
        sys.executable,
        "-u",
        "scripts/setup_single_node.py",
        "--netuid",
        str(netuid),
        "--owner-wallet",
        owner_wallet,
        "--chain-endpoint",
        chain_endpoint,
    ]

    try:
        subprocess.run(
            setup_cmd,
            check=True,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        print("[entrypoint] validator bootstrap failed", file=sys.stderr)
        raise SystemExit(1) from None

    # The basic validator reads /app/.kubetee_netuid itself (load_config), so
    # no env override is needed here.
    print("[entrypoint] validator bootstrap complete")
    # Exec the validator so it becomes PID 1 / receives signals cleanly.
    # It fails fast on missing/invalid static config (D14) - a refusal here
    # is a configuration error, not a crash loop.
    validator_cmd = [sys.executable, "scripts/validator.py"]
    os.execv(sys.executable, validator_cmd)


if __name__ == "__main__":
    main()
