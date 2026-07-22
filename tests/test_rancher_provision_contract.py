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


def test_local_provisioner_reconciles_exact_validator_authority():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert '-X PUT "$RANCHER/v3/globalroles/$ROLE_ID"' in text
    assert '-X DELETE "$RANCHER/v3/globalrolebindings/$BIND_ID"' in text
    assert "role rules verified exact" in text
    assert "bindings verified exact" in text

    start = text.index("ROLE_SPEC=")
    end = text.index("ROLE_MATCHES=", start)
    role = text[start:end]
    for empty_field in (
        "inheritedClusterRoles: []",
        "inheritedFleetWorkspacePermissions: null",
        "namespacedRules: {}",
    ):
        assert empty_field in role
    assert "inheritedNamespacedRules" not in role
    assert ".inheritedNamespacedRules" not in text
    assert "builtin: false" in role
    assert role.count("resourceNames: []") == 2
    assert role.count("nonResourceURLs: []") == 2


def test_local_provisioner_revokes_persisted_scoped_tokens_before_minting():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert '-X DELETE "$RANCHER/v3/tokens/$TOKEN_ID"' in text
    assert '-X DELETE "$RANCHER/v3/tokens/$PLATFORM_TOKEN_ID"' in text
    assert "prior validator token revocation verification failed" in text
    assert "prior platform token revocation verification failed" in text
    assert text.index("tokens?limit=-1&userId=$USER_ID") < text.index("VLTOK=")
    assert text.index("tokens?limit=-1&userId=$PLATFORM_USER_ID") < text.index(
        "PLATFORM_LOGIN_TOKEN="
    )


def test_local_provisioner_uses_distinct_platform_writer_credential():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert 'PLATFORM_USERNAME="kubetee-platform"' in text
    assert 'PLATFORM_ROLE_NAME="kubetee-platform-binding-store"' in text
    assert "rancher-platform-token" not in text
    assert '[ "$PLATFORM_BEARER" != "$BEARER" ]' in text
    assert "temporary platform credential revoked" in text

    start = text.index("PLATFORM_ROLE_SPEC=")
    end = text.index("PLATFORM_ROLE_MATCHES=", start)
    role = text[start:end]
    assert 'resources: ["clusters"]' in role
    assert 'verbs: ["get", "list", "patch"]' in role
    assert 'resources: ["nodes"]' not in role
    assert '"delete"' not in role


def test_local_provisioner_runtime_checks_platform_get_list_patch_contract():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert "/apis/management.cattle.io/v3/clusters" in text
    assert "application/json-patch+json" in text
    assert (
        "platform credential runtime contract verified (get/list/patch)"
        in text
    )
    assert '-H "Authorization: Bearer $PLATFORM_BEARER"' in text
    assert "application/merge-patch+json" not in text


def test_local_provisioner_fails_closed_unless_downstream_is_active_with_a_node():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    poll = text.index("for _ in $(seq 1 60)")
    gate = text.index(
        '|| { log "downstream did not become active with a node";', poll
    )
    binding = text.index("ORIGIN_FP=", poll)
    assert poll < gate < binding
    assert '[ "$ST" = "active" ] && [ "$N" -ge 1 ]' in text[poll:binding]


def test_platform_contract_token_is_minted_immediately_before_probe():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    binding = text.index("PATCH_BODY=")
    mint = text.index("PLATFORM_LOGIN_TOKEN=")
    probe = text.index("PLATFORM_CLUSTER_API=")
    assert binding < mint < probe


def test_platform_patch_contract_requires_exact_maps_and_fresh_resource_version():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert '--argjson patch "$PLATFORM_PATCH"' in text
    assert ".metadata.labels == $patch[2].value" in text
    assert ".metadata.annotations == $patch[3].value" in text
    assert (
        '.metadata.resourceVersion | type == "string" and length > 0' in text
    )
    assert "$response.metadata.labels[.key] == .value" not in text


def test_local_provisioner_seeds_complete_platform_durable_binding():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    for annotation in (
        "kubetee.ai/origin-fingerprint",
        "kubetee.ai/cluster-id",
        "kubetee.ai/chain-genesis-hash",
        "kubetee.ai/metagraph-block-hash",
        "kubetee.ai/observed-at-unix-ms",
        "kubetee.ai/challenge-id",
        "kubetee.ai/challenge-sha256",
        "kubetee.ai/hotkey-signature",
        "kubetee.ai/signer-ss58",
        "kubetee.ai/session-public-key",
        "kubetee.ai/provisioning-request-sha256",
        "kubetee.ai/cluster-api-ca-sha256",
        "kubetee.ai/kube-system-uid",
        "kubetee.ai/cluster-api-url",
        "kubetee.ai/tls-server-name",
        "kubetee.ai/fleet-identity",
        "kubetee.ai/baseline-release-sha256",
        "kubetee.ai/created-at-unix-ms",
        "kubetee.ai/revocation-generation",
        "kubetee.ai/cleanup-evidence",
        "kubetee.ai/audit-event-ids",
        "kubetee.ai/fingerprint-aliases",
    ):
        assert annotation in text
