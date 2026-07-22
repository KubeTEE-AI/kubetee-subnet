"""Static trust-contract checks for the disposable Rancher provisioner."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).parent.parent


def test_local_provisioner_uses_platform_binding_contract():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()
    for key in (
        "kubetee.ai/binding-id",
        "kubetee.ai/hotkey",
        "kubetee.ai/coldkey",
        "kubetee.ai/provider-id",
        "kubetee.ai/binding-status",
        "kubetee.ai/generation",
        "kubetee.ai/netuid",
        "kubetee.ai/network",
        "kubetee.ai/origin-fp-prefix",
        "kubetee.ai/enrollment-uid",
    ):
        assert key in text
    retired_label = "kubetee.ai/" + "miner-hotkey"
    assert retired_label not in text
    assert '"ENROLLED"' in text


def test_local_provisioner_requires_complete_synthetic_identity():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()
    for variable in (
        "MINER_HOTKEY",
        "MINER_COLDKEY",
        "MINER_UID",
        "MINER_NETUID",
        "MINER_NETWORK",
    ):
        assert f"{variable}=" in text
        assert f"${{{variable}:?" in text


def test_local_provisioner_never_logs_bootstrap_url_or_binding_identity():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert "registration manifest: $MURL" not in text
    assert "canonical synthetic ENROLLED binding to $CID" not in text
