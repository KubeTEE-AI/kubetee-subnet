# UAT Runbook — g004 Basic Miner-Node Validator

Executable runbook for the g004 integration UAT (spec
`docs/superpowers/specs/2026-07-16-basic-miner-node-validator.md` in the
monorepo; acceptance criteria AC9(a/b/c), AC11, AC12, AC13). Each demo lists
exact commands, expected assertions with tolerances, artifact capture, and
**named operator actions** (steps a human must perform — the validator has
no authority to do them).

**Safety banner — read before executing:**

- Demos run against the **self-contained docker compose stack**: the
  in-compose Rancher and its disposable `miner-cluster` downstream. External
  Rancher endpoints (staging or production) are **out of scope** for these
  demos. The only Rancher mutations here are the label actions in AC9(b)
  and — **only with explicit recorded operator approval** — the AC12
  disposable-cluster DELETE, all against the stack's own Rancher.
- **Production miner clusters are banned from every demo.** Never point the
  stack at an external Rancher for a UAT run.
- `.env` values (especially `RANCHER_BEARER_TOKEN`) must never appear in
  captured artifacts, issues, or commits. The validator redacts by design;
  still run the secret grep in §0.4 before publishing any artifact.

## 0. Environment setup

### 0.1 Prerequisites

- Merged stack: PR-1…PR-4 on `main` (or the stacked branches checked out).
- No `.env` needed: the stack is self-contained. `rancher-init` mints the
  validator's Rancher token, imports the disposable `miner-cluster`
  downstream, and labels it `kubetee.ai/miner-hotkey=<bob>` automatically
  on every `up`. Resolve the downstream's cluster id (used by the label
  commands below):

```bash
docker compose logs rancher-init | grep "import cluster"   # -> id=c-xxxxx
```

  Print bob's hotkey if needed:

```bash
docker compose exec validator python -c \
  "import bittensor as bt; print(bt.Wallet(name='bob', hotkey='default').hotkeypub.ss58_address)"
```

### 0.2 Artifact locations

All artifacts go under `logs/uat-g004/` (gitignored `logs/` directory;
attach redacted copies to the epic, never commit `.env` content):

```bash
mkdir -p logs/uat-g004
```

Per-demo capture pattern (`<demo>` = a9a, a9b, a9c, a11, a12, a13):

```bash
docker compose logs --no-color validator > logs/uat-g004/<demo>-validator.log
```

### 0.3 Start the stack

```bash
cd repos/subnet/kubetee-subnet
docker compose up -d --build
# Wait for phase 1 (setup) to finish and phase 2 (validator) to start:
docker compose logs -f validator | grep -m1 "basic validator started"
```

Resolve the actual netuid (the setup writes the one it owns):

```bash
NETUID=$(docker compose exec validator cat /app/.kubetee_netuid 2>/dev/null || echo 1); echo "$NETUID"
```

### 0.4 Secret scan (run before publishing ANY artifact)

```bash
# Must print nothing. If it prints, STOP: do not publish; file an incident.
grep -RniE "token-[a-z0-9]+:" logs/uat-g004/ || echo "CLEAN"
```

## 1. AC9(a) — healthy path: score 1, accepted weights, 0.10/0.90 split

**Preconditions:** stack up (§0.3); miner label on bob's hotkey (§0.1,
automatic); the `miner-cluster` downstream active with an active node.

**Commands:**

```bash
# 1. One full healthy cycle logged (score 1, chain acceptance):
docker compose logs validator | grep "set_weights accepted on chain" | tail -3

# 2. Metagraph snapshot (weights + hotkeys) - the POST-acceptance snapshot:
docker compose exec validator btcli subnets metagraph \
  --netuid "$NETUID" --network ws://chain:9944 \
  | tee logs/uat-g004/a9a-metagraph.txt

# 3. D13 hyperparameter check (report honestly):
docker compose exec validator btcli subnets hyperparameters \
  --netuid "$NETUID" --network ws://chain:9944 \
  | tee logs/uat-g004/a9a-hypers.txt
docker compose exec validator cat /app/.kubetee_owned
```

**Assertions:**

- Validator log line `set_weights accepted on chain: ... scoring=1 ...`
  with bob's hotkey scored `1` in the same line's `scores=` map.
- Metagraph weights from the validator UID: bob's UID weight `0.10 ± 0.01`
  and owner UID weight `0.90 ± 0.01` (u16 quantization + normalization
  tolerance). Record the raw values.
- **D13 proper-key check:** in the SAME metagraph snapshot, the owner
  UID's hotkey equals `KUBETEE_OWNER_HOTKEY`
  (`5FLbZav21bAsjH5SAdmJZwTP5C4b3bcaaWqC6GSmGmsbzUJ9`).
- **D13 hyperparameter check:** if `/app/.kubetee_owned` is `true` and the
  hyperparameter output exposes it, assert `recycle_or_burn == Recycle`
  (record queried name, chain response, image tag). On the pinned
  localnet image ownership is `false` (`SubtokenDisabled`, spec D1):
  record the check as **SKIPPED/LIMITED — D1 environment limitation**,
  citing the ownership-check log lines. This is the expected Early Access
  outcome; do not claim the hyperparameter was verified.

**Artifacts:** `a9a-validator.log`, `a9a-metagraph.txt`, `a9a-hypers.txt`.

## 2. AC9(b) — score 0: label removed, 100% owner weights

**Named operator action (Rancher, outside validator authority):** remove
the `kubetee.ai/miner-hotkey` label from the miner-cluster — one command
against the in-compose Rancher (any dev can run it):

```bash
docker compose exec rancher kubectl label \
  clusters.management.cattle.io <cluster-id> kubetee.ai/miner-hotkey-
```

Record the time and cluster id in the artifact notes.

**Commands (after ≥ 2 poll intervals, ~2–3 min):**

```bash
docker compose logs --since 5m validator | grep "set_weights accepted" | tail -3
docker compose exec validator btcli subnets metagraph \
  --netuid "$NETUID" --network ws://chain:9944 \
  | tee logs/uat-g004/a9b-metagraph.txt
```

**Assertions:**

- Log shows `scoring=0` and bob scored `0` in `scores=`; weights line has
  owner at `1.0` (bob explicit `0.0`).
- Metagraph shows owner UID weight `1.0 ± 0.01`, bob `0.0 + 0.01`.
- The process never exited (`docker compose ps validator` → `running`).

**Named operator action (restore):** re-add the label to the same cluster:

```bash
docker compose exec rancher kubectl label \
  clusters.management.cattle.io <cluster-id> \
  kubetee.ai/miner-hotkey=<bob hotkey SS58> --overwrite
```

**Restoration is verified** by a subsequent score-1 cycle: repeat the
AC9(a) log assertion and record it in `a9b-restore.log`.

**Artifacts:** `a9b-validator.log`, `a9b-metagraph.txt`, `a9b-restore.log`,
operator action notes (who/when/cluster id).

## 3. AC9(c) — runtime outage skip + startup refusal (D10/D14)

### 3.1 Runtime outage → skip (credentials present, endpoint unreachable)

Create the outage override (credentials stay set so startup succeeds —
never simulate an outage by unsetting credentials, that is the D14
startup path):

```bash
cat > docker-compose.uat-outage.yml <<'EOF'
services:
  validator:
    environment:
      - RANCHER_URL=https://127.0.0.1:9
EOF

docker compose -f docker-compose.yml -f docker-compose.uat-outage.yml up -d validator
docker compose logs -f validator | grep -m1 "cycle skipped set_weights"
```

**Assertions:**

- Log: `cycle skipped set_weights: reason=rancher_unavailable ...` each
  cycle; NO `set_weights accepted` lines during the outage window.
- Error metric incremented (from inside the compose network):

```bash
docker compose exec validator python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:9100/metrics').read().decode())" \
  | grep -E "kubetee_rancher_errors_total|kubetee_cycles_skipped_total" \
  | tee logs/uat-g004/a9c-metrics.txt
# assert kubetee_rancher_errors_total{category="transport"} >= 1
# assert kubetee_cycles_skipped_total{reason="rancher_unavailable"} >= 1
```

- Process stays up: `docker compose ps validator` → `running` (no
  restart-loop; container restart count unchanged).

Restore: `docker compose -f docker-compose.yml up -d validator` and assert
a subsequent `set_weights accepted` cycle.

### 3.2 Startup refusal (credentials unset → clear config error)

```bash
docker compose run --rm --no-deps \
  -e RANCHER_URL= -e RANCHER_BEARER_TOKEN= \
  validator python scripts/validator.py \
  2>&1 | tee logs/uat-g004/a9c-refusal.log; echo "exit=$?"
```

**Assertions:** output contains `refusing to start: invalid static
configuration` naming BOTH `RANCHER_URL` and `RANCHER_BEARER_TOKEN`; exit
code `2`; no loop started (no `basic validator started` line); no secret
value echoed.

**Artifacts:** `a9c-validator.log`, `a9c-metrics.txt`, `a9c-refusal.log`.

## 4. AC11 — metrics exposure (compose-internal, bounded labels)

```bash
# 4.1 Scrape from a container INSIDE the compose network (not the validator itself):
docker run --rm --network kubetee-subnet_default curlimages/curl -sf \
  http://validator:9100/metrics | tee logs/uat-g004/a11-scrape.txt | head -40

# 4.2 Assert the endpoint is NOT host-exposed:
docker compose port validator 9100 || echo "NOT-HOST-EXPOSED"
curl -sf --max-time 5 http://127.0.0.1:9100/metrics && echo "FAIL: host-exposed" || echo "OK: unreachable from host"
```

**Assertions:**

- Scrape succeeds inside the network and contains the required series:
  `kubetee_rancher_errors_total`, `kubetee_set_weights_total`,
  `kubetee_cycles_skipped_total`, `kubetee_consecutive_skips`,
  `kubetee_degraded_mode`, `kubetee_last_successful_scoring_timestamp`,
  `kubetee_miners_discovered`, `kubetee_miners_scoring`,
  `kubetee_reconciliation_deletions_total`,
  `kubetee_reconciliation_suppressed_total`,
  `kubetee_reconciliation_conflicts_total`.
- Every label value is a fixed enum (categories/reasons/results only — no
  URLs, ids, hotkeys, or free text); no secret material anywhere.
- `docker compose port validator 9100` prints nothing and the host curl
  fails (compose-internal only).

**Artifacts:** `a11-scrape.txt` + the two negative-probe outputs.

## 5. AC13 — degraded mode (≈ 11 minutes) and recovery

Uses the §3.1 unreachable-endpoint override (credentials present, D14) and
the pinned production parameters (`KUBETEE_MAX_CONSECUTIVE_SKIPS=10`,
`KUBETEE_POLL_SECONDS=60` — do NOT shrink them for the demo).

```bash
docker compose -f docker-compose.yml -f docker-compose.uat-outage.yml up -d validator
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee logs/uat-g004/a13-start.txt

# Wait >= 11 cycles (~11-12 min at 60s). Then:
docker compose logs --since 15m validator | grep -E "DEGRADED MODE|cycle skipped" \
  | tee logs/uat-g004/a13-log.txt | tail -5
docker compose exec validator python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:9100/metrics').read().decode())" \
  | grep -E "kubetee_degraded_mode|kubetee_consecutive_skips" \
  | tee logs/uat-g004/a13-metrics.txt
```

**Assertions:**

- After the 11th consecutive skip: critical log `DEGRADED MODE entered:
  11 consecutive skipped cycles exceeded KUBETEE_MAX_CONSECUTIVE_SKIPS=10`.
- `kubetee_degraded_mode 1.0` and `kubetee_consecutive_skips >= 11`.
- **No auto-zero:** no `set_weights` call happened during the outage (no
  new `set_weights accepted`/`rejected` lines); the last on-chain weights
  are unchanged (compare a metagraph snapshot against `a9a-metagraph.txt`).
- Process still `running`.

**Recovery:**

```bash
docker compose -f docker-compose.yml up -d validator
# After the next successful cycle:
docker compose exec validator python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:9100/metrics').read().decode())" \
  | grep kubetee_degraded_mode
# assert kubetee_degraded_mode 0.0
```

**Artifacts:** `a13-start.txt`, `a13-log.txt`, `a13-metrics.txt`,
recovery metric output.

## 6. AC12 — reconciliation demo (OPERATOR-APPROVAL-GATED, destructive)

**HARD GATES — all required before executing:**

1. **Explicit operator approval recorded in the epic**
   (KubeTEE-AI/kubetee-subnet#4) referencing this section.
2. The target is the stack's own disposable **`miner-cluster`** downstream
   (record its cluster id from `rancher-init`) — relabelled with a
   **throwaway test hotkey, never bob's**. External Rancher endpoints and
   production miner clusters are **banned** from this demo.
3. Wall-clock budget ≥ 15 minutes (the pinned
   `KUBETEE_RECONCILE_MIN_SECONDS=900` threshold — do not lower it).
4. The V1 capability matrix is **non-authoritative**: only this demo (or
   its honest limitation record) proves DELETE authorization.

If any gate is missing, **record the limitation path instead**: capture the
`unauthorized — operator action required` suppression (or the absence of a
disposable target) in the epic and stop — that is an accepted AC12 outcome.

**Steps:**

1. **Named operator action:** relabel the stack's `miner-cluster` to a
   throwaway test hotkey (e.g. a fresh `btcli wallet new_hotkey` address —
   record it):

```bash
docker compose exec rancher kubectl label \
  clusters.management.cattle.io <cluster-id> \
  kubetee.ai/miner-hotkey=<TEST hotkey SS58> --overwrite
```

   Do NOT register that hotkey on the localnet metagraph (absence from the
   metagraph is the trigger condition). If the test hotkey was ever
   registered, deregister it first, or record honestly that absence was
   simulated at the metagraph seam.
2. Run the stack normally (§0.3). The validator observes the labeled
   cluster with an unregistered hotkey each cycle.
3. Wait ≥ 3 successful cycles AND ≥ 15 minutes. Watch:

```bash
docker compose logs -f validator | grep -E "reconciliation" \
  | tee logs/uat-g004/a12-log.txt
```

4. **Final identity check before DELETE (automatic, verify in log):** the
   evidence bundle must show the pre-delete recheck (`recheck` field) and
   the target cluster id equals the disposable cluster's recorded id.
   **Abort on any ambiguity** — if the logged cluster id differs from the
   provenance record, `docker compose down` immediately.
5. Capture the evidence bundle (the `reconciliation evidence:` log line):
   hotkey, uid-at-last-sighting, cluster id/uuid, absence-cycle history
   with metagraph blocks, recheck result, `response_class`
   (`deleted-2xx` / `conflict-404/409` / `unauthorized`), correlation id.
6. Metrics:

```bash
docker compose exec validator python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:9100/metrics').read().decode())" \
  | grep kubetee_reconciliation | tee logs/uat-g004/a12-metrics.txt
# deleted:      kubetee_reconciliation_deletions_total >= 1
# unauthorized: kubetee_reconciliation_suppressed_total{reason="unauthorized_operator_action_required"} >= 1
```

7. **Named operator action (restore):** confirm ONLY the disposable
   `miner-cluster` registration is gone (the `local` management cluster is
   protected and must be untouched); record final Rancher state in the
   epic. A plain `docker compose down -v && docker compose up -d` resets
   the whole environment (re-imports and relabels a fresh downstream).

**Outcomes (record exactly one):** (a) DELETE proven against the disposable
cluster with the full evidence bundle, or (b) token unauthorized → the
fail-closed suppression captured and the D6 token-scope limitation recorded
honestly. Both close AC12.

**Artifacts:** `a12-log.txt`, `a12-metrics.txt`, provenance + approval
links, operator restore notes.

## 7. Ledger and teardown

Record an AC-by-AC ledger comment in the epic (#4): for each of AC9(a),
AC9(b), AC9(c), AC11, AC12, AC13 — PASS / LIMITED (with citation) / not
run, linking the artifacts. Update the spec/goal status evidence in the
monorepo afterwards.

**Teardown (default preserves evidence):**

```bash
docker compose down          # containers stopped, volumes preserved
rm -f docker-compose.uat-outage.yml
# `docker compose down -v` ONLY as an explicit, confirmed disposable-localnet
# cleanup after all artifacts are captured.
```
