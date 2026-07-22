# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KubeTEE AI is the **AI Factory** of the Bittensor network — it turns decentralized GPU clusters into a confidential AI factory. AI workloads run inside hardware-secured Trusted Execution Environments (TEE) using Kata Containers and Confidential Containers (CoCo), scheduled across Bittensor miner clusters by Armada, on decentralized RKE2 Kubernetes infrastructure.

**Key Partnerships:**
- NVIDIA Inception Program member (access to NeMo Microservices, NIM models, AI Blueprints)
- Confidential Computing Consortium (CCC) member
- OpenInfra Foundation contributor (Kata Containers)
- Direct collaboration with Intel and NVIDIA engineers

**Current Version:** 0.0.0 (early development/template stage)

## Bittensor Subnet Documentation

Bittensor subnet development documentation lives upstream — see the official [Bittensor docs](https://docs.bittensor.com) and [Learn Bittensor](https://learnbittensor.org) for subnet architecture, incentive design, and implementation patterns. Local KubeTEE subnet docs are under `docs/` (see [Research & Documentation](README.md#research--documentation) in the README).

**Key Insights (still load-bearing for this subnet):**
1. Most production subnets do NOT use traditional dendrite/synapse patterns — score measurable properties directly (this subnet reads the metagraph + Rancher v3 API directly, no synapse layer).
2. **NEVER write miner code** — only write `scripts/validator.py`; infrastructure miners register clusters and the validator scores them.
3. Keep subnets minimal — focus on the validator (the "referee"), leave ingenuity to miners.
4. 256 UID slots per subnet with dynamic registration costs provide sybil resistance.

## Common Development Commands

### Installation and Setup

```bash
# Install subnet package in development mode
pip install -e .

# Install dependencies
pip install -r requirements.txt
```

### Code Quality Checks

```bash
# Format check (line-length 79)
black --line-length 79 --exclude '(env|venv|.eggs|.git)' --check .

# Apply formatting
black --line-length 79 --exclude '(env|venv|.eggs|.git)' .

# Pylint check
pylint --fail-on=W,E,F --exit-zero ./
```

### Running Nodes

**Miner (requires 8x H100/H200/B200/B300 GPUs with TEE attestation):**

Infrastructure miners register their RKE2 clusters with Rancher Fleet (labeled with `kubetee.ai/*` hotkey/coldkey labels). No separate miner process is required - the validator communicates directly with the registered cluster via Rancher Fleet and scores it via TEE attestation + Armada job metrics. See `docs/NODE-REGISTRATION.md`.

**Validator (self-contained compose stack — see SUBNET.md):**
```bash
# Runs its own Rancher + localnet chain + validator
# The compose stack lives in the root kubetee workspace
cd ..
docker compose up -d --build
# Logs: http://localhost:8080 (dozzle)
```
`scripts/validator_entrypoint.py` bootstraps the subnet via `scripts/setup_single_node.py`, then execs `scripts/validator.py`, which reads `RANCHER_URL` / `RANCHER_BEARER_TOKEN` / optional transport-scoped `RANCHER_CA_FILE` / `KUBETEE_*` from the environment and fails fast on missing/invalid config.

### Local Development (Staging)

```bash
# Run local subtensor blockchain
cd subtensor
BUILD_BINARY=0 ./scripts/localnet.sh

# Chain endpoint for local development
--subtensor.chain_endpoint ws://127.0.0.1:9946

# Create subnet (costs τ1000 for first subnet)
btcli subnet create --wallet.name owner --subtensor.chain_endpoint ws://127.0.0.1:9946

# Register miner/validator
btcli subnet register --wallet.name miner --wallet.hotkey default --subtensor.chain_endpoint ws://127.0.0.1:9946

# Mint tokens from local faucet
btcli wallet faucet --wallet.name owner --subtensor.chain_endpoint ws://127.0.0.1:9946
```

### Wallet Management

```bash
# Create coldkey
btcli wallet new_coldkey --wallet.name <NAME>

# Create hotkey
btcli wallet new_hotkey --wallet.name <NAME> --wallet.hotkey <HOTKEY>

# Check wallet overview
btcli wallet overview --wallet.name <NAME>

# Add stake to validator
btcli stake add --wallet.name validator --wallet.hotkey default
```

## Architecture Overview

### Incentive Mechanism (Single: Infrastructure)

KubeTEE Early Access uses a **single Bittensor incentive mechanism** that distributes emissions as weights to miners based on the resources they provide in their RKE2 cluster and how reliably they execute Armada-scheduled confidential jobs. There is no benchmark, bounty, referral, or reseller mechanism — SN90 compute is already priced competitively because it is subsidized by Bittensor subnet emissions, and a referrer/reseller discount layer would be gamed for discounted pricing. Early Access pairs **emissions** (supply-side) with **Alpha / TAO paid jobs** priced at a **resources price per hour** — competitive and dynamic per the job queues (see [Competitive Pricing](README.md#competitive-pricing)). Fiat billing (USDC-on-BASE) remains a Phase 2 roadmap item.

**Mechanism: Infrastructure (100% emissions)**
- Rewards miners providing RKE2 cluster resources (GPU nodes) that run confidential AI jobs scheduled by Armada
- Metrics: TEE attestation (Intel TDX/SGX, NVIDIA CC), Armada job success/throughput/fair-share, uptime, resource utilization, FIPS-140-2 validated baseline (FIPS-140-3 Phase 3 target)
- **Competitive pricing (Phase 0, Early Access):** miners are scored against the other Bittensor compute subnets — Targon (SN4, supply-side payout feed via `stats.targon.com`), Lium (SN51, demand-side rental prices), Chutes (SN64, demand-side inference prices) — each with a verifiable feed (public API + on-chain metagraph). Targon GPU miners all run 8-card nodes (same form factor as SN90); live per-8-card-node payouts are B300 ~64, B200 ~52, H200 ~28, H100 ~24 TAO/epoch — the supply-side band SN90 miner compensation must match. The validator discovers a per-job-class target price from competitor signals, SN90 demand (Armada queue depth), and a **75% average utilization target**, then weights miners on whether their delivered compute is priced competitively. This same target price is the **resources price per hour** consumers pay in Alpha/TAO for the compute they consume (demand-side). A miner with perfect attestation but a price 2× the competitor average scores low. See `docs/COMPETITIVE-PRICING.md`.
- One hotkey per cluster; all nodes co-located in a single data center
- Fresh TEE attestation is a planned independent gate; it is not implemented
  by the current infrastructure-ready slice
- Location: `scripts/miner_scoring.py`

**Critical Detail:** A single weight matrix is used. The validator sets one
set of weights per epoch via Bittensor `set_weights` (no `mechanism_id`
split). The benchmark, bounty, referrer, and reseller mechanisms from the
earlier design are removed. The shipping Early Access validator produces a
binary infrastructure-readiness score from canonical enrollment identity,
Rancher readiness, HA topology, capacity, GPU passthrough, and runtime wiring.
Competitive pricing, fresh TEE attestation, Armada/job health, tunnel/probe,
workload identity, and KeyLease feeds remain roadmap dimensions.

### Core Architecture Layers

```
Entry Points (scripts/)
  └── validator_entrypoint.py - Container entrypoint (setup → exec validator)
        ↓
Setup (scripts/setup_single_node.py)
  └── btcli bootstrap: subnet, owner/alice/bob triad, stake, emissions, conviction/recycle
        ↓
Validator Loop (scripts/validator.py) — per cycle:
  ├── metagraph read (chain_state.py)
  ├── Rancher v3 enumeration (rancher_client.py) — GET-only, fail-closed pagination
  ├── reconciliation (reconciliation.py) — guarded deregistration on sustained absence
  ├── validation (infrastructure_validation.py) — pure fail-closed policy
  ├── scoring (miner_scoring.py) — verdict scores + S/N weight split
  ├── metrics (validator_metrics.py) — Prometheus + degraded-mode skip accountant
  └── set_weights on-chain (alice signs)
```

### Validator Cycle

**Per cycle (`scripts/validator.py`, spec 4.2):**
1. Read the metagraph (`scripts/chain_state.py`) — discover miners by hotkey
2. Enumerate clusters/nodes with GET-only Rancher v3 calls (`scripts/rancher_client.py`)
3. Reconcile — guarded deregistration of clusters whose hotkey has been absent from the metagraph for ≥3 cycles / ≥900s (`scripts/reconciliation.py`)
4. Validate — recompute the binary infrastructure verdict for every miner
   from the canonical binding and complete cluster/node snapshot
   (`scripts/infrastructure_validation.py`); explicit evidence failures score
   zero, while a Rancher evidence outage skips the whole cycle
5. Split weights between eligible miners and the owner recycle UID
   (`scripts/miner_scoring.py`)
6. Set weights on-chain via Bittensor `set_weights`, signed by alice
7. Emit bounded verdict metrics + aggregate cycle-evidence logs
   (`scripts/validator_metrics.py`)

Fail-fast at startup on any missing/invalid static config (D14); at runtime, Rancher outage / rejected set_weights / unexpected errors degrade to skip/backoff and the loop continues.

**Revenue Flow (Early Access + Phase 2):**
```
EARLY ACCESS (Phase 0):
     ├─→ Emissions → miners (supply-side: capacity rewards)
     └─→ Alpha / TAO paid jobs → resource-hours consumed
          (price competitive vs Targon/Lium/Chutes, dynamic per job queues)
     ↓
MINER (runs confidential Armada jobs)
     ↓
VALIDATOR → set_weights → Bittensor emissions to miners

PHASE 2 (planned):
     ├─→ USDC-on-BASE job billing (fiat, layered on resources-per-hour pricing)
```

### Validator Rancher API Access (hotkey-signed auth)

Validators read cluster metrics and information from the **Rancher v3 REST API** (management cluster at `RANCHER_URL`, e.g. `https://staging-rancher.kubetee.ai`) — cluster state, node health/capacity, resource usage, and Fleet/Armada-derived info — in addition to Prometheus. This supersedes direct Rancher Fleet API access for scoring inputs.

**Chosen mechanism — hotkey-signed auth via an auth mechanism connected to Rancher:**
- A Rancher v3 call requires a bearer token (`Authorization: Bearer token-xxxxx:yyyyy`); the kubeconfig client cert used for `kubectl` does **not** work for `/v3`.
- **Planned flow:** the validator (or miner) signs a challenge with its Bittensor **hotkey** (SR25519). An auth mechanism connected to Rancher — a custom external auth provider (SAML / OIDC) backed by the subnet — verifies the signature on-chain and maps the hotkey to a Rancher principal. Tracked as tasks in the subnet [Roadmap](README.md#roadmap) (Phase 0).
  - **Validators (current combined runtime)** require a short-lived/rotatable least-privilege token with cluster/node GET/list plus cluster DELETE for guarded deregistration, and no create/update/patch or unrelated-resource authority. A truly read-only scoring token requires reconciliation to move behind a separate operator-owned mutation credential/controller.
  - **Miners** receive a **read-only** principal (bound to `cluster-readonly`) scoped to **their own cluster** (the cluster carrying their canonical `kubetee.ai/hotkey` binding), provisioned automatically **when a new cluster is created** — they can observe their cluster (nodes, workloads, metrics) while the subnet owner manages it via Fleet GitOps.
- Alternative considered (not chosen): **Subnet-owner-issued per-validator tokens** — the subnet owner pre-provisions the narrow Rancher API key per validator hotkey (delivered out-of-band); the validator loads it like `.env`. Simpler but moves trust to out-of-band delivery and lacks hotkey-binding.
- Whatever the mechanism: validator tokens must remain bounded to cluster/node reads plus guarded cluster deletion; miner tokens are read-only and scoped to their own cluster; all tokens are short-lived or rotatable and never exposed.

### Key Files and Locations

**Entry Points:**
- `scripts/validator_entrypoint.py` - Container entrypoint: runs `setup_single_node.py` (btcli bootstrap) then execs the validator
- `scripts/validator.py` - Validator main loop (g004): metagraph → Rancher enumeration → reconciliation → scoring → set_weights, with fail-fast startup and degraded-mode skip/backoff

**Core Scoring & Reconciliation:**
- `scripts/infrastructure_validation.py` - Pure canonical-binding and infrastructure-readiness policy
- `scripts/miner_scoring.py` - Miner identity validation + verdict-to-weight S/N split
- `scripts/reconciliation.py` - Guarded deregistration engine (absence thresholds, pre-delete recheck, protected clusters)
- `scripts/validator_metrics.py` - Prometheus metrics + degraded-mode skip accountant
- `scripts/chain_state.py` - Real on-chain ownership/stake queries (no hardcoded values)

**Rancher & Setup:**
- `scripts/rancher_client.py` - Contained Rancher v3 client (origin-pinned, endpoint allowlist, fail-closed pagination)
- `scripts/rancher_provision.sh` - Mints the least-privilege `kubetee-validator` Rancher token + labels the disposable miner cluster
- `scripts/setup_single_node.py` - btcli bootstrap (subnet, owner/alice/bob triad, stake, emissions, conviction/recycle hypers)
- `scripts/print_subnet_stats.py` - Subnet stats printer (reuses one Subtensor connection)

**Smart Contracts (Phase 2, not in Early Access):**
Payment processing, escrow, and Alpha recycling contracts (BASE L2) plus the Bittensor EVM registry are planned for Phase 2 and are **not included** in the Early Access repo.

**Hardware Requirements:**
- `docs/GPU-NODE-REQUIREMENTS.md` - Miner: 8x H100/H200/B200 GPUs with TEE attestation, Validator: no GPU needed

**Scoring & Economics Docs:**
- `docs/COMPETITIVE-PRICING.md` - Competitive pricing scoring design: Targon/Lium/Chutes price feeds, per-class target price, 75% utilization target, how price becomes weights — Phase 0 (Early Access); the target price doubles as the resources price per hour for Alpha/TAO paid jobs
- `docs/TOKENOMICS.md` - Utility token & DePIN model: recycle vs burn, no-treasury securities posture, cross-subnet consumption loop, subsidy trajectory

**Job Pricing MCP Server (design concept, Phase 1):** an agent-facing [MCP](https://modelcontextprotocol.io/) server that prices and deploys confidential compute jobs. It is a **read client of the validator's published target price** (Phase 0 Competitive Pricing) — not a price-setter. Tools: `get_target_price(job_class, gpu_type)`, `quote_job(resources, duration, job_class)` → resource-hours × target price per hour = Alpha/TAO cost, `submit_job(job_spec, priced)` → Armada queue with a confidential `runtimeClassName`. Control-plane only (prices + queues; never sees job data); job pods run in `kata-qemu-nvidia-gpu-tdx` / `kata-qemu-tdx` TEEs; payment settled on-chain / Phase 2 escrow. Used by end-user agents and orchestrators (Airflow / Metaflow). See README "Job Pricing MCP Server".

## Development Workflow

**Commit & Push Policy:**
- **Always commit and push when there is a change.** After completing a unit of work (an edit, a fix, a documentation update, a feature), stage, commit, and push it to `origin` — do not leave finished work sitting uncommitted in the working tree.
- Commit only what was actually changed for the task; do not sweep unrelated files into the commit.
- Follow the commit message convention: `<type>(subnet): <description>` with types `feat`, `fix`, `docs`, `refactor`, `chore`.
- Push immediately after committing so `origin/main` reflects the current state of the work. If a push is rejected (remote moved), rebase on `origin/main` and push again — never force-push to `main`.
- If a change is intentionally incomplete or WIP, say so explicitly in the commit message rather than leaving it uncommitted.

**Branch Strategy:**
- `main` - Production branch (protected)
- `staging` - Active development branch
- `feature/<ticket>/<description>` - Feature branches
- `release/<version>/<description>` - Release preparation
- `hotfix/<version>/<description>` - Critical fixes

**Feature Development:**
1. Branch from `staging`: `git checkout -b feature/my-feature staging`
2. Develop and test locally
3. Open PR against `staging`
4. CI/CD checks must pass (black, pylint, build)
5. Merge to `staging`
6. Delete feature branch

**Release Process:**
1. Create release branch from `staging`
2. Bump version (e.g., in `requirements.txt` / image tag)
3. Merge to `main`
4. Tag release: `git tag -a v<VERSION> -m "Release <VERSION>"`
5. Back-merge to `staging`

## CI/CD Pipeline

**Code Quality Checks (run locally or via repo CI):**
- `black` - Code formatting check (line-length 79)
- `pylint` - Static code analysis
- `build` - Install and validate package

**Python Version Support:** 3.13+

All PRs must pass: black, pylint, and build checks.

### Claude GitHub Actions

Every PR triggers **Claude Code GitHub Actions** for automated AI-powered review and validation:

**Security Checks:**
- Vulnerability scanning in dependencies
- Secret detection (API keys, credentials)
- Smart contract security analysis
- Supply chain attack prevention

**Code Quality:**
- AI-powered code review with context-aware suggestions
- Architecture consistency validation
- Best practices enforcement
- Documentation completeness check

**Testing:**
- Test coverage analysis
- Edge case identification
- Integration test validation
- Regression risk assessment

**Automated Workflows:**
- PR description generation and enhancement
- Commit message quality checks
- Breaking change detection
- Dependency update recommendations

**Configuration:** `.github/workflows/claude.yml`

All PRs require Claude Code review approval.

## Technology Stack

**Core Framework:**
- bittensor (>=11.0.0.dev0) — Bittensor v11+ unified package (SDK + btcli), from [RaoFoundation/subtensor](https://github.com/RaoFoundation/subtensor) (`sdk/python`). Dev pre-release; SDK deps are `websockets`, `bittensor-core`, `typer`, `rich`, `eth-account` (no starlette/pydantic/torch). **TODO: bump pin to `>=11.0.0` once the stable 11.0.0 release is published.**

**NVIDIA Stack:**
- NeMo Microservices - LLM inference
- NIM Models - Pre-trained models
- AI Blueprints:
  - RAG (Retrieval-Augmented Generation)
  - Video Search and Summarization
  - Streaming Data to RAG
  - NeMo Retriever Microservice
- NIM Operator (experimental Kata & Dynamo support):
  - [Kata Sandbox Workloads (Experimental)](https://docs.nvidia.com/nim-operator/latest/kata-sandbox.html) — `NIMService` with `runtimeClassName: kata-qemu-nvidia-gpu`; NVIDIA preview, not production; CoCo support planned for a future release
  - [Dynamo (Experimental)](https://docs.nvidia.com/nim-operator/latest/dynamo.html) — `DynamoGraphDeployment` CRDs via `dynamo.enabled=true`; OpenAI-compatible frontend, disaggregated serving
  - **Status:** both are NVIDIA-marked *experimental / not production*. KubeTEE is working directly with the NVIDIA NIM Operator team and the Kata Containers team to harden these for production confidential deployments. Until then, NeMo Microservices on KubeTEE run on the **stable** `kata-qemu-nvidia-gpu-tdx` / `kata-qemu-tdx` runtime classes; NIM Operator Kata/Dynamo paths are a Phase 2+ roadmap item.
  - **Kata/CoCo limitations (NVIDIA, verifiable):** NIM Operator Kata sandbox is *not* CC (no encryption; `kata-qemu-nvidia-gpu`, GPU Op in `cc.mode=off`); CoCo + NIMCache unsupported in the Operator today. The stable CoCo reference architecture is containerd-only, requires all GPUs on a host in CC mode (single confidential VM for multi-GPU), no nested virt, no PCI P2P DMA, no host-side NVIDIA driver (VFIO passthrough). NIM Operator does not configure multi-node NIM microservices. Sources: [Kata Sandbox](https://docs.nvidia.com/nim-operator/latest/kata-sandbox.html), [CoCo Reference Architecture](https://docs.nvidia.com/datacenter/cloud-native/confidential-containers/latest/overview.html), [NIM Operator Release Notes](https://docs.nvidia.com/nim-operator/latest/release-notes.html).
  - **Bittensor subnet integrations (SOTA, confidential-ready):** KubeTEE replaces/augments NeMo stack layers with SOTA Bittensor subnets run inside `kata-qemu-nvidia-gpu-tdx` / `kata-qemu-tdx` — Gradients SN56 (AutoML fine-tuning → NeMo Customizer), Affine SN120 (RL/reason mining → Customizer), Albedo SN97 (coding-LLM king-of-the-hill → Customizer/eval), Orion SN27 (data curation → Data Designer), Desearch SN22 (real-time search → Retriever/RAG), Chutes SN64 + Parallax (decentralized MoE training/inference, TEE-only migration → distributed training/inference), Hippius SN75 (S3+IPFS storage, already AMD SEV-SNP CC → solves CoCo ephemeral-data-only limit), Ditto SN118 (agent memory/context), **BitSec SN60 (security gate — design concept, planned pre-promotion analysis of AI workload code/image before staging/production; to be detailed during integration)**. Open set — any subnet with a verifiable SOTA feed for a NeMo layer is a candidate. See README "Bittensor Subnet Integrations (SOTA, Confidential-Ready)" and "BitSec SN60 — Security Gate for AI Workload Promotion".

**Infrastructure:**
- Kubernetes (RKE2) - FIPS-140-2 validated container orchestration (FIPS-140-3 as a Phase 3 target)
- Rancher - Multi-cluster management
- Kata Containers - Secure container runtime with TEE support
- Prometheus - Metrics collection

**Security:**
- Intel TDX/SGX - CPU-based TEE
- NVIDIA Confidential Computing - GPU-based TEE (Hopper/Blackwell)
- FIPS-140-2 validated baseline (FIPS-140-3 as a Phase 3 target)

**Blockchain:**
- Bittensor - native emissions via `set_weights` (Early Access)
- BASE L2 (Coinbase) - USDC payments (Phase 2)
- Solidity smart contracts - Phase 2 (not in Early Access repo)

## Important Implementation Patterns

### Adding a Scoring Input

The g004 validator has no synapse/protocol layer — it reads the metagraph and the Rancher v3 API directly. To add a new scoring input:
1. Extend `scripts/rancher_client.py` (or add a new read-only client) for the new data source
2. Fold the new signal into `scripts/miner_scoring.py`'s score calculation
3. Keep the binary fail-closed posture and the S/N weight-split invariants

### Adding a New Mechanism (post-Early-Access)

Early Access uses a single Infrastructure mechanism in `scripts/miner_scoring.py`. To add a second mechanism later:
1. Add a new scorer module under `scripts/`
2. Combine its output with `scripts/miner_scoring.py`'s weights
3. Keep weights normalized (sum to 1.0)
4. Configure on-chain emission splits if needed

### Modifying Scoring Logic

1. Update `scripts/miner_scoring.py` (the single scorer)
2. Preserve the invariants: fail-closed liveness, S/N split, weights sum to 1.0
3. Test in isolation (`tests/test_miner_scoring.py`) before deploying

### Weight Setting

Early Access sets a single weight matrix (no `mechanism_id` split):
```python
self.subtensor.set_weights(
    wallet=self.wallet,
    netuid=self.config.netuid,
    uids=uids,
    weights=weights,
)
```

## Debugging and Monitoring

**Validator Logs:**
- Location: `~/.bittensor/validators/<netuid>/`
- Infrastructure mechanism stats logged every 60s
- Use `bt.logging` at appropriate levels (trace, debug, info, warning, error)

**Miner Verification:**
```bash
# Check if registered
btcli subnets list

# Check wallet overview
btcli wallet overview --wallet.name miner

# Monitor axon for incoming requests (check logs)
```

**Testing Connectivity:**
- Use Dummy protocol for basic connectivity tests
- Verify blacklist/priority logic in miner
- Test with `--logging.debug` flag

## Security Considerations

**TEE Requirements:**
- Miners MUST provide TEE attestation (Intel TDX/SGX or NVIDIA CC)
- 8-GPU nodes required (H100/H200/B200/B300)
- FIPS-140-2 validated baseline mandatory (FIPS-140-3 as a Phase 3 target)

**Blacklist Logic:**
- Implemented in miner's `blacklist()` method
- Priority queue based on stake
- Reject requests from unauthorized validators

**Data Protection:**
- End-to-end encrypted compute pipeline
- Confidential Computing at both CPU and GPU level
- No data leaves TEE without encryption

## Project-Specific Notes

**Current State:** This is an early-stage template (v0.0.0) with production-ready architecture but placeholder implementations. The infrastructure requires:
- Full NVIDIA stack integration (NeMo, NIM, Blueprints)
- Armada multi-cluster batch scheduler integration
- Multi-cluster Kubernetes setup with Rancher Fleet (RKE2)
- TEE attestation service integration (Kata + CoCo)
- FIPS-140-2 validated baseline (FIPS-140-3 as a Phase 3 target)

**Miner Implementation:** Infrastructure miners register their RKE2 clusters with Rancher Fleet (no separate miner process). Validators communicate directly with registered Kubernetes clusters via Rancher Fleet and score them via TEE attestation + Armada job metrics. Miners must provide:
- Kubernetes cluster with Rancher Fleet agent
- TEE attestation (Intel TDX/SGX or NVIDIA CC)
- 8x H100/H200/B200 GPUs minimum
- Health metrics exposed via Prometheus

**Validator Implementation:** The validator handles:
- Single Infrastructure mechanism scoring via MechanismManager
- TEE attestation verification (Kata cronjobs)
- Armada job metric collection via Prometheus + Rancher v3 API (cluster/node state, resource info)
- Weight calculation and on-chain `set_weights` (single mechanism)

**Smart Contracts (Phase 2):** Deployment targets (not in Early Access):
- BASE L2 (Coinbase) - USDC job billing, escrow, Alpha recycling
- Bittensor EVM - optional Phase 2 registry (Early Access emissions are native `set_weights`, no contract)

## Key Takeaways

1. Early Access uses a **single Infrastructure incentive mechanism** that distributes emissions as weights to miners based on RKE2 cluster resources and Armada job execution
2. **Single weight matrix** — validator sets one set of weights per epoch (no multi-mechanism split)
3. **TEE is mandatory** for miners (Intel TDX/SGX, NVIDIA Confidential Computing) — no attestation = no emissions
4. **NVIDIA AI stack** (NeMo, NIM, Blueprints) runs as Armada-scheduled confidential jobs in Kata + CoCo TEE
5. **Armada** is the multi-cluster batch scheduler across RKE2 miner clusters (one hotkey per cluster, single data center)
6. **Early Access billing is emissions + Alpha/TAO paid jobs** — emissions reward miners for capacity (supply-side); consumers pay Alpha/TAO at a **resources price per hour** for compute consumed (demand-side), priced competitively vs Targon/Lium/Chutes and dynamically per the job queues. USDC-on-BASE fiat billing is a Phase 2 roadmap item. There is no referrer / reseller program — compute is already competitively priced via Bittensor emission subsidies, and a discount layer would be gamed
7. **Security-first design** — FIPS-140-2 validated RKE2 baseline in Early Access (FIPS-140-3 as a Phase 3 target), CCC membership, confidential computing throughout
8. **Hardware requirements** — 8x H100/H200/B200 GPUs minimum for miners
9. **Current version 0.0.0** indicates template stage — production deployment requires significant additional work
