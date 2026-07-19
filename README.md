# KubeTEE AI Factory — Confidential Compute for Decentralized AI Jobs

> Enterprise-Grade Confidential Computing AI Factory on Decentralized Kubernetes Infrastructure, scheduled by Armada across Bittensor miner clusters

[![FIPS-140-3 Target](https://img.shields.io/badge/FIPS--140--3-Target-blue)](https://docs.rke2.io/security/fips_support)
[![FIPS-140-2](https://img.shields.io/badge/FIPS--140--2-Validated-green)](https://docs.rke2.io/security/fips_support)
[![Kata Containers](https://img.shields.io/badge/Kata%20Containers-TEE%20Runtime-blue)](https://katacontainers.io/)
[![Confidential Containers](https://img.shields.io/badge/Confidential%20Containers-CoCo-9b59b6)](https://github.com/confidential-containers/confidential-containers)
[![RKE2](https://img.shields.io/badge/RKE2-Kubernetes-3FDD43)](https://docs.rke2.io/)
[![Rancher](https://img.shields.io/badge/Rancher-Multi--Cluster-0075A8)](https://www.rancher.io/)
[![Armada](https://img.shields.io/badge/Armada-Multi--Cluster%20Scheduler-blue)](https://armadaproject.io/)
[![Confidential Computing](https://img.shields.io/badge/Confidential%20Computing-Enabled-brightgreen)](https://confidentialcomputing.io/)
[![Intel TDX](https://img.shields.io/badge/Intel%20TDX-Supported-lightgrey)](https://www.intel.com/content/www/us/en/developer/tools/tdx/overview.html)
[![Intel SGX](https://img.shields.io/badge/Intel%20SGX-Supported-blueviolet)](https://www.intel.com/content/www/us/en/architecture-and-technology/software-guard-extensions.html)
[![Trusted Execution Environment](https://img.shields.io/badge/Trusted%20Execution%20Environment-TEE-green)](https://en.wikipedia.org/wiki/Trusted_execution_environment)
[![NVIDIA](https://img.shields.io/badge/NVIDIA-GPU%20Optimized-green)](https://developer.nvidia.com/)
[![NVIDIA Inception](https://img.shields.io/badge/NVIDIA-Inception-76B900)](https://www.nvidia.com/startups/)
[![CCC Member](https://img.shields.io/badge/Confidential%20Computing%20Consortium-Member-blue)](https://confidentialcomputing.io/)
[![OpenInfra](https://img.shields.io/badge/OpenInfra%20Foundation-Kata%20Containers-DA1A32)](https://openinfra.org/)

---

## About

**KubeTEE AI** is the **AI Factory** of the Bittensor network: it turns decentralized GPU clusters into a confidential AI factory. AI workloads run inside hardware-secured Trusted Execution Environments (TEE) using [Kata Containers](https://katacontainers.io/) and [Confidential Containers (CoCo)](https://github.com/confidential-containers/confidential-containers), and are scheduled across miner clusters by [Armada](https://armadaproject.io/) — a CNCF Sandbox multi-cluster Kubernetes batch scheduler.

KubeTEE AI is registered with the [**NVIDIA Inception Program**](https://www.nvidia.com/startups/) and is an active contributor to both the [**Kata Containers**](https://katacontainers.io/) and [**Confidential Containers (CoCo)**](https://github.com/confidential-containers/confidential-containers) ecosystems. It also leverages [**CNCF**](https://www.cncf.io/) projects for cloud-native infrastructure.

### Bittensor Miner

As part of Bittensor ecosystem as a miner since Febuary 2024, Pierre known as the french miner from Cyprus by Targon was the first to provide Confidential Computing nodes on Targon Subnet 4. We helped Chutes Subnet 64 to onboard B200/B300 nodes and helped Lium Subnet 51 to deploy recently Confidential Computing working with their stack.

I was also the first to provide Confidential Computing to Telegram Cocoon and Phala Network.

### Background

With 40 years of expertise, Started in 1986 to install Linux and Novell servers and in 1992 one of the first internet provider in Canada, as an Infrastructure architect deploying internet in Moroco and managing tech stack at scale in cloud providers. My specialty is security and I did security audits for Fortune 500 companies.

### Motivation

My expertise for Confidential Computing, Kubernetes, networking and security at Kernel and hardware level can benefit Bittensor ecosystem and I want to help every subnets in the ecosystem by providing the most secure and efficient AI Factory stack to elevate Bittensor offering of decentrilized Artifical Inteligence.

Providing High Quality infrastructure to the 2 Computing and Inference subnets on Bittensor for more than 2.5 years (Chutes #64, Targon #3 and Lium #51) with monitoring, upgrades and my help to improve each stack. I wanted to offer different tech stack that I belive Bittensor ecosystem can use and extend from.

**Direct Engineering Collaboration**: KubeTEE AI works directly with **INTEL** and **NVIDIA** engineers throughout the development and testing process of the NVIDIA technology especialy Kata/CoCo Containers. This close collaboration ensures optimal integration of confidential computing features, early access to emerging technologies, and validation of our implementation against the most stringent security and performance standards.

KubeTEE AI actively contributes to OpenInfra and CNCF projects — [Kata Containers](https://katacontainers.io/) and [Confidential Containers (CoCo)](https://github.com/confidential-containers/confidential-containers) provide the TEE foundation, and [Armada](https://armadaproject.io/) schedules workloads across miner clusters (detailed in [Architecture](#architecture)).

### Confidential Computing Consortium Resources

As a member of the [Confidential Computing Consortium (CCC)](https://confidentialcomputing.io/), we recommend the following resources from the consortium:

- **[Protecting Agentic AI Workloads with Confidential Computing](https://confidentialcomputing.io/2026/01/20/protecting-agentic-ai-workloads-with-confidential-computing/)** (January 2026)  
  This article by Mike Bursell, Executive Director of the CCC, explains how Confidential Computing addresses critical security challenges for Agentic AI workloads. Key takeaways:
  - **The Security Problem**: Agents operating in environments not owned by the Agent's owner are at risk from people and applications with sufficient permissions who can read or change data or the application itself
  - **Isolation Requirements**: Agents need identity integrity protection and capability confidentiality protection, breaking the standard model where infrastructure controllers control workloads
  - **Confidential Computing Solution**: Hardware-based isolation rooted in silicon provides protection of data and applications in-use, with remote attestation capabilities for verification
  - **Perfect Fit for Agentic AI**: Allows owners to trust their Agents and enables interaction verification that data has not been compromised or exfiltrated

  This directly aligns with KubeTEE AI's architecture, which uses Intel TDX/SGX and NVIDIA Confidential Computing to protect AI workloads in decentralized Kubernetes infrastructure.

- **[Gartner Top 10 Strategic Technology Trends for 2026](https://www.gartner.com/en/articles/top-technology-trends-2026)** (Gartner IT Symposium/Xpo 2026)  
  Gartner ranks **Confidential Computing as #3** on their Top 10 Strategic Technology Trends for 2026, alongside other trends directly relevant to KubeTEE AI:
  1. AI-Native Development Platforms
  2. AI Supercomputing Platforms
  3. **Confidential Computing** — protects sensitive data while in use, enabling secure AI and analytics across untrusted infrastructure
  4. **Multiagent Systems** — modular AI agents collaborate on complex tasks, improving automation and scalability
  5. Domain-Specific Language Models
  6. Physical AI
  7. **Preemptive Cybersecurity**
  8. **Digital Provenance**
  9. **AI Security Platforms**
  10. Geopatriation

  Gartner organizes these trends into three themes: **The Architect** (AI platforms and infrastructure), **The Synthesist** (AI application and orchestration), and **The Vanguard** (security, trust and governance). KubeTEE AI operates across all three themes with TEE-enabled infrastructure, multi-agent AI workloads, and enterprise-grade security compliance.

### Mission & Vision

**Mission**: To turn decentralized GPU clusters into a confidential AI factory — running AI training, inference, and data-processing jobs in Trusted Execution Environments, scheduled fairly across Bittensor miner clusters by Armada, with the highest standards of security, compliance, and performance.

**Key Differentiators**:
- **Security-First**: TEE-enabled infrastructure with FIPS-140-3 as the Early Access target (FIPS-140-2 validated RKE2 baseline) and Kata Containers isolation
- **Armada-Scheduled**: multi-cluster batch scheduling with fair-use queuing, gang scheduling, and preemption across decentralized clusters
- **NVIDIA-Powered**: NeMo Microservices, NIM models, and AI Blueprints as first-class confidential job types
- **Decentralized**: one hotkey per cluster, nodes co-located in a single data center, expanding across global regions
- **Open Source**: Built on OpenInfra Foundation and CNCF projects with community-driven innovation

---

## Table of Contents

- [KubeTEE AI Factory — Confidential Compute for Decentralized AI Jobs](#kubetee-ai-factory--confidential-compute-for-decentralized-ai-jobs)
  - [About](#about)
    - [Bittensor Miner](#bittensor-miner)
    - [Background](#background)
    - [Motivation](#motivation)
    - [Confidential Computing Consortium Resources](#confidential-computing-consortium-resources)
    - [Mission \& Vision](#mission--vision)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
    - [Early Access](#early-access)
  - [The Confidential Compute Challenge: Problems We Solve](#the-confidential-compute-challenge-problems-we-solve)
  - [Architecture](#architecture)
    - [Confidential Computing (Kata + CoCo)](#confidential-computing-kata--coco)
    - [Infrastructure](#infrastructure)
      - [Kubernetes High Availability](#kubernetes-high-availability)
      - [Armada Multi-Cluster Batch Scheduling](#armada-multi-cluster-batch-scheduling)
    - [Security \& Compliance](#security--compliance)
      - [Network Security](#network-security)
      - [Data Protection](#data-protection)
      - [Monitoring \& Audit](#monitoring--audit)
    - [Multi-Cluster Topology](#multi-cluster-topology)
      - [Subnet Owner Infrastructure](#subnet-owner-infrastructure)
      - [Miner Infrastructure](#miner-infrastructure)
    - [Early Access Topology](#early-access-topology)
  - [Supported AI Workloads (Job Types)](#supported-ai-workloads-job-types)
    - [NVIDIA NeMo Microservices](#nvidia-nemo-microservices)
  - [Subnet Economics](#subnet-economics)
    - [Incentive Mechanism: Infrastructure (Early Access)](#incentive-mechanism-infrastructure-early-access)
      - [Staging vs Production](#staging-vs-production)
    - [Payments \& Revenue (Roadmap)](#payments--revenue-roadmap)
  - [Tokenomics — Utility Token \& DePIN Model](#tokenomics--utility-token--depin-model)
    - [Recycle vs Burn](#recycle-vs-burn)
    - [Corporate Structure (vertically split)](#corporate-structure-vertically-split)
    - [Cross-Subnet Consumption Loop (utility-token flywheel)](#cross-subnet-consumption-loop-utility-token-flywheel)
    - [DePIN Subsidy Trajectory](#depin-subsidy-trajectory)
  - [Validator Scoring \& Attestation](#validator-scoring--attestation)
    - [Validator Runtime (TEE)](#validator-runtime-tee)
    - [Rancher v3 Access (Hotkey-signed Auth)](#rancher-v3-access-hotkey-signed-auth)
    - [TEE Attestation](#tee-attestation)
    - [Armada Job Metrics](#armada-job-metrics)
    - [Infrastructure Health](#infrastructure-health)
    - [Competitive Pricing](#competitive-pricing)
    - [Weight Setting](#weight-setting)
  - [Submitting a Confidential Job](#submitting-a-confidential-job)
    - [Miner Registration](#miner-registration)
  - [Workflow Orchestration (Airflow \& Metaflow)](#workflow-orchestration-airflow--metaflow)
  - [For Miners (Infrastructure)](#for-miners-infrastructure)
  - [Roadmap](#roadmap)
    - [Phase 0 — Early Access (Current)](#phase-0--early-access-current)
    - [Phase 1 — Expansion](#phase-1--expansion)
    - [Phase 2 — Paid Jobs](#phase-2--paid-jobs)
    - [Phase 3 — Job-Type Growth](#phase-3--job-type-growth)
  - [Research \& Documentation](#research--documentation)
    - [Documentation](#documentation)
    - [External Resources](#external-resources)
    - [Community \& Support](#community--support)

---

## Overview

KubeTEE AI Factory provides Enterprise-Grade Confidential Computing for AI batch jobs on a Decentralized Multi-Cluster Kubernetes RKE2 infrastructure. Jobs are submitted to Armada queues and scheduled across miner clusters, executing inside Trusted Execution Environments (TEE) so that data and models are protected **at rest, in transit, and in use** — and never leave the confidential computing boundary.

Each miner cluster is identified by a permanent Bittensor **hotkey/coldkey** pair. Armada dispatches batch jobs to these clusters as Kubernetes pods; the pods run under a confidential `runtimeClassName` (`kata-qemu-nvidia-gpu-tdx` for GPU TEE, `kata-qemu-tdx` for CPU TEE) so the workload is hardware-isolated and attested. CoCo provides transparent confidential image decryption and remote attestation — unmodified containers run inside the TEE without changes.

### Early Access

KubeTEE is in **Early Access**. The first deployment targets **two clusters in the USA**, one hotkey each, with all nodes of a cluster co-located in a single data center. Early Access focuses on:

- Standing up the Armada multi-cluster batch scheduler across miner clusters
- Running confidential AI jobs (NeMo / NIM / Blueprints) in Kata + CoCo TEE pods
- The **validator incentive mechanism**: scoring miners on TEE attestation, Armada job success, uptime, and **competitive pricing** against the other compute subnets (Targon, Lium, Chutes) with a 75% utilization target
- **Emissions-only** rewards (no USDC job billing yet — see [Roadmap](#roadmap))
- **Security**: Confidential Computing TEE with FIPS-140-3 as the Early Access target on a FIPS-140-2 validated RKE2 baseline

---

## The Confidential Compute Challenge: Problems We Solve

Organizations running sensitive AI workloads — training, fine-tuning, inference, data processing — face an impossible choice between security, cost, and trust. KubeTEE resolves all three:

1. **Private data & models must stay private** — Public cloud AI and traditional deployments expose data in memory and give providers/insiders access. KubeTEE enforces hardware TEE isolation (Intel TDX/SGX, NVIDIA CC) via Kata + CoCo, with remote attestation so you can verify the exact code running on your data; data is protected at rest, in transit, and in use.
2. **Regulated workloads need verifiable compute** — Healthcare (HIPAA), Finance (SOC2/PCI-DSS), Government (FedRAMP) need proof of isolation. KubeTEE provides FIPS-140-3 target on FIPS-140-2 validated RKE2, cryptographic attestation, audit trails (Prometheus, Kubernetes events), and isolated namespaces for tenant separation.
3. **Trust in decentralized infrastructure** — Centralized clouds are single points of failure with vendor lock-in. KubeTEE's decentralized multi-cluster architecture, Bittensor incentives, validator attestation, and open standards (Kubernetes, Armada, Kata, CoCo) remove the single point of failure and the lock-in.

---

## Architecture

### Confidential Computing (Kata + CoCo)

**Trusted Execution Environment (TEE)**
- Kata Containers for workload isolation
- Confidential Containers with Workload Identity Validation
- Intel TDX/SGX
- NVIDIA Hopper/Blackwell/Vera Ruben

CoCo provides transparent confidential image decryption and remote attestation via the KBS, so unmodified containers run inside the TEE. Confidential job execution uses the `kata-qemu-nvidia-gpu-tdx` (GPU) and `kata-qemu-tdx` (CPU) runtime classes — see [Armada Multi-Cluster Batch Scheduling](#armada-multi-cluster-batch-scheduling).

### Infrastructure

#### Kubernetes High Availability

**RKE2 Rancher Kubernetes**
- [FIPS-140-2 validated](https://docs.rke2.io/security/fips_support) U.S. Federal Government Grade Security, with FIPS-140-3 as the Early Access target
- Fully conformant distribution focused on security and compliance

**Multi-Cluster Management**
- [Rancher Fleet](https://fleet.rancher.io/) GitOps-based Multi-Cluster Management
- Regional deployment: Americas, EU, Middle East, Africa, Asia
- Native integration with Rancher for unified management

**Rancher UI RBAC Management**
- Users/Miners access to isolated Kubernetes Namespaces
- Project-based resource isolation
- Fleet workspaces for multi-tenancy

#### Armada Multi-Cluster Batch Scheduling

[Armada](https://armadaproject.io/) ([GitHub](https://github.com/armadaproject/armada)) is a CNCF Sandbox multi-cluster Kubernetes batch scheduler. It transforms Kubernetes into a high-throughput batch platform while remaining compatible with service workloads, and is used in production to run millions of jobs per day across tens of thousands of nodes.

**Component placement**:
- **Armada Server** (controller, scheduler, lookout + Pulsar/Redis/Postgres) runs on the **subnet-owner control plane** alongside the validator
- **Armada Executor + Installer** run on **each miner cluster**, turning the cluster into a scheduling target (pool)
- Jobs are submitted to **Armada queues** and scheduled across miner clusters with **fair-use queuing**, **gang scheduling**, and **preemption**

**Confidential execution**:
- Jobs land on nodes with a confidential `runtimeClassName`:
  - `kata-qemu-nvidia-gpu-tdx` — Confidential GPU (Intel TDX + NVIDIA GPU passthrough)
  - `kata-qemu-tdx` — Confidential CPU-only (Intel TDX, no GPU)
  - `nvidia` — Non-confidential GPU (staging/dev only)
- **CoCo** handles transparent confidential image decryption and remote attestation via the KBS, so unmodified containers run inside the TEE

Armada addresses Kubernetes batch limitations that matter for the Factory: single-cluster scaling limits, etcd throughput ceilings, and the lack of fair-use / gang scheduling in the default kube-scheduler.

### Security & Compliance

#### Network Security
- Linkerd mTLS communication within the cluster
- Network Policies enforcement
- RBAC (Role-Based Access Control)

#### Data Protection
- **Rancher Longhorn**: Encrypted Storage with 3 Replicas
- Encrypted Container Repository
- External Secrets Manager (Vault & CoCo KBS Trustee)

#### Monitoring & Audit
- Prometheus Metrics
- Kubernetes Events tracking
- UpTime, QoS, and Performance monitoring
- ElasticSearch Audit logs

### Multi-Cluster Topology

#### Subnet Owner Infrastructure
- Global Multi-Cluster Control Plane with Rancher on Confidential Computing TEE
- Rancher Multi-Cluster Management with Fleet for GitOps
  - RKE2 Rancher Kubernetes with FIPS-140-3 target (FIPS-140-2 validated baseline)
  - Kata Containers (TEE)
  - [Confidential Containers](https://confidentialcontainers.org/docs/overview/) Operator
  - Armada Server (controller, scheduler, lookout + Pulsar/Redis/Postgres)
- Validator runs in a TEE on the control plane; KubeTEE can also host the validator code (see [Validator Runtime (TEE)](#validator-runtime-tee))

#### Miner Infrastructure
- RKE2 Rancher Kubernetes
- One Cluster per Miner (identified by hotkey/coldkey, not UID)
  - One data center per cluster — all nodes co-located in a single DC
  - Regional deployment (One Region/Zone Control Plane with same region workers)
  - Cluster labeled with `kubetee.ai/` prefixed labels for permanent identification
  - Required labels: `kubetee.ai/continent`, `kubetee.ai/country`, `kubetee.ai/city`, `kubetee.ai/miner-hotkey`, `kubetee.ai/miner-coldkey`, `kubetee.ai/miner-uid`
- Kata Containers and CoCo Containers (TEE)
- Armada Executor + Installer (scheduled by the subnet-owner Armada Server)
- Fleet Agent for automated deployments

**Important**: Clusters are labeled with `kubetee.ai/miner-hotkey` and `kubetee.ai/miner-coldkey` for permanent identification. These labels never change, while `kubetee.ai/miner-uid` can be updated if a miner deregisters and re-registers on the subnet.

### Early Access Topology

```mermaid
flowchart LR
    subgraph owner["Subnet Owner Control Plane (stagingrancher)"]
        Validator["Validator\nweights + emissions"]
        ArmadaServer["Armada Server\nscheduler + queues\nPulsar/Redis/Postgres"]
    end
    subgraph clusterA["Miner Cluster A — 1 hotkey, 1 DC (USA)"]
        ExecA["Armada Executor"]
        NodeA["GPU nodes\nkata-qemu-nvidia-gpu-tdx"]
    end
    subgraph clusterB["Miner Cluster B — 1 hotkey, 1 DC (USA)"]
        ExecB["Armada Executor"]
        NodeB["GPU nodes\nkata-qemu-nvidia-gpu-tdx"]
    end
    Client["Job Submitter\nNeMo/NIM/Blueprint job"] -->|submit| ArmadaServer
    ArmadaServer -->|schedule| ExecA
    ArmadaServer -->|schedule| ExecB
    ExecA --> NodeA
    ExecB --> NodeB
    NodeA -.->|attestation + metrics| Validator
    NodeB -.->|attestation + metrics| Validator
    Validator -->|set weights| Chain["Bittensor\nemissions"]
```

> The **Validator** and **Armada Server** run on the control plane inside confidential Kata + CoCo TEE pods (see [Validator Runtime (TEE)](#validator-runtime-tee)).

---

## Supported AI Workloads (Job Types)

KubeTEE AI Factory schedules AI workloads as Armada batch jobs that execute inside Kata + CoCo TEE pods. The Factory ships with first-class job templates built on the NVIDIA AI stack — NeMo Microservices, NIM models, and AI Blueprints — and any containerized batch job can be submitted to an Armada queue.


### NVIDIA NeMo Microservices

[NVIDIA NeMo Microservices](https://docs.nvidia.com/nemo/microservices/latest/about/index.html) are API-first, modular tools for customizing, evaluating, and securing LLMs and embedding models on Kubernetes. A goal of the KubeTEE AI Factory is to run the full NVIDIA AI stack — NeMo Microservices, NIM models, and AI Blueprints — inside Confidential Computing (Kata + CoCo TEE), scheduled as Armada batch jobs. Each cluster exposes a shared mTLS-secured, high-availability NeMo Microservices infrastructure.

---

## Subnet Economics

### Incentive Mechanism: Infrastructure (Early Access)

KubeTEE Early Access uses a **single Infrastructure incentive mechanism**. Miners earn Bittensor emissions by providing confidential compute capacity and reliably executing Armada-scheduled jobs. Early Access is **emissions-only** — paid billing is a Phase 2 roadmap item (see [Payments & Revenue](#payments--revenue-roadmap)).

**Purpose**: Reward miners for providing Kubernetes infrastructure that runs confidential AI jobs scheduled by Armada.

**Key Feature**: Emissions are distributed per resources provided (GPU nodes), weighted by attested TEE health, job-execution quality, and uptime.

**Mandatory Requirement**:
- **TEE Attestation** (Intel TDX/SGX, NVIDIA CC) must be proven — **no attestation = no emissions**

**Resource Utilization Guidance**:
- **Below 75% capacity**: Penalized — underutilized, not contributing proportionally to subnet demand
- **Target ~80% capacity**: Optimal — ensures miners provide exactly what the subnet needs

**Benefits**:
- TEE compliance is enforced, not optional
- Clear incentive to provide higher-tier GPU nodes
- Job-execution quality rewards miners that reliably run confidential workloads
- Resource utilization ensures balanced subnet capacity — no over/under provisioning

#### Staging vs Production

**Staging Environment** (Permissionless):
- Test applications, infrastructure, upgrades, job validation
- Gateway to Production environment
- Community Staging jobs

**Production Environment** (After Staging testing Period):
- Multi-Clusters (one per data center per miner hotkey)
- Must pass Staging validation period
- Optional KYC for regulated workloads.

### Payments & Revenue (Roadmap)

Early Access is **emissions-only**. The following payment and revenue features are planned for Phase 2 (see [Roadmap](#roadmap)):

- **Subnet 90 Alpha, Other Subnets Alpha, TAO** Discounted for Bittensor community.
- **USDC-on-BASE job billing** — pull-based, per-epoch metering of Armada job resource usage
- **Referrer / integrator / reseller program** — revenue share with on-chain attribution
- **Automated USDC→TAO→Alpha recycling** — unused emissions recycled

---

## Tokenomics — Utility Token & DePIN Model

SN90 (KubeTEE) Alpha is a **utility token consumed to access confidential compute**, not a security. The design follows a DePIN subsidy model: external inference demand buys Alpha on the open market and spends it to consume compute; spent Alpha is **recycled** to unissued supply and re-emitted through the protocol's fixed emission split — a self-sustaining security budget for the compute network (the Bitcoin-fee model applied to Alpha). Full analysis: [Tokenomics — Utility Token & DePIN Model](./docs/TOKENOMICS.md).

### Recycle vs Burn

When Alpha is spent for compute, the subnet mechanism chooses what happens to it:

- **Burn** — permanent supply reduction; does not reduce `SubnetAlphaOut`; maximum scarcity signal.
- **Recycle** (chosen) — returns to unissued supply, reduces `SubnetAlphaOut`, extends the Alpha emission runway, pushes halving thresholds out, and refills the miner incentive budget.

For a compute subnet whose product is ongoing work, **recycle** is the right economics: consumption funds future miner emissions. Neither method games emission share — the miner-withholding penalty is source-based, not method-based.

### Corporate Structure (vertically split)

```mermaid
flowchart LR
    Proto["Bittensor protocol<br/>41 / 41 / 18 emission split"]
    Proto -->|18% owner stream| Kube["KubeTEE LTD<br/>subnet owner<br/>mechanism + IP"]
    Proto -->|41% miner stream| Hori["1-HORIZON LTD<br/>miner operator<br/>GPU/TEE capex"]
    Proto -->|41% miner stream| Ext["External miners<br/>(permissionless)"]
    Hori -.->|"separate coldkeys<br/>(MinerBurned tripwire)"| Proto
    Kube -.->|"related-party license<br/>(off-chain, disclosed)"| Hori
```

- **KubeTEE LTD — subnet owner**: owns the mechanism, the €198k subnet registration, and the **18% owner emission stream**. No token sales against promises, no customer balances, no treasury — all unused emissions are recycled.
- **1-HORIZON LTD — miner operator**: competes for the **41% miner share** like any miner; funds GPU/TEE capex. Registers, competes, and is deregistered under identical rules as every other miner.
- **On-chain tripwire**: the `MinerBurned` penalty targets miner emission flowing to subnet-owner-controlled coldkeys. 1-HORIZON's miner hotkeys must trace to genuinely separate coldkeys, not KubeTEE-controlled ones.
- **Target state**: the related-party (1-HORIZON) share shrinks as external miners grow — a declining related-party share is the on-chain evidence the network is real.

### Cross-Subnet Consumption Loop (utility-token flywheel)

```mermaid
flowchart LR
    Cust["External customers<br/>pay fiat for inference"] --> SN64["SN64 (Chutes)<br/>inference / subscription"]
    SN64 -->|swap TAO for Alpha<br/>on open pool| Pool["SN90 Alpha pool<br/>(open market, no discounts)"]
    Pool -->|Alpha| SN64
    SN64 -->|spend Alpha<br/>for compute| SN90["SN90 (KubeTEE)<br/>confidential compute"]
    SN90 -->|spent Alpha recycled| Unissued["Unissued supply<br/>(zero discretion)"]
    Unissued -->|re-emit via 41/41/18| Proto["Bittensor protocol"]
    Proto -->|miners / validators / owner| SN90
    SN64 -.->|run validator on SN90| Val["SN64-aligned validator<br/>scores miner output = SLA"]
    Val -.->|Yuma Consensus| Proto
```

External customers pay fiat for inference → SN64 (Chutes) swaps TAO for SN90 Alpha on the **open pool** (no discounts, no allocations, no side-letters) → spends Alpha to consume SN90 confidential compute → spent Alpha is **recycled** to unissued supply → re-emitted via the **41/41/18** split (miners / validators / owner). An **SN64-aligned validator** on SN90 scores miner output — the protocol-native SLA (no contract needed). This is external demand one hop removed, not circular emissions-farming.

### DePIN Subsidy Trajectory

```mermaid
flowchart LR
    A["Pre-crossover<br/>emissions fund the subsidy<br/>net inflationary"] --> B["Crossover<br/>consumption = emissions<br/>net issuance ~ 0"] --> C["Post-crossover<br/>net-deflationary<br/>miners paid fully"]
    KPI["Subsidy ratio KPI<br/>emission value / miner compensation<br/>monotonically declining"] -.-> A
    Moat["Stack-efficiency moat grows<br/>K8s bin-packing · TEE premium · utilization<br/>70/30 at launch to 30/70 by crossover"] -.-> C
```

Miner compensation = emissions + consumption spend. While emissions cover most of the cost base, miners price compute below cash cost and SN64 pockets the gap (funded by Alpha dilution). The **subsidy ratio** (emission value ÷ total miner compensation) is the single on-chain KPI, monotonically declining:

- **Pre-crossover** (amber): net inflationary; emissions fund the subsidy.
- **Crossover**: consumption spend = emissions → net Alpha issuance ≈ 0; consumers fund the miner budget through the pool.
- **Post-crossover**: net-deflationary while still paying miners fully.

Defenses: subsidy tapers by a **published glide path** (not surprise); **stack efficiency** is the moat (Kubernetes bin-packing, TEE-attestation confidential-compute premium, higher utilization) — target 70% subsidy / 30% efficiency at launch → 30/70 by crossover. Score verifiable properties (delivered capacity, attested TEE execution, validator-issued challenges) and make self-consumption economically neutral to defeat **wash consumption**.


---

## Validator Scoring & Attestation

The validator is the subnet's referee. In Early Access it scores each miner (one hotkey per cluster) on a single Infrastructure mechanism and sets Bittensor weights each epoch.

> **Current Early Access stand-in:** the shipping validator scores node liveness only today; the full TEE-attestation + Armada + health scoring below is the design target (see [Roadmap](#roadmap) and [SUBNET.md](SUBNET.md)).

### Validator Runtime (TEE)

The validator is the subnet's referee — so the referee itself must be trustworthy. The validator process runs **inside a confidential TEE pod** (`kata-qemu-nvidia-gpu-tdx` or `kata-qemu-tdx`) on the subnet-owner control plane, with CoCo remote attestation proving the validator code and configuration are unmodified. Scoring, weight-setting, and credentials (Rancher token, Bittensor wallet) stay confidential and tamper-resistant — the validator cannot be silently altered by the host or hypervisor.

**KubeTEE-hosted validator**: KubeTEE offers to run the validator code in KubeTEE clusters, so a validator operator does not need to provision and operate their own TEE infrastructure. KubeTEE schedules the validator as a confidential workload in a KubeTEE confidential cluster, with attestation evidence available to the subnet. This lowers the barrier to running a validator and ensures every validator runs in a genuine, attested TEE.

### Rancher v3 Access (Hotkey-signed Auth)

To read cluster and node metrics for scoring, the validator calls the **Rancher v3 REST API**. Access is granted by **hotkey-signed authentication**: the validator signs a challenge with its Bittensor **hotkey** (SR25519), and an auth mechanism connected to Rancher verifies the signature on-chain, maps the hotkey to a Rancher principal, and issues a **short-lived, read-only** Rancher v3 bearer token bound to `cluster-readonly`. The hotkey is the only credential — no long-lived admin token is held by the validator — and it stays inside the validator's TEE pod.

Miners use the same hotkey-signed flow, scoped read-only to their own cluster (the one labeled with their `kubetee.ai/miner-hotkey`), provisioned automatically when their cluster is created.

### TEE Attestation
- The validator runs attestation cronjobs inside Kata Containers to verify each miner cluster's TEE (Intel TDX/SGX, NVIDIA CC)
- CoCo remote attestation confirms the confidential container image and runtime are unmodified
- **No valid attestation → zero emissions** for that miner

### Armada Job Metrics
- The validator pulls Armada scheduler/executor metrics via Prometheus: job success rate, throughput, scheduling latency, preemption fairness, and gang-scheduling success
- Miners that reliably execute confidential jobs under `kata-*` runtime classes score higher

### Infrastructure Health
- Uptime, QoS, capacity, and latency from Prometheus and Kubernetes events
- FIPS-140-2/3 validated

### Competitive Pricing

SN90 sells compute, so its miners are scored against the **other Bittensor compute subnets** — **Targon (SN4)**, **Lium (SN51)**, and **Chutes (SN64)** — each of which exposes a **verifiable** feed (public API + on-chain metagraph for emission/attestation proof). Targon exposes a **supply-side** payout feed (per-miner emission payout by compute type and card count, via `stats.targon.com`); every Targon GPU miner runs an **8-card node** — the same form factor SN90 requires — so the live per-8-card-node payout (B300 ~64, B200 ~52, H200 ~28, H100 ~24 TAO/epoch) is the direct benchmark SN90 miner compensation must match or miners migrate to SN4. Lium and Chutes expose **demand-side** listing prices. The validator scrapes those feeds each epoch, cross-checks them against the metagraph, and computes a **target price** per SN90 job class (GPU-hour by GPU type, CPU-hour, per-token inference).

The target price is **discovered, not decreed** — a function of four inputs:

- **The compute needed** — the job class (GPU type / GPU-hours / CPU-hours / per-token); price is computed per class, not as a flat number.
- **Competitor signals for the same class** — Targon's per-miner payout by compute type (supply-side) and Lium's / Chutes's listing prices (demand-side), each cross-checked on-chain.
- **SN90 demand** — Armada queue depth and scheduling wait time for that class.
- **The 75% utilization target** — the equilibrium anchor. Below 75% average capacity, price is pushed down to attract demand and fill capacity; at 75%, price sits at the competitor average; above 75%, price is pushed up to ration demand and preserve headroom.

The target price is a **scoring input, not a bill**. Miners are scored on whether the compute they deliver is priced at or below the target (full credit), modestly above (reduced credit), or far above (zero credit for that class — SN90 would lose the demand to SN4/SN51/SN64). A miner with perfect attestation but a price 2× the competitor average scores low. This is what "competitive with the other subnets" means mechanically: the weight vector rewards miners that keep SN90 in the competitive band. The 75% target also doubles as the **wash-consumption defense** — a miner faking utilization pushes the subnet above 75%, which raises the target price and makes its own wash spend more expensive.

Every input is a public API or on-chain data; the validator publishes the scraped competitor prices and the computed target price each epoch as Prometheus metrics, so the weight vector is auditable end-to-end. Full design — competitor feeds, the target-price formula, scoring integration, and verifiability table: [Competitive Pricing & Miner Scoring](./docs/COMPETITIVE-PRICING.md).

> **Status:** competitive pricing is a **roadmap** scoring dimension (Phase 2, alongside USDC job billing — both depend on a real price existing). The shipping Early Access validator scores node liveness only (see [SUBNET.md](SUBNET.md)).

### Weight Setting
- Scores are normalized per miner hotkey and set on-chain via Bittensor `set_weights` (single mechanism)
- Reference implementation: [`scripts/validator.py`](scripts/validator.py) (scoring: [`scripts/miner_scoring.py`](scripts/miner_scoring.py), reconciliation: [`scripts/reconciliation.py`](scripts/reconciliation.py), Rancher v3 client: [`scripts/rancher_client.py`](scripts/rancher_client.py))

---

## Submitting a Confidential Job

Jobs are submitted to Armada queues and scheduled onto miner clusters with a confidential `runtimeClassName`. In Early Access, job submission is available to the subnet owner and authorized integrators.


### Miner Registration

Miners register clusters (one hotkey per cluster) with the subnet owner for Rancher Fleet and Armada enrollment. See [For Miners (Infrastructure)](#for-miners-infrastructure).

---

## Workflow Orchestration (Airflow & Metaflow)

Single confidential jobs are submitted to Armada queues (see [Submitting a Confidential Job](#submitting-a-confidential-job)). For **multi-step AI pipelines** — ETL → fine-tune → evaluate → register → deploy — KubeTEE integrates with two open-source orchestrators so each pipeline step runs as a confidential Armada batch job inside Kata + CoCo TEE pods:

- **[Apache Airflow](https://airflow.apache.org/)** — DAG-based pipeline orchestration. Author DAGs on the control plane (or externally); each task submits an Armada job spec with a confidential `runtimeClassName`. Airflow schedules the *pipeline*; Armada schedules the *task pods* across miner clusters.
- **[Metaflow](https://metaflow.org/)** — a Python framework for data-science / ML workflows. Author flows with `@step`-style decorators; a KubeTEE Metaflow producer submits each step to an Armada queue as a confidential pod. Iterate locally, run production steps in TEE.

**Confidential pipelines**: every task pod runs under `kata-qemu-nvidia-gpu-tdx` (GPU) or `kata-qemu-tdx` (CPU) with CoCo remote attestation. Pipeline artifacts move through encrypted Longhorn volumes or an encrypted object store; secrets are injected via the CoCo KBS — no plaintext secrets in DAG/flow code. A pipeline can verify a step's attestation evidence before passing artifacts downstream.

See [Workflow Orchestration — Airflow & Metaflow](./docs/WORKFLOW-ORCHESTRATION.md) for architecture, connector design, and example DAG / Metaflow flow snippets.

> **Status:** integration is on the roadmap — Airflow and Metaflow Armada connectors land in Phase 1 / Phase 3 (see [Roadmap](#roadmap)).

---

## For Miners (Infrastructure)

**Early Access Cluster Rules**:
- One hotkey per cluster (one miner = one cluster)
- All nodes co-located in a single data center (low-latency, same-DC networking)
- First two clusters deployed in the USA
- Armada Executor + Installer deployed on the cluster (scheduled by the subnet-owner Armada Server)
- Confidential runtime classes available: `kata-qemu-nvidia-gpu-tdx` (GPU TEE), `kata-qemu-tdx` (CPU TEE)

**Minimum For Staging Permissionless Participation**:

- ✅ INTEL TDX Compatible node with NVIDIA H100/H200
- ✅ BIOS TDX/SGX Enabled
- ✅ Kernel TDX/SGX Enabled
- ✅ One Cluster per Miner (labeled with `kubetee.ai/` prefixed labels)
- ✅ Same Regional deployment (Workers in same Data Center)
- ✅ Cluster registered with Rancher for Fleet management
- ✅ Cluster must be labeled with required labels:
  - `kubetee.ai/continent`, `kubetee.ai/country`, `kubetee.ai/city` (geographic identification)
  - `kubetee.ai/miner-hotkey`, `kubetee.ai/miner-coldkey` (permanent miner identification)
  - `kubetee.ai/miner-uid` (current UID, updateable)

**For Production Participation**:

- ✅ Successfully passed Staging validation period

**Reference Documentation**:
- [Node Registration](./docs/NODE-REGISTRATION.md) — Miner RKE2 node registration and the `kubetee.ai/miner-hotkey` label requirement
- [GPU Node Requirements](./docs/GPU-NODE-REQUIREMENTS.md) — GPU/TEE hardware requirements (CPU TDX/SEV-SNP, BIOS, kernel)
- [Cluster Naming Convention](./docs/CLUSTER_NAMING_CONVENTION.md) — `kubetee.ai/*` labels and Fleet GitOps targeting
- [FIPS-140-3 Target](./docs/FIPS-140-3.md) — RKE2 + Kata + CoCo FIPS stack

---

## Roadmap

### Phase 0 — Early Access (Current)

- [ ] Deploy 2 US clusters (one hotkey each, nodes co-located in a single DC)
- [ ] Armada Server on the subnet-owner control plane; Armada Executor on each miner cluster
- [ ] Kata + CoCo TEE runtime classes (`kata-qemu-nvidia-gpu-tdx`, `kata-qemu-tdx`)
- [ ] Single Infrastructure validator mechanism (design: TEE attestation + Armada job metrics + uptime; Early Access stand-in: node liveness)
- [ ] Validator runs in a TEE (Kata + CoCo) on the control plane; CoCo attestation proves the validator code is unmodified
- [ ] KubeTEE-hosted validator offering: KubeTEE runs the validator code in a KubeTEE confidential cluster for operators without their own TEE infrastructure
- [ ] Validator Rancher v3 API access: a validator authenticates by **signing a challenge with its Bittensor hotkey**; an auth mechanism connected to Rancher verifies the signature and issues a **read-only** Rancher v3 bearer token (bound to `cluster-readonly`) — see [Rancher v3 Access (Hotkey-signed Auth)](#rancher-v3-access-hotkey-signed-auth) and CLAUDE.md "Validator Rancher API Access"
- [ ] Miner Rancher access on cluster creation: the miner authenticates with the same **hotkey-signed** flow, scoped **read-only** to their own cluster (the one labeled with their `kubetee.ai/miner-hotkey`, bound to `cluster-readonly`) so the miner can observe their cluster (subnet owner manages via Fleet)
- [ ] Emissions-only rewards
- [ ] FIPS-140-3 target on FIPS-140-2 validated RKE2 baseline
- [ ] Confidential NeMo / NIM / Blueprint job templates
- [ ] Confidential Subnets Owners and Approved Integrators templates.

### Phase 1 — Expansion

- [ ] More US + international clusters
- [ ] Armada fair-use + gang scheduling hardening
- [ ] Automated TEE attestation cronjobs
- [ ] Validator scoring expansion: TEE attestation + Armada job metrics + infrastructure health (replacing the Early Access liveness stand-in)
- [ ] Apache Airflow + Metaflow Armada connectors — multi-step confidential pipelines (see [Workflow Orchestration](./docs/WORKFLOW-ORCHESTRATION.md))
- [ ] Build documentation website

### Phase 2 — Paid Jobs

- [ ] Alpha, TAO, USDC-on-BASE job billing (pull-based, per-epoch metering)
- [ ] Competitive pricing dimension: scrape Targon (SN4) / Lium (SN51) / Chutes (SN64) price feeds, compute per-class target price, score miners on price competitiveness against a 75% utilization target (see [Competitive Pricing](./docs/COMPETITIVE-PRICING.md))
- [ ] Referrer / integrator / reseller program (on-chain attribution)
- [ ] Automated USDC→TAO→Alpha recycling (unused emissions recycled)

### Phase 3 — Job-Type Growth

- [ ] More job templates
- [ ] Multi-arch TEE (Intel TDX + AMD SEV-SNP)
- [ ] Additional confidential compute runtimes

---

## Research & Documentation

### Documentation
- [Node Registration](./docs/NODE-REGISTRATION.md) — Miner RKE2 node registration and `kubetee.ai/*` labels
- [GPU Node Requirements](./docs/GPU-NODE-REQUIREMENTS.md) — GPU/TEE hardware requirements
- [Cluster Naming Convention](./docs/CLUSTER_NAMING_CONVENTION.md) — `kubetee.ai/*` labels and Fleet GitOps targeting
- [FIPS-140-3 Target](./docs/FIPS-140-3.md) — RKE2 + Kata + CoCo FIPS stack research
- [Confidential Containers Certification](./docs/certification-confidential-containers.md) — CC standards and Kata runtime mapping
- [UAT-g004 Runbook](./docs/UAT-g004.md) — Self-contained single-node validator UAT procedures
- [Workflow Orchestration — Airflow & Metaflow](./docs/WORKFLOW-ORCHESTRATION.md) — orchestrating multi-step confidential pipelines on Armada
- [Tokenomics — Utility Token & DePIN Model](./docs/TOKENOMICS.md) — recycle vs burn, securities posture, cross-subnet consumption loop, DePIN subsidy trajectory
- [Competitive Pricing & Miner Scoring](./docs/COMPETITIVE-PRICING.md) — pricing SN90 against Targon/Lium/Chutes, the 75% utilization target, and how price becomes weights

### External Resources
- [Armada](https://armadaproject.io/) | [Armada GitHub](https://github.com/armadaproject/armada) — multi-cluster batch scheduler
- [Apache Airflow](https://airflow.apache.org/) | [Metaflow](https://metaflow.org/) — pipeline orchestration for confidential Armada jobs
- [Kata Containers](https://katacontainers.io/) | [Confidential Containers](https://github.com/confidential-containers/confidential-containers)
- [RKE2 FIPS Support](https://docs.rke2.io/security/fips_support)

### Community & Support

- **GitHub**: [KubeTEE-AI-Blueprints](https://github.com/KubeTEE-AI-Blueprints)
- **Documentation**: [docs/](./docs/)
- **Discord**: Coming soon
- **Twitter**: Coming soon

---

**Built by the KubeTEE Community**

*Confidential compute for decentralized AI jobs — secured by TEE, scheduled by Armada, incentivized by Bittensor.*
