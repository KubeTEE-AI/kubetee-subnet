"""g004 V1: deterministic redaction/allowlist checks for the Rancher fixtures.

Every fixture under tests/fixtures/rancher/ must contain only allowlisted
keys and synthetic values. This test IS the redaction gate: if a future
re-capture leaks a live field, hostname, address, or credential shape,
it fails deterministically.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "rancher"

COLLECTION_KEYS = {"type", "resourceType", "links", "pagination", "data"}
PAGINATION_KEYS = {"first", "next", "last", "limit", "total", "partial"}
OBJECT_KEYS = {
    "id", "type", "baseType", "uuid", "state", "transitioning",
    "transitioningMessage", "labels", "links", "clusterId",
}
LINK_KEYS = {"self", "remove", "nodes"}
SYNTHETIC_ORIGIN = "https://rancher.example"

FORBIDDEN_PATTERNS = re.compile(
    r"token-|bearer|secret|password|kubeconfig|cacert|BEGIN CERT|"
    r"ipaddress|externalip|hostname|serviceaccount|kubetee\.ai/?\s*$|"
    r"staging-rancher",
    re.IGNORECASE,
)
# Real chain addresses must not appear; synthetic ones carry the FAKE marker.
SS58_LIKE = re.compile(r"5[A-HJ-NP-Za-km-z1-9]{47}")


def fixture_files() -> list[pathlib.Path]:
    return sorted(FIXTURES.glob("*.json"))


def test_fixture_directory_is_populated():
    names = {p.name for p in fixture_files()}
    assert {"clusters.json", "clusters-page1.json", "clusters-page2.json",
            "nodes.json", "contract.json"} <= names


@pytest.mark.parametrize(
    "path",
    [p for p in fixture_files() if p.name != "contract.json"],
    ids=lambda p: p.name,
)
def test_no_forbidden_content(path: pathlib.Path):
    text = path.read_text()
    for line in text.splitlines():
        assert not FORBIDDEN_PATTERNS.search(line), (path.name, line[:80])
    for match in SS58_LIKE.findall(text):
        assert "FAKE" in match, f"non-synthetic SS58-like value in {path.name}"


def test_contract_carries_no_credential_shapes():
    # The contract may NAME dropped secret fields; it must never hold values.
    text = (FIXTURES / "contract.json").read_text()
    assert not re.search(r"token-\w{5}:", text)
    assert not re.search(r"BEGIN (RSA |EC )?PRIVATE KEY|BEGIN CERTIFICATE", text)
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text), "IP literal in contract"
    for match in SS58_LIKE.findall(text):
        assert "FAKE" in match


@pytest.mark.parametrize(
    "path",
    [p for p in fixture_files() if p.name != "contract.json"],
    ids=lambda p: p.name,
)
def test_allowlist_keys_only(path: pathlib.Path):
    doc = json.loads(path.read_text())
    assert set(doc) <= COLLECTION_KEYS, set(doc) - COLLECTION_KEYS
    assert set(doc["pagination"]) <= PAGINATION_KEYS
    for obj in doc["data"]:
        assert set(obj) <= OBJECT_KEYS, (path.name, set(obj) - OBJECT_KEYS)
        assert set(obj.get("links", {})) <= LINK_KEYS
        for url in obj.get("links", {}).values():
            assert url.startswith(SYNTHETIC_ORIGIN), url
        for key in obj.get("labels", {}):
            assert key.startswith("kubetee.ai/"), key


def test_contract_pins_required_semantics():
    contract = json.loads((FIXTURES / "contract.json").read_text())
    assert contract["cluster"]["active_value"] == "active"
    assert contract["node"]["active_value"] == "active"
    assert "next" in contract["collection"]["pagination_fields"]
    assert contract["http_client_requirements"]["user_agent_required"] is True
    assert contract["cluster"]["miner_label_key"] == "kubetee.ai/miner-hotkey"
    assert contract["transitional_or_unknown_treated_inactive"]


def test_pagination_pair_is_marker_complete():
    page1 = json.loads((FIXTURES / "clusters-page1.json").read_text())
    page2 = json.loads((FIXTURES / "clusters-page2.json").read_text())
    assert page1["pagination"]["partial"] is True
    assert "next" in page1["pagination"]
    assert "next" not in page2["pagination"], "final page must not chain further"
    total = page1["pagination"]["total"]
    assert len(page1["data"]) + len(page2["data"]) == total
