#!/usr/bin/env sh
# g004 hermetic UAT - automated Rancher provisioning (UNCOMMITTED dev tooling).
#
# Runs ONCE in the `uat-init` container of docker-compose.uat.yml. It brings a
# freshly-booted containerised Rancher from zero to "a labelled, active,
# disposable downstream cluster the validator can score" with no manual steps:
#
#   1. wait for Rancher, log in with the hardcoded dev bootstrap password
#   2. mint a least-privilege validator token -> /shared/rancher-token;
#      mint a distinct short-lived platform token only for a scoped contract
#      check, then revoke it before declaring readiness
#   3. read the Rancher CA via /v3         -> /shared/rancher-ca.crt
#   4. create an imported cluster, fetch its registration manifest
#   5. apply the manifest into the rancher/k3s `miner-cluster` downstream
#   6. wait for the downstream to go active, then apply a synthetic canonical
#      ENROLLED binding for bob via the /k8s/clusters/local proxy PATCH
#
# The minted token is ephemeral (regenerated every `up`); it is written to a
# shared volume and never printed. Local UAT parity is pinned to the
# staging-verified rancher/rancher:v2.14.3 + rancher/k3s:v1.35.5-k3s1 pair.
set -eu

RANCHER="${RANCHER_URL:-https://rancher}"
BOOT="${BOOTSTRAP_PASSWORD:?bootstrap password required}"
MINER_HOTKEY="${MINER_HOTKEY:?bob hotkey ss58 required}"
MINER_COLDKEY="${MINER_COLDKEY:?bob coldkey ss58 required}"
MINER_UID="${MINER_UID:?bob enrollment uid required}"
MINER_NETUID="${MINER_NETUID:?subnet netuid required}"
MINER_NETWORK="${MINER_NETWORK:?chain network required}"
CLUSTER_NAME="${CLUSTER_NAME:-kubetee-uat}"
SHARED="${SHARED_DIR:-/shared}"
K3S_KUBECONFIG="${K3S_KUBECONFIG:-/k3s-out/kubeconfig.yaml}"
EXT_TOKEN_API="$RANCHER/apis/ext.cattle.io/v1/tokens"
EXT_TOKEN_LIMIT="100"
EXT_TOKEN_USER_LABEL="cattle.io/user-id"
VALIDATOR_TOKEN_TTL_MS="3600000"
PLATFORM_TOKEN_TTL_MS="300000"
RANCHER_ID_PATTERN='^[A-Za-z0-9][A-Za-z0-9._-]{0,253}$'

log() { echo "[uat-init $(date -u +%H:%M:%SZ)] $*"; }
cr()  { curl -sk --max-time 25 "$@"; }

validate_login_document() {
  jq -e --arg pattern "$RANCHER_ID_PATTERN" '
    (.id | type == "string" and test($pattern))
    and (.token | type == "string" and length > 0)
  ' >/dev/null
}

login_to_rancher() {
  for _ in $(seq 1 120); do
    login_document=$(cr -f -X POST \
      "$RANCHER/v3-public/localProviders/local?action=login" \
      -H 'Content-Type: application/json' \
      -d "{\"username\":\"admin\",\"password\":\"$BOOT\"}" \
      2>/dev/null || true)
    if printf '%s' "$login_document" | validate_login_document; then
      printf '%s' "$login_document"
      return 0
    fi
    sleep 3
  done
  log "Rancher local login did not become ready"
  return 1
}

validate_ext_token_list() {
  user_id=$1
  jq -e --arg user "$user_id" --arg limit "$EXT_TOKEN_LIMIT" \
    --arg pattern "$RANCHER_ID_PATTERN" '
    .apiVersion == "ext.cattle.io/v1"
    and .kind == "TokenList"
    and (.metadata | type == "object")
    and (.metadata.resourceVersion | type == "string" and length > 0)
    and ((.metadata.continue // "") == "")
    and (.items | type == "array" and length <= ($limit | tonumber))
    and all(.items[];
      .apiVersion == "ext.cattle.io/v1"
      and .kind == "Token"
      and (.metadata.name | type == "string" and test($pattern))
      and .spec.userID == $user
      and ((.status.bearerToken // "") == "")
      and ((.status.value // "") == ""))
  ' >/dev/null
}

list_ext_tokens() {
  auth_token=$1
  user_id=$2
  cr -fG "$EXT_TOKEN_API" \
    -H "Authorization: Bearer $auth_token" \
    --data-urlencode "limit=$EXT_TOKEN_LIMIT" \
    --data-urlencode "labelSelector=$EXT_TOKEN_USER_LABEL=$user_id"
}

delete_ext_tokens_except() {
  auth_token=$1
  user_id=$2
  keep_id=${3:-}
  ext_list=$(list_ext_tokens "$auth_token" "$user_id")
  printf '%s' "$ext_list" | validate_ext_token_list "$user_id" \
    || { log "extension token list validation failed"; return 1; }
  for ext_token_id in $(printf '%s' "$ext_list" | jq -r '.items[].metadata.name'); do
    if [ -n "$keep_id" ] && [ "$ext_token_id" = "$keep_id" ]; then
      continue
    fi
    cr -f -X DELETE "$EXT_TOKEN_API/$ext_token_id" \
      -H "Authorization: Bearer $auth_token" >/dev/null
  done
}

assert_ext_tokens_exact() {
  auth_token=$1
  user_id=$2
  keep_id=${3:-}
  description=${4:-}
  ttl_ms=${5:-0}
  ext_list=$(list_ext_tokens "$auth_token" "$user_id")
  printf '%s' "$ext_list" | validate_ext_token_list "$user_id" \
    || { log "extension token audit validation failed"; return 1; }
  if [ -z "$keep_id" ]; then
    printf '%s' "$ext_list" | jq -e '.items | length == 0' >/dev/null
    return
  fi
  printf '%s' "$ext_list" | jq -e --arg keep "$keep_id" \
    --arg description "$description" --argjson ttl "$ttl_ms" '
    .items | length == 1
    and .[0].metadata.name == $keep
    and .[0].spec.description == $description
    and .[0].spec.ttl == $ttl
  ' >/dev/null
}

mint_ext_token() {
  owner_token=$1
  description=$2
  ttl_ms=$3
  create_body=$(jq -nc --arg description "$description" \
    --argjson ttl "$ttl_ms" '{
      apiVersion: "ext.cattle.io/v1",
      kind: "Token",
      spec: {
        description: $description,
        ttl: $ttl
      }
    }')
  cr -f -X POST "$EXT_TOKEN_API" \
    -H "Authorization: Bearer $owner_token" \
    -H 'Content-Type: application/json' -d "$create_body"
}

validate_ext_token_create() {
  user_id=$1
  description=$2
  ttl_ms=$3
  jq -e --arg user "$user_id" --arg description "$description" \
    --argjson ttl "$ttl_ms" --arg pattern "$RANCHER_ID_PATTERN" '
    .metadata.name as $name
    | .apiVersion == "ext.cattle.io/v1"
      and .kind == "Token"
      and ($name | type == "string" and test($pattern))
      and (.metadata.resourceVersion | type == "string" and length > 0)
      and .spec.userID == $user
      and .spec.userPrincipal.name == ("local://" + $user)
      and .spec.description == $description
      and .spec.ttl == $ttl
      and (.status.value | type == "string" and length > 0)
      and (.status.value as $value
        | .status.bearerToken == ("ext/" + $name + ":" + $value))
  ' >/dev/null
}

delete_known_login() {
  admin_token=$1
  login_id=$2
  printf '%s' "$login_id" | jq -eR --arg pattern "$RANCHER_ID_PATTERN" \
    'test($pattern)' >/dev/null \
    || { log "login token id validation failed"; return 1; }
  for attempt in $(seq 1 20); do
    status=$(cr -o /dev/null -w '%{http_code}' -X DELETE \
      "$RANCHER/v3/tokens/$login_id" \
      -H "Authorization: Bearer $admin_token" || true)
    case "$status" in
      200|204) return 0 ;;
      404) if [ "$attempt" -lt 20 ]; then sleep 1; fi ;;
      *) log "login token deletion failed"; return 1 ;;
    esac
  done
  log "login token deletion did not become ready"
  return 1
}

wait_for_ext_token_api() {
  for _ in $(seq 1 120); do
    readiness_document=$(cr -fG "$EXT_TOKEN_API" \
      -H "Authorization: Bearer $LTOK" \
      --data-urlencode "limit=1" 2>/dev/null || true)
    if printf '%s' "$readiness_document" | jq -e '
      .apiVersion == "ext.cattle.io/v1"
      and .kind == "TokenList"
      and (.metadata.resourceVersion | type == "string" and length > 0)
      and (.items | type == "array" and length <= 1)
    ' >/dev/null 2>&1; then
      return 0
    fi
    sleep 3
  done
  log "Rancher extension token API did not become ready"
  return 1
}

# --- tools (alpine base) -----------------------------------------------------
command -v jq >/dev/null 2>&1 || apk add --no-cache curl jq bind-tools >/dev/null
if ! command -v kubectl >/dev/null 2>&1; then
  KV=v1.31.0
  curl -sSL -o /usr/local/bin/kubectl "https://dl.k8s.io/release/${KV}/bin/linux/amd64/kubectl"
  chmod +x /usr/local/bin/kubectl
fi

# The shared volume may persist across `up` (fast-reboot mode); clear the
# readiness marker so the validator waits for THIS run's provisioning.
rm -f "$SHARED/ready"

# --- 1. wait for Rancher, then log in ---------------------------------------
log "waiting for Rancher API at $RANCHER ..."
until [ "$(cr "$RANCHER/ping" 2>/dev/null)" = "pong" ]; do sleep 3; done
log "Rancher up; logging in"
ADMIN_LOGIN_RESPONSE=$(login_to_rancher)
printf '%s' "$ADMIN_LOGIN_RESPONSE" | validate_login_document \
  || { log "admin login response malformed"; exit 1; }
ADMIN_LOGIN_TOKEN_ID=$(printf '%s' "$ADMIN_LOGIN_RESPONSE" | jq -r .id)
LTOK=$(printf '%s' "$ADMIN_LOGIN_RESPONSE" | jq -r .token)
unset ADMIN_LOGIN_RESPONSE
wait_for_ext_token_api

# --- 2. server-url + SCOPED validator identity + token -----------------------
# The validator must NOT hold admin: its designed authority is read (clusters,
# nodes) plus the single guarded reconciliation DELETE - nothing else. Create a
# dedicated user bound to a custom global role with exactly those verbs, and
# mint the validator's token for THAT user. Admin stays inside this container.
cr -X PUT "$RANCHER/v3/settings/server-url" -H "Authorization: Bearer $LTOK" \
   -H 'Content-Type: application/json' \
   -d "{\"name\":\"server-url\",\"value\":\"$RANCHER\"}" >/dev/null || true

VAL_USERNAME="kubetee-validator"
VAL_ROLE_NAME="kubetee-validator-scoring"

# 2a. custom global role: reconcile the complete authorization-bearing shape,
# including persisted Rancher volumes created by an older, broader script.
ROLE_SPEC=$(jq -nc --arg name "$VAL_ROLE_NAME" '{
  type: "globalRole",
  name: $name,
  description: "KubeTEE validator: cluster read + guarded delete, node read",
  builtin: false,
  newUserDefault: false,
  inheritedClusterRoles: [],
  inheritedFleetWorkspacePermissions: null,
  namespacedRules: {},
  rules: [
    {apiGroups: ["management.cattle.io"], resources: ["clusters"],
     verbs: ["get", "list", "delete"], resourceNames: [], nonResourceURLs: []},
    {apiGroups: ["management.cattle.io"], resources: ["nodes"],
     verbs: ["get", "list"], resourceNames: [], nonResourceURLs: []}
  ]
}')
ROLE_MATCHES=$(cr "$RANCHER/v3/globalroles?limit=-1&name=$VAL_ROLE_NAME" \
                 -H "Authorization: Bearer $LTOK")
ROLE_COUNT=$(printf '%s' "$ROLE_MATCHES" | jq '[.data[] | select(.name == $name)] | length' \
               --arg name "$VAL_ROLE_NAME")
[ "$ROLE_COUNT" -le 1 ] || { log "scoped global role is ambiguous"; exit 1; }
ROLE_ID=$(printf '%s' "$ROLE_MATCHES" | jq -r --arg name "$VAL_ROLE_NAME" \
            '.data[] | select(.name == $name) | .id' | head -1)
if [ -z "$ROLE_ID" ]; then
  ROLE_ID=$(cr -X POST "$RANCHER/v3/globalrole" -H "Authorization: Bearer $LTOK" \
             -H 'Content-Type: application/json' -d "$ROLE_SPEC" | jq -r .id)
else
  ROLE_SPEC=$(printf '%s' "$ROLE_SPEC" | jq -c --arg id "$ROLE_ID" '. + {id: $id}')
  cr -X PUT "$RANCHER/v3/globalroles/$ROLE_ID" \
     -H "Authorization: Bearer $LTOK" -H 'Content-Type: application/json' \
     -d "$ROLE_SPEC" >/dev/null
fi
[ -n "$ROLE_ID" ] && [ "$ROLE_ID" != "null" ] || { log "global role create failed"; exit 1; }
ROLE_ACTUAL=$(cr "$RANCHER/v3/globalroles/$ROLE_ID" -H "Authorization: Bearer $LTOK")
printf '%s' "$ROLE_ACTUAL" | jq -e --arg name "$VAL_ROLE_NAME" '
  def normalized_rules:
    [.[] | {
      apiGroups: (.apiGroups // []), resources: (.resources // []),
      verbs: (.verbs // []), resourceNames: (.resourceNames // []),
      nonResourceURLs: (.nonResourceURLs // [])
    }] | sort_by(.resources[0]);
  .name == $name
  and (.builtin // false) == false
  and (.newUserDefault // false) == false
  and (.inheritedClusterRoles // []) == []
  and (.inheritedFleetWorkspacePermissions // null) == null
  and (.namespacedRules // {}) == {}
  and ((.rules | normalized_rules) == ([
    {apiGroups: ["management.cattle.io"], resources: ["clusters"],
     verbs: ["get", "list", "delete"], resourceNames: [], nonResourceURLs: []},
    {apiGroups: ["management.cattle.io"], resources: ["nodes"],
     verbs: ["get", "list"], resourceNames: [], nonResourceURLs: []}
  ] | normalized_rules))' >/dev/null || { log "scoped global role verification failed"; exit 1; }
log "role rules verified exact"
log "scoped global role: $ROLE_ID"

# 2b. dedicated user with a per-`up` random password (never persisted/echoed)
VAL_PASSWORD=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
USER_ID=$(cr "$RANCHER/v3/users?username=$VAL_USERNAME" -H "Authorization: Bearer $LTOK" \
           | jq -r '.data[0].id // empty')
if [ -z "$USER_ID" ]; then
  USER_ID=$(cr -X POST "$RANCHER/v3/user" -H "Authorization: Bearer $LTOK" \
             -H 'Content-Type: application/json' \
             -d "{\"type\":\"user\",\"username\":\"$VAL_USERNAME\",
                  \"password\":\"$VAL_PASSWORD\",\"mustChangePassword\":false,
                  \"enabled\":true}" | jq -r .id)
else
  # persisted Rancher: rotate to this run's password so we can log in
  cr -X POST "$RANCHER/v3/users/$USER_ID?action=setpassword" \
     -H "Authorization: Bearer $LTOK" -H 'Content-Type: application/json' \
     -d "{\"newPassword\":\"$VAL_PASSWORD\"}" >/dev/null
fi
[ -n "$USER_ID" ] && [ "$USER_ID" != "null" ] || { log "user create failed"; exit 1; }
log "validator user: $USER_ID"

# 2c. bindings: reconcile exactly login basics (user-base) + the scoped role.
# Remove stale/extra roles and duplicate desired bindings before minting a token.
EXISTING_BINDS=$(cr "$RANCHER/v3/globalrolebindings?limit=-1&userId=$USER_ID" \
                  -H "Authorization: Bearer $LTOK")
for BIND_ID in $(printf '%s' "$EXISTING_BINDS" | jq -r \
                   --arg user "$USER_ID" --arg scoped "$ROLE_ID" '
  .data[]
  | select(.userId == $user)
  | select(.globalRoleId != "user-base" and .globalRoleId != $scoped)
  | .id // empty'); do
  cr -X DELETE "$RANCHER/v3/globalrolebindings/$BIND_ID" \
     -H "Authorization: Bearer $LTOK" >/dev/null
done
for ROLE in "user-base" "$ROLE_ID"; do
  KEEP_BIND=""
  for BIND_ID in $(printf '%s' "$EXISTING_BINDS" | jq -r \
                     --arg user "$USER_ID" --arg role "$ROLE" '
    .data[] | select(.userId == $user and .globalRoleId == $role) | .id // empty'); do
    if [ -z "$KEEP_BIND" ]; then
      KEEP_BIND="$BIND_ID"
    else
      cr -X DELETE "$RANCHER/v3/globalrolebindings/$BIND_ID" \
         -H "Authorization: Bearer $LTOK" >/dev/null
    fi
  done
  if [ -z "$KEEP_BIND" ]; then
    cr -X POST "$RANCHER/v3/globalrolebinding" -H "Authorization: Bearer $LTOK" \
       -H 'Content-Type: application/json' \
       -d "{\"type\":\"globalRoleBinding\",\"globalRoleId\":\"$ROLE\",\"userId\":\"$USER_ID\"}" >/dev/null
  fi
done
VERIFIED_BINDS=$(cr "$RANCHER/v3/globalrolebindings?limit=-1&userId=$USER_ID" \
                  -H "Authorization: Bearer $LTOK")
printf '%s' "$VERIFIED_BINDS" | jq -e --arg user "$USER_ID" --arg scoped "$ROLE_ID" '
  ([.data[] | select(.userId == $user) | .globalRoleId] | sort)
  == (["user-base", $scoped] | sort)' >/dev/null \
  || { log "validator role binding verification failed"; exit 1; }
log "bindings verified exact (user-base + $VAL_ROLE_NAME)"

# 2d. Revoke extension tokens from earlier disposable runs before logging in
# and minting this run's only long-lived validator credential.
delete_ext_tokens_except "$LTOK" "$USER_ID"
assert_ext_tokens_exact "$LTOK" "$USER_ID"
VALIDATOR_LOGIN_RESPONSE=$(cr -f -X POST \
  "$RANCHER/v3-public/localProviders/local?action=login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$VAL_USERNAME\",\"password\":\"$VAL_PASSWORD\"}")
printf '%s' "$VALIDATOR_LOGIN_RESPONSE" | validate_login_document \
  || { log "validator login failed"; exit 1; }
VALIDATOR_LOGIN_TOKEN_ID=$(printf '%s' "$VALIDATOR_LOGIN_RESPONSE" | jq -r .id)
VLTOK=$(printf '%s' "$VALIDATOR_LOGIN_RESPONSE" | jq -r .token)
unset VALIDATOR_LOGIN_RESPONSE
VALIDATOR_TOKEN_DESCRIPTION="kubetee-validator-scoring"
VALIDATOR_TOKEN_RESPONSE=$(mint_ext_token "$VLTOK" "$VALIDATOR_TOKEN_DESCRIPTION" "$VALIDATOR_TOKEN_TTL_MS")
printf '%s' "$VALIDATOR_TOKEN_RESPONSE" | validate_ext_token_create "$USER_ID" \
  "$VALIDATOR_TOKEN_DESCRIPTION" "$VALIDATOR_TOKEN_TTL_MS" \
  || { log "validator extension token mint failed"; exit 1; }
VALIDATOR_TOKEN_ID=$(printf '%s' "$VALIDATOR_TOKEN_RESPONSE" | jq -r .metadata.name)
BEARER=$(printf '%s' "$VALIDATOR_TOKEN_RESPONSE" | jq -r .status.bearerToken)
unset VALIDATOR_TOKEN_RESPONSE VLTOK
delete_known_login "$LTOK" "$VALIDATOR_LOGIN_TOKEN_ID"
delete_ext_tokens_except "$LTOK" "$USER_ID" "$VALIDATOR_TOKEN_ID"
assert_ext_tokens_exact "$LTOK" "$USER_ID" "$VALIDATOR_TOKEN_ID" \
  "$VALIDATOR_TOKEN_DESCRIPTION" "$VALIDATOR_TOKEN_TTL_MS" \
  || { log "validator extension token post-mint audit failed"; exit 1; }
( umask 077; printf '%s' "$BEARER" > "$SHARED/rancher-token" )   # never echoed
log "minted SCOPED validator API token -> $SHARED/rancher-token"

# 2e. The platform binding store is a different trust domain. It needs
# get/list/PATCH on management.cattle.io Cluster objects for resourceVersion-
# guarded label updates, but no node reads and no DELETE. Never reuse or widen
# the validator identity for this writer.
PLATFORM_USERNAME="kubetee-platform"
PLATFORM_ROLE_NAME="kubetee-platform-binding-store"

PLATFORM_ROLE_SPEC=$(jq -nc --arg name "$PLATFORM_ROLE_NAME" '{
  type: "globalRole",
  name: $name,
  description: "KubeTEE platform: resourceVersion-guarded cluster binding store",
  builtin: false,
  newUserDefault: false,
  inheritedClusterRoles: [],
  inheritedFleetWorkspacePermissions: null,
  namespacedRules: {},
  rules: [
    {apiGroups: ["management.cattle.io"], resources: ["clusters"],
     verbs: ["get", "list", "patch"], resourceNames: [], nonResourceURLs: []}
  ]
}')
PLATFORM_ROLE_MATCHES=$(cr "$RANCHER/v3/globalroles?limit=-1&name=$PLATFORM_ROLE_NAME" \
                          -H "Authorization: Bearer $LTOK")
PLATFORM_ROLE_COUNT=$(printf '%s' "$PLATFORM_ROLE_MATCHES" | jq \
  '[.data[] | select(.name == $name)] | length' --arg name "$PLATFORM_ROLE_NAME")
[ "$PLATFORM_ROLE_COUNT" -le 1 ] || { log "platform global role is ambiguous"; exit 1; }
PLATFORM_ROLE_ID=$(printf '%s' "$PLATFORM_ROLE_MATCHES" | jq -r \
  --arg name "$PLATFORM_ROLE_NAME" \
  '.data[] | select(.name == $name) | .id' | head -1)
if [ -z "$PLATFORM_ROLE_ID" ]; then
  PLATFORM_ROLE_ID=$(cr -X POST "$RANCHER/v3/globalrole" \
    -H "Authorization: Bearer $LTOK" -H 'Content-Type: application/json' \
    -d "$PLATFORM_ROLE_SPEC" | jq -r .id)
else
  PLATFORM_ROLE_SPEC=$(printf '%s' "$PLATFORM_ROLE_SPEC" | jq -c \
    --arg id "$PLATFORM_ROLE_ID" '. + {id: $id}')
  cr -X PUT "$RANCHER/v3/globalroles/$PLATFORM_ROLE_ID" \
     -H "Authorization: Bearer $LTOK" -H 'Content-Type: application/json' \
     -d "$PLATFORM_ROLE_SPEC" >/dev/null
fi
[ -n "$PLATFORM_ROLE_ID" ] && [ "$PLATFORM_ROLE_ID" != "null" ] \
  || { log "platform global role create failed"; exit 1; }
PLATFORM_ROLE_ACTUAL=$(cr "$RANCHER/v3/globalroles/$PLATFORM_ROLE_ID" \
                         -H "Authorization: Bearer $LTOK")
printf '%s' "$PLATFORM_ROLE_ACTUAL" | jq -e --arg name "$PLATFORM_ROLE_NAME" '
  def normalized_rules:
    [.[] | {
      apiGroups: (.apiGroups // []), resources: (.resources // []),
      verbs: (.verbs // []), resourceNames: (.resourceNames // []),
      nonResourceURLs: (.nonResourceURLs // [])
    }] | sort_by(.resources[0]);
  .name == $name
  and (.builtin // false) == false
  and (.newUserDefault // false) == false
  and (.inheritedClusterRoles // []) == []
  and (.inheritedFleetWorkspacePermissions // null) == null
  and (.namespacedRules // {}) == {}
  and ((.rules | normalized_rules) == ([
    {apiGroups: ["management.cattle.io"], resources: ["clusters"],
     verbs: ["get", "list", "patch"], resourceNames: [], nonResourceURLs: []}
  ] | normalized_rules))' >/dev/null \
  || { log "platform global role verification failed"; exit 1; }
log "platform role rules verified exact"

PLATFORM_PASSWORD=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
PLATFORM_USER_ID=$(cr "$RANCHER/v3/users?username=$PLATFORM_USERNAME" \
                     -H "Authorization: Bearer $LTOK" \
                   | jq -r '.data[0].id // empty')
if [ -z "$PLATFORM_USER_ID" ]; then
  PLATFORM_USER_ID=$(cr -X POST "$RANCHER/v3/user" \
    -H "Authorization: Bearer $LTOK" -H 'Content-Type: application/json' \
    -d "{\"type\":\"user\",\"username\":\"$PLATFORM_USERNAME\",
         \"password\":\"$PLATFORM_PASSWORD\",\"mustChangePassword\":false,
         \"enabled\":true}" | jq -r .id)
else
  cr -X POST "$RANCHER/v3/users/$PLATFORM_USER_ID?action=setpassword" \
     -H "Authorization: Bearer $LTOK" -H 'Content-Type: application/json' \
     -d "{\"newPassword\":\"$PLATFORM_PASSWORD\"}" >/dev/null
fi
[ -n "$PLATFORM_USER_ID" ] && [ "$PLATFORM_USER_ID" != "null" ] \
  || { log "platform user create failed"; exit 1; }

PLATFORM_EXISTING_BINDS=$(cr \
  "$RANCHER/v3/globalrolebindings?limit=-1&userId=$PLATFORM_USER_ID" \
  -H "Authorization: Bearer $LTOK")
for PLATFORM_BIND_ID in $(printf '%s' "$PLATFORM_EXISTING_BINDS" | jq -r \
  --arg user "$PLATFORM_USER_ID" --arg scoped "$PLATFORM_ROLE_ID" '
  .data[]
  | select(.userId == $user)
  | select(.globalRoleId != "user-base" and .globalRoleId != $scoped)
  | .id // empty'); do
  cr -X DELETE "$RANCHER/v3/globalrolebindings/$PLATFORM_BIND_ID" \
     -H "Authorization: Bearer $LTOK" >/dev/null
done
for PLATFORM_ROLE in "user-base" "$PLATFORM_ROLE_ID"; do
  PLATFORM_KEEP_BIND=""
  for PLATFORM_BIND_ID in $(printf '%s' "$PLATFORM_EXISTING_BINDS" | jq -r \
    --arg user "$PLATFORM_USER_ID" --arg role "$PLATFORM_ROLE" '
    .data[] | select(.userId == $user and .globalRoleId == $role) | .id // empty'); do
    if [ -z "$PLATFORM_KEEP_BIND" ]; then
      PLATFORM_KEEP_BIND="$PLATFORM_BIND_ID"
    else
      cr -X DELETE "$RANCHER/v3/globalrolebindings/$PLATFORM_BIND_ID" \
         -H "Authorization: Bearer $LTOK" >/dev/null
    fi
  done
  if [ -z "$PLATFORM_KEEP_BIND" ]; then
    cr -X POST "$RANCHER/v3/globalrolebinding" \
       -H "Authorization: Bearer $LTOK" -H 'Content-Type: application/json' \
       -d "{\"type\":\"globalRoleBinding\",\"globalRoleId\":\"$PLATFORM_ROLE\",\"userId\":\"$PLATFORM_USER_ID\"}" >/dev/null
  fi
done
PLATFORM_VERIFIED_BINDS=$(cr \
  "$RANCHER/v3/globalrolebindings?limit=-1&userId=$PLATFORM_USER_ID" \
  -H "Authorization: Bearer $LTOK")
printf '%s' "$PLATFORM_VERIFIED_BINDS" | jq -e \
  --arg user "$PLATFORM_USER_ID" --arg scoped "$PLATFORM_ROLE_ID" '
  ([.data[] | select(.userId == $user) | .globalRoleId] | sort)
  == (["user-base", $scoped] | sort)' >/dev/null \
  || { log "platform role binding verification failed"; exit 1; }
log "platform bindings verified exact (user-base + $PLATFORM_ROLE_NAME)"

# --- 3. CA -> shared ---------------------------------------------------------
cr "$RANCHER/v3/settings/cacerts" -H "Authorization: Bearer $LTOK" | jq -r .value > "$SHARED/rancher-ca.crt"
log "wrote Rancher CA ($(wc -c < "$SHARED/rancher-ca.crt") bytes)"

# --- 4. imported cluster (delete stale by name, import fresh) + manifest ------
# The downstream is ephemeral, so any cluster of this name left in a persisted
# Rancher (after `down` without -v) is stale - remove it and import clean.
for old in $(cr "$RANCHER/v3/clusters?name=$CLUSTER_NAME" -H "Authorization: Bearer $LTOK" | jq -r '.data[].id // empty'); do
  log "removing stale imported cluster"
  cr -X DELETE "$RANCHER/v3/clusters/$old" -H "Authorization: Bearer $LTOK" >/dev/null || true
done
CID=$(cr -X POST "$RANCHER/v3/cluster" -H "Authorization: Bearer $LTOK" \
       -H 'Content-Type: application/json' \
       -d "{\"type\":\"cluster\",\"name\":\"$CLUSTER_NAME\",\"import\":true}" | jq -r .id)
[ -n "$CID" ] && [ "$CID" != "null" ] || { log "cluster create failed"; exit 1; }
log "import cluster created"
cr -X POST "$RANCHER/v3/clusterregistrationtoken" -H "Authorization: Bearer $LTOK" \
   -H 'Content-Type: application/json' \
   -d "{\"type\":\"clusterRegistrationToken\",\"clusterId\":\"$CID\"}" >/dev/null || true
MURL=""
for _ in $(seq 1 20); do
  MURL=$(cr "$RANCHER/v3/clusterregistrationtoken?clusterId=$CID" -H "Authorization: Bearer $LTOK" \
          | jq -r '[.data[].manifestUrl // empty] | map(select(.!="")) | .[0] // empty')
  [ -n "$MURL" ] && break; sleep 3
done
[ -n "$MURL" ] || { log "no manifest url"; exit 1; }
log "registration manifest obtained"

# --- 5. apply manifest into the downstream miner-cluster ---------------------
until [ -f "$K3S_KUBECONFIG" ]; do log "waiting for miner-cluster kubeconfig ..."; sleep 3; done
sed -e 's#https://127.0.0.1:6443#https://miner-cluster:6443#' \
    -e 's#https://0.0.0.0:6443#https://miner-cluster:6443#' \
    "$K3S_KUBECONFIG" > /tmp/miner.kubeconfig
export KUBECONFIG=/tmp/miner.kubeconfig
until kubectl get --raw=/readyz >/dev/null 2>&1; do log "waiting for miner-cluster API ..."; sleep 3; done
cr "$MURL" | kubectl apply -f -
log "registration manifest applied into miner-cluster"

# The cattle-cluster-agent pod cannot resolve the compose service name `rancher`
# (Docker's embedded DNS 127.0.0.11 is unreachable from inside k3s pods). Inject
# a hostAlias mapping `rancher` -> the Rancher container IP so the agent (and TLS
# SAN, which is `rancher`) both resolve. The IP is stable within one `up`.
RANCHER_IP=$(dig +short rancher 2>/dev/null | head -1)
[ -n "$RANCHER_IP" ] || RANCHER_IP=$(getent hosts rancher 2>/dev/null | awk '{print $1}' | head -1)
until kubectl -n cattle-system get deploy cattle-cluster-agent >/dev/null 2>&1; do sleep 2; done
kubectl -n cattle-system patch deployment cattle-cluster-agent --type merge \
  -p "{\"spec\":{\"template\":{\"spec\":{\"hostAliases\":[{\"ip\":\"$RANCHER_IP\",\"hostnames\":[\"rancher\"]}]}}}}"
log "patched agent hostAlias rancher -> $RANCHER_IP"

# --- 6. wait active, then bind via /k8s proxy PATCH --------------------------
for _ in $(seq 1 60); do
  ST=$(cr "$RANCHER/v3/clusters/$CID" -H "Authorization: Bearer $LTOK" | jq -r .state)
  N=$(cr "$RANCHER/v3/nodes?clusterId=$CID" -H "Authorization: Bearer $LTOK" | jq -r '.data | length')
  log "downstream state=$ST nodes=$N"
  [ "$ST" = "active" ] && [ "$N" -ge 1 ] && break
  sleep 6
done
[ "$ST" = "active" ] && [ "$N" -ge 1 ] \
  || { log "downstream did not become active with a node"; exit 1; }
ORIGIN_FP=$(printf '%s' "local-rancher-binding:$CID" | sha256sum | awk '{print $1}')
ORIGIN_FP_PREFIX=${ORIGIN_FP%?}
KUBE_SYSTEM_UID=$(kubectl get namespace kube-system -o jsonpath='{.metadata.uid}')
[ -n "$KUBE_SYSTEM_UID" ] || { log "kube-system uid unavailable"; exit 1; }
SYNTHETIC_EVIDENCE=$(printf '%s' "local-rancher-evidence:$CID" | sha256sum | awk '{print $1}')
CREATED_AT_UNIX_MS="$(date +%s)000"
FINGERPRINT_ALIASES=$(jq -nc --arg fp "$ORIGIN_FP" --argjson at "$CREATED_AT_UNIX_MS" \
  '[{fingerprint: $fp, added_at_unix_ms: $at}]')
PATCH_BODY=$(jq -n \
  --arg hotkey "$MINER_HOTKEY" \
  --arg coldkey "$MINER_COLDKEY" \
  --arg uid "$MINER_UID" \
  --arg netuid "$MINER_NETUID" \
  --arg network "$MINER_NETWORK" \
  --arg prefix "$ORIGIN_FP_PREFIX" \
  --arg origin "$ORIGIN_FP" \
  --arg cluster_uid "$KUBE_SYSTEM_UID" \
  --arg evidence "$SYNTHETIC_EVIDENCE" \
  --arg created_at "$CREATED_AT_UNIX_MS" \
  --arg aliases "$FINGERPRINT_ALIASES" \
  '{
    metadata: {
      labels: {
        "kubetee.ai/binding-id": "local-bob-binding",
        "kubetee.ai/hotkey": $hotkey,
        "kubetee.ai/coldkey": $coldkey,
        "kubetee.ai/provider-id": "00000000-0000-4000-8000-000000000002",
        "kubetee.ai/binding-status": "ENROLLED",
        "kubetee.ai/generation": "1",
        "kubetee.ai/netuid": $netuid,
        "kubetee.ai/network": $network,
        "kubetee.ai/origin-fp-prefix": $prefix
      },
      annotations: {
        "kubetee.ai/origin-fingerprint": $origin,
        "kubetee.ai/cluster-id": $cluster_uid,
        "kubetee.ai/chain-genesis-hash": $evidence,
        "kubetee.ai/enrollment-uid": $uid,
        "kubetee.ai/metagraph-block-hash": $evidence,
        "kubetee.ai/observed-at-unix-ms": $created_at,
        "kubetee.ai/challenge-id": "local-synthetic-challenge",
        "kubetee.ai/challenge-sha256": $evidence,
        "kubetee.ai/hotkey-signature": $evidence,
        "kubetee.ai/signer-ss58": $hotkey,
        "kubetee.ai/session-public-key": $evidence,
        "kubetee.ai/provisioning-request-sha256": $evidence,
        "kubetee.ai/cluster-api-ca-sha256": $evidence,
        "kubetee.ai/kube-system-uid": $cluster_uid,
        "kubetee.ai/cluster-api-url": "https://miner-cluster:6443",
        "kubetee.ai/tls-server-name": "miner-cluster",
        "kubetee.ai/fleet-identity": "local-synthetic-fleet",
        "kubetee.ai/baseline-release-sha256": $evidence,
        "kubetee.ai/created-at-unix-ms": $created_at,
        "kubetee.ai/revocation-generation": "0",
        "kubetee.ai/cleanup-evidence": "",
        "kubetee.ai/audit-event-ids": "",
        "kubetee.ai/fingerprint-aliases": $aliases
      }
    }
  }')

# Mint the short-lived writer token only after the bounded downstream setup,
# immediately before its first use. The user and exact role were reconciled
# earlier, but no writer credential existed while registration was pending.
delete_ext_tokens_except "$LTOK" "$PLATFORM_USER_ID"
assert_ext_tokens_exact "$LTOK" "$PLATFORM_USER_ID"
PLATFORM_LOGIN_RESPONSE=$(cr -f -X POST \
  "$RANCHER/v3-public/localProviders/local?action=login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$PLATFORM_USERNAME\",\"password\":\"$PLATFORM_PASSWORD\"}")
printf '%s' "$PLATFORM_LOGIN_RESPONSE" | validate_login_document \
  || { log "platform login failed"; exit 1; }
PLATFORM_LOGIN_TOKEN_ID=$(printf '%s' "$PLATFORM_LOGIN_RESPONSE" | jq -r .id)
PLATFORM_LOGIN_TOKEN=$(printf '%s' "$PLATFORM_LOGIN_RESPONSE" | jq -r .token)
unset PLATFORM_LOGIN_RESPONSE
PLATFORM_TOKEN_DESCRIPTION="kubetee-platform-binding-store-contract"
PLATFORM_TOKEN_RESPONSE=$(mint_ext_token "$PLATFORM_LOGIN_TOKEN" "$PLATFORM_TOKEN_DESCRIPTION" "$PLATFORM_TOKEN_TTL_MS")
printf '%s' "$PLATFORM_TOKEN_RESPONSE" | validate_ext_token_create \
  "$PLATFORM_USER_ID" "$PLATFORM_TOKEN_DESCRIPTION" "$PLATFORM_TOKEN_TTL_MS" \
  || { log "platform extension token mint failed"; exit 1; }
PLATFORM_TOKEN_ID=$(printf '%s' "$PLATFORM_TOKEN_RESPONSE" | jq -r .metadata.name)
PLATFORM_BEARER=$(printf '%s' "$PLATFORM_TOKEN_RESPONSE" | jq -r .status.bearerToken)
unset PLATFORM_TOKEN_RESPONSE PLATFORM_LOGIN_TOKEN
delete_known_login "$LTOK" "$PLATFORM_LOGIN_TOKEN_ID"
delete_ext_tokens_except "$LTOK" "$PLATFORM_USER_ID" "$PLATFORM_TOKEN_ID"
assert_ext_tokens_exact "$LTOK" "$PLATFORM_USER_ID" "$PLATFORM_TOKEN_ID" \
  "$PLATFORM_TOKEN_DESCRIPTION" "$PLATFORM_TOKEN_TTL_MS" \
  || { log "platform extension token post-mint audit failed"; exit 1; }
[ "$PLATFORM_BEARER" != "$BEARER" ] \
  || { log "platform and validator credentials must be distinct"; exit 1; }
log "minted temporary SCOPED platform contract token"

# Exercise the distinct platform credential against the same API contract used
# by rancherbinding.HTTPClusterAPI. This scoped identity, not admin, applies the
# complete synthetic durable binding through resourceVersion-guarded JSON Patch.
PLATFORM_CLUSTER_API="$RANCHER/k8s/clusters/local/apis/management.cattle.io/v3/clusters"
PLATFORM_LIST_OK=false
for _ in $(seq 1 20); do
  if cr -f "$PLATFORM_CLUSTER_API?limit=1" \
       -H "Authorization: Bearer $PLATFORM_BEARER" \
       | jq -e --arg api "management.cattle.io/v3" '
           .apiVersion == $api
           and .kind == "ClusterList"
           and (.metadata.resourceVersion | type == "string" and length > 0)
           and (.items | type == "array")' >/dev/null; then
    PLATFORM_LIST_OK=true
    break
  fi
  sleep 2
done
[ "$PLATFORM_LIST_OK" = true ] \
  || { log "platform credential list contract failed"; exit 1; }

PLATFORM_CLUSTER=$(cr -f "$PLATFORM_CLUSTER_API/$CID" \
  -H "Authorization: Bearer $PLATFORM_BEARER")
PLATFORM_RESOURCE_VERSION=$(printf '%s' "$PLATFORM_CLUSTER" | jq -er \
  --arg cid "$CID" --arg api "management.cattle.io/v3" '
  select(.apiVersion == $api and .kind == "Cluster" and .metadata.name == $cid)
  | .metadata.resourceVersion
  | select(type == "string" and length > 0)')
PLATFORM_PATCH=$(printf '%s' "$PLATFORM_CLUSTER" | jq -c \
  --arg cid "$CID" --arg rv "$PLATFORM_RESOURCE_VERSION" \
  --argjson binding "$PATCH_BODY" '[
    {op: "test", path: "/metadata/name", value: $cid},
    {op: "test", path: "/metadata/resourceVersion", value: $rv},
    {op: "add", path: "/metadata/labels",
     value: ((.metadata.labels // {}) + $binding.metadata.labels)},
    {op: "add", path: "/metadata/annotations",
     value: ((.metadata.annotations // {}) + $binding.metadata.annotations)}
  ]')
cr -f -X PATCH "$PLATFORM_CLUSTER_API/$CID" \
  -H "Authorization: Bearer $PLATFORM_BEARER" \
  -H 'Content-Type: application/json-patch+json' \
  -d "$PLATFORM_PATCH" \
  | jq -e --arg cid "$CID" --arg api "management.cattle.io/v3" \
      --arg old_rv "$PLATFORM_RESOURCE_VERSION" \
      --argjson patch "$PLATFORM_PATCH" '
      .apiVersion == $api
        and .kind == "Cluster"
        and .metadata.name == $cid
        and (.metadata.resourceVersion
             | type == "string" and length > 0 and . != $old_rv)
        and (.metadata.labels == $patch[2].value)
        and (.metadata.annotations == $patch[3].value)' >/dev/null
log "applied complete canonical synthetic ENROLLED binding"
unset PLATFORM_CLUSTER PLATFORM_PATCH PLATFORM_RESOURCE_VERSION
log "platform credential runtime contract verified (get/list/patch)"

# The platform token exists only to prove this disposable contract. Revoke it
# before publishing the ready marker; no mutation credential is persisted.
delete_ext_tokens_except "$LTOK" "$PLATFORM_USER_ID"
assert_ext_tokens_exact "$LTOK" "$PLATFORM_USER_ID" \
  || { log "temporary platform extension token revocation failed"; exit 1; }
unset PLATFORM_BEARER PLATFORM_TOKEN_ID PLATFORM_LOGIN_TOKEN_ID
log "temporary platform credential revoked"

echo "$CID" > "$SHARED/cluster-id"
delete_known_login "$LTOK" "$ADMIN_LOGIN_TOKEN_ID"
unset LTOK ADMIN_LOGIN_TOKEN_ID
touch "$SHARED/ready"
log "PROVISIONING COMPLETE"
