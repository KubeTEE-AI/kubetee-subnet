# KubeTEE Subnet (v11 Bittensor)

This document explains how to run miners and validators for the KubeTEE subnet.

**Important (2026-07):** We are on a development branch moving away from the legacy v10 `bittensor-subnet-template`. 
The structure is being modernized for Bittensor 11+ (signed requests for neuron comms + unified `bittensor` SDK).

For the **testing pyramid** we use a "single node" local setup based on the official RaoFoundation localnet.

## Local Single-Node Testing Pyramid (Recommended for Development)

This gives you a fast local chain + your validator (and optional miners) with full logs.

### 1. Prerequisites
- Docker + Compose
- Python 3.10+ + `pip install bittensor` (for btcli and SDK on host)
- Wallets will be created under `~/.bittensor`

### 2. Start the stack (chain + validator + dozzle)

The validator container now self-initializes: on startup it first runs the btcli registration + hyperparam setup, then starts the owner validator.

```bash
cd repos/subnet/kubetee-subnet

# Build images and start everything detached
docker compose up -d --build

# View live logs in browser (Dozzle)
# Open http://localhost:8080
```

Services (all using deterministic pinned dev accounts):
- `chain`: subtensor-localnet (FAST_BLOCKS for fast testing)
- `validator`: entrypoint does btcli (register subnet if not exists, register the owner/alice/bob triad, add stake, start emissions, set conviction/recycle hypers) then basic_validator (alice signs set_weights; miners scored via the read-only Rancher v3 API; weights split `KUBETEE_MINER_SHARE` to miners, rest to the owner recycle UID)
- `conviction-setter`: bash while-loop that periodically re-sets the conviction hypers
- `subnet-stats`: btcli loop that prints hypers (conviction, recycle), stake, metagraph (emissions, UIDs, weights), balances etc. — everything visible in logs
- `dozzle`: log viewer (http://localhost:8080)
- `miner-1` (optional profile)

Stop: `docker compose down`

Follow the interesting logs:
```bash
docker compose logs -f validator subnet-stats conviction-setter
```

### 3. Single-Node Setup Script (register + hypers for conviction + recycle)

The setup is now performed **inside the validator container** automatically.

If you want to run (or re-run) setup manually from the **host** (e.g. for debugging or different netuid):

```bash
python scripts/setup_single_node.py --netuid 1 --owner-wallet owner --chain-endpoint ws://127.0.0.1:9944
```

(When running inside compose the entrypoint uses the internal `ws://chain:9944`.)

What the setup (run at validator startup) does:
- Waits for chain
- **Uses pinned deterministic dev seeds** (Alice + owner) — fdn-subnet style (Alith etc.). Owner SS58 + UID stable.
- Ensures/creates subnet if it does not exist
- Registers the owner hotkey as a neuron on the subnet
- Puts some stake on the subnet for the owner (`btcli stake add`)
- Starts emissions (`sudo start`)
- Sets the key hyperparameters for the use case:
  - `owner_cut_auto_lock_enabled=true` (owner cut auto-locks into CONVICTION)
  - `recycle_or_burn=Recycle` (emissions directed to owner UID get recycled, not burned)
- Then the long-running owner validator sets weights=1.0 to the owner UID.

This lets you observe "miner incentive recycling" (via weights + recycle hyper) + conviction behavior.

See `keys/README.md` for the pinned seeds and fdn parallel.

The conviction-setter and subnet-stats containers (see below) provide continuous observation in logs.

### 4. The Basic Validator (Rancher-scored miner share + owner recycle)

Inside the compose validator container the flow is:

1. `scripts/validator_entrypoint.py` runs first (btcli commands for register + hypers, owner/alice/bob triad)
2. Once that exits, it execs `python scripts/basic_validator.py`

Each cycle the validator discovers miners from the metagraph (every registered
hotkey that is not the owner or validator key), scores each miner's
`kubetee.ai/miner-hotkey`-labeled Rancher cluster with a binary fail-closed
node-active rule, and sets weights: `KUBETEE_MINER_SHARE` (default 0.10) split
across scoring miners, the remainder to the owner recycle UID. Combined with
`recycle_or_burn=Recycle` the owner-directed share recycles instead of burning.
With no scoring miner it degenerates to 100% owner weight (the previous
owner-validator behavior). Missing/invalid static config (including
`RANCHER_URL`/`RANCHER_BEARER_TOKEN`) refuses to start; a runtime Rancher
outage skips weight-setting for the cycle instead of scoring anyone 0.

Environment in compose (see `docker-compose.yml` and `.env.example`):
- `KUBETEE_SUBNET_NETUID=1`
- `BT_NETWORK=ws://chain:9944` (internal to compose)
- `BT_WALLET=alice` (validator signing wallet; the owner wallet stays `KUBETEE_OWNER_WALLET=owner`)
- `KUBETEE_OWNER_HOTKEY` / `KUBETEE_VALIDATOR_HOTKEY` (UIDs resolved from the metagraph by hotkey — no `TARGET_UID`)
- `RANCHER_URL` / `RANCHER_BEARER_TOKEN` from the gitignored `.env`

To run the validator manually on host (after you ran setup yourself):
```bash
BT_NETWORK=ws://127.0.0.1:9944 \
KUBETEE_SUBNET_NETUID=1 \
KUBETEE_OWNER_HOTKEY=5FLbZav21bAsjH5SAdmJZwTP5C4b3bcaaWqC6GSmGmsbzUJ9 \
KUBETEE_VALIDATOR_HOTKEY=5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY \
RANCHER_URL=... RANCHER_BEARER_TOKEN=... \
python scripts/basic_validator.py
```

### Observer / Sidecar Containers

Two additional containers are started by default to make the single-node pyramid easy to observe in dozzle:

- **conviction-setter**: A simple bash `while true` loop that repeatedly runs the `btcli sudo set` commands for `owner_cut_auto_lock_enabled` and `recycle_or_burn=Recycle`. This keeps (or re-asserts) the conviction/recycle behavior on the subnet.

- **subnet-stats**: A `while true` btcli stats printer that outputs (to container logs):
  - `subnets hyperparameters` (conviction + recycle_or_burn visible here)
  - `stake list`
  - `metagraph` (UIDs, stake, weights, emission columns — primary way to see "miner recycling" in action when the owner validator sets weight 1.0)
  - wallet balances

Run with:
```bash
docker compose logs -f validator subnet-stats conviction-setter
```

Everything is designed so you can watch the full flow (register → stake → emissions start → weights → recycled emissions + conviction) live.

### 5. Running a Miner

For local testing, miners are mostly infrastructure/TEE providers for KubeTEE.

Basic pattern (v11 style - no more legacy axon/dendrite):

1. Register a hotkey on the subnet (as miner).
2. Run your miner process that:
   - Serves via plain HTTP + signs requests with `bittensor.http_auth`
   - Responds to validator queries (see signed-requests guide)
   - Reports infrastructure/TEE status, etc.

Example minimal miner skeleton will be added as we clean more legacy code.

For now, you can use the optional `miner-1` profile as a stub, or implement against the protocol your validator expects.

To register a test miner:
```bash
btcli subnet register --netuid 1 --wallet.name miner1 --wallet-hotkey default --network local --yes
```

### 6. View Everything in Dozzle

After `docker compose up -d`:

- Go to http://localhost:8080
- Select containers: `kubetee-chain`, `kubetee-validator`, `kubetee-dozzle`, etc.
- Filter by "emissions", "conviction", "weights", "hyperparameter", etc.

This is the main way to review the single-node pyramid run.

### 7. Testnet / Mainnet Notes

- Use real funded wallets.
- `btcli ... --network test` or `finney`
- Set `BT_NETWORK=ws://...` accordingly.
- For mainnet you must be the subnet owner (coldkey) to set hypers and start emissions.
- Always test recycle + conviction on local first.

### 8. Common Commands (v11 / btcli)

```bash
# View hypers
btcli subnets hyperparameters --netuid 1 --network local

# Set (owner only)
btcli sudo set --netuid 1 --param owner_cut_auto_lock_enabled --value true --network local
btcli sudo set --netuid 1 --param recycle_or_burn --value Recycle --network local

# Start emissions
btcli sudo start --netuid 1 --network local

# Weights (the validator does this)
btcli weights set --netuid 1 --uids 0 --weights 1.0 --network local

# Conviction view
btcli subnets conviction --netuid 1 --network local
```

### 9. Conviction + Recycle Goal

By enabling `owner_cut_auto_lock_enabled`:
- The 18% owner cut is auto-locked into a conviction position (time-weighted, proves commitment).

By using owner-validator + `recycle_or_burn=Recycle`:
- Miner-directed emissions to owner UID are recycled (re-emittable) instead of burned.

This matches the requirement: "auto set subnet owners emissions to be into conviction" + recycle instead of burn.

---

**Next steps on the branch:**
- More v11-native miner/validator base (remove remaining legacy template/ bits).
- Full testing pyramid layers (in-mem → localnet integration → multi-node).
- TEE/attestation integration into the scoring.

See also: `scripts/setup_single_node.py`, `scripts/basic_validator.py`, `docker-compose.yml`, and the previous pyramid spec.
