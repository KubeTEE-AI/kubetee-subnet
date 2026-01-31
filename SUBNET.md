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

```bash
cd repos/subnet/kubetee-subnet

# Build images and start everything detached
docker compose up -d --build

# View live logs in browser (Dozzle)
# Open http://localhost:8080
```

Services:
- `chain`: `ghcr.io/raofoundation/subtensor-localnet:devnet` (fast blocks by default)
- `validator`: Runs the owner-validator (sets weights to recycle/conviction mode)
- `dozzle`: Log viewer
- `miner-1` (optional): `docker compose --profile with-miners up -d`

Stop: `docker compose down`

### 3. Run the Single-Node Setup Script (starts emissions + conviction + recycle)

After the chain is healthy, run the setup script **from the host**:

```bash
python scripts/setup_single_node.py --netuid 1 --owner-wallet owner
```

What it does:
- Waits for chain
- Creates/funds dev wallets (using Alice dev account)
- Ensures subnet exists + owner neuron registered
- Calls `start` to enable emissions
- Sets hyperparameters:
  - `owner_cut_auto_lock_enabled=true` → owner cut (18%) is **automatically locked into CONVICTION**
  - `recycle_or_burn=Recycle` → emissions directed to owner UID are **recycled** (not burned)
- Owner emissions now flow into conviction (locked, builds conviction over time) + recycled path.

You can also run it with different netuid if `create` gave you another one.

### 4. The Owner Validator (recycle + conviction use case)

The validator in the compose runs:

```bash
python scripts/owner_validator.py
```

It sets weight 1.0 to the target owner UID so that the miner-incentive portion of emissions goes to the owner key (combined with the Recycle setting above).

Environment in compose:
- `TARGET_UID=0` (or the UID you registered for the owner hotkey)
- You can override via `.env` or compose override.

To run manually on host (after setup):
```bash
BT_NETWORK=ws://127.0.0.1:9944 \
KUBETEE_SUBNET_NETUID=1 \
TARGET_UID=0 \
python scripts/owner_validator.py
```

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

See also: `scripts/setup_single_node.py`, `scripts/owner_validator.py`, `docker-compose.yml`, and the previous pyramid spec.
