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
```bash
python neurons/miner.py \
  --netuid <NETUID> \
  --subtensor.chain_endpoint <ENDPOINT> \
  --wallet.name <WALLET_NAME> \
  --wallet.hotkey <HOTKEY> \
  --logging.debug
```

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

### Multi-Mechanism Incentive System

This subnet implements **native Bittensor multiple incentive mechanisms** with three on-chain mechanisms plus an off-chain referral program:

1. **Mechanism 0: Infrastructure (60% emissions)**
   - Rewards miners providing Kubernetes infrastructure
   - Metrics: uptime, TEE compliance, latency, GPU capacity
   - Miners receive **50% revenue share** from service requests
   - Location: `template/mechanisms/infrastructure.py`

2. **Mechanism 1: Benchmark Competition (30% emissions)**
   - Rewards DeepResearch Benchmark improvements
   - **Lifetime Score with Decay** model (5% monthly decay, 30% floor)
   - Early improvers continue earning even after others improve
   - Location: `template/mechanisms/benchmark.py`

3. **Mechanism 2: Bounty Treasury (10% emissions)**
   - Treasury key accumulates emissions for development bounties
   - Fixed TAO values (paid in Alpha tokens) per bounty
   - Manual payout by subnet owner when PR is merged
   - Location: `template/mechanisms/bounty_treasury.py`

4. **Referrers (NO emissions, 50% revenue share)**
   - NOT registered on Bittensor subnet (no emissions)
   - Register via CLI, get unique referral code
   - Earn 50% of revenue from referred users
   - Location: `template/reseller/referral.py`

**Critical Detail:** Three mechanisms use emissions (Infrastructure 60%, Benchmark 30%, Bounty Treasury 10%). Referrers use pure revenue share with NO emissions. Each mechanism has separate weight matrices and independent Yuma Consensus calculations.

### Core Architecture Layers

```
Entry Points (neurons/)
  ├── validator.py - Main validator loop
  └── miner.py - Main miner loop
        ↓
Base Abstractions (template/base/)
  ├── neuron.py - BaseNeuron (core lifecycle)
  ├── validator.py - BaseValidatorNeuron
  └── miner.py - BaseMinerNeuron
        ↓
Protocol Definitions (template/protocol.py)
  ├── ServiceRequest - AI inference with revenue tracking
  ├── InfrastructureStatus - Health and capacity reporting
  └── Dummy - Connectivity testing
        ↓
Mechanism Coordination (template/mechanisms/)
  ├── manager.py - MechanismManager (coordinates all mechanisms)
  ├── definitions.py - Mechanism configurations (60/30/10 split)
  ├── infrastructure.py - Infrastructure scoring (Mechanism 0)
  ├── benchmark.py - Benchmark scoring with Lifetime Decay (Mechanism 1)
  └── bounty_treasury.py - Treasury accumulation for bounties (Mechanism 2)
        ↓
Validator Logic (template/validator/)
  ├── forward.py - Query miners, track revenue
  ├── reward.py - Calculate rewards
  └── revenue.py - Revenue tracking
```

### Protocol Flow

**Forward Pass (template/validator/forward.py):**
1. Query infrastructure status from all miners
2. Process pending service requests (with revenue tracking)
3. Run connectivity tests (dummy protocol)
4. Record metrics per mechanism
5. Calculate weights per mechanism
6. Set weights using `mechanism_id` parameter

**Revenue Flow:**
```
USER REQUEST
     ↓
VALIDATOR (processes request)
     ↓
MINER (serves request)
     ↓
REVENUE TRACKING
     ├─→ Infrastructure Miner: 50% of revenue
     ├─→ KubeTEE Owner: 50% (or 25% if referred)
     └─→ Referrer: 50% of revenue (if user was referred)
```

### Key Files and Locations

**Entry Points:**
- `neurons/validator.py` - Validator main loop, initializes MechanismManager, runs forward pass, sets weights
- `neurons/miner.py` - Miner main loop, implements forward() to process requests

**Core Mechanisms:**
- `template/mechanisms/definitions.py` - Emission splits (60/40/0), mechanism configurations
- `template/mechanisms/manager.py` - MechanismManager coordinates all mechanisms
- `template/mechanisms/infrastructure.py` - InfrastructureScorer (health, latency, TEE, revenue)
- `template/mechanisms/open_source.py` - OpenSourceScorer (benchmark scores, code quality)
- `template/reseller/referral.py` - ReferralManager (50% revenue share, NO emissions)

**Protocol and Base:**
- `template/protocol.py` - Synapse definitions (ServiceRequest, InfrastructureStatus, Dummy)
- `template/base/neuron.py` - BaseNeuron with lifecycle management
- `template/__init__.py` - Version management (`__version__ = "0.0.0"`)

**Smart Contracts:**
- `contracts/KubeTEEPayment.sol` - Payment processing
- `contracts/KubeTEEBuybackBurn.sol` - Deflationary tokenomics
- `contracts/KubeTEEEscrow.sol` - Miner payment escrow
- `contracts/KubeTEEReseller.sol` - Referrer tracking

**Hardware Requirements:**
- `min_compute.yml` - Miner: 8x H100/H200/B200 GPUs with TEE attestation, Validator: no GPU needed

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

**CircleCI Jobs (.circleci/config.yml):**
- `black` - Code formatting check (line-length 79)
- `pylint` - Static code analysis
- `check_compatibility` - Python 3.8-3.11 compatibility
- `build` - Install and validate package

**Python Version Support:** 3.8, 3.9, 3.10, 3.11

All PRs must pass: black, pylint, and build checks.

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
- Kubernetes (RKE2) - FIPS-140-2 certified container orchestration
- Rancher - Multi-cluster management
- Kata Containers - Secure container runtime with TEE support
- Prometheus - Metrics collection

**Security:**
- Intel TDX/SGX - CPU-based TEE
- NVIDIA Confidential Computing - GPU-based TEE (Hopper/Blackwell)
- FIPS-140-2 compliance

**Blockchain:**
- Solidity smart contracts
- BASE L2 (Coinbase) - USDC payments
- Bittensor EVM - Emission-related payments

## Important Implementation Patterns

### Adding a New Protocol

1. Define in `template/protocol.py` as `bt.Synapse` subclass:
```python
class MyProtocol(bt.Synapse):
    # Define fields
    def deserialize(self) -> "MyProtocol":
        return self
```

2. Add handler in miner's `forward()` (`neurons/miner.py`)
3. Add query logic in validator's `forward()` (`template/validator/forward.py`)

### Adding a New Mechanism

1. Create scorer in `template/mechanisms/<mechanism_name>.py`
2. Add to `definitions.py` MECHANISMS list
3. Update emission splits (must sum to 100%)
4. Register in MechanismManager
5. Configure on-chain via `configure_emission_splits()`

### Modifying Scoring Logic

1. Update appropriate scorer (`infrastructure.py`, `open_source.py`, `resellers.py`)
2. Implement `calculate_weights()` method
3. Weights should be normalized (sum to 1.0)
4. Test in isolation before deploying

### Weight Setting Per Mechanism

Weights are set separately for each mechanism using the `mechanism_id` parameter:
```python
self.subtensor.set_weights(
    wallet=self.wallet,
    netuid=self.config.netuid,
    uids=uids,
    weights=weights,
    mechanism_id=mechanism_id  # 0 for Infrastructure, 1 for OpenSource
)
```

## Debugging and Monitoring

**Validator Logs:**
- Location: `~/.bittensor/validators/<netuid>/`
- Mechanism stats logged every 60s
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
- FIPS-140-2 compliance mandatory

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
- Smart contract deployment (BASE L2 and Bittensor EVM)
- Multi-cluster Kubernetes setup with Rancher Fleet
- TEE attestation service integration
- DeepResearch Benchmark integration

**Miner Implementation:** The current miner (`neurons/miner.py`) is a template. Production miners need to implement:
- Kubernetes cluster management
- TEE attestation reporting
- AI model serving (NVIDIA NIM integration)
- Health metrics reporting
- Revenue tracking

**Validator Implementation:** The validator handles:
- Multi-mechanism coordination via MechanismManager
- Revenue tracking and attribution
- Weight calculation per mechanism
- Referrer payment distribution

**Smart Contracts:** Deployment targets:
- Bittensor EVM for emission-related payments
- BASE L2 for USDC payments (lower fees)

## Key Takeaways

1. This subnet uses **four economic models** with three receiving emissions (Infrastructure 60%, Benchmark 30%, Bounty Treasury 10%) plus Referrers (50% revenue share, NO emissions)
2. **Separate weight matrices** per mechanism with independent Yuma Consensus
3. **Lifetime Score with Decay** for benchmark competition - early improvers continue earning (5% monthly decay, 30% floor)
4. **Bounty Treasury** accumulates 10% emissions for manual payouts on merged PRs (fixed TAO values in Alpha)
5. **TEE is mandatory** for miners (Intel TDX/SGX, NVIDIA Confidential Computing)
6. **NVIDIA partnership** is central - leverages NeMo, NIM, and AI Blueprints
7. **Multi-chain strategy** - BASE L2 for payments, Bittensor EVM for emissions
8. **Revenue share** - Miners get 50%, Referrers get 50%, KubeTEE gets remainder
9. **Development workflow** - Feature → Staging → Main with CircleCI automation
10. **Hardware requirements** are extreme - 8x H100/H200/B200 GPUs minimum for miners
11. **Current version 0.0.0** indicates template stage - production deployment requires significant additional work
12. **Security-first design** - FIPS-140-2, CCC membership, confidential computing throughout
