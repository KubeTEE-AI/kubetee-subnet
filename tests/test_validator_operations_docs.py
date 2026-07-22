"""Public validator operations documentation safety contract."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).parent.parent
GUIDE = ROOT / "docs" / "RUNNING_A_VALIDATOR.md"


def test_operations_guide_uses_a_direct_mainnet_container():
    text = GUIDE.read_text(encoding="utf-8")

    assert "# Running a KubeTEE Validator" in text
    assert "## Finney mainnet" in text
    assert "docker run -d" in text
    assert "--name kubetee-validator" in text
    assert "--restart unless-stopped" in text
    assert "--env-file /secure/path/validator.env" in text
    assert "-v /secure/path/validator-wallet:/root/.bittensor:ro" in text
    assert "-v /secure/path/rancher-ca.crt:/shared/rancher-ca.crt:ro" in text
    assert "-p 127.0.0.1:9100:9100" in text
    assert "python -u scripts/validator.py" in text
    assert "docker compose" not in text
    assert "make subnet" not in text


def test_operations_guide_records_the_public_mainnet_snapshot_defaults():
    text = GUIDE.read_text(encoding="utf-8")

    assert "KUBETEE_SUBNET_NETUID=90" in text
    assert "KUBETEE_OWNER_HOTKEY=5EKtGWqskt8qBqdAZ78pSWRCYRuYmDc5XbwJPDqH1EpiSTEE" in text
    assert "KUBETEE_CHAIN_NETWORK=finney" in text
    assert "BTCLI v11" in text
    assert "block 8680289" in text
    assert "https://rancher.kubetee.ai" in text
    assert "provisional" in text
    assert "not DNS-resolvable" in text


def test_operations_guide_never_exposes_credentials_or_bootstraps_chain_state():
    text = GUIDE.read_text(encoding="utf-8")

    assert "RANCHER_BEARER_TOKEN=<" not in text
    assert "token-" not in text
    assert "BEGIN PRIVATE KEY" not in text
    assert "overrides the local bootstrap entrypoint" in text
    assert "never creates a subnet, registers a key, stakes, or changes Finney state" in text


def test_operations_guide_keeps_external_environment_file_outside_checkout():
    text = GUIDE.read_text(encoding="utf-8")
    external_env_file = "/secure/path/validator.env"

    assert (
        "Create a private environment file at "
        f"`{external_env_file}` outside the\nrepository."
    ) in text
    assert f"chmod 600 {external_env_file}" in text
    assert text.count(f"--env-file {external_env_file}") == 1
    assert "--env-file validator.env" not in text


def test_operations_guide_requires_external_rancher_ca_bundle_path():
    text = GUIDE.read_text(encoding="utf-8")

    assert "/secure/path/rancher-ca.crt:/shared/rancher-ca.crt:ro" in text


def test_operations_guide_requires_a_dedicated_hotkey_only_wallet_root():
    text = GUIDE.read_text(encoding="utf-8")

    assert "wallet root contains only the signing hotkey and public coldkey metadata" in text
    assert "Do not mount a normal/operator wallet root" in text
    assert "private coldkey or recovery material" in text
