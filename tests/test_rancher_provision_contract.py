"""Static trust-contract checks for the disposable Rancher provisioner."""

from __future__ import annotations

import os
import pathlib
import shlex
import subprocess

import pytest

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

    helper = text.index("create_local_login()")
    gate = text.index("login_to_rancher()")
    login = text.index("LTOK=", gate)
    assert helper < gate < login
    assert (
        '"$RANCHER/v3-public/localProviders/local?action=login"'
        in text[helper:gate]
    )
    assert "-w '%{http_code}'" in text[helper:gate]
    assert '[ "$login_status" = "201" ]' in text[helper:gate]
    assert "umask 077" in text[helper:gate]
    assert "trap 'rm -f \"$login_response_file\"' EXIT" in text[helper:gate]
    assert "trap 'exit 1' HUP INT TERM" in text[helper:gate]
    assert 'create_local_login "admin" "$BOOT"' in text[gate:login]
    assert "for _ in $(seq 1 120)" in text[gate:login]
    assert "Rancher local login did not become ready" in text[gate:login]


def test_local_provisioner_routes_every_login_through_exact_status_helper():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()
    endpoint = '"$RANCHER/v3-public/localProviders/local?action=login"'

    assert text.count(endpoint) == 1
    assert (
        'VALIDATOR_LOGIN_RESPONSE=$(create_local_login "$VAL_USERNAME" '
        '"$VAL_PASSWORD")' in text
    )
    assert (
        'PLATFORM_LOGIN_RESPONSE=$(create_local_login "$PLATFORM_USERNAME" '
        '"$PLATFORM_PASSWORD")' in text
    )


def _run_local_login(
    tmp_path: pathlib.Path,
    status: str,
    *,
    response_body: str = (
        '{"id":"body-hostile-marker","token":"token-hostile-marker"}'
    ),
) -> tuple[dict[str, int], subprocess.CompletedProcess[str]]:
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()
    helpers = text[
        text.index("validate_login_document()") : text.index(
            "validate_ext_token_list()"
        )
    ]
    harness_path = tmp_path / "local-login.sh"
    username = "username-hostile-marker"
    password = "password-hostile-marker"

    harness_path.write_text(f"""#!/usr/bin/env sh
RANCHER=https://rancher.invalid
RANCHER_ID_PATTERN='^[A-Za-z0-9][A-Za-z0-9._-]{{0,253}}$'
LOGIN_STATUS={shlex.quote(status)}
LOGIN_BODY={shlex.quote(response_body)}
EXPECTED_USERNAME={shlex.quote(username)}
EXPECTED_PASSWORD={shlex.quote(password)}
PAYLOAD_VALID_PATH={shlex.quote(str(tmp_path / "payload-valid"))}

cr() {{
  output_file=
  payload=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -o)
        shift
        output_file=$1
        ;;
      -d)
        shift
        payload=$1
        ;;
    esac
    shift
  done
  [ -n "$output_file" ] || return 90
  if printf '%s' "$payload" | jq -e \
    --arg username "$EXPECTED_USERNAME" \
    --arg password "$EXPECTED_PASSWORD" \
    '.username == $username and .password == $password' >/dev/null; then
    printf '1\n' > "$PAYLOAD_VALID_PATH"
  else
    printf '0\n' > "$PAYLOAD_VALID_PATH"
  fi
  printf '%s' "$LOGIN_BODY" > "$output_file"
  [ "$LOGIN_STATUS" != "transport" ] || return 1
  printf '%s' "$LOGIN_STATUS"
}}

log() {{ return 91; }}
sleep() {{ return 92; }}

{helpers}

if login_document=$(create_local_login "$EXPECTED_USERNAME" "$EXPECTED_PASSWORD"); then
  result=0
else
  result=$?
fi
if [ "$login_document" = "$LOGIN_BODY" ]; then
  response_matches=1
else
  response_matches=0
fi
if [ -z "$login_document" ]; then
  response_empty=1
else
  response_empty=0
fi
unset login_document LOGIN_BODY EXPECTED_USERNAME EXPECTED_PASSWORD
printf 'result=%s\n' "$result"
printf 'response_matches=%s\n' "$response_matches"
printf 'response_empty=%s\n' "$response_empty"
printf 'payload_valid=%s\n' "$(cat "$PAYLOAD_VALID_PATH")"
""")
    result = subprocess.run(
        ["sh", str(harness_path)],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "TMPDIR": str(tmp_path)},
    )
    outcome = {
        key: int(value)
        for key, value in (
            line.split("=", maxsplit=1) for line in result.stdout.splitlines()
        )
    }
    return outcome, result


def test_local_login_accepts_only_exact_201(tmp_path: pathlib.Path):
    outcome, result = _run_local_login(tmp_path, "201")

    assert result.returncode == 0
    assert result.stderr == ""
    assert outcome == {
        "result": 0,
        "response_matches": 1,
        "response_empty": 0,
        "payload_valid": 1,
    }
    assert list(tmp_path.glob("kubetee-login.*")) == []


def test_local_login_cleans_malformed_201_without_disclosure(
    tmp_path: pathlib.Path,
):
    outcome, result = _run_local_login(
        tmp_path,
        "201",
        response_body="malformed-body-hostile-marker",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert outcome == {
        "result": 1,
        "response_matches": 0,
        "response_empty": 1,
        "payload_valid": 1,
    }
    assert "malformed-body-hostile-marker" not in result.stdout
    assert list(tmp_path.glob("kubetee-login.*")) == []


def test_local_login_cleans_transport_failure_without_disclosure(
    tmp_path: pathlib.Path,
):
    outcome, result = _run_local_login(tmp_path, "transport")

    assert result.returncode == 0
    assert result.stderr == ""
    assert outcome == {
        "result": 1,
        "response_matches": 0,
        "response_empty": 1,
        "payload_valid": 1,
    }
    assert "body-hostile-marker" not in result.stdout
    assert "token-hostile-marker" not in result.stdout
    assert list(tmp_path.glob("kubetee-login.*")) == []


@pytest.mark.parametrize("status", ["200", "202", "204", "299"])
def test_local_login_rejects_other_2xx_without_disclosure(
    tmp_path: pathlib.Path,
    status: str,
):
    outcome, result = _run_local_login(tmp_path, status)

    assert result.returncode == 0
    assert result.stderr == ""
    assert outcome == {
        "result": 1,
        "response_matches": 0,
        "response_empty": 1,
        "payload_valid": 1,
    }
    for hostile_marker in (
        "body-hostile-marker",
        "token-hostile-marker",
        "username-hostile-marker",
        "password-hostile-marker",
    ):
        assert hostile_marker not in result.stdout
        assert hostile_marker not in result.stderr
    assert list(tmp_path.glob("kubetee-login.*")) == []


def test_local_provisioner_uses_bounded_extension_token_api_only():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert 'EXT_TOKEN_API="$RANCHER/apis/ext.cattle.io/v1/tokens"' in text
    assert 'EXT_TOKEN_LIMIT="100"' in text
    assert 'EXT_TOKEN_USER_LABEL="cattle.io/user-id"' in text
    assert "authn.management.cattle.io/token-userId" not in text
    list_helper = text[
        text.index("list_ext_tokens()") : text.index(
            "delete_ext_tokens_except()"
        )
    ]
    assert (
        '--data-urlencode "labelSelector=$EXT_TOKEN_USER_LABEL=$user_id"'
        in list_helper
    )
    assert '"$RANCHER/v3/token"' not in text
    assert '"$RANCHER/v3/tokens?' not in text
    assert "metadata.continue" in text
    assert "length <= ($limit | tonumber)" in text


def test_local_provisioner_creates_owner_bound_one_shot_extension_tokens():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert 'apiVersion: "ext.cattle.io/v1"' in text
    assert 'kind: "Token"' in text
    create_helper = text[
        text.index("mint_ext_token()") : text.index(
            "validate_ext_token_create()"
        )
    ]
    assert "userID:" not in create_helper
    assert "userPrincipal:" not in create_helper
    assert ".status.bearerToken" in text
    assert '.status.bearerToken == ("ext/" + $name + ":" + $value)' in text
    list_validation = text[
        text.index("validate_ext_token_list()") : text.index(
            "mint_ext_token()"
        )
    ]
    assert '((.status.bearerToken // "") == "")' in list_validation
    assert '((.status.value // "") == "")' in list_validation


def test_local_provisioner_uses_millisecond_ttls_and_distinct_credentials():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert 'VALIDATOR_TOKEN_TTL_MS="3600000"' in text
    assert 'PLATFORM_TOKEN_TTL_MS="300000"' in text
    assert 'mint_ext_token "$VLTOK" "$VALIDATOR_TOKEN_DESCRIPTION"' in text
    assert (
        'mint_ext_token "$PLATFORM_LOGIN_TOKEN" "$PLATFORM_TOKEN_DESCRIPTION"'
        in text
    )
    assert '[ "$PLATFORM_BEARER" != "$BEARER" ]' in text


def _assert_no_norman_login_token_path(text: str) -> None:
    assert "$RANCHER/v3/tokens" not in text


def test_local_provisioner_rejects_unquoted_norman_login_token_path_fixture():
    with pytest.raises(AssertionError):
        _assert_no_norman_login_token_path("cr $RANCHER/v3/tokens/mutation")


def test_local_provisioner_revokes_only_known_logins_via_management_tokens():
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()

    assert (
        'LOGIN_TOKEN_API="$RANCHER/k8s/clusters/local/apis/management.cattle.io/v3/tokens"'
        in text
    )
    assert (
        'delete_known_login "$LTOK" "$VALIDATOR_LOGIN_TOKEN_ID" "$VLTOK"'
        in text
    )
    assert (
        'delete_known_login "$LTOK" "$PLATFORM_LOGIN_TOKEN_ID" "$PLATFORM_LOGIN_TOKEN"'
        in text
    )
    assert 'delete_known_login "$LTOK" "$ADMIN_LOGIN_TOKEN_ID" "$LTOK"' in text
    assert '"$LOGIN_TOKEN_API/$login_id"' in text
    _assert_no_norman_login_token_path(text)


def _run_delete_known_login(
    tmp_path: pathlib.Path,
    delete_status: str,
    revoked_bearer_status: str,
    *,
    login_id: str = "login-1",
    expected_log: str = "",
) -> dict[str, int]:
    text = (ROOT / "scripts" / "rancher_provision.sh").read_text()
    deletion = text[
        text.index("delete_known_login()") : text.index(
            "wait_for_ext_token_api()"
        )
    ]
    delete_status_path = tmp_path / "delete-status"
    revoked_bearer_status_path = tmp_path / "revoked-bearer-status"
    calls_path = tmp_path / "calls"
    sleeps_path = tmp_path / "sleeps"
    logs_path = tmp_path / "logs"
    harness_path = tmp_path / "delete-known-login.sh"
    delete_status_path.write_text(delete_status)
    revoked_bearer_status_path.write_text(revoked_bearer_status)

    harness_path.write_text(f"""#!/usr/bin/env sh
RANCHER=https://rancher.invalid
RANCHER_ID_PATTERN='^[A-Za-z0-9][A-Za-z0-9._-]{{0,253}}$'
LOGIN_TOKEN_API="$RANCHER/k8s/clusters/local/apis/management.cattle.io/v3/tokens"
EXT_TOKEN_API="$RANCHER/apis/ext.cattle.io/v1/tokens"
EXT_TOKEN_LIMIT="100"
DELETE_STATUS_PATH={shlex.quote(str(delete_status_path))}
REVOKED_BEARER_STATUS_PATH={shlex.quote(str(revoked_bearer_status_path))}
CALLS_PATH={shlex.quote(str(calls_path))}
SLEEPS_PATH={shlex.quote(str(sleeps_path))}
LOGS_PATH={shlex.quote(str(logs_path))}
EXPECTED_LOG={shlex.quote(expected_log)}
EXPECTED_LOGIN_ID={shlex.quote(login_id)}

count_lines() {{
  if [ -f "$1" ]; then
    wc -l < "$1"
  else
    printf '0\n'
  fi
}}

count_calls() {{
  if [ -f "$CALLS_PATH" ]; then
    grep -c "^$1$" "$CALLS_PATH" || true
  else
    printf '0\n'
  fi
}}

cr() {{
  if [ "$#" -eq 9 ] \
    && [ "$1" = "-o" ] \
    && [ "$2" = "/dev/null" ] \
    && [ "$3" = "-w" ] \
    && [ "$4" = "%{{http_code}}" ] \
    && [ "$5" = "-X" ] \
    && [ "$6" = "DELETE" ] \
    && [ "$7" = "$LOGIN_TOKEN_API/$EXPECTED_LOGIN_ID" ] \
    && [ "$8" = "-H" ] \
    && [ "$9" = "Authorization: Bearer admin-token" ]; then
    status=$(cat "$DELETE_STATUS_PATH")
    printf 'delete\n' >> "$CALLS_PATH"
  elif [ "$#" -eq 10 ] \
    && [ "$1" = "-o" ] \
    && [ "$2" = "/dev/null" ] \
    && [ "$3" = "-w" ] \
    && [ "$4" = "%{{http_code}}" ] \
    && [ "$5" = "-G" ] \
    && [ "$6" = "$EXT_TOKEN_API" ] \
    && [ "$7" = "-H" ] \
    && [ "$8" = "Authorization: Bearer login-token" ] \
    && [ "$9" = "--data-urlencode" ] \
    && [ "${{10}}" = "limit=$EXT_TOKEN_LIMIT" ]; then
    status=$(cat "$REVOKED_BEARER_STATUS_PATH")
    printf 'list\n' >> "$CALLS_PATH"
  else
    return 1
  fi
  case "$status" in
    transport) return 1 ;;
    empty) return 0 ;;
    *) printf '%s' "$status" ;;
  esac
}}

sleep() {{ printf 'sleep\n' >> "$SLEEPS_PATH"; }}

log() {{
  [ "$#" -eq 1 ] && [ "$1" = "$EXPECTED_LOG" ] || exit 97
  printf 'log\n' >> "$LOGS_PATH"
}}

{deletion}

delete_known_login admin-token {shlex.quote(login_id)} login-token
result=$?
printf 'result=%s\n' "$result"
printf 'delete_calls=%s\n' "$(count_calls delete)"
printf 'list_calls=%s\n' "$(count_calls list)"
printf 'sleeps=%s\n' "$(count_lines "$SLEEPS_PATH")"
printf 'logs=%s\n' "$(count_lines "$LOGS_PATH")"
""")
    result = subprocess.run(
        ["sh", str(harness_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return {
        key: int(value)
        for key, value in (
            line.split("=", maxsplit=1) for line in result.stdout.splitlines()
        )
    }


def test_local_provisioner_accepts_exact_delete_then_revoked_bearer_401(
    tmp_path: pathlib.Path,
):
    outcome = _run_delete_known_login(tmp_path, "200", "401")

    assert outcome == {
        "result": 0,
        "delete_calls": 1,
        "list_calls": 1,
        "sleeps": 0,
        "logs": 0,
    }


def test_local_provisioner_fails_safely_for_404_login_delete(
    tmp_path: pathlib.Path,
):
    outcome = _run_delete_known_login(
        tmp_path, "404", "401", expected_log="login token deletion failed"
    )

    assert outcome == {
        "result": 1,
        "delete_calls": 1,
        "list_calls": 0,
        "sleeps": 0,
        "logs": 1,
    }


def test_local_provisioner_fails_safely_for_204_login_delete(
    tmp_path: pathlib.Path,
):
    outcome = _run_delete_known_login(
        tmp_path, "204", "401", expected_log="login token deletion failed"
    )

    assert outcome == {
        "result": 1,
        "delete_calls": 1,
        "list_calls": 0,
        "sleeps": 0,
        "logs": 1,
    }


def test_local_provisioner_fails_safely_for_500_login_delete(
    tmp_path: pathlib.Path,
):
    outcome = _run_delete_known_login(
        tmp_path, "500", "401", expected_log="login token deletion failed"
    )

    assert outcome == {
        "result": 1,
        "delete_calls": 1,
        "list_calls": 0,
        "sleeps": 0,
        "logs": 1,
    }


def test_local_provisioner_fails_safely_when_deleted_bearer_remains_authorized(
    tmp_path: pathlib.Path,
):
    outcome = _run_delete_known_login(
        tmp_path,
        "200",
        "200",
        expected_log="login token revocation verification failed",
    )

    assert outcome == {
        "result": 1,
        "delete_calls": 1,
        "list_calls": 1,
        "sleeps": 0,
        "logs": 1,
    }


def test_local_provisioner_fails_safely_for_transport_login_delete_failure(
    tmp_path: pathlib.Path,
):
    outcome = _run_delete_known_login(
        tmp_path,
        "transport",
        "401",
        expected_log="login token deletion failed",
    )

    assert outcome == {
        "result": 1,
        "delete_calls": 1,
        "list_calls": 0,
        "sleeps": 0,
        "logs": 1,
    }


def test_local_provisioner_rejects_invalid_login_id_without_http_call(
    tmp_path: pathlib.Path,
):
    outcome = _run_delete_known_login(
        tmp_path,
        "200",
        "401",
        login_id="invalid/login-id",
        expected_log="login token id validation failed",
    )

    assert outcome == {
        "result": 1,
        "delete_calls": 0,
        "list_calls": 0,
        "sleeps": 0,
        "logs": 1,
    }


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

    assert text.index(
        'delete_ext_tokens_except "$LTOK" "$USER_ID"'
    ) < text.index("VALIDATOR_LOGIN_RESPONSE=")
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
