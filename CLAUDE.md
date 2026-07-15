# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KubeTEE AI is an enterprise-grade AI-as-a-Service (AIaaS) platform built on the Bittensor decentralized network. It provides Deep Research AI Agents running in Trusted Execution Environments (TEE) on decentralized Kubernetes infrastructure.

**Key Partnerships:**
- NVIDIA Inception Program member (access to NeMo Microservices, NIM models, AI Blueprints)
- Confidential Computing Consortium (CCC) member
- OpenInfra Foundation contributor (Kata Containers)
- Direct collaboration with Intel and NVIDIA engineers

**Current Version:** 0.0.0 (early development/template stage)

## Bittensor Subnet Documentation

Comprehensive Bittensor subnet development documentation is available in `docs/Chi/docs/`. This is essential reading for understanding subnet architecture, incentive design, and implementation patterns.

**Start Here:**
- `docs/Chi/docs/17-writing-a-subnet.md` - Simplicity-first approach, "what am I measuring?"
- `docs/Chi/docs/15-validator-only-development.md` - **CRITICAL**: Validator-only development philosophy

**Foundational Concepts:**
- `docs/Chi/docs/01-overview.md` - What Bittensor is, key roles, network structure
- `docs/Chi/docs/02-core-concepts.md` - Subnets, neurons, keys, tokens, stake, metagraph
- `docs/Chi/docs/03-architecture.md` - Chain layer, SDK layer, communication primitives

**Subnet Development:**
- `docs/Chi/docs/04-mechanism-patterns.md` - **CRITICAL**: Production mechanism architectures (NOT just dendrite/synapse)
- `docs/Chi/docs/06-building-miners.md` - Implementing miners across different patterns
- `docs/Chi/docs/07-building-validators.md` - Scoring algorithms and weight setting
- `docs/Chi/docs/08-incentive-design.md` - Designing effective reward mechanisms

**Technical Reference:**
- `docs/Chi/docs/09-python-sdk.md` - SDK classes, methods, usage patterns
- `docs/Chi/docs/10-btcli-reference.md` - Command-line interface reference
- `docs/Chi/docs/11-hyperparameters.md` - Configurable subnet parameters
- `docs/Chi/docs/12-epoch-mechanism.md` - On-chain consensus and emissions

**Deployment:**
- `docs/Chi/docs/13-local-development.md` - Running localnet for development
- `docs/Chi/docs/14-deployment.md` - Testnet and mainnet deployment
- `docs/Chi/docs/16-how-to-use-template.md` - Step-by-step guide to creating a subnet

**Key Insights from Chi Docs:**
1. Most production subnets do NOT use traditional dendrite/synapse patterns - see `04-mechanism-patterns.md`
2. **NEVER write miner code** - only write `validator.py`, miners read it to understand the interface
3. Keep subnets minimal - focus on the validator (the "referee"), leave ingenuity to miners
4. 256 UID slots per subnet with dynamic registration costs provide sybil resistance

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

**Miner (requires 8x H100/H200/B200 GPUs with TEE attestation):**

Infrastructure miners register their RKE2 clusters with Rancher Fleet (labeled with `kubetee.ai/*` hotkey/coldkey labels). No separate miner process is required - the validator communicates directly with the registered cluster via Rancher Fleet and scores it via TEE attestation + Armada job metrics. See `docs/NODE-REGISTRATION.md`.

**Validator:**
```bash
python neurons/validator.py \
  --netuid <NETUID> \
  --subtensor.chain_endpoint <ENDPOINT> \
  --wallet.name <WALLET_NAME> \
  --wallet.hotkey <HOTKEY> \
  --logging.debug
```

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

KubeTEE Early Access uses a **single Bittensor incentive mechanism** that distributes emissions as weights to miners based on the resources they provide in their RKE2 cluster and how reliably they execute Armada-scheduled confidential jobs. There is no benchmark, bounty, or referral mechanism in Early Access — payments and revenue share are a Phase 2 roadmap item.

**Mechanism: Infrastructure (100% emissions)**
- Rewards miners providing RKE2 cluster resources (GPU nodes) that run confidential AI jobs scheduled by Armada
- Metrics: TEE attestation (Intel TDX/SGX, NVIDIA CC), Armada job success/throughput/fair-share, uptime, resource utilization, FIPS-140-3 progress
- One hotkey per cluster; all nodes co-located in a single data center
- No attestation = no emissions
- Location: `template/mechanisms/infrastructure.py`

**Critical Detail:** A single weight matrix is used. The validator sets one set of weights per epoch via Bittensor `set_weights` (no `mechanism_id` split). The benchmark, bounty treasury, and referrer mechanisms from the earlier design are removed for Early Access.

### Core Architecture Layers

```
Entry Points (neurons/)
  └── validator.py - Main validator loop
        ↓
Base Abstractions (template/base/)
  ├── neuron.py - BaseNeuron (core lifecycle)
  └── validator.py - BaseValidatorNeuron
        ↓
Protocol Definitions (template/protocol.py)
  ├── ServiceRequest - AI inference with revenue tracking
  ├── InfrastructureStatus - Health and capacity reporting
  └── Dummy - Connectivity testing
        ↓
Mechanism Coordination (template/mechanisms/)
  ├── manager.py - MechanismManager (coordinates the single Infrastructure mechanism)
  ├── definitions.py - Single mechanism configuration (Infrastructure 100%)
  └── infrastructure.py - Infrastructure scoring (TEE, Armada jobs, uptime, capacity)
        ↓
Validator Logic (template/validator/)
  ├── forward.py - Query miners, track revenue
  ├── reward.py - Calculate rewards
  └── revenue.py - Revenue tracking
```

### Protocol Flow

**Forward Pass (template/validator/forward.py):**
1. Query infrastructure status from all miners (one hotkey per RKE2 cluster)
2. Verify TEE attestation per cluster (Kata cronjobs)
3. Pull Armada job metrics (success, throughput, fair-share) via Prometheus, and cluster/node state + resource info from the Rancher v3 API
4. Run connectivity tests (dummy protocol)
5. Calculate a single Infrastructure weight per miner
6. Set weights on-chain via Bittensor `set_weights` (single mechanism)

**Revenue Flow (Phase 2, not in Early Access):**
```
EARLY ACCESS: emissions only
     ↓
MINER (runs confidential Armada jobs)
     ↓
VALIDATOR → set_weights → Bittensor emissions to miners

PHASE 2 (planned):
     ├─→ USDC-on-BASE job billing
     └─→ Referrer / reseller revenue share
```

### Validator Rancher API Access (design TBD)

Validators read cluster metrics and information from the **Rancher v3 REST API** (management cluster at `RANCHER_URL`, e.g. `https://staging-rancher.kubetee.ai`) — cluster state, node health/capacity, resource usage, and Fleet/Armada-derived info — in addition to Prometheus. This supersedes direct Rancher Fleet API access for scoring inputs.

**Open design — how a validator obtains a Rancher bearer token after signing in as a validator with its Bittensor hotkey:**
- A Rancher v3 call requires a bearer token (`Authorization: Bearer token-xxxxx:yyyyy`); the kubeconfig client cert used for `kubectl` does **not** work for `/v3`.
- **Chosen approach (preferred): Rancher external auth mapped to Bittensor hotkeys** — register each Bittensor hotkey (**validators and miners**) as a Rancher principal via a custom auth provider (SAML / OIDC) backed by the subnet, so a node signs in with its hotkey and receives a session/API token for the v3 API. Tracked as tasks in the subnet [Roadmap](README.md#roadmap) (Phase 0).
  - **Validators** receive a **read-only** token (bound to `cluster-readonly`) to pull cluster/node metrics across clusters for scoring.
  - **Miners** receive a **read-only** principal (bound to `cluster-readonly`) scoped to **their own cluster** (the cluster labeled with their `kubetee.ai/miner-hotkey`), provisioned automatically **when a new cluster is created** — they can observe their cluster (nodes, workloads, metrics) while the subnet owner manages it via Fleet GitOps.
- Alternatives considered (not chosen):
  1. **Signed-hotkey challenge** — the validator signs a challenge with its Bittensor hotkey; a subnet-owner-operated service verifies the signature on-chain and mints a short-lived, read-only Rancher API token (scoped to the validator's cluster(s)) via the v3 API.
  2. **Subnet-owner-issued per-validator tokens** — the subnet owner pre-provisions a read-only Rancher API key per validator hotkey (delivered out-of-band); the validator loads it like `.env`.
- Whatever the mechanism: validator tokens must be **read-only** (bound to `cluster-readonly`); miner tokens are scoped to their own cluster; all tokens are **short-lived or rotatable** and never exposed.
- References: `../CREATE-CLUSTER-GUIDE.md` (v3 API + `.env` token sourcing), `../cluster-readonly-roletemplate.yaml` (read-only RoleTemplate to bind validator principals to).

### Key Files and Locations

**Entry Points:**
- `neurons/validator.py` - Validator main loop, runs forward pass, sets weights for the single Infrastructure mechanism

**Core Mechanisms:**
- `template/mechanisms/definitions.py` - Single mechanism configuration (Infrastructure 100%)
- `template/mechanisms/manager.py` - MechanismManager coordinates the Infrastructure mechanism
- `template/mechanisms/infrastructure.py` - InfrastructureScorer (TEE attestation, Armada job metrics, uptime, capacity, FIPS-140-3)
- `template/reseller/` - Phase 2 reseller/referral code (not active in Early Access)

**Protocol and Base:**
- `template/protocol.py` - Synapse definitions (ServiceRequest, InfrastructureStatus, Dummy)
- `template/base/neuron.py` - BaseNeuron with lifecycle management
- `template/__init__.py` - Version management (`__version__ = "0.0.0"`)

**Smart Contracts (Phase 2, not in Early Access):**
Payment processing, escrow, reseller/referrer attribution, and buyback/treasury contracts (BASE L2) plus the Bittensor EVM registry are planned for Phase 2 and are **not included** in the Early Access repo.

**Hardware Requirements:**
- `docs/GPU-NODE-REQUIREMENTS.md` - Miner: 8x H100/H200/B200 GPUs with TEE attestation, Validator: no GPU needed

## Development Workflow

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
2. Update version in `template/__init__.py`
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
- Bittensor SDK (>=9.11.1) - Decentralized network protocol
- Starlette (>=0.30.0) - ASGI web framework
- Pydantic (>=2) - Data validation
- PyTorch (>=2) - ML model support

**NVIDIA Stack:**
- NeMo Microservices - LLM inference
- NIM Models - Pre-trained models
- AI Blueprints:
  - AIQ Research Assistant
  - RAG (Retrieval-Augmented Generation)
  - Video Search and Summarization
  - Streaming Data to RAG
  - NeMo Retriever Microservice

**Infrastructure:**
- Kubernetes (RKE2) - FIPS-140-2 validated container orchestration (FIPS-140-3 target)
- Rancher - Multi-cluster management
- Kata Containers - Secure container runtime with TEE support
- Prometheus - Metrics collection

**Security:**
- Intel TDX/SGX - CPU-based TEE
- NVIDIA Confidential Computing - GPU-based TEE (Hopper/Blackwell)
- FIPS-140-3 target on a FIPS-140-2 validated baseline

**Blockchain:**
- Bittensor - native emissions via `set_weights` (Early Access)
- BASE L2 (Coinbase) - USDC payments (Phase 2)
- Solidity smart contracts - Phase 2 (not in Early Access repo)

## Important Implementation Patterns

### Adding a New Protocol

1. Define in `template/protocol.py` as `bt.Synapse` subclass:
```python
class MyProtocol(bt.Synapse):
    # Define fields
    def deserialize(self) -> "MyProtocol":
        return self
```

2. Validators query miners via Rancher Fleet API (no miner process needed)
3. Add query logic in validator's `forward()` (`template/validator/forward.py`)

### Adding a New Mechanism (post-Early-Access)

Early Access uses a single Infrastructure mechanism. To add a second mechanism later:
1. Create scorer in `template/mechanisms/<mechanism_name>.py`
2. Add to `definitions.py` MECHANISMS list
3. Update emission splits (must sum to 100%)
4. Register in MechanismManager
5. Configure on-chain via `configure_emission_splits()`

### Modifying Scoring Logic

1. Update `template/mechanisms/infrastructure.py` (the single scorer)
2. Implement `calculate_weights()` method
3. Weights should be normalized (sum to 1.0)
4. Test in isolation before deploying

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
- FIPS-140-3 target (FIPS-140-2 validated baseline) mandatory

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
- FIPS-140-3 target on a FIPS-140-2 validated baseline

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
- (Phase 2) Revenue tracking and reseller/referrer payment distribution

**Smart Contracts (Phase 2):** Deployment targets (not in Early Access):
- BASE L2 (Coinbase) - USDC job billing, escrow, reseller/referrer attribution, buyback/treasury
- Bittensor EVM - optional Phase 2 registry (Early Access emissions are native `set_weights`, no contract)

## Key Takeaways

1. Early Access uses a **single Infrastructure incentive mechanism** that distributes emissions as weights to miners based on RKE2 cluster resources and Armada job execution
2. **Single weight matrix** — validator sets one set of weights per epoch (no multi-mechanism split)
3. **TEE is mandatory** for miners (Intel TDX/SGX, NVIDIA Confidential Computing) — no attestation = no emissions
4. **NVIDIA AI stack** (NeMo, NIM, Blueprints) runs as Armada-scheduled confidential jobs in Kata + CoCo TEE
5. **Armada** is the multi-cluster batch scheduler across RKE2 miner clusters (one hotkey per cluster, single data center)
6. **Payments are Phase 2** — emissions-only in Early Access; USDC-on-BASE billing, revenue share, and referral program are roadmap
7. **Security-first design** — FIPS-140-3 target on FIPS-140-2 validated RKE2, CCC membership, confidential computing throughout
8. **Hardware requirements** — 8x H100/H200/B200 GPUs minimum for miners
9. **Current version 0.0.0** indicates template stage — production deployment requires significant additional work
