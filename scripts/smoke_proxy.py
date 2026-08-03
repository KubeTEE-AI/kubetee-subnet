"""Reader-side smoke test for the KubeTEE Rancher proxy.

Signs a request with the validator's hotkey (from VALIDATOR_HOTKEY_SEED env)
and calls the proxy at https://validator.kubetee.ai/v3/clusters. Confirms
the proxy authenticates the hotkey and forwards the request upstream.

Usage:
    VALIDATOR_HOTKEY_SEED="<mnemonic>" python scripts/smoke_proxy.py
"""

import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "validator"))

import bittensor_core  # noqa: E402
from chain_state import derive_hotkey_keypair  # noqa: E402

PROXY_URL = os.environ.get("KUBETEE_PROXY_URL", "https://validator.kubetee.ai")
PATH = "/v3/clusters"


def main() -> int:
    seed = os.environ.get("VALIDATOR_HOTKEY_SEED", "").strip()
    if not seed:
        print("VALIDATOR_HOTKEY_SEED is required", file=sys.stderr)
        return 1
    keypair = derive_hotkey_keypair(seed)
    ts = int(time.time())
    query = ""
    message = f"{PATH}\n{query}\n{ts}".encode()
    signature = bytes(keypair.sign(message)).hex()
    url = f"{PROXY_URL}{PATH}"
    req = urllib.request.Request(
        url,
        headers={
            "BT-Validator-Hotkey": keypair.ss58_address,
            "BT-Validator-Signature": signature,
            "BT-Validator-Ts": str(ts),
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            print(f"HTTP {resp.status}")
            print(body[:500])
            return 0 if resp.status == 200 else 1
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()[:200]}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
