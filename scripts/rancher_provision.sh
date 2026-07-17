#!/usr/bin/env sh
# g004 hermetic UAT - automated Rancher provisioning (UNCOMMITTED dev tooling).
#
# Runs ONCE in the `uat-init` container of docker-compose.uat.yml. It brings a
# freshly-booted containerised Rancher from zero to "a labelled, active,
# disposable downstream cluster the validator can score" with no manual steps:
#
#   1. wait for Rancher, log in with the hardcoded dev bootstrap password
#   2. mint a validator API token via /v3  -> /shared/rancher-token
#   3. read the Rancher CA via /v3         -> /shared/rancher-ca.crt
#   4. create an imported cluster, fetch its registration manifest
#   5. apply the manifest into the rancher/k3s `miner-cluster` downstream
#   6. wait for the downstream to go active, then label it with bob's hotkey
#      (via the /k8s/clusters/local proxy PATCH - the API form of `kubectl label`)
#
# The minted token is ephemeral (regenerated every `up`); it is written to a
# shared volume and never printed. All operations were proven end-to-end
# against rancher/rancher:v2.14.2 + rancher/k3s:v1.35.5-k3s1 on 2026-07-16.
set -eu

RANCHER="${RANCHER_URL:-https://rancher}"
BOOT="${BOOTSTRAP_PASSWORD:?bootstrap password required}"
MINER_HOTKEY="${MINER_HOTKEY:?bob hotkey ss58 required}"
CLUSTER_NAME="${CLUSTER_NAME:-kubetee-uat}"
SHARED="${SHARED_DIR:-/shared}"
K3S_KUBECONFIG="${K3S_KUBECONFIG:-/k3s-out/kubeconfig.yaml}"

log() { echo "[uat-init $(date -u +%H:%M:%SZ)] $*"; }
cr()  { curl -sk --max-time 25 "$@"; }

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
LTOK=$(cr -X POST "$RANCHER/v3-public/localProviders/local?action=login" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"admin\",\"password\":\"$BOOT\"}" | jq -r .token)
[ -n "$LTOK" ] && [ "$LTOK" != "null" ] || { log "login failed"; exit 1; }

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

# 2a. custom global role: clusters get/list/watch/delete, nodes get/list/watch
ROLE_ID=$(cr "$RANCHER/v3/globalroles?name=$VAL_ROLE_NAME" -H "Authorization: Bearer $LTOK" \
           | jq -r '.data[0].id // empty')
if [ -z "$ROLE_ID" ]; then
  ROLE_ID=$(cr -X POST "$RANCHER/v3/globalrole" -H "Authorization: Bearer $LTOK" \
             -H 'Content-Type: application/json' -d "{
    \"type\": \"globalRole\",
    \"name\": \"$VAL_ROLE_NAME\",
    \"description\": \"KubeTEE validator: cluster read + guarded delete, node read\",
    \"rules\": [
      {\"apiGroups\": [\"management.cattle.io\"], \"resources\": [\"clusters\"],
       \"verbs\": [\"get\", \"list\", \"watch\", \"delete\"]},
      {\"apiGroups\": [\"management.cattle.io\"], \"resources\": [\"nodes\"],
       \"verbs\": [\"get\", \"list\", \"watch\"]}
    ]}" | jq -r .id)
fi
[ -n "$ROLE_ID" ] && [ "$ROLE_ID" != "null" ] || { log "global role create failed"; exit 1; }
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

# 2c. bindings: login basics (user-base) + the scoped role (idempotent)
EXISTING_BINDS=$(cr "$RANCHER/v3/globalrolebindings?userId=$USER_ID" \
                  -H "Authorization: Bearer $LTOK" | jq -r '[.data[].globalRoleId] | join(",")')
for ROLE in "user-base" "$ROLE_ID"; do
  case ",$EXISTING_BINDS," in *",$ROLE,"*) continue;; esac
  cr -X POST "$RANCHER/v3/globalrolebinding" -H "Authorization: Bearer $LTOK" \
     -H 'Content-Type: application/json' \
     -d "{\"type\":\"globalRoleBinding\",\"globalRoleId\":\"$ROLE\",\"userId\":\"$USER_ID\"}" >/dev/null
done
log "bindings ensured (user-base + $VAL_ROLE_NAME)"

# 2d. log in AS the scoped user and mint the validator token from that session
VLTOK=$(cr -X POST "$RANCHER/v3-public/localProviders/local?action=login" \
         -H 'Content-Type: application/json' \
         -d "{\"username\":\"$VAL_USERNAME\",\"password\":\"$VAL_PASSWORD\"}" | jq -r .token)
[ -n "$VLTOK" ] && [ "$VLTOK" != "null" ] || { log "validator login failed"; exit 1; }
BEARER=$(cr -X POST "$RANCHER/v3/token" -H "Authorization: Bearer $VLTOK" \
          -H 'Content-Type: application/json' \
          -d '{"type":"token","description":"kubetee-validator-scoring","ttl":0}' | jq -r .token)
[ -n "$BEARER" ] && [ "$BEARER" != "null" ] || { log "token mint failed"; exit 1; }
( umask 077; printf '%s' "$BEARER" > "$SHARED/rancher-token" )   # never echoed
log "minted SCOPED validator API token -> $SHARED/rancher-token"

# --- 3. CA -> shared ---------------------------------------------------------
cr "$RANCHER/v3/settings/cacerts" -H "Authorization: Bearer $LTOK" | jq -r .value > "$SHARED/rancher-ca.crt"
log "wrote Rancher CA ($(wc -c < "$SHARED/rancher-ca.crt") bytes)"

# --- 4. imported cluster (delete stale by name, import fresh) + manifest ------
# The downstream is ephemeral, so any cluster of this name left in a persisted
# Rancher (after `down` without -v) is stale - remove it and import clean.
for old in $(cr "$RANCHER/v3/clusters?name=$CLUSTER_NAME" -H "Authorization: Bearer $LTOK" | jq -r '.data[].id // empty'); do
  log "removing stale cluster $old"
  cr -X DELETE "$RANCHER/v3/clusters/$old" -H "Authorization: Bearer $LTOK" >/dev/null || true
done
CID=$(cr -X POST "$RANCHER/v3/cluster" -H "Authorization: Bearer $LTOK" \
       -H 'Content-Type: application/json' \
       -d "{\"type\":\"cluster\",\"name\":\"$CLUSTER_NAME\",\"import\":true}" | jq -r .id)
[ -n "$CID" ] && [ "$CID" != "null" ] || { log "cluster create failed"; exit 1; }
log "import cluster id=$CID"
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
log "registration manifest: $MURL"

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

# --- 6. wait active, then label via /k8s proxy PATCH -------------------------
for _ in $(seq 1 60); do
  ST=$(cr "$RANCHER/v3/clusters/$CID" -H "Authorization: Bearer $LTOK" | jq -r .state)
  N=$(cr "$RANCHER/v3/nodes?clusterId=$CID" -H "Authorization: Bearer $LTOK" | jq -r '.data | length')
  log "downstream state=$ST nodes=$N"
  [ "$ST" = "active" ] && [ "$N" -ge 1 ] && break
  sleep 6
done
cr -X PATCH "$RANCHER/k8s/clusters/local/apis/management.cattle.io/v3/clusters/$CID" \
   -H "Authorization: Bearer $LTOK" -H 'Content-Type: application/merge-patch+json' \
   -d "{\"metadata\":{\"labels\":{\"kubetee.ai/miner-hotkey\":\"$MINER_HOTKEY\"}}}" >/dev/null
log "labelled $CID with kubetee.ai/miner-hotkey=<bob>"

echo "$CID" > "$SHARED/cluster-id"
touch "$SHARED/ready"
log "PROVISIONING COMPLETE (cluster=$CID)"
