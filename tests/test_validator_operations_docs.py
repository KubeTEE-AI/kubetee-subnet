"""Public validator operations documentation safety contract."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).parent.parent
GUIDE = ROOT / "docs" / "RUNNING_A_VALIDATOR.md"


def test_operations_guide_separates_localnet_from_mainnet():
    text = GUIDE.read_text(encoding="utf-8")
    assert "# Running a KubeTEE Validator" in text
    assert "## Localnet only" in text
    assert "## Finney mainnet" in text
    assert "make subnet" in text
    assert "make subnet-external" in text
    assert "ghcr.io/kubetee-ai/kubetee-subnet:latest" in text


def test_operations_guide_never_uses_dev_keys_as_mainnet_values():
    text = GUIDE.read_text(encoding="utf-8")
    assert "owner / alice / bob" in text
    assert "never use those identities on Finney" in text
    assert "RANCHER_BEARER_TOKEN=<" not in text
    assert "token-" not in text
    assert "BEGIN PRIVATE KEY" not in text


def test_operations_guide_keeps_external_environment_file_outside_checkout():
    text = GUIDE.read_text(encoding="utf-8")
    external_env_file = "/secure/path/validator.env"

    assert (
        "Create a private environment file at "
        f"`{external_env_file}` outside the\nrepository."
    ) in text
    assert f"chmod 600 {external_env_file}" in text
    assert text.count(f"--env-file {external_env_file}") == 5
    assert "--env-file validator.env" not in text

    observation = text.split("Verify observable behavior without printing credentials:", 1)[1]
    observation = observation.split("A startup error", 1)[0]
    assert observation.count(f"--env-file {external_env_file}") == 2


def test_operations_guide_covers_safe_dynamic_localnet_inspection():
    text = GUIDE.read_text(encoding="utf-8")

    assert "make subnet-clean" in text
    assert "NETUID=$(cat /app/.kubetee_netuid)" in text
    assert 'btcli subnets metagraph --netuid "$NETUID" --network ws://chain:9944' in text
    assert "validator permit" in text
    assert "stake" in text
    assert "weights" in text
    assert "http://127.0.0.1:9100/metrics" in text
    assert "debug/synthetic" in text
    assert "not production certification" in text


def test_operations_guide_requires_external_rancher_ca_bundle_path():
    text = GUIDE.read_text(encoding="utf-8")

    assert "Required host path to the Rancher CA/bundle file." in text
