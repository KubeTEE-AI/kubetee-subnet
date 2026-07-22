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
