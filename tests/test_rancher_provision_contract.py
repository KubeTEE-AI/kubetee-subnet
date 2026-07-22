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


def test_local_provisioner_waits_for_successful_v3_login_before_provisioning():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    gate = text.index('login_to_rancher()')
    login = text.index("LTOK=", gate)
    assert gate < login
    assert '"$RANCHER/v3-public/localProviders/local?action=login"' in text[
        gate:login
    ]
    assert "for _ in $(seq 1 120)" in text[gate:login]
    assert "Rancher local login did not become ready" in text[gate:login]


def test_local_provisioner_uses_bounded_extension_token_api_only():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert 'EXT_TOKEN_API="$RANCHER/apis/ext.cattle.io/v1/tokens"' in text
    assert 'EXT_TOKEN_LIMIT="100"' in text
    assert 'EXT_TOKEN_USER_LABEL="cattle.io/user-id"' in text
    assert "authn.management.cattle.io/token-userId" not in text
    list_helper = text[text.index("list_ext_tokens()") : text.index("delete_ext_tokens_except()")]
    assert '--data-urlencode "labelSelector=$EXT_TOKEN_USER_LABEL=$user_id"' in list_helper
    assert '"$RANCHER/v3/token"' not in text
    assert '"$RANCHER/v3/tokens?' not in text
    assert "metadata.continue" in text
    assert 'length <= ($limit | tonumber)' in text


def test_local_provisioner_creates_owner_bound_one_shot_extension_tokens():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert 'apiVersion: "ext.cattle.io/v1"' in text
    assert 'kind: "Token"' in text
    create_helper = text[
        text.index("mint_ext_token()") : text.index("validate_ext_token_create()")
    ]
    assert "userID:" not in create_helper
    assert "userPrincipal:" not in create_helper
    assert ".status.bearerToken" in text
    assert '.status.bearerToken == ("ext/" + $name + ":" + $value)' in text
    list_validation = text[
        text.index("validate_ext_token_list()") : text.index("mint_ext_token()")
    ]
    assert '((.status.bearerToken // "") == "")' in list_validation
    assert '((.status.value // "") == "")' in list_validation


def test_local_provisioner_uses_millisecond_ttls_and_distinct_credentials():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert 'VALIDATOR_TOKEN_TTL_MS="3600000"' in text
    assert 'PLATFORM_TOKEN_TTL_MS="300000"' in text
    assert 'mint_ext_token "$VLTOK" "$VALIDATOR_TOKEN_DESCRIPTION"' in text
    assert 'mint_ext_token "$PLATFORM_LOGIN_TOKEN" "$PLATFORM_TOKEN_DESCRIPTION"' in text
    assert '[ "$PLATFORM_BEARER" != "$BEARER" ]' in text


def test_local_provisioner_deletes_only_known_legacy_login_ids():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert 'delete_known_login "$LTOK" "$VALIDATOR_LOGIN_TOKEN_ID"' in text
    assert 'delete_known_login "$LTOK" "$PLATFORM_LOGIN_TOKEN_ID"' in text
    assert 'delete_known_login "$LTOK" "$ADMIN_LOGIN_TOKEN_ID"' in text
    assert '"$RANCHER/v3/tokens/$login_id"' in text


def test_local_provisioner_retries_exact_login_deletion_only_after_404():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()
    deletion = text[
        text.index("delete_known_login()") : text.index("wait_for_ext_token_api()")
    ]

    assert "for _ in $(seq 1 20); do" in deletion
    assert "status=$(cr -o /dev/null -w '%{http_code}' -X DELETE \\" in deletion
    assert '"$RANCHER/v3/tokens/$login_id"' in deletion
    assert "200|204) return 0 ;;" in deletion
    assert "404) sleep 1 ;;" in deletion
    assert '*) log "login token deletion failed"; return 1 ;;' in deletion
    assert 'log "login token deletion did not become ready"' in deletion


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

    assert text.index('delete_ext_tokens_except "$LTOK" "$USER_ID"') < text.index(
        "VALIDATOR_LOGIN_RESPONSE="
    )
    assert text.index(
        'delete_ext_tokens_except "$LTOK" "$PLATFORM_USER_ID"'
    ) < text.index("PLATFORM_LOGIN_RESPONSE=")
    assert '"$RANCHER/v3/tokens?limit=-1' not in text


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
