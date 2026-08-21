# KubeTEE Subnet Validator

The KubeTEE SN90 validator scores miners, sets on-chain weights, and (for the subnet-owner) publishes the public price card + payout snapshot + dashboard. It runs as a single Python process inside a Docker container.

## Quick start (Docker)

```bash
# 1. From this directory, copy the env template and fill in your secrets
cp .env.example .env
$EDITOR .env

# 2. Start the validator
docker compose up -d

# 3. Watch the logs
docker compose logs -f
```

The image is public (`ghcr.io/kubetee-ai/kubetee-validator:v1`) — no registry credentials are needed once the `kubetee-subnet` repo is public.

The `docker-compose.yaml` includes **Watchtower** as an optional sidecar that auto-updates the validator to the latest `v1.x.y` image every hour. The validator is pinned to the major tag `v1` (not `latest`, not a specific patch), so it auto-upgrades to the latest minor/patch release within v1 but **never crosses to a breaking v2**. To roll back, pin a specific tag and stop Watchtower (see [Auto-update & rollback](#auto-update--rollback) below).

### Dry-run (no `set_weights`, single cycle)

Before going live, verify your config against the real Finney chain + Rancher without signing anything:

```bash
docker compose run --rm -e DRY_RUN=1 -e ONCE=1 validator
```

This runs one epoch cycle, logs the full scoring breakdown, and exits. No weights are submitted to the chain.

## Auto-update & rollback

The `docker-compose.yaml` ships with **Watchtower** as a sidecar that auto-updates the validator to the latest `v1.x.y` image.

**How it works:**
- The validator is pinned to the **major tag `v1`** (not `latest`, not `v1.0.0`)
- Watchtower polls ghcr.io every hour (`WATCHTOWER_POLL_INTERVAL=3600`)
- When a new `v1.x.y` image is pushed, Watchtower pulls it and gracefully restarts the validator
- Only the labeled validator container is touched — other containers on the host are never updated
- Watchtower never updates itself (manual `docker compose pull watchtower` only)

**Why the major tag, not `latest`:**
- `v1` tracks the latest minor/patch within v1 — auto-upgrades are safe (no breaking changes by definition)
- `latest` would cross major boundaries — a v2.0.0 push would auto-update a v1 validator to a breaking version
- The `release-image.yml` workflow pushes `v1`, `v1.0`, `v1.0.0`, and `latest` on every semver tag

**Rollback to a specific version:**
```bash
# 1. Stop Watchtower so it doesn't re-upgrade
docker compose stop watchtower

# 2. Pin the validator to a specific version
$EDITOR docker-compose.yaml
#   change: image: ghcr.io/kubetee-ai/kubetee-validator:v1
#   to:     image: ghcr.io/kubetee-ai/kubetee-validator:v1.0.0

# 3. Pull and restart
docker compose pull validator && docker compose up -d validator
```

**Disable auto-update entirely:**
```bash
# Comment out or remove the watchtower service in docker-compose.yaml,
# or just stop it:
docker compose stop watchtower
```

**Adjust the poll interval** (via `.env`):
```bash
# .env
WATCHTOWER_POLL_INTERVAL=86400   # check once a day instead of hourly
```

## Two modes

The validator has two modes, selected entirely by the `.env` file:

### Reader mode (third-party validators)

```bash
# .env
SUBNET_NETUID=90
BT_NETWORK=finney
VALIDATOR_HOTKEY_SEED=<your mnemonic>
RANCHER_URL=https://validator.kubetee.ai
TAOSTATS_API_KEY=<your Taostats key>
KUBETEE_OWNER_UID=0
```

A reader validator:
- Has **no Rancher bearer token** — `RANCHER_BEARER_TOKEN` is omitted (defaults to empty)
- Points `RANCHER_URL` at the subnet-owner's proxy (`https://validator.kubetee.ai`)
- Signs each Rancher request with its **Bittensor hotkey** (sr25519) — the proxy verifies the signature against the live Finney metagraph and forwards to upstream Rancher
- Does **not** serve the proxy (port 9101 is unused)
- Does **not** publish to S3 (no Hippius keys)
- Runs the same Targon supply-side clamp as the owner (always on)

A reader needs only: a valid Bittensor hotkey registered on SN90 with `validator_permit=True` + a Taostats API key. No Rancher account, no manual onboarding.

The owner staging miner (UID **56**) is CC-capable; CC can be turned off on a node for debug. That scoring exception is **hardcoded** in `config.py` (`OWNER_MINER_UID = 56`) so every validator scores the same GPU inventory — there is no env var to set.

### Owner mode (subnet-owner only)

The subnet-owner validator runs with additional credentials (`RANCHER_BEARER_TOKEN`, Hippius S3 keys) that are **not published** — they are private to the subnet owner. The owner validator:
- Speaks **directly** to Rancher with the bearer token (GET-only, least-privilege GlobalRole)
- **Serves the Rancher proxy** on port 9101 — third-party validators authenticate with their hotkey signature and the proxy injects the bearer token upstream
- **Publishes** the price card, payout snapshot, and dashboard to Hippius S3
- Runs the same Targon supply-side clamp as readers (pulls the GPU card down toward SN4 payouts)

## Environment variables

See [`.env.example`](./.env.example) for the full list with inline comments. Summary:

| Variable | Required | Owner | Reader | Description |
|----------|----------|-------|--------|-------------|
| `SUBNET_NETUID` | yes | 90 | 90 | Subnet UID |
| `BT_NETWORK` | no | finney | finney | Chain network |
| `VALIDATOR_HOTKEY_SEED` | yes | mnemonic | mnemonic | sr25519 seed for `set_weights` + proxy auth |
| `RANCHER_URL` | yes | Rancher API URL | `https://validator.kubetee.ai` | Rancher evidence source |
| `RANCHER_BEARER_TOKEN` | owner only | token | **empty** | Rancher API key (owner) / empty (reader uses proxy) |
| `TAOSTATS_API_KEY` | yes | key | key | TAO/USD price feed |
| `KUBETEE_OWNER_UID` | no | 0 | 0 | UID receiving the recycle-to-UID weight |
| `KUBETEE_HIPPIUS_ACCESS_KEY` | owner only | key | — | S3 publish (publisher role) |
| `KUBETEE_HIPPIUS_SECRET_KEY` | owner only | key | — | S3 publish (publisher role) |
| `KUBETEE_PROXY_PORT` | no | 9101 | — | Proxy listen port (owner only) |
| `KUBETEE_METRICS_PORT` | no | 9100 | 9100 | Prometheus metrics port |
| `DRY_RUN` | no | — | — | Set to `1` to skip `set_weights` |
| `ONCE` | no | — | — | Set to `1` to run a single cycle and exit |

## How scoring works

Each cycle (default 360s ≈ one chain epoch):

1. **Read metagraph** — Finney SN90 neurons, hotkeys, emissions, hyperparams
2. **Read Rancher evidence** — clusters + nodes (owner: direct / reader: via proxy)
3. **Resolve GPU price card** — published `price-card.json` from S3, envelope-clamped to `[0.8x, 1.25x]` of the compiled-in default
4. **Price feed** — TAO/USD from Taostats × alpha→TAO from chain metagraph. Falls back to S3 `payout.json` if Taostats is down
5. **Score miners** — per-GPU-class USD earned × tenure → proportional weight
6. **Set weights** — once per epoch, respecting `weights_rate_limit` cooldown
7. **Publish** (owner only) — price card, payout snapshot (with `tao_usd` + `alpha_to_tao`), dashboard to Hippius S3

Whatever miners do not earn is **recycled to the owner UID** (set as weight on the owner's hotkey).

## Fallback chain

| Dependency | Primary | Fallback | Last resort |
|------------|---------|----------|-------------|
| TAO/USD (Taostats) | Live API | in-process / disk cache → S3 `payout.json["tao_usd"]` | skip cycle |
| Alpha→TAO | Chain metagraph `mg.price` | S3 `payout.json["alpha_to_tao"]` | skip cycle |
| GPU card (Targon) | Live API | local disk cache | S3 `payout.json["per_card_usd"]` → compiled default |
| Rancher evidence | Owner: direct / Reader: proxy | — | skip cycle (stale evidence mis-scores) |
| Chain metagraph | Finney subtensor | — | skip cycle (chain is source of truth) |

The owner publishes `payout.json` every cycle with `tao_usd` + `alpha_to_tao` + `per_card_usd`, so a reader validator survives a Taostats or Targon outage by using the owner's last-known snapshot (one cycle stale, strictly better than skipping).

## Proxy (owner only)

When `RANCHER_URL` + `RANCHER_BEARER_TOKEN` are both set, the validator also serves a hotkey-authenticated read-only Rancher proxy on port 9101.

**Strict allowlist** — the proxy only forwards two endpoints:

| Method | Path | Query | Action |
|--------|------|-------|--------|
| GET | `/v3/clusters` | `limit`, `marker` | forward to `RancherClient.list_clusters()` |
| GET | `/v3/nodes` | `clusterId` (required), `limit`, `marker` | forward to `RancherClient.list_nodes(clusterId)` |
| * | any other | * | **403** |

Enforcement is at three layers: exact path match, GET-only, query param allowlist. A malicious validator cannot enumerate users, read secrets, or mutate Rancher state through the proxy.

**Auth**: the reader signs `<path>\n<query>\n<ts>` with its hotkey private key (sr25519). The proxy verifies the signature using only the public SS58 address (from the live metagraph) — it never sees the reader's private key.

**Eligibility**: the proxy only accepts hotkeys that are registered on the subnet **and** have `validator_permit=True` in the live metagraph. Miners (no permit) are always rejected with **403**.

**Client version**: every reader request includes `BT-Validator-Version` (and `User-Agent: kubetee-validator/<ver>`). The proxy logs it on every query / 200 / 403. To reject deprecated clients later, set `KUBETEE_PROXY_MIN_VERSION` on the **owner** validator (e.g. `1.0.1`); unset means logging only (missing versions still allowed).

**Reader requirement**: Cloudflare bot-fight mode on `kubetee.ai` blocks the default Python urllib User-Agent (error 1010). `RancherClient` sets `User-Agent: kubetee-validator/<version>` automatically.

Every proxy request is logged:
```
proxy query: hotkey=5EKt…STEE version=1.1.3 path=/v3/clusters query=limit=1000
proxy 200: hotkey=5EKt…STEE version=1.1.3 path=/v3/clusters items=4 bytes=35138
```

## Metrics

Prometheus metrics on port 9100:

- `kubetee_validator_cycles_total` — epoch cycles completed
- `kubetee_validator_skips_total{reason}` — cycles skipped (by reason)
- `kubetee_validator_weights_set_total` — successful `set_weights` calls
- `kubetee_validator_publish_total{kind,ok}` — S3 publish attempts
- `kubetee_validator_earning_miners` — number of miners with non-zero score

## Local development

```bash
# Install dev deps
pip install -e ".[dev]"

# Run tests
pytest tests/ -q

# Run the validator locally (no Docker)
python validator.py

# Smoke test the proxy (from a reader perspective)
VALIDATOR_HOTKEY_SEED=<mnemonic> python scripts/smoke_proxy.py
```

## Files

| File | Purpose |
|------|---------|
| `validator.py` | Main epoch loop — orchestrates all modules |
| `config.py` | Env var loading + validation (fail-fast) |
| `chain_state.py` | Bittensor SDK wrapper — metagraph, hyperparams, `set_weights` |
| `rancher_client.py` | GET-only Rancher v3 client (owner: bearer / reader: hotkey-signed) |
| `rancher_proxy.py` | Hotkey-authenticated proxy server (owner only, port 9101) |
| `infrastructure_validation.py` | Miner readiness verdict from Rancher node/cluster data |
| `miner_scoring.py` | USD-denominated proportional weight computation |
| `price_feed.py` | TAO/USD (Taostats) + alpha→TAO (chain) + S3 fallback |
| `targon_payout_feed.py` | Targon SN4 live per-card USD + 4-tier fallback |
| `price_card.py` | Build/parse/clamp the GPU price card |
| `hippius_store.py` | SigV4-signed S3 client (publish + anonymous read) |
| `dashboard.py` | Static HTML dashboard generator (baked-in data) |
| `validator_metrics.py` | Prometheus metrics |
| `Dockerfile` | Image definition (python:3.14-slim, non-root) |
| `docker-compose.yaml` | One-command deploy (owner or reader) |
| `.env.example` | Full env var template with inline comments |
| `tests/` | Pytest unit tests (70+ tests, no bittensor_core needed) |
| `scripts/smoke_finney.py` | Read-only Finney + Rancher sanity check |
| `scripts/smoke_proxy.py` | Reader-side proxy smoke test |

## Release

See [RELEASE-AND-VERSIONING.md](../RELEASE-AND-VERSIONING.md) for the semantic versioning scheme, image tag mapping, and full release procedure.
