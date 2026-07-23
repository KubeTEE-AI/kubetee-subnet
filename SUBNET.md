# KubeTEE Subnet (v11 Bittensor)

This document explains how to run the KubeTEE subnet stack in Early Access:
the local single-node chain, the **basic validator** (g004), and the
operational policies that come with it.

**Important (2026-07):** We are on a development branch moving away from the
legacy v10 `bittensor-subnet-template`. The structure is being modernized for
Bittensor 11+ (signed requests for neuron comms + unified `bittensor` SDK).

**Early Access scoring boundary:** the basic validator applies a binary,
fail-closed **infrastructure-readiness** policy to a fresh Rancher v3 snapshot.
Production checks canonical enrollment identity, cluster/node readiness, HA
roles, per-node CPU and memory, supported eight-GPU workers, passthrough
wiring, and the confidential runtime handler. This does **not** prove fresh
TEE attestation, a live tunnel/probe, workload identity, Armada readiness, or
an unexpired KeyLease; those remain independent serving gates.

## The Basic Validator (Early Access)

### Flow

Each cycle (every `KUBETEE_POLL_SECONDS`, minimum 60s) the validator:

1. **Reads the metagraph** and discovers miners: every registered hotkey
   that is not the chain-reported subnet owner or our configured
   `KUBETEE_VALIDATOR_HOTKEY`. UIDs are resolved by hotkey SS58 — there is no
   fixed-UID or manually configured owner-hotkey input.
2. **Enumerates Rancher** (GET-only, complete pagination): finds each
   miner's unique cluster by the canonical `kubetee.ai/hotkey` binding label
   and reads its nodes.
3. **Runs deregistration reconciliation** (the single guarded Rancher
   mutation — see below).
4. **Validates each miner** binary fail-closed. The `production` profile
   requires the canonical binding, Ready cluster/nodes, 3 etcd, 3
   control-plane, a schedulable worker, at least 8 CPU/16 GiB per active
   node, and supported eight-GPU passthrough workers exposing
   `kata-qemu-nvidia-gpu-tdx`. The explicit `debug` profile retains strict
   identity/state checks but accepts one active node for the disposable
   local stack. A complete per-miner failure scores `0` immediately.
5. **Sets weights**, signed by **alice** (`BT_WALLET=alice`): each scoring
   miner gets `KUBETEE_MINER_SHARE / N`; the owner recycle UID gets
   `1 − KUBETEE_MINER_SHARE` (or `1.0` when no miner scores); all other
   UIDs get explicit zero. Success is claimed only on chain acceptance.
6. **Logs and exports Prometheus metrics** (structured, redacted — the
   bearer token and response bodies never appear in logs or metrics).

With no scoring miner the subnet degenerates to owner-only recycle
(100% owner weight) — the behavior of the retired owner validator.

### Canonical enrollment binding

Onboarding writes the platform binding contract to the Rancher Cluster: the
nine labels `kubetee.ai/binding-id`, `kubetee.ai/hotkey`,
`kubetee.ai/coldkey`, `kubetee.ai/provider-id`,
`kubetee.ai/binding-status`, `kubetee.ai/generation`,
`kubetee.ai/netuid`, `kubetee.ai/network`, and
`kubetee.ai/origin-fp-prefix`, plus the `kubetee.ai/enrollment-uid`
annotation. The
validator reads only that annotation and never copies or logs other
enrollment evidence.

`kubetee.ai/binding-status=ENROLLED` means onboarding completed; it is not an
eligibility verdict. Every validation cycle rechecks the binding against the
fresh metagraph. Missing/malformed identity, a non-`ENROLLED` state, a stale
UID/coldkey/netuid/network, duplicate hotkey candidate, or duplicate binding
ID scores `0`. The validator never writes validation state back to Rancher.

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
  hotkey equals the owner hotkey reported by the selected netuid's
  metagraph).

### Localnet readiness sequence (D1)

The disposable local bootstrap creates one **new** subnet and uses the live
post-create snapshot to resolve its unique netuid (the dedicated local proof
uses netuid 2). It retains the owner/alice/bob registration triad, then
requires a positive live ownership verdict before any owner-only action. The
setup runs checked `btcli sudo start` activation, stakes **only alice** (the
validator) by exactly **1 TAO**, and then attempts the conviction/recycle
hyperparameters. Activation and the validator stake fail closed; their CLI
output is deliberately discarded.

Validator permits and weight-rate availability are transient local-chain
conditions. A local UAT must therefore wait through the permit/rate window
and require a typed accepted `ExtrinsicResult(success=True)` weight result;
registration, eligibility, or a submitted weight alone is not a successful
proof.

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
the gitignored `.env` (`RANCHER_URL`, `RANCHER_BEARER_TOKEN`, and optional
`RANCHER_CA_FILE`). The custom CA is scoped to Rancher HTTP and never replaces
the chain client's TLS trust store. Containment is code-side either way: the
Rancher client is structurally GET-only apart from the single guarded
reconciliation DELETE, pins one https origin, refuses redirects, and never
logs the token.

**Authorization contract (D6):** the combined validator/reconciler token is
not read-only. It must grant cluster/node GET/list plus cluster DELETE and
nothing else — never admin, create, update, patch, or unrelated-resource
authority. The local provisioner mints that exact shape. External operators
must provision and verify the same role before use. A future separation of
reconciliation into an operator-owned controller may reduce the scoring token
to true read-only access.

### Failure handling: fail-fast startup vs runtime skip (D14/D10)

- **Startup (fail-fast):** every static config value is validated before
  the loop starts — `KUBETEE_MINER_SHARE`, `KUBETEE_POLL_SECONDS` (≥ 60),
  `KUBETEE_MAX_CONSECUTIVE_SKIPS`, reconcile parameters, the validator
  hotkey (present), `KUBETEE_VALIDATION_PROFILE` (defaults to `production`;
  set `debug` explicitly only for local UAT), `KUBETEE_CHAIN_NETWORK`, and
  `RANCHER_URL`/`RANCHER_BEARER_TOKEN` (present, well-formed https origin).
  Any violation → the process refuses to start with a clear error naming
  every offending variable (values of secrets are never echoed).
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

When a cluster whose canonical hotkey, netuid, and network labels match this
validator's trust domain is no longer
registered on the metagraph, the validator removes that cluster from
Rancher — the **only** write it can ever perform. Guards (all mandatory,
fail-closed): runs only after a fresh successful metagraph read **and** a
complete Rancher enumeration in the same cycle; absence must persist ≥
`KUBETEE_RECONCILE_MIN_CYCLES` (3) successful cycles **and** ≥
`KUBETEE_RECONCILE_MIN_SECONDS` (900) wall-clock; a same-cycle pre-delete
recheck (a head-pinned metagraph at least as new as the strictly advancing
cycle block + final GET re-validating id/uuid/hotkey/netuid/network);
unlabeled and management (`local`) clusters are structurally out of reach;
404/409 are idempotent; an unauthorized token fails closed as
`operator action required` (never a silent no-op). Every deletion or
unauthorized suppression emits a sanitized audit record (identifiers/history
only — never payloads or secrets); all suppression paths emit bounded metrics.
Counters are in-memory: a restart only defers deletion (the safe direction).

### Prometheus metrics

The validator exposes `prometheus_client` text metrics on
`KUBETEE_METRICS_PORT` (9100), **compose-internal only** (no host port
mapping). Key series: `kubetee_rancher_errors_total{category}`,
`kubetee_set_weights_total{result}`, `kubetee_cycles_skipped_total{reason}`,
`kubetee_consecutive_skips`, `kubetee_degraded_mode`,
`kubetee_last_successful_scoring_timestamp`, `kubetee_miners_discovered`,
`kubetee_miners_scoring`, `kubetee_validation_status{status}`,
`kubetee_validation_reason{reason}`,
`kubetee_reconciliation_deletions_total`,
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
  point the validator at an **external** chain/Rancher. Root
  `make subnet-external` requires the chain network/netuid, existing signing
  wallet path/name/hotkey, validator hotkey, `RANCHER_URL`, token, CA
  file, and binding-domain `KUBETEE_CHAIN_NETWORK`. External mode selects the
  `production` policy; the self-contained stack explicitly selects `debug`.
  The validator still refuses to start without all required values (by design,
  D14) — in the local compose stack they are supplied by the stack itself.

### 2. Start the stack (chain + Rancher + miner-cluster + validator + dozzle)

One `up` brings the whole self-contained environment: the local chain, the
containerised Rancher, the disposable miner-cluster (imported and labelled
by `rancher-init`), and the validator. The validator container
self-initializes: it waits for Rancher provisioning, runs the btcli
registration + hyperparam setup, then starts the basic validator. First
boot takes a few minutes (Rancher bootstrap); later `up`s after `down`
**without** `-v` are much faster (the Rancher control plane persists).

### Running the Validator (Compose Stack)

The compose stack lives in the root `kubetee` workspace:

```bash
cd ..
docker compose up -d --build
# Logs: http://localhost:8080 (dozzle)
```

The `kubetee-subnet` repo provides the validator image (`Dockerfile`); the
root Compose files own the startup command, bootstrap sequencing, and metrics
healthcheck. The local Compose command wires the image together with Rancher,
the localnet chain, and Dozzle; the external command runs `scripts/validator.py`
directly.

For standalone development without compose, see
[Running the validator manually (host)](#4-running-the-validator-manually-host)
below.

Services (all using deterministic pinned dev accounts, see `keys/README.md`):

- `chain`: subtensor-localnet (FAST_BLOCKS for fast testing)
- `validator`: the local Compose command creates a unique subnet, registers the
  **owner/alice/bob** triad, checks ownership, activates emissions, stakes
  **alice only** by 1 TAO, attempts conviction/recycle hypers, then runs
  `validator.py`
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
python scripts/setup_single_node.py --owner-wallet owner --chain-endpoint ws://127.0.0.1:9944
```

What it does:

- Waits for the chain
- **Uses pinned deterministic dev seeds** for the triad (D7): `owner`
  (subnet owner / recycle target), `alice` (validator, also the funding
  source), `bob` (miner)
- Creates one new subnet and resolves its unique created netuid from live
  chain state, then registers all three wallets in owner/alice/bob order
- Requires a live positive ownership check, then uses checked activation,
  stakes **only alice by 1 TAO**, and attempts conviction/recycle
  hyperparameters
- Treats a local chain run as ready only after the transient permit/rate
  window yields a typed accepted validator weight

### 4. Running the validator manually (host)

`scripts/validator.py` is the validator entrypoint. In `debug` mode it runs
the disposable local `setup_single_node.py` bootstrap before starting the
validator loop. In `production` mode it never creates a subnet, registers
wallets, stakes, or changes chain hyperparameters; provide the already
registered validator and Rancher configuration explicitly.

```bash
BT_NETWORK=finney \
KUBETEE_SUBNET_NETUID=1 \
BT_WALLET=alice \
KUBETEE_VALIDATOR_HOTKEY=5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY \
RANCHER_URL=... RANCHER_BEARER_TOKEN=... RANCHER_CA_FILE=/path/to/ca.crt \
KUBETEE_CHAIN_NETWORK=finney KUBETEE_VALIDATION_PROFILE=production \
python scripts/validator.py
```

### 5. Observability

- **Dozzle** (http://localhost:8080): filter the validator logs for
  `set_weights`, `cycle skipped`, `DEGRADED`, `reconciliation`.
- **Metrics**: from inside the compose network,
  `http://validator:9100/metrics` (deliberately not reachable from the
  host).
- **subnet-stats** loop prints hypers (conviction, recycle_or_burn where
  readable), stake, ownership, and the alice validator stake.

### 6. Testnet / Mainnet notes

- Use real funded wallets; `--network test` or `finney`.
- Provision and verify the D6 least-privilege cluster/node-read plus guarded
  cluster-delete role before any non-local deployment.
- Always test recycle + conviction on local first.

### 7. Common commands (v11 / btcli)

```bash
# View hypers on the uniquely created local subnet (netuid 2 in the dedicated proof)
btcli subnets hyperparameters --netuid 2 --network ws://127.0.0.1:9944

# Set (owner only, after the live ownership gate)
btcli sudo set --netuid 2 --param recycle_or_burn --value Recycle --network ws://127.0.0.1:9944

# Metagraph (UIDs, stake, weights - the place to see the split)
btcli subnets metagraph --netuid 2 --network ws://127.0.0.1:9944
```

---

See also: `scripts/setup_single_node.py`, `scripts/validator.py`,
`docker-compose.yml`, `.env.example`, `keys/README.md`, and
`docs/NODE-REGISTRATION.md` (miner-side node registration + the
canonical enrolled-cluster binding requirement).
