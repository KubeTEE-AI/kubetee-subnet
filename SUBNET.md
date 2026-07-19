# KubeTEE Subnet (v11 Bittensor)

This document explains how to run the KubeTEE subnet stack in Early Access:
the local single-node chain, the **basic validator** (g004), and the
operational policies that come with it.

**Important (2026-07):** We are on a development branch moving away from the
legacy v10 `bittensor-subnet-template`. The structure is being modernized for
Bittensor 11+ (signed requests for neuron comms + unified `bittensor` SDK).

**Early Access scoring caveat:** the basic validator scores **node liveness
only** — a binary, fail-closed check against the Rancher v3 API. It is a
liveness proxy, **not** TEE attestation, capacity, or job-quality scoring
(those are the future scoring epic, see `README.md`). Liveness scoring
establishes no eligibility, attestation, or security compliance.

## The Basic Validator (Early Access)

### Flow

Each cycle (every `KUBETEE_POLL_SECONDS`, minimum 60s) the validator:

1. **Reads the metagraph** and discovers miners: every registered hotkey
   that is not one of our own subnet keys (`KUBETEE_OWNER_HOTKEY`,
   `KUBETEE_VALIDATOR_HOTKEY`). UIDs are resolved by hotkey SS58 — there is
   no fixed-UID configuration.
2. **Enumerates Rancher** (read-only, complete pagination): finds each
   miner's cluster by the `kubetee.ai/miner-hotkey` label and reads its
   nodes.
3. **Runs deregistration reconciliation** (the single guarded Rancher
   mutation — see below).
4. **Scores each miner** binary fail-closed: `1` iff exactly one labeled
   cluster matches, the cluster is `active`, and at least one node is
   `active`; anything missing, ambiguous, transitional, or unverifiable
   scores `0`.
5. **Sets weights**, signed by **alice** (`BT_WALLET=alice`): each scoring
   miner gets `KUBETEE_MINER_SHARE / N`; the owner recycle UID gets
   `1 − KUBETEE_MINER_SHARE` (or `1.0` when no miner scores); all other
   UIDs get explicit zero. Success is claimed only on chain acceptance.
6. **Logs and exports Prometheus metrics** (structured, redacted — the
   bearer token and response bodies never appear in logs or metrics).

With no scoring miner the subnet degenerates to owner-only recycle
(100% owner weight) — the behavior of the retired owner validator.

### Manual cluster label step (Early Access)

The miner→cluster mapping is the `kubetee.ai/miner-hotkey` cluster label,
whose value is the miner's hotkey SS58. In Early Access the **operator sets
this label manually** when registering the miner's cluster (registration is
operator-performed, not permissionless):

1. Rancher UI → Cluster Management → select the miner's cluster → Edit
   Config → Labels & Annotations, **or** the equivalent `kubectl label
   clusters.provisioning.cattle.io ...` on the management cluster.
2. Add label `kubetee.ai/miner-hotkey=<miner hotkey SS58>` (for the Early
   Access miner this is **bob's** hotkey).
3. Exactly one cluster may carry a given hotkey value — duplicates score 0
   (ambiguous, fail-closed).

A registered miner without a labeled active cluster scores 0. The label is
trusted only because the operator sets it; binding labels to verified
enrollment is part of the future permissionless epic.

### Configurable weight split (D12)

`KUBETEE_MINER_SHARE` lives in `.env` (see `.env.example`), default
**0.10** — i.e. 10% to scoring miners, 90% recycled to the subnet-owner
UID. It must be finite and within `[0, 1]`; anything else refuses to start.
Changing the split is a `.env` edit + container restart, no code change.

### Recycle mechanism (D13)

Recycling works by **directing weights to the owner-controlled UID while
the subnet has `recycle_or_burn=Recycle` set** (the compose setup phase
sets it, ownership permitting). That mechanism is accepted per Bittensor
docs and owner decision D13. What the validator/UAT verifies is exactly:

- the hyperparameters we set are in place, **where the chain allows
  reading/setting them**, and
- the weights target the **proper owner-controlled key** (the owner UID's
  hotkey equals `KUBETEE_OWNER_HOTKEY`).

### Localnet environment limitation (D1)

On the pinned `ghcr.io/opentensor/subtensor-localnet:latest` image, netuid 1
is pre-owned by a bootstrap key and `btcli subnet create` fails with
`SubtokenDisabled`. Owner-only hyperparameters (`recycle_or_burn`,
`owner_cut_auto_lock_enabled`) therefore **cannot be set on-chain there**;
the setup reports this honestly (ownership check, `/app/.kubetee_owned`)
and skips the doomed sudo calls instead of hammering the chain. This is a
documented **environment limitation, not a doubt about the recycle
mechanism** — the weight split is demonstrated live on localnet and the
on-chain recycle-hyperparameter proof is deferred to a future testnet
slice. UAT reports the hyperparameter check as SKIPPED/LIMITED with this
citation on the pinned image.

### Rancher access in the dev stack, and token debt (D6)

The dev compose stack is **self-contained**: a `rancher` service
(containerised Rancher with its embedded k3s management cluster) plus a
disposable `miner-cluster` downstream. The one-shot `rancher-init` service
**mints the validator's Rancher API token automatically on every `up`** and
publishes it (with the Rancher CA) through a shared volume — nothing
Rancher-related needs to live in `.env` for local development. The Rancher
bootstrap password in `docker-compose.yml` is a hardcoded **disposable dev
credential**, exactly like the pinned dev seeds.

Running against an **external** Rancher (staging or otherwise) still uses
the gitignored `.env` (`RANCHER_URL`, `RANCHER_BEARER_TOKEN`). Containment
is code-side either way: the Rancher client is structurally GET-only apart
from the single guarded reconciliation DELETE, pins one https origin,
refuses redirects, and never logs the token.

**Recorded debt item (D6):** for any non-local deployment the validator
token must be bound to a `cluster-readonly`-style role (read plus the
single delete, nothing else) and verified — never an admin or unverified
token. The dev stack's auto-minted token must converge to the same scoped
shape so local runs exercise the real authorization posture. This must be
resolved **before any non-local deployment** and must not be silently
extended.

### Failure handling: fail-fast startup vs runtime skip (D14/D10)

- **Startup (fail-fast):** every static config value is validated before
  the loop starts — `KUBETEE_MINER_SHARE`, `KUBETEE_POLL_SECONDS` (≥ 60),
  `KUBETEE_MAX_CONSECUTIVE_SKIPS`, reconcile parameters, owner + validator
  hotkeys (present, distinct), and `RANCHER_URL`/`RANCHER_BEARER_TOKEN`
  (present, well-formed https origin). Any violation → the process refuses
  to start with a clear error naming every offending variable (values of
  secrets are never echoed).
- **Runtime (never exit):** once started, the validator **never exits on a
  runtime error**. A Rancher outage (transport error, timeout, 5xx, auth
  rejection) **skips `set_weights` for that cycle** — our own observability
  outage must never zero a miner — logs the reason, increments the error
  metric, and suppresses reconciliation. A rejected `set_weights` is logged
  honestly with a redacted error and retried with bounded backoff. Even an
  unexpected in-cycle exception degrades to backoff and the loop continues.
  Only operator signals (`docker compose down`, SIGTERM) stop the process.

### Degraded mode and remediation policy (D10 staleness bound)

Consecutive skipped cycles are counted and capped by
`KUBETEE_MAX_CONSECUTIVE_SKIPS` (default **10**, ≈ 10 minutes at the 60s
interval). Exceeding the cap does **not** auto-zero anyone's weights — it
puts the validator into an explicit, loudly logged **degraded mode** with
the Prometheus flag `kubetee_degraded_mode=1`. On-chain weights are stale
from the last successful cycle and stay that way until scoring recovers.

**Operator remediation policy:**

1. Alert on `kubetee_degraded_mode == 1` (and on
   `kubetee_consecutive_skips` climbing).
2. Diagnose the skip reason from the validator logs
   (`cycle skipped set_weights: reason=...`) and the
   `kubetee_rancher_errors_total{category=...}` counters — typical causes:
   Rancher outage, revoked/expired token (auth), network path.
3. Fix the cause (restore Rancher/network; rotate the token in `.env` and
   restart the container for credential failures — credential *changes*
   are a restart, not a runtime reload).
4. Recovery is automatic: the first fully successful scoring cycle clears
   the flag and resets the counter. Verify `kubetee_degraded_mode == 0`
   and a fresh `kubetee_last_successful_scoring_timestamp`.
5. Never "remediate" by zeroing weights manually — stale-but-visible is
   the designed failure mode; scoring integrity returns with evidence.

### Deregistration reconciliation (single guarded mutation)

When a `kubetee.ai/miner-hotkey`-labeled cluster's hotkey is no longer
registered on the metagraph, the validator removes that cluster from
Rancher — the **only** write it can ever perform. Guards (all mandatory,
fail-closed): runs only after a fresh successful metagraph read **and** a
complete Rancher enumeration in the same cycle; absence must persist ≥
`KUBETEE_RECONCILE_MIN_CYCLES` (3) successful cycles **and** ≥
`KUBETEE_RECONCILE_MIN_SECONDS` (900) wall-clock; a same-cycle pre-delete
recheck (fresh metagraph read + final GET re-validating id/uuid/label);
unlabeled and management (`local`) clusters are structurally out of reach;
404/409 are idempotent; an unauthorized token fails closed as
`operator action required` (never a silent no-op). Every deletion or
suppression logs an evidence bundle (identifiers and history only — never
payloads or secrets). Counters are in-memory: a restart only defers
deletion (the safe direction).

### Prometheus metrics

The validator exposes `prometheus_client` text metrics on
`KUBETEE_METRICS_PORT` (9100), **compose-internal only** (no host port
mapping). Key series: `kubetee_rancher_errors_total{category}`,
`kubetee_set_weights_total{result}`, `kubetee_cycles_skipped_total{reason}`,
`kubetee_consecutive_skips`, `kubetee_degraded_mode`,
`kubetee_last_successful_scoring_timestamp`, `kubetee_miners_discovered`,
`kubetee_miners_scoring`, `kubetee_reconciliation_deletions_total`,
`kubetee_reconciliation_suppressed_total{reason}`,
`kubetee_reconciliation_conflicts_total`. All label values are fixed enums;
no metric or label ever carries secret material.

## Local Single-Node Testing Stack

This gives you a fast local chain + the validator (and optional miners) with full logs.

### 1. Prerequisites

- Docker + Compose
- Python 3.10+ + `pip install bittensor` (for btcli and SDK on host)
- Wallets are created inside the validator container (in the
  `bittensor-wallets` named volume) from pinned dev seeds — your host
  `~/.bittensor` is not touched. Inspect via
  `docker compose exec validator btcli wallet ...`.
- No `.env` is required for the normal self-contained stack: `rancher-init`
  mints the validator's Rancher token automatically each `up`. Use a `.env`
  (copy `.env.example`, never commit it) only to override tunables or to
  point the validator at an **external** Rancher (`RANCHER_URL` +
  `RANCHER_BEARER_TOKEN`). The validator still refuses to start without a
  Rancher URL + token in its environment (by design, D14) — in the compose
  stack these are supplied by the stack itself.

### 2. Start the stack (chain + Rancher + miner-cluster + validator + dozzle)

One `up` brings the whole self-contained environment: the local chain, the
containerised Rancher, the disposable miner-cluster (imported and labelled
by `rancher-init`), and the validator. The validator container
self-initializes: it waits for Rancher provisioning, runs the btcli
registration + hyperparam setup, then starts the basic validator. First
boot takes a few minutes (Rancher bootstrap); later `up`s after `down`
**without** `-v` are much faster (the Rancher control plane persists).

```bash
cd repos/subnet/kubetee-subnet

# Build images and start everything detached
docker compose up -d --build

# View live logs in browser (Dozzle)
# Open http://localhost:8080
```

Services (all using deterministic pinned dev accounts, see `keys/README.md`):

- `chain`: subtensor-localnet (FAST_BLOCKS for fast testing)
- `validator`: entrypoint does btcli (register subnet if not exists,
  register the **owner/alice/bob** triad, add stake, start emissions,
  attempt conviction/recycle hypers) then runs `validator.py`
  (alice signs `set_weights`)
- background conviction-setter + subnet-stats loops inside the validator
  container (single chain connection each — HTTP 429 lesson)
- `dozzle`: log viewer (http://localhost:8080)
- `miner-1` (optional profile, stub)

Stop: `docker compose down`

Follow the interesting logs:

```bash
docker compose logs -f validator
```

### 3. Single-node setup script (register + hypers)

The setup runs **inside the validator container** automatically. To run
(or re-run) it manually from the **host**:

```bash
python scripts/setup_single_node.py --netuid 1 --owner-wallet owner --chain-endpoint ws://127.0.0.1:9944
```

What it does:

- Waits for the chain
- **Uses pinned deterministic dev seeds** for the triad (D7): `owner`
  (subnet owner / recycle target), `alice` (validator, also the funding
  source), `bob` (miner)
- Creates the subnet if needed, registers and stakes all three wallets
  (stake attempts are best-effort: the pinned image can reject them with
  `SubtokenDisabled` — reported honestly, see the D1 limitation above)
- Starts emissions and attempts the conviction/recycle hyperparameters
  **only when a live ownership check passes** (never blind retries)

### 4. Running the validator manually (host)

```bash
BT_NETWORK=ws://127.0.0.1:9944 \
KUBETEE_SUBNET_NETUID=1 \
BT_WALLET=alice \
KUBETEE_OWNER_HOTKEY=5FLbZav21bAsjH5SAdmJZwTP5C4b3bcaaWqC6GSmGmsbzUJ9 \
KUBETEE_VALIDATOR_HOTKEY=5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY \
RANCHER_URL=... RANCHER_BEARER_TOKEN=... \
python scripts/validator.py
```

### 5. Observability

- **Dozzle** (http://localhost:8080): filter the validator logs for
  `set_weights`, `cycle skipped`, `DEGRADED`, `reconciliation`.
- **Metrics**: from inside the compose network,
  `http://validator:9100/metrics` (deliberately not reachable from the
  host).
- **subnet-stats** loop prints hypers (conviction, recycle_or_burn where
  readable), stake, ownership, and wallet stake for owner + bob.

### 6. Testnet / Mainnet notes

- Use real funded wallets; `--network test` or `finney`.
- **Resolve the D6 token debt first** (cluster-readonly-bound token) —
  mandatory before any non-local deployment.
- Always test recycle + conviction on local first.

### 7. Common commands (v11 / btcli)

```bash
# View hypers (recycle_or_burn visible where the chain exposes it)
btcli subnets hyperparameters --netuid 1 --network ws://127.0.0.1:9944

# Set (owner only; fails on the pinned localnet image - D1)
btcli sudo set --netuid 1 --param recycle_or_burn --value Recycle --network ws://127.0.0.1:9944

# Metagraph (UIDs, stake, weights - the place to see the split)
btcli subnets metagraph --netuid 1 --network ws://127.0.0.1:9944
```

---

See also: `scripts/setup_single_node.py`, `scripts/validator.py`,
`docker-compose.yml`, `.env.example`, `keys/README.md`, and
`docs/NODE-REGISTRATION.md` (miner-side node registration + the
`kubetee.ai/miner-hotkey` label requirement).
