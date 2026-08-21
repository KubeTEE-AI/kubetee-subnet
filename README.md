# KubeTEE AI Factory — Decentralized Clusters (Kube) for SOTA AI Services in Trusted Execution Environment (TEE)

> Enterprise-grade confidential computing for **SOTA AI services** and **enhanced services for enterprises** on decentralized Kubernetes across Bittensor miner clusters

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
[![X](https://img.shields.io/badge/X-@KubeTEEAI-black)](https://x.com/KubeTEEAI)

---

## About

**KubeTEE AI** is the **AI Factory** of the Bittensor network: it turns decentralized GPU clusters into a confidential factory for **SOTA AI services** and **enhanced services for enterprises**. Inference, NeMo microservices, retrieval, and agents run inside hardware-secured Trusted Execution Environments (TEE) using [Kata Containers](https://katacontainers.io/) and [Confidential Containers (CoCo)](https://github.com/confidential-containers/confidential-containers). **Batch jobs** (fine-tune, eval, multi-step pipelines) are one of those services — scheduled by [Armada](https://armadaproject.io/) when an enterprise needs them — not the product itself.

KubeTEE AI is registered with the [**NVIDIA Inception Program**](https://www.nvidia.com/startups/) and is an active contributor to both the [**Kata Containers**](https://katacontainers.io/) and [**Confidential Containers (CoCo)**](https://github.com/confidential-containers/confidential-containers) ecosystems. It also leverages [**CNCF**](https://www.cncf.io/) projects for cloud-native infrastructure.

### About the Owner

Known as Pierre in the Bittensor community, I have mined since February 2024. I was the first to bring Confidential Computing nodes to Targon (Subnet 4), later helped Chutes (Subnet 64) onboard B200/B300 nodes, and most recently worked with the Lium (Subnet 51) team to deploy Confidential Computing on their stack. Beyond Bittensor, I was also the first to provide Confidential Computing to Telegram Cocoon and Phala Network.

Forty years in infrastructure architecture and deployment at scale. I started in 1986 installing Linux and Novell servers, and in 1992 built one of the first internet providers in Canada. I deployed internet distribution infrastructure in Morocco and have managed tech stacks at scale for cloud providers. One of my specialty is security, and I have done multiple security audits for Fortune 500 companies.

### Motivation

My expertise in Confidential Computing, Kubernetes, networking, and security at the kernel and hardware level can benefit the Bittensor ecosystem. Having run infrastructure for the compute subnets for more than two years — monitoring, upgrades, and improvements to each subnet tech stack including recently onboarding B200/B300 on Chutes and H200 on Lium — I want to offer a different tech stack that I believe the ecosystem can benefit from and build on: the most secure and efficient decentralized AI Factory stack available.

**Direct Engineering Collaboration**: I work directly with **Intel** and **NVIDIA** engineers throughout the development and testing of NVIDIA technology, especially Kata and CoCo Containers. This close collaboration ensures optimal integration of confidential computing features, early access to emerging technologies, and validation of the KubeTEE implementation against the most stringent security and performance standards.

I actively contribute to OpenInfra and CNCF projects — [Kata Containers](https://katacontainers.io/) and [Confidential Containers (CoCo)](https://github.com/confidential-containers/confidential-containers) provide the TEE foundation for Kubernetes orchestration.

### Confidential Computing Consortium Resources

As a member of the [Confidential Computing Consortium (CCC)](https://confidentialcomputing.io/), I recommend two references:

- **[Protecting Agentic AI Workloads with Confidential Computing](https://confidentialcomputing.io/2026/01/20/protecting-agentic-ai-workloads-with-confidential-computing/)** (January 2026) — Mike Bursell, CCC Executive Director, on why an agent running in infrastructure its owner does not control needs hardware-rooted isolation and remote attestation to get identity integrity and capability confidentiality. That is precisely the threat model KubeTEE's Intel TDX/SGX + NVIDIA CC architecture addresses.
- **[Gartner Top 10 Strategic Technology Trends for 2026](https://www.gartner.com/en/articles/top-technology-trends-2026)** — Gartner ranks **Confidential Computing #3**, alongside AI Supercomputing Platforms (#2), Multiagent Systems (#4), Preemptive Cybersecurity (#7), Digital Provenance (#8), and AI Security Platforms (#9). KubeTEE spans all three of Gartner's themes: The Architect (AI infrastructure), The Synthesist (orchestration), and The Vanguard (security and trust).

### Mission & Vision

**Mission**: To turn decentralized multi-cluster GPU nodes into a worldwide (and in-space) confidential AI factory — hosting **SOTA AI services** and **enhanced services for enterprises** in Trusted Execution Environments across Bittensor miner clusters, with the highest standards of security, compliance, and performance. Batch jobs are a secondary service on the same clusters.

**Key Differentiators**:
- **Security-First**: TEE-enabled infrastructure on a FIPS-validated RKE2 baseline with Kata Containers isolation
- **Multi Cluster Scheduler**: multi-cluster batch scheduling with fair-use queuing, gang scheduling, and preemption across decentralized clusters
- **SOTA AI services**: NeMo Microservices, NIM models, and AI Blueprints as first-class confidential enterprise services — and, where NVIDIA's own stack falls short (see [Kata / CoCo Limitations](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#4-kata--coco-limitations-nvidia)), SOTA [Bittensor subnet integrations](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#5-bittensor-subnet-integrations-sota-confidential-ready) running inside Kata + CoCo TEE instead
- **Decentralized**: one hotkey per cluster, nodes located in distinct data center, expanding across global regions
- **Open Source**: Built on OpenInfra Foundation and CNCF projects with community-driven innovation

---

## Table of Contents

- [About](#about) — owner, motivation, mission
  - [About the Owner](#about-the-owner)
  - [Motivation](#motivation)
  - [Confidential Computing Consortium Resources](#confidential-computing-consortium-resources)
  - [Mission & Vision](#mission--vision)
- [Overview](#overview)
  - [Early Access](#early-access)
  - [What Ships Today](#what-ships-today)
- [The Confidential Compute Challenge: Problems We Solve](#the-confidential-compute-challenge-problems-we-solve)
- [Deploying in a TEE: The Engineering Challenge](#deploying-in-a-tee-the-engineering-challenge)
- [Debugging on the staging cluster](#debugging-on-the-staging-cluster)
- [Architecture](#architecture)
  - [Confidential Computing (Kata + CoCo)](#confidential-computing-kata--coco)
  - [Infrastructure](#infrastructure) — RKE2 HA; Armada for the batch-job service
  - [Security & Compliance](#security--compliance)
  - [Multi-Cluster Topology](#multi-cluster-topology)
  - [Early Access Topology](#early-access-topology)
- [Supported SOTA AI Services](#supported-sota-ai-services)
  - [Serving Configurations](#serving-configurations--every-service-requires-fast-inference)
  - [NVIDIA NeMo Microservices & Bittensor Subnet Integrations](#nvidia-nemo-microservices--bittensor-subnet-integrations) — attestation-gated TLS, NIM Operator Kata/CoCo limits, SOTA Bittensor subnet substitutes, Stage 0 supply-chain CI
- [Subnet Economics](#subnet-economics)
  - [Incentive Mechanism: Infrastructure](#incentive-mechanism-infrastructure-early-access)
  - [Payment methods](#payment-methods)
  - [Staging vs Production](#staging-vs-production)
- [Tokenomics — Utility Token & DePIN Model](#tokenomics--utility-token--depin-model)
- [Validator Scoring & Attestation](#validator-scoring--attestation)
  - [Validator Runtime (TEE)](#validator-runtime-tee)
  - [Evidence Feeds](#evidence-feeds)
  - [Competitive Pricing](#competitive-pricing)
  - [Weight Setting](#weight-setting)
- [Submitting a Confidential Job](#submitting-a-confidential-job)
  - [LiteLLM Gateway — the multi-service front door](#litellm-gateway--the-multi-service-front-door)
  - [SN28 sayGM — idle capacity, not the product](#sn28-saygm--idle-capacity-not-the-product)
  - [Workflow Orchestration (Airflow & Metaflow)](#workflow-orchestration-airflow--metaflow)
  - [Jobs MCP Server](#jobs-mcp-server) — agent and chat-driven job deployment
- [For Miners (Infrastructure)](#for-miners-infrastructure)
  - [Miner onboarding](#miner-onboarding)
  - [Miner deposit (registration collateral)](#miner-deposit-registration-collateral)
- [Roadmap](#roadmap) — [Phase 0](#phase-0--early-access-current) · [Phase 1](#phase-1--expansion) · [Phase 2](#phase-2--paid-jobs) · [Phase 3](#phase-3--job-type-growth)
- [Research & Documentation](#research--documentation)
- [Community & Support](#community--support)

---

## Overview

KubeTEE AI Factory provides enterprise-grade confidential computing for **SOTA AI services** on a decentralized multi-cluster Kubernetes RKE2 infrastructure. Services run inside Trusted Execution Environments (TEE) so that data and models are protected **at rest, in transit, and in use** — and never leave the confidential computing boundary. **Batch jobs** (fine-tune, eval, pipelines) are a secondary service on the same clusters, submitted to Armada queues when needed.

Each miner cluster is identified by a permanent Bittensor **hotkey/coldkey** pair. **SOTA AI services** run as Kubernetes pods under a confidential `runtimeClassName` so they are hardware-isolated and attested. When that service is a batch job, Armada dispatches it. TEE classes are **`kata-qemu-nvidia-gpu-tdx-runtime-rs`** (GPU) and **`kata-qemu-tdx-runtime-rs`** (CPU-only). Every node on the **staging cluster** is TEE CC capable. Kata guest debug is **off**; CoCo Trustee attests those guests. For diagnostics, CC can be turned **off** on a staging node, and guest debug can be enabled **per pod**; Trustee attests only when debug is off.

The RKE2 baseline is **[FIPS-140-2 validated](https://docs.rke2.io/security/fips_support)** today; FIPS-140-3 is a [Phase 3](#phase-3--job-type-growth) target. Both are referred to below simply as the FIPS-validated baseline.

> **Open-source by default.** Every technology in the KubeTEE stack is open source — RKE2, Rancher, Kata Containers, Confidential Containers, Armada, LiteLLM, Longhorn, cert-manager, NVIDIA GPU Operator, and the Bittensor subtensor SDK. KubeTEE does not vendor-lock or proprietary-fork any of them. Where KubeTEE adds patches, fixes, or features (e.g. the Kata runtime-rs NVSwitch passthrough fix, the CSI direct-volume data-loss fix, the LiteLLM provider integration), the modifications live in **forks under the [KubeTEE-AI](https://github.com/KubeTEE-AI) GitHub organization** and are contributed upstream wherever the upstream project accepts them. The forks are public so anyone can audit what changed, and the contribution path back to upstream is the long-term goal for every patch.

### Early Access

KubeTEE is in **Early Access**. The first deployment targets **two clusters in the USA**, one hotkey each, with all nodes of a cluster co-located in a single data center. Early Access focuses on:

- Standing up the Armada multi-cluster batch scheduler across miner clusters
- Running confidential AI jobs in Kata + CoCo TEE pods
- A **staging cluster** operated by Pierre as the subnet-owner staging miner — all nodes are TEE CC capable. Workloads run on miner clusters; if a workload fails, it can be targeted at staging for debug. Kata guest debug is **off**; CoCo Trustee attests those guests. CC can be turned off on a staging node for debug; guest debug can be enabled per pod. See [Debugging on the staging cluster](#debugging-on-the-staging-cluster)
- The **validator incentive mechanism**: scoring miners on TEE attestation, Armada job success, uptime, and **competitive pricing** against the other compute subnets (Targon, Lium, Chutes)
- **Emissions + Alpha/TAO paid jobs** — the supply and demand sides of a single mechanism (see [Subnet Economics](#subnet-economics))

### What Ships Today

This README documents both what runs in the KubeTEE infrastructure and what is designed. Sections describing unimplemented work carry a status note pointing back here; this table is the single source of truth for the distinction. **The Bittensor validator v1 is built, tested, and live on Finney** — it scores the subnet-owner staging miner on a single Infrastructure mechanism and sets weights once per epoch. The "Designed / to be built" column lists future-scoring dimensions on top of that base.

| Area | Exists today (infrastructure / design) | Designed / to be built |
|------|--------------------|--------------------|
| **Confidential&nbsp;runtime** | Kata + CoCo TEE runtime classes on TDX H200/B200 nodes | AMD SEV-SNP multi-arch + RTX 5000 Pro Server Edition testing ([Phase 1](#phase-1--expansion)) |
| **Service&nbsp;transport** | Grey-cloud DNS + Traefik TLS passthrough into the LiteLLM TDX guest. [Attestation-gated TLS](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#2-attestation-gated-tls-between-services) (RA-TLS: TLS public key in TDX `report_data`, Trustee + Intel Trust Authority) is the client-attested hop on top of that path | Native TLS from the LiteLLM guest to NIM guests on miner clusters |
| **Staging&nbsp;cluster** | Subnet-owner staging cluster — every node is TEE CC capable. Debug target if a workload fails. Kata **guest debug off**; CoCo Trustee attests those guests. CC can be turned off on a node for debug; guest debug can be enabled per pod. | — |
| **Security&nbsp;gate** | — | Supply-chain CI (SAST, Trustee/KBS secrets, image CVE, IaC/Helm policy, image provenance) — design, not yet automated |
| **Validator&nbsp;scoring** | **v1 live on Finney:** binary infrastructure-readiness gate (hotkey binding, Rancher readiness, HA topology, capacity, 8-GPU passthrough, confidential runtime handler) + USD-denominated compensation pricing via Taostats + Targon SN4 supply-side clamp + [KubeTEE Validator/Miners Dashboard](https://s3.hippius.com/kubetee-validator/index.html) (hosted on Hippius) | `PROBATION`→`EARNING` state machine; fresh TEE attestation, Armada job metrics, serving probes, workload identity |
| **Validator&nbsp;pricing** | **v1 live:** Taostats compensation feed (`api/dtao/pool/latest/v1`) + Targon SN4 payout feed (`stats.targon.com/api/miners`) + per-GPU price card (H100 $4 / H200 $5.50 / B200 $8 / B300 $10 / RTX6000 $2.50 /GPU/hr); one `set_weights` per epoch with rate-limit cooldown | Lium / Chutes demand-side scrape, per-job-class target price, price-competitiveness weighting |
| **Validator&nbsp;runtime** | **v1 live:** flat self-contained Python unit (12 modules, 35 tests) running as a container on the operator's machine; sets weights once per epoch | Run inside a Kata + CoCo TEE pod on the control plane with CoCo remote attestation (the referee itself attested) |
| **Armada** | — | **In development** — Server on the control plane, Executor on each miner cluster ([Phase 0](#phase-0--early-access-current)); move into Kata + CoCo TEE pods with attestation-gated TLS ([Phase 1](#phase-1--expansion)) |
| **Miner&nbsp;onboarding** | KubeTEE applies the hotkey binding | Permissionless self-service ([Phase 1](#phase-1--expansion)) |
| **Miner&nbsp;deposit** | 100 TAO gate **measured, not enforced** | On-chain collateral bonding ([Phase 1](#phase-1--expansion)) |
| **Payments** | Alpha / TAO at a resources price per hour. **TAO is live on Base** (Chainlink CCIP-bridged ERC-20, Aerodrome TAO/USDC — [ForeverMoney SN98](https://x.com/forevermoney_ai/status/2090469070248235027), 2026-08-21) | USDC-on-BASE and TAO-on-BASE job billing + automated recycle ([Phase 2](#phase-2--paid-jobs)) |
| **LiteLLM&nbsp;gateway** | `llm.kubetee.ai` — OpenAI-compatible inference plus virtual keys, budgets, rate limits, and spend tracking. Cloudflare DNS-only (grey cloud) to oakland node IPs. LiteLLM runs in `kata-qemu-tdx-runtime-rs` with guest debug off; Traefik TLS passthrough terminates in the guest. CoCo Trustee attests the guest. Inference backends are in-cluster NIM on the staging cluster; miner clusters are extra `api_base` rows under the same `model_name`. | Wire `/mcp` and `/a2a` surfaces and the fine-tuning / batch endpoints through to Armada; KubeTEE as an upstream LiteLLM **provider**; RA-TLS so clients attest the terminator |
| **Inference&nbsp;models** | **Live on the staging cluster** through `llm.kubetee.ai`: GLM-5.2, DeepSeek-V4-Flash-0731, **Ornith-1.5-397B**. **SN28 (sayGM) live 2026-08-19** as an **idle-capacity** demand channel — not SN90's product, not an exclusive public-inference path. Paid offers: `z-ai/glm-5.2` **48.25%** below retail, `deepseek/deepseek-v4-flash-0731` **50%** below retail ([SN28-SAYGM.md](./docs/SN28-SAYGM.md)). Free window closed at **14,812,329,857** tokens. **In collaboration with SN28 sayGM, KubeTEE was the first to provide Ornith-1.5-397B worldwide** (2026-08-20). | Expand the confidential model catalogue (more GPU classes, embedding/judge/retrieval models). Do not declare Kimi/Qwen/MiMo on SN28. |
| **Jobs&nbsp;MCP&nbsp;server** | — | **Not developed yet** — agent- and chat-driven job deployment at `llm.kubetee.ai/mcp` ([Phase 1](#phase-1--expansion)) |
| **Albedo&nbsp;SN97&nbsp;eval&nbsp;PoC** | **Parked (2026-08-13).** 100-sample king-of-the-hill eval succeeded 2026-08-09 on `na-us-oakland-56`. Revisit when Armada + CoCo Trustee are the complete job flow so upstream SN97 deploys **without modifications or architecture changes** — [SN97-ALBEDO-POC.md](./docs/SN97-ALBEDO-POC.md) | Complete Armada + Trustee, then deploy unmodified Albedo / Denrite |

---

## The Confidential Compute Challenge: Problems We Solve

Enterprises running sensitive SOTA AI services — inference, agents, training, fine-tuning, data processing — face an impossible choice between security, cost, and trust. KubeTEE resolves all three:

1. **Private data & models must stay private** — Public cloud AI and traditional deployments expose data in memory and give providers/insiders access. KubeTEE enforces hardware TEE isolation (Intel TDX/SGX, NVIDIA CC) via Kata + CoCo, with remote attestation so you can verify the exact code running on your data; data is protected at rest, in transit, and in use.
2. **Regulated AI services need verifiable compute** — Healthcare (HIPAA), Finance (SOC2/PCI-DSS), Government (FedRAMP) need proof of isolation. KubeTEE provides a FIPS-validated RKE2 baseline, cryptographic attestation, audit trails (Prometheus, Kubernetes events), and isolated namespaces for tenant separation.
3. **Trust in decentralized infrastructure** — Centralized clouds are single points of failure with vendor lock-in. KubeTEE's decentralized multi-cluster architecture, Bittensor incentives, validator attestation, and open standards (Kubernetes, Armada, Kata, CoCo) remove the single point of failure and the lock-in.

---

## Deploying in a TEE: The Engineering Challenge

The section above is why customers need confidential compute. This one is why it is hard to build — and why Early Access keeps a CC-capable staging cluster as a **debug target** when a workload fails, rather than a required promotion workflow.

**A confidential pod is a virtual machine with an encrypted, attested memory boundary, not a namespaced process on the host.** Every assumption a Kubernetes workload makes about devices, storage, resources, startup time, and debuggability is renegotiated at that boundary — multi-GPU/NVSwitch passthrough, guest-vs-pod sizing, cold start, storage semantics, observability, destructive failures, and version-coupled stacks. Each has been hit bringing up this stack, and most have an upstream issue attached.

Two consequences follow directly, and they shape Early Access:

1. **CC can be turned off on a staging node for debug.** Every staging node is TEE CC capable. Turning CC off (or guest debug on for a pod) is a diagnostic choice so an operator can tell "the workload is broken" from "the TEE path is broken."
2. **Guest debug is off by default so CoCo Trustee can attest the guest.** Turning debug on for a pod is a diagnostic choice: that guest is then not attested. Staging and miner TEE pods run with debug off unless an operator enables it on that pod.

More on staging as a debug target: [Deploying in a TEE — Challenge and debugging](./docs/TEE-DEPLOYMENT-AND-CICD.md).

### Example: Upstream Participation — kata-containers #13535

KubeTEE does not just consume upstream projects; it hardens them and reports what it finds. A concrete example from Early Access:

While bringing up a 2.5 TB Kimi-K3 inference pod (8× B300 GPU passthrough) under `kata-qemu-nvidia-gpu-tdx-runtime-rs`, the sandbox hung at boot and hit the 1200s `create_container` timeout before the guest kernel even started. Root cause: the `OVMF.inteltdx.fd` shipped in **kata-deploy v4.0.0** performs **eager memory acceptance** for Intel TDX guests — spending all its time in `TDCALL [TDG.MEM.PAGE.ACCEPT]` for large-memory VMs. The distro `ovmf-inteltdx` (Ubuntu, with lazy-accept enabled by `PcdLazyAcceptPartialMemorySize=512`) booted the same 512 GB TDX VM in under 15 seconds. KubeTEE filed the issue with full evidence (serial logs, kata config, kernel `CONFIG_UNACCEPTED_MEMORY=y`), root-cause analysis (Config-A vs Config-B build, PCD defaults), and three proposed solutions — [kata-containers#13535](https://github.com/kata-containers/kata-containers/issues/13535).

This is the model: hit the failure in production, isolate it (CC off on a staging node for debug, plus the distro OVMF comparison), file it upstream with a reproducible root cause and a fix proposal, and carry a local workaround until the upstream fix lands. KubeTEE maintains a fork branch (`ovmf-tdx-bump-202605`) with a pre-built Config-B OVMF from `edk2-stable202605` and a reproducible build script for pipeline testing.

---

## Debugging on the staging cluster

Workloads run on **miner clusters** (CC on, guest debug off; CoCo Trustee attests). There is no required staging promotion workflow.

If a workload fails, it can be targeted at the **staging cluster** for diagnostics. Every staging node is TEE CC capable. CC can be turned off on a node for debug, and guest debug can be enabled **per pod**. Trustee attests only when debug is off.

```mermaid
flowchart LR
    Jobs["AI service"] --> Miners["Miner clusters<br/>CC on, guest debug off<br/>CoCo Trustee attests"]
    Jobs -.->|"on failure, debug"| Staging["Staging cluster<br/>CC-capable; CC off and<br/>per-pod guest debug available"]
```

Supply-chain CI (SAST, Trustee secrets, image CVE, IaC) is designed, not yet automated — see [the security gate](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#6-stage-0--supply-chain-security-gate). Detail: [Deploying in a TEE](./docs/TEE-DEPLOYMENT-AND-CICD.md).

---

## Architecture

### Confidential Computing (Kata + CoCo)

**Trusted Execution Environment (TEE)**
- Kata Containers for workload isolation
- Confidential Containers with Workload Identity Validation
- Intel TDX/SGX
- NVIDIA Hopper/Blackwell/Vera Rubin

Confidential services execute under the TEE runtime classes in the [Overview](#overview). On staging, every node is TEE CC capable; Kata guest debug is off and CoCo Trustee attests those guests. CC can be turned off on a staging node for debug. Batch jobs use the same runtime classes; see [Armada Multi-Cluster Batch Scheduling](#armada-multi-cluster-batch-scheduling) for that secondary path.

### Infrastructure

#### Kubernetes High Availability

**RKE2 Rancher Kubernetes**
- FIPS-validated, U.S. Federal Government Grade Security
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

**Confidentiality of the scheduler itself** is a second step, not part of the initial install. Phase 0 stands Armada up; [Phase 1](#phase-1--expansion) moves the Server and Executors into Kata + CoCo TEE pods and puts [attestation-gated TLS](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#2-attestation-gated-tls-between-services) on the Server-to-Executor control channel, so a scheduler will not dispatch to an executor that cannot attest and an executor will not accept work from an unattested scheduler. Until then the scheduler is trusted infrastructure while the *jobs* it dispatches are already confidential.

**Confidential execution**:
- Jobs land on nodes with a confidential `runtimeClassName` — `kata-qemu-nvidia-gpu-tdx-runtime-rs` for Intel TDX + NVIDIA GPU passthrough, `kata-qemu-tdx-runtime-rs` for CPU-only TDX. On staging, CC can be turned off on a node for debug.
- **CoCo + Trustee/KBS** handle remote attestation when guest debug is off, so the job image needs no modification to run confidentially. Debug can be enabled per pod for diagnostics.

Armada addresses Kubernetes batch limitations that matter for the Factory: single-cluster scaling limits, etcd throughput ceilings, and the lack of fair-use / gang scheduling in the default kube-scheduler.

> **Status:** Armada is not deployed yet. Standing up the Server and Executors is a [Phase 0](#phase-0--early-access-current) item; moving them into TEE is [Phase 1](#phase-1--expansion) ([What Ships Today](#what-ships-today)).

### Security & Compliance

#### Network Security
- Network Policies enforcement (Calico)
- RBAC (Role-Based Access Control)

#### Data Protection
- **Rancher Longhorn**: Encrypted Storage with 3 Replicas
- Encrypted Container Repository
- **CoCo Trustee / KBS** — secrets and image-decryption keys are released only to an attested guest (guest debug off). Not Kubernetes Secrets, not Git.

#### Monitoring & Audit
- Prometheus Metrics
- Kubernetes Events tracking
- UpTime, QoS, and Performance monitoring
- Loki + Grafana Alloy log aggregation

### Multi-Cluster Topology

#### Subnet Owner Infrastructure
- Global Multi-Cluster Control Plane with Rancher on Confidential Computing TEE
- Rancher Multi-Cluster Management with Fleet for GitOps
  - RKE2 Rancher Kubernetes (FIPS-validated baseline)
  - Kata Containers (TEE)
  - [Confidential Containers](https://confidentialcontainers.org/docs/overview/) Operator
  - Armada Server (controller, scheduler, lookout + Pulsar/Redis/Postgres)
- Validator runs in a TEE on the control plane; KubeTEE can also host the validator code (see [Validator Runtime (TEE)](#validator-runtime-tee))

#### Miner Infrastructure
- RKE2 Rancher Kubernetes
- One Cluster per Miner (identified by hotkey, not UID)
  - One data center per cluster — all nodes co-located in a single DC
  - Regional deployment (One Region/Zone Control Plane with same region workers)
  - Cluster carries the `kubetee.ai/hotkey` binding label, **applied by the
    KubeTEE platform** during enrollment — not something the miner creates
- Kata Containers and CoCo Containers (TEE)
- Armada Executor + Installer (scheduled by the subnet-owner Armada Server)
- Fleet Agent for automated deployments


### Early Access Topology

```mermaid
flowchart LR
    subgraph owner["Subnet Owner Control Plane"]
        Validator["Validator\nweights + emissions"]
        ArmadaServer["Armada Server\nscheduler + queues\nPulsar/Redis/Postgres"]
    end
    subgraph staging["KubeTEE Staging Cluster — subnet-owner"]
        NodeTEE["CC-capable TDX GPU nodes (H200 / B200)<br/>kata-qemu-nvidia-gpu-tdx-runtime-rs<br/>guest debug off; Trustee attests<br/>CC can be turned off for debug"]
    end
    subgraph clusterA["Miner Cluster A — 1 hotkey, 1 DC (USA)"]
        ExecA["Armada Executor"]
        NodeA["GPU nodes\nkata-qemu-nvidia-gpu-tdx-runtime-rs\nguest debug off"]
    end
    subgraph clusterB["Miner Cluster B — 1 hotkey, 1 DC (USA)"]
        ExecB["Armada Executor"]
        NodeB["GPU nodes\nkata-qemu-nvidia-gpu-tdx-runtime-rs\nguest debug off"]
    end
    Client["Job Submitter\nNeMo/NIM/Blueprint job"] -->|submit| ArmadaServer
    Client -.->|"on failure, debug"| NodeTEE
    ArmadaServer -->|schedule| ExecA
    ArmadaServer -->|schedule| ExecB
    ExecA --> NodeA
    ExecB --> NodeB
    NodeA -.->|attestation + metrics| Validator
    NodeB -.->|attestation + metrics| Validator
    Validator -->|set weights| Chain["Bittensor\nemissions"]
```

> The **Validator** runs on the control plane inside a confidential Kata + CoCo TEE pod (see [Validator Runtime (TEE)](#validator-runtime-tee)). The **Armada Server** and **Executors** are drawn here as designed: they are stood up in [Phase 0](#phase-0--early-access-current) and move into TEE pods in [Phase 1](#phase-1--expansion) ([What Ships Today](#what-ships-today)).
>
> The **staging cluster** is KubeTEE's own. Every node is TEE CC capable. It is a **debug target** if a workload fails — not a required promotion step. Kata guest debug is **off**; CoCo Trustee attests those guests. CC can be turned off on a staging node for debug; guest debug can be enabled per pod. Miner clusters keep CC on with guest debug off. See [For Miners (Infrastructure)](#for-miners-infrastructure) and [Debugging on the staging cluster](#debugging-on-the-staging-cluster).

---

## Supported SOTA AI Services

KubeTEE AI Factory hosts **SOTA AI services** and **enhanced services for enterprises** inside Kata + CoCo TEE pods — inference (NIM / SGLang), NeMo microservices, retrieval, and agents — shared HA per cluster. The Factory ships first-class templates on the NVIDIA AI stack — NeMo Microservices, NIM models, and AI Blueprints.

**Batch jobs** (fine-tune, eval, multi-step pipelines) are a secondary service on the same clusters. When an enterprise needs that path, the job is submitted to an Armada queue.

### Serving Configurations — Every Service Requires Fast Inference

Confidential execution is not an excuse for slow inference. **Every AI service on KubeTEE requires fast inference**, whether it is an agent loop, a consumer chat session, or an overnight batch. The Kata + CoCo boundary is a security property, not a performance tax, and each service is held to a latency and throughput target inside the TEE.

No single operating point serves an agentic tool-calling loop and a heavy-context batch equally well, so **every model is published in three serving configurations**. All three run the same attested weights on the same confidential runtime — what differs is how the serve is tuned: concurrency ceiling, batching and chunked-prefill sizing, KV-cache budget, and speculative decoding.

| Configuration | Target service | Optimized for |
|---------------|-----------------|---------------|
| **Low-latency** | Agentic, low concurrency | Time-to-first-token and per-token latency for tool-calling loops, where every hop blocks the caller. Concurrency is deliberately capped to keep the tail predictable. |
| **Balanced** | General, consumer-aligned | The default consumer-facing operating point — interactive chat responsiveness at a sane occupancy per GPU. |
| **High-throughput** | Batches and heavy-context jobs, no human in the loop | Aggregate tokens per second per GPU — long-context ingestion, evaluation sweeps, and bulk generation, where queueing is acceptable and hardware efficiency dominates. |

A consumer picks the configuration alongside the model at submission. Because the choice determines how much hardware the job occupies and for how long, it is the main lever a consumer has over the resources price per hour (see [Subnet Economics](#subnet-economics) and [Jobs MCP Server](#jobs-mcp-server)).

### NVIDIA NeMo Microservices & Bittensor Subnet Integrations

[NVIDIA NeMo Microservices](https://docs.nvidia.com/nemo/microservices/latest/about/index.html) (Customizer, Evaluator, Guardrails, Retriever, model endpoints) run as **cluster-resident services** that other SOTA AI services — and, secondarily, batch jobs — call inside the confidential boundary — shared HA per cluster, amortized across every consumer. Service-to-service traffic uses **attestation-gated TLS** (in-guest keypairs, certificates issued only against a valid TDX quote, verified through Intel Trust Authority, terminated inside the guest) — not cert-manager, not a service mesh, not host-level encryption, because the host is the adversary. The NVIDIA NIM Operator has **experimental** Kata sandbox + Dynamo support, but KubeTEE runs the **stable** `kata-qemu-nvidia-gpu-tdx` runtime classes instead and is working with NVIDIA to graduate the experimental paths (Phase 3).

Given the NIM Operator's current Kata/CoCo limitations, KubeTEE's thesis is that **the Bittensor ecosystem already contains SOTA, verifiable substitutes** for several NeMo stack layers. Each subnet below exposes a verifiable feed (public API + on-chain metagraph) and is a **potential partnership** — a candidate integration, not a shipping integration — that could run inside `kata-qemu-nvidia-gpu-tdx` / `kata-qemu-tdx` with its outputs attested and persisted on confidential storage. This is the Bittensor-native path to a confidential AI Factory not locked to a single vendor's experimental stack.

| NeMo layer | Bittensor subnet (potential partner) | What it could replace/augment |
|---|---|---|
| Data Designer | [Orion SN27](https://github.com/SILX-LABS/Orion) | Decentralized data discovery / generation / curation with on-chain quality validation |
| Customizer (fine-tuning) | [Gradients SN56](https://www.gradients.io/) | AutoML tournaments — open-source SFT/DPO/GRPO training scripts |
| Customizer (RL/reasoning) | [Affine SN120](https://www.affine.io/) | Incentivized RL "reason mining" — challenger-vs-champion duels |
| Customizer (distillation) + Evaluator + Inference | [Albedo SN97](https://github.com/unarbos/distil) ([albedo](https://github.com/unarbos/albedo)) | Competitive **model distillation** (not coding agents): miners compress a large teacher into ≤33B students; validators run king-of-the-hill duels on a multi-axis composite; the reigning king is a reusable open checkpoint ([chat.arbos.life](https://chat.arbos.life) upstream). **PoC parked 2026-08-13** after a successful 100-sample run (2026-08-09); revisit when Armada + CoCo Trustee can run **unmodified** SN97 — [SN97-ALBEDO-POC.md](./docs/SN97-ALBEDO-POC.md) · [upstream PR](https://github.com/unarbos/albedo/pull/4) |
| Retriever / RAG | [Desearch SN22](https://desearch.ai/) | Decentralized real-time web + X/Twitter search for AI agents |
| Video Search & Summarization | [Score SN44](https://github.com/score-technologies/turbovision) | Decentralized computer vision — object detection, tracking, structured annotations |
| Inference + distributed training | [Chutes SN64](https://chutes.ai/) / Parallax | Serverless inference + decentralized MoE training (already fully TEE-only) |
| Persistent storage | [Hippius SN75](https://hippius.com/) | S3-compatible + IPFS pinning (already ships AMD SEV-SNP CC) |
| Agent memory / context | [Ditto SN118](https://heyditto.ai/) | Open-source persistent memory layer for AI agents (Claude / Cursor / MCP) |

This is an **open set**: any Bittensor subnet with a SOTA, verifiable solution for a NeMo stack layer is a candidate. The full table with SOTA roles, confidential-computing fit, and the "could replace/augment" mapping: [NeMo Microservices & Bittensor Subnet Integrations](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#5-bittensor-subnet-integrations-sota-confidential-ready).

**Stage 0 is ordinary supply-chain CI**, not a Bittensor subnet. Workloads are gated on SAST, image CVE/SCA, IaC/Helm policy, and image provenance before they run on miner clusters. **Secrets live in CoCo Trustee / KBS** and are released only to an attested guest — they are not Kubernetes Secrets and must not appear in Git, Helm, or image layers ([supply-chain CI](./docs/TEE-DEPLOYMENT-AND-CICD.md#supply-chain-ci), [secrets and images](./docs/TEE-DEPLOYMENT-AND-CICD.md#secrets-and-images)). [BitSec SN60](https://bitsec.ai/) is a Solidity-agent contest scored on SCA-Bench; it does **not** fit that gate. An optional later partnership is a one-time audit of SN90 validator/incentive code, kept out of the CI gate — [why SN60 is not the gate](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#6-stage-0--supply-chain-security-gate).

Full detail — the attestation-gated TLS protocol, the NIM Operator experimental paths and Kata/CoCo limitations, the subnet integrations table, and the Stage 0 gate: [NeMo Microservices & Bittensor Subnet Integrations](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md).

---

## Subnet Economics

### Incentive Mechanism: Infrastructure (Early Access)

KubeTEE Early Access uses a **single Infrastructure incentive mechanism** with two sides. On the **supply side**, miners earn Bittensor emissions for providing confidential compute capacity and reliably executing Armada-scheduled jobs; emissions are distributed per resources provided (GPU nodes), weighted by attested TEE health, job-execution quality, and uptime. On the **demand side**, consumers pay Alpha or TAO at a published **resources price per hour** for the compute they consume.

**TEE attestation is mandatory** — Intel TDX/SGX and NVIDIA CC must be proven, and **no attestation means no emissions**. Compliance is enforced rather than requested, higher-tier GPU nodes earn more, and a miner is paid on capacity it makes available *and can prove*.

#### Payment methods

**Subnet 90 Alpha, other subnets' Alpha, and TAO** are all accepted at the published resources-per-hour price. There are **no discounts and no referrer or reseller program**: SN90 compute is already priced competitively because it is subsidized by subnet emissions, so a discount layer would simply be gamed (see the [Tokenomics](#tokenomics--utility-token--depin-model) boundary conditions).

**TAO is live on Base** (2026-08-21) as a Chainlink CCIP-bridged ERC-20 — announced by [ForeverMoney (SN98)](https://x.com/forevermoney_ai/status/2090469070248235027), tradeable against USDC on Aerodrome (`0xf3081494b87e8d5fb7960f066e931d1d0e6e3d67`). A consumer can buy TAO from USDC or ETH in a Base wallet, without a Bittensor-native wallet, then spend it for SN90 compute. Finney TAO and TAO-on-BASE are the same asset on two rails; CCIP is the canonical bridge ([forevermoney.ai](https://forevermoney.ai/)). This is the acquisition path — settlement of a job still recycles Alpha on Finney (see [Tokenomics](./docs/TOKENOMICS.md#tao-on-base)).

The price itself is **competitive** (benchmarked against Targon/Lium/Chutes) and **dynamic with queue depth** — see [Competitive Pricing](#competitive-pricing). **USDC-on-BASE and TAO-on-BASE billing** plus **automated USDC→TAO-on-BASE→Finney TAO→Alpha recycling** layer on in [Phase 2](#phase-2--paid-jobs). The Base rail is no longer a custom-bridge problem: TAO itself is the Base asset.

#### Staging vs Production

**Staging Environment** (Subnet Owner):
- Operated by the subnet-owner. Every node is TEE CC capable. Debug target if a workload fails — not a required promotion step. Kata guest debug is **off**; CoCo Trustee attests those guests. CC can be turned off on a node for debug; guest debug can be enabled per pod ([Deploying in a TEE](./docs/TEE-DEPLOYMENT-AND-CICD.md))
- Test applications, infrastructure, upgrades; community Staging jobs

**Production Environment** (Permissionless with minimum qualification and collaterals):
- Multi-cluster — one per data center per miner hotkey
- Must pass minimum requirements (hardware, HA topology, 8-GPU workers, passthrough wiring), TEE attestation, and infrastructure-readiness validation
- **TEE-only, Kata guest debug off**, CoCo Trustee attests
- Verified accreditation — IP addresses and data center certifications/accreditations for regulated workloads

---

## Tokenomics — Utility Token & DePIN Model

SN90 (KubeTEE) Alpha is a **utility token consumed to access confidential compute**, not a security. The design follows a DePIN subsidy model: external inference demand buys Alpha on the open market and spends it to consume compute; spent Alpha is **recycled** to unissued supply and re-emitted through the protocol's fixed emission split — a self-sustaining security budget for the compute network (the Bitcoin-fee model applied to Alpha).

- **Owner conviction auto-locked to perpetuity** — KubeTEE AI LTD owns the 18% owner emission stream and the $198k (≈1,003 TAO) subnet registration; 100% of its dTAO conviction is programmatically re-locked on-chain so it never decays and is never withdrawn. The owner holds no discretionary liquid position to sell — removes the large-discretionary-insider-position fact pattern from the securities analysis.
- **Recycle vs burn** — spent Alpha is **recycled** (returned to unissued supply, extends the emission runway, refills the miner budget), not burned. For a compute subnet whose product is ongoing work, recycle funds future miner emissions.
- **Corporate structure (vertically split)** — KubeTEE AI LTD (subnet owner, mechanism + IP, 18% stream) and 1-HORIZON LTD (miner operator, competes for the 41% miner share under identical rules as every external miner). The target state is a declining related-party share — the on-chain evidence the network is real.
- **Cross-subnet consumption loop** — external customers → consuming subnet swaps TAO for SN90 Alpha on the open pool (no discounts) → spends Alpha on SN90 confidential compute → spent Alpha recycled → re-emitted via 41/41/18. TAO can now be acquired on **Base** (CCIP-bridged ERC-20, Aerodrome USDC/TAO) as well as on Finney. A consumer-aligned validator on SN90 scores miner output as the protocol-native SLA. External demand one hop removed, not circular emissions-farming.
- **DePIN subsidy trajectory** — the emission subsidy line decays as consumption revenue rises; they cross at the **crossover** (net Alpha issuance ≈ 0, consumers fund the miner budget). The subsidy ratio (emission value ÷ total miner compensation) is the single on-chain KPI, monotonically declining. Defenses: published glide path, stack-efficiency moat (bin-packing, TEE premium, utilization), and self-consumption made economically neutral to defeat wash consumption.

Full analysis (securities posture, recycle mechanics, flywheel, trajectory charts): [Tokenomics — Utility Token & DePIN Model](./docs/TOKENOMICS.md).


---

## Validator Scoring & Attestation

The validator is the subnet's referee. In Early Access it scores each miner (one hotkey per cluster) on a single Infrastructure mechanism and sets Bittensor weights each epoch.

> **Status:** validator v1 is **built, tested (35 tests), and live on Finney** —
> it scores the subnet-owner staging miner on a single Infrastructure mechanism and sets Bittensor
> weights once per epoch (boundary-aligned, with `weights_rate_limit` cooldown).
> The KubeTEE Validator/Miners Dashboard is published to Hippius S3 every cycle at
> [https://s3.hippius.com/kubetee-validator/index.html](https://s3.hippius.com/kubetee-validator/index.html).
> The sections below
> describe both the running v1 and the future-scoring dimensions on top of it.
> The build-level details are in the `validator/` directory; the pricing design
> is in [Competitive Pricing & Miner Scoring](./docs/COMPETITIVE-PRICING.md).
> See [What Ships Today](#what-ships-today).

The validator shape: on each epoch the validator reads the metagraph,
enumerates clusters/nodes via a GET-only Rancher v3 client, reconciles
(guarded deregistration on sustained absence), recomputes a **binary
infrastructure-readiness verdict** per miner (hotkey binding, Rancher
readiness, HA topology, capacity, GPU passthrough, runtime handler), converts
a USD compensation target into a weight per miner, and sets weights on-chain
via Bittensor `set_weights`. Attestation, Armada, and serving gates are future
scoring dimensions on top of that base.

### Validator Runtime (TEE)

The referee itself must be trustworthy, so the validator process runs **inside a confidential TEE pod** on the subnet-owner control plane, with CoCo remote attestation proving the validator code and configuration are unmodified. Scoring, weight-setting, and credentials (Rancher token, Bittensor wallet) stay confidential and tamper-resistant — the validator cannot be silently altered by the host or hypervisor.

**KubeTEE-hosted validator**: KubeTEE offers to run the validator code in KubeTEE clusters, so a validator operator does not need to provision and operate their own TEE infrastructure. KubeTEE schedules the validator as a confidential workload in a KubeTEE confidential cluster, with attestation evidence available to the subnet. This lowers the barrier to running a validator and ensures every validator runs in a genuine, attested TEE.

### Evidence Feeds

Scoring today reads one feed: Rancher-reported readiness, topology, capacity, GPU passthrough, and runtime-handler inventory. Three more are designed and **not yet in the weight path**:

- **TEE attestation** — an attestation verifier checking each miner cluster's TEE (Intel TDX/SGX, NVIDIA CC), with CoCo remote attestation proving the confidential image and runtime are unmodified.
- **Armada job metrics** — job success, throughput, latency, fairness, and gang-scheduling evidence from the scheduler and executors.
- **Infrastructure health** — uptime history, QoS, latency, and FIPS validation.

Until they land, the weights make no claim about attested TEE health or job quality.

### Competitive Pricing

SN90 sells compute, so its miners are scored against the **other Bittensor compute subnets** — **Targon (SN4)**, **Lium (SN51)**, and **Chutes (SN64)** — each of which exposes a **verifiable** feed (public API + on-chain metagraph). The validator discovers a **target price** per SN90 job class (GPU-hour by GPU type, CPU-hour, per-token) from competitor signals and SN90 demand, then scores miners on whether their delivered compute is priced at or below that target. A miner with perfect attestation but a price 2× the competitor average scores low — "competitive with the other subnets" means the weight vector rewards miners that keep SN90 in the competitive band.

**Two price feeds — only one is in the weight path (both are implemented and live in v1):**

- **Compensation pricing (weight-bearing, live).** Each cycle a Taostats feed fetches TAO/USD (the chain doesn't know USD) and the on-chain metagraph supplies alpha→TAO (zero delay, `mg.price`); the miner share of emissions is USD-denominated: an `EARNING` miner's score is `usd_target_per_hour × tenure × window_hours ÷ usd_per_alpha`, where `usd_target_per_hour` applies the GPU $/GPU/hour card to that miner's capacity. Whatever miners do not earn recycles to the owner UID. The feed is a **hard dependency**: if it fails, the cycle is skipped, the previous on-chain weights persist, and reliability counters freeze — the validator never guesses a price.
- **Competitive pricing (Targon supply-side clamp, live).** Reads what SN4 actually pays per card for each GPU class from `https://stats.targon.com/api/miners` and clamps the GPU card **downward only** (floored at 75% of the card). One publisher (subnet-owner validator) writes a snapshot to [Hippius (SN75)](https://docs.hippius.com/storage/s3/integration) S3; many readers. Fails **soft**: live → last-known → card, never skips a cycle.

The **Lium/Chutes demand-side scrape**, per-job-class target price, and price-competitiveness weighting remain **design-only**. Full design (formula, feeds, failure contracts, verifiability): [Competitive Pricing & Miner Scoring](./docs/COMPETITIVE-PRICING.md).

### Weight Setting

These are the validator behaviors:
- Scores are normalized per miner hotkey and set on-chain via Bittensor `set_weights` (single mechanism)
- The miner/owner split is **dynamic, not a fixed share**: each cycle the validator converts a USD compensation target into Alpha at the live token price, and everything miners do not earn recycles to the owner UID
- A cycle that cannot get a trustworthy price, Rancher inventory, or metagraph read is **skipped** rather than guessed — the previous on-chain weights persist and the reliability counters freeze, so an outage never blames miners

---

## Submitting a Confidential Job

The primary door is the **[LiteLLM gateway](#litellm-gateway--the-multi-service-front-door)** at `llm.kubetee.ai` (ships today) — SOTA inference, tools, and agents. **Batch jobs** are a secondary service: **[Airflow and Metaflow connectors](#workflow-orchestration-airflow--metaflow)** for multi-step pipelines (designed, not built) and the **[Jobs MCP server](#jobs-mcp-server)** for conversational submit (not developed yet). Those land on Armada queues (Armada is in development) with a confidential `runtimeClassName`. In Early Access, direct Armada submission will be open to the subnet owner and authorized integrators.

(Miners join the other side of this: they register one cluster per hotkey with the subnet owner for Rancher Fleet and Armada enrollment — see [For Miners (Infrastructure)](#for-miners-infrastructure).)

### LiteLLM Gateway — the multi-service front door

[LiteLLM](https://github.com/BerriAI/litellm) is an open-source **LLM gateway**, and calling it an "inference proxy" undersells it: a single deployment terminates **three protocol surfaces** — `/v1/chat/completions` for models, `/mcp` for tool servers, and `/a2a` for agent-to-agent invocation — behind one auth, budget, and audit layer ([deployment architecture](https://docs.litellm.ai/docs/mcp_deployment)). KubeTEE runs it at **`llm.kubetee.ai`** as the gateway for the Factory — the surfaces map onto confidential services as follows:

| LiteLLM surface | What it does | KubeTEE mapping |
|-----------------|--------------|-----------------|
| `/chat/completions`, `/completions`, [`/responses`](https://docs.litellm.ai/docs/proxy/user_keys) | OpenAI-compatible inference | Confidential SGLang / NIM model services in TEE pods, in all three [serving configurations](#serving-configurations--every-job-requires-fast-inference) |
| `/embeddings`, `/rerank` | Vectorization and reranking | Confidential retrieval services (the NeMo Retriever layer, or a [subnet substitute](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#5-bittensor-subnet-integrations-sota-confidential-ready)) |
| `/images`, `/images/edits`, `/audio/speech`, `/audio/transcriptions` | Multimodal generation and ASR | Multimodal job types on the same attested runtime |
| [`/fine_tuning/jobs`](https://docs.litellm.ai/docs/fine_tuning), `/batches`, `/files` | Long-running asynchronous work | **The OpenAI-shaped door onto Armada confidential jobs** — the same batch path the MCP server deploys to, reachable by anything that already speaks the OpenAI fine-tuning API |
| [`/mcp`](https://docs.litellm.ai/docs/mcp_deployment) | MCP gateway — publishes tool servers to any MCP client, with per-user credential passthrough (`x-mcp-{server}-authorization`) | Where the [Jobs MCP server](#jobs-mcp-server) is published, so job deployment inherits the gateway's auth and budgets rather than reinventing them |
| [`/a2a`](https://docs.litellm.ai/docs/a2a) | Agent-to-agent — routes JSON-RPC `message/send` to registered downstream agents | Agents executing **inside** TEE pods, callable without exposing the cluster |
| [Guardrails](https://docs.litellm.ai/docs/adding_provider/generic_guardrail_api) | Policy enforcement across every endpoint above | Pre- and post-call policy on confidential traffic |
| [Virtual keys, teams, orgs](https://docs.litellm.ai/docs/proxy/virtual_keys), hierarchical budgets, RPM limits, spend tracking | Multi-tenant governance — budgets inherit down the hierarchy and requests are blocked in real time when any level is exhausted | **The metering surface for Alpha/TAO billing** at the published resources price per hour (see [Subnet Economics](#subnet-economics)) |

**The gateway itself runs inside a TEE.** LiteLLM runs under `kata-qemu-tdx-runtime-rs` with guest debug off. Cloudflare hosts DNS for `llm.kubetee.ai` as **grey cloud** (DNS-only) to the oakland node ExternalIPs. Cluster ingress is **TLS passthrough**: Traefik holds no private key and forwards TLS records into the guest, where an in-sandbox terminator decrypts onto LiteLLM loopback. From there the gateway speaks [attestation-gated TLS](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#2-attestation-gated-tls-between-services) to model services. CoCo Trustee attests the guest. A caller who verifies the gateway certificate against its TDX quote (RA-TLS: TLS public key in `report_data`) covers the terminator.

When a miner cluster has a model, LiteLLM gets another row with the same `model_name` and that cluster's private `api_base`. `simple-shuffle` / `least-busy` uses capacity on every healthy backend.

Two things follow. First, an internal AI service or pipeline deployed in the KubeTEE multi-cluster adopts KubeTEE by changing a base URL — no KubeTEE-specific SDK, and the tools, agents, and fine-tuning jobs they already run keep working, only now inside a TEE. Second, KubeTEE contributes to LiteLLM upstream and is integrating as a **provider inside the open-source project**, so a LiteLLM deployment *someone else* operates (including SN28/SayGM) can route to KubeTEE confidential compute as a first-class backend rather than a hand-configured custom endpoint. Meeting consumers in the open-source platforms they already run is the distribution strategy; the gateway is not a KubeTEE-only walled garden.

> **Status:** `llm.kubetee.ai` serves inference and multi-tenant governance (virtual keys, budgets, rate limits, spend tracking). Cloudflare is DNS-only (grey cloud). LiteLLM runs in `kata-qemu-tdx-runtime-rs` with guest debug off, Traefik TLS passthrough, and in-guest termination. CoCo Trustee attests the guest. Remaining: RA-TLS so clients attest the terminator; native TLS from the LiteLLM guest to NIM guests; wiring `/mcp`, `/a2a`, and the fine-tuning and batch endpoints through to Armada; upstream provider integration. See [What Ships Today](#what-ships-today).

### SN28 sayGM — idle capacity, not the product

**SN90 is not an inference subnet.** It hosts **SOTA AI services** for enterprises. Serving models to the general public is not the product. Factory services on the clusters always get priority. What goes to [sayGM (SN28)](https://saygm.com/) is **idle GPU headroom** — capacity that would otherwise sit warm and unused.

That channel is **live** (2026-08-19). Buyers use the OpenAI-compatible sayGM API; the KubeTEE miner forwards to `llm.kubetee.ai` inside Intel TDX + NVIDIA CC. Same stack as the Factory gateway. Details: [SN28-SAYGM.md](./docs/SN28-SAYGM.md).

**First worldwide — Ornith-1.5-397B.** In collaboration with [sayGM (SN28)](https://saygm.com/), KubeTEE was the first to serve [Ornith-1.5-397B](https://huggingface.co/ornith-ai/Ornith-1.5-397B-NVFP4) anywhere in the world (2026-08-20), as idle-capacity on the same SN28 channel.

| Buyer model | Discount vs sayGM retail |
|---|---|
| `z-ai/glm-5.2` (`glm-5.2`) | **48.25%** |
| `deepseek/deepseek-v4-flash-0731` | **50%** |
| `ornith/ornith-1.5-397b` | first worldwide availability (2026-08-20) |

The free window that preceded this used **14,812,329,857** tokens.

### Workflow Orchestration (Airflow & Metaflow)

For **multi-step AI pipelines** — ETL → fine-tune → evaluate → register → deploy — KubeTEE integrates with [Apache Airflow](https://airflow.apache.org/) (DAG-based) and [Metaflow](https://metaflow.org/) (Python `@step` flows) so each pipeline step runs as a confidential Armada batch job inside Kata + CoCo TEE pods. Airflow schedules the *pipeline*; Armada schedules the *task pods* across miner clusters. Every task pod runs under a TEE runtime class with CoCo remote attestation, and a pipeline can verify a step's attestation evidence before passing artifacts downstream.

See [Workflow Orchestration — Airflow & Metaflow](./docs/WORKFLOW-ORCHESTRATION.md) for architecture, connector design, and example DAG / Metaflow flow snippets.

> **Status:** designed, not built — the Armada connectors are a [Phase 1](#phase-1--expansion) item ([What Ships Today](#what-ships-today)). Armada itself is in development.

### Jobs MCP Server

The **Jobs MCP server** is the [Model Context Protocol](https://modelcontextprotocol.io/) front door to the Factory: it is how a job gets **deployed**, and pricing is one step in that path rather than the point of it. Three kinds of caller use the same interface — an **autonomous AI agent** deciding it needs compute, a **human in a chat client** (Claude, Cursor, or any MCP-capable assistant) asking for a job in natural language, and a **pipeline orchestrator** such as Airflow or Metaflow submitting a step. Whoever is calling, the server is the single validator-aligned interface between "I want to run this" and "the job is queued on a miner cluster."

**This complements the REST surface — it does not replace it, and it is not a separate deployment.** The [LiteLLM gateway](#litellm-gateway--the-multi-service-front-door) is itself an [MCP gateway](https://docs.litellm.ai/docs/mcp_deployment): the Jobs MCP server is published *through* `/mcp`, so it inherits the gateway's virtual keys, budgets, rate limits, and spend tracking instead of reinventing them, and a client that already points at `llm.kubetee.ai` for inference discovers job deployment at the same endpoint with the same credential.

**What it adds** is intent-level submission. REST is the right shape when the caller already knows what it wants — a fine-tuning job with a file id and a model name. It is the wrong shape for *"fine-tune this model on eight H200s overnight, high-throughput config"*, where the caller needs the catalogue browsed, the cost quoted, the trade-off explained, and the job tracked to completion in one conversation. That is what MCP is for, and why the same capability is exposed twice: **the OpenAI fine-tuning and batch APIs for programmatic callers, MCP for agents and humans reasoning about the job before committing to it.**

**Pricing is a step, not the product.** Quoting exists so a caller knows the cost before committing, and so every consumer is quoted against the same numbers the validator enforces on miners. The validator discovers a per-job-class **target price** each epoch from Targon / Lium / Chutes signals and SN90 demand (see [Competitive Pricing](#competitive-pricing) — the Taostats compensation feed and the Targon supply-side clamp are implemented and live in v1; the Lium/Chutes demand-side scrape is design-only). The server is a **read client** of that published price, never a price-setter, which is why the deployment path depends on the competitive-pricing work landing first.

**Tools (design concept):**
- `list_job_templates()` — the catalogue a caller can deploy: NeMo / NIM / Blueprint templates, the [serving configurations](#serving-configurations--every-job-requires-fast-inference), and the GPU classes each is available on.
- `get_target_price(job_class, gpu_type)` — the current validator-established target resources price per hour for a job class.
- `quote_job(resources, duration, job_class)` — resource-hours (GPU type × count × hours, CPU-hours, or per-token) × target price per hour → the Alpha/TAO cost the caller pays.
- `submit_job(job_spec, priced)` — deploys the priced job to the Armada queue with a confidential `runtimeClassName`; returns the Armada job id.
- `get_job_status(job_id)` — queue position, execution state, and the attestation evidence for the pod that ran it, so a chat client or agent can follow a job to completion.

**Flow:**

```mermaid
flowchart LR
    App["OpenAI-API client<br/>(SDK, app, other LiteLLM deploys)"]
    Human["Human in chat<br/>(Claude, Cursor, any MCP client)"]
    Agent["AI Agent / Orchestrator<br/>(Airflow, Metaflow, autonomous)"]
    Lite["LiteLLM gateway — llm.kubetee.ai<br/>/chat/completions · /mcp · /a2a<br/>keys · budgets · spend"]
    MCP["Jobs MCP Server<br/>(published via /mcp)"]
    Val["Validator<br/>(publishes target price)"]
    Arm["Armada Queue"]
    TEE["Miner Cluster<br/>(Kata + CoCo TEE)"]

    App -->|"inference / fine-tuning / batches"| Lite
    Human -->|"natural language request"| Lite
    Agent -->|"quote_job / submit_job"| Lite
    Lite -->|"inference"| TEE
    Lite <-->|"tool calls"| MCP
    Val -->|"target price / epoch<br/>(Prometheus + on-chain)"| MCP
    MCP -->|"priced job spec"| Arm
    Arm -->|"schedule pod"| TEE
    TEE -.->|"attestation evidence"| MCP
```

**Confidentiality:** the server is control-plane only — it quotes, queues, and reports status; it never sees job data. The pods it deploys run inside TEEs with CoCo remote attestation and KBS-injected secrets, so even the operator of the MCP server cannot read what the job processes. Payment for the quoted resource-hour cost is settled on-chain or via the Phase 2 escrow — the server records the quote, it does not custody funds.

> **Status:** not developed yet — a [Phase 1](#phase-1--expansion) item that depends on the competitive-pricing work being implemented first ([What Ships Today](#what-ships-today)).

---

## For Miners (Infrastructure)

### Miner onboarding

**KubeTEE onboards each miner today.** The miner supplies the cluster and the
hardware it runs on (requirements below); KubeTEE binds it by applying the
`kubetee.ai/hotkey` label that links the cluster to the miner's registered
hotkey. Rancher Fleet GitOps then deploys the infrastructure onto RKE2 and
verifies attestations and metrics.

**Self-service permissionless onboarding ships in Phase 1** — see
[Roadmap](#phase-1--expansion). Until then the platform endpoints, credentials,
and binding procedures behind onboarding are intentionally not published in this
public repository.

> **Onboarding rate is demand-driven.** The rate at which KubeTEE onboards new miners is governed by demand-side consumption — production deployments that have been staged, measured, and incentivized. New miner capacity is added to match proven demand, not ahead of it, so emissions are not diluted by unused clusters. Spare GPUs on **already-live** clusters can go to the [SN28 sayGM idle-capacity channel](#sn28-saygm--idle-capacity-not-the-product); that is utilisation, not a reason to onboard more miners.

> **The staging cluster is not a template for miners.** KubeTEE operates one staging cluster where every node is TEE CC capable. It is a **debug target** if a workload fails — not a required promotion step. CC can be turned off on a staging node for debug; guest debug can be enabled per pod. Kata guest debug is **off** by default; CoCo Trustee attests those guests. Miners keep CC on: capacity with CC off is not confidential capacity and is not what the subnet scores. Miners provide attested confidential capacity (debug off) and execute jobs.

**Minimum For Staging Participation** — what the **miner** provides:

> KubeTEE is a decentralized multi-cluster architecture. Miners must provide the minimum requirements below to allow high availability, deploy the full tech stack, and have enough nodes to run SOTA AI services and enhanced services for enterprises. These minimum requirements are written and enforced in Phase 0.

- **8 nodes minimum per cluster** (5 control-plane + etcd + worker combined, 3+ dedicated 8-GPU workers **per GPU type**) — all co-located in a single data center. The 5 combined nodes run the tech stack (GPU Operator, Kata/CoCo, Longhorn, NeMo, Armada Executor, monitoring) and serve inference; **3 dedicated GPU workers per GPU type** ensure HA for each GPU type (a mixed-GPU cluster needs 3 per type, e.g. 3 H200 + 3 B200). Fewer nodes cannot simultaneously host the tech stack and serve inference with HA. Full topology + scaling table: [GPU Node Requirements — Cluster Architecture & HA](./docs/GPU-NODE-REQUIREMENTS.md#cluster-architecture--high-availability)
- Intel TDX (AMD SEV-SNP, Phase 1) compatible nodes with NVIDIA H100/H200/B200/B300; BIOS + kernel TDX/SGX enabled; one cluster per miner; cluster registered with Rancher for Fleet management
- Production Rancher inventory passes the infrastructure-readiness policy (readiness, HA topology, CPU/memory, eight-GPU workers, passthrough wiring, confidential runtime handler)
- A **100 TAO deposit** held as on-chain registration collateral on the mining hotkey — see [Miner deposit (registration collateral)](#miner-deposit-registration-collateral)

What **KubeTEE** applies (platform enrollment — not a miner task): the `kubetee.ai/hotkey` binding label (one cluster per hotkey) and any further `kubetee.ai/*` platform labels; the validator reads only the hotkey label and the `kubetee.ai/ban` safety switch.

**For Production Participation**: must pass minimum requirements (hardware, HA topology, 8-GPU workers, passthrough wiring), TEE attestation, and infrastructure-readiness validation.

Full hardware/firmware requirements, the registration command, and the label contract: [Node Registration](./docs/NODE-REGISTRATION.md), [GPU Node Requirements](./docs/GPU-NODE-REQUIREMENTS.md), [Cluster Naming Convention](./docs/CLUSTER_NAMING_CONVENTION.md).

### Miner deposit (registration collateral)

Every miner posts a **100 TAO deposit** as on-chain **registration collateral** on its own mining hotkey — the same amount for every miner. It is **not a fee, not custodial, and not slashable**: it stays on the miner's hotkey (KubeTEE never holds it), and a miner that breaches its SLA stops being scored → emission stops → deposit draining stops → the capital **freezes on the miner's own hotkey** rather than being taken. That freeze reverses as soon as the miner is back in compliance.

> **Status:** the gate **measures but does not enforce**, so every miner's coverage is visible before anyone's score depends on it ([What Ships Today](#what-ships-today)). Bonding a share of the registration price on chain is a separate [Phase 1](#phase-1--expansion) change this deposit does not depend on.

Full detail — the chain primitive, Alpha conversion, grace/recovery, `btcli` commands, owner/miner/validator runbooks: [Miner Deposit (Registration Collateral)](./docs/MINER-DEPOSIT.md). Hardware and label requirements: [GPU Node Requirements](./docs/GPU-NODE-REQUIREMENTS.md), [Node Registration](./docs/NODE-REGISTRATION.md), [Cluster Naming Convention](./docs/CLUSTER_NAMING_CONVENTION.md).

---

## Roadmap

### Phase 0 — Early Access (Current)

- [x] Kata + CoCo TEE runtime classes (`kata-qemu-nvidia-gpu-tdx`, `kata-qemu-tdx`)
- [x] Staging cluster — every node is TEE CC capable (H200/B200). Debug target if a workload fails; CC can be turned off on a node for debug (see [Debugging on the staging cluster](#debugging-on-the-staging-cluster))
- [x] Kata guest debug **off** on the staging cluster — CoCo Trustee attests those guests. Debug can be enabled per pod for diagnostics.
- [ ] Validator runs in a TEE (Kata + CoCo) on the control plane; CoCo attestation proves the validator code is unmodified
- [x] [Attestation-gated TLS](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#2-attestation-gated-tls-between-services) on the served backend (Kata runtime deployed) — in-guest keypairs, certificates issued only against a valid TDX quote verified through Intel Trust Authority, ingress on TLS passthrough, termination inside the guest
- [x] **SN28 (sayGM) idle-capacity channel** — live 2026-08-19 ([SN28-SAYGM.md](./docs/SN28-SAYGM.md)). SN90 is **not** an inference subnet; Factory AI services keep priority; SN28 gets spare headroom. Buyer offers: `z-ai/glm-5.2` **48.25%** below retail, `deepseek/deepseek-v4-flash-0731` **50%** below retail. **Ornith-1.5-397B** — first worldwide availability, in collaboration with SN28 sayGM (2026-08-20). Free window closed at 14,812,329,857 tokens. Do not declare Kimi / Qwen / MiMo on SN28.
- [ ] **Confidential model catalogue** — more TEE-served models on `llm.kubetee.ai` (and optionally extra SN28 SKUs). SN28 is a demand channel, **not** the exclusive path to public inference. Every model published in all three [serving configurations](#serving-configurations--every-job-requires-fast-inference) and billed at below-OpenRouter prices per token on the gateway (a demand channel, **not** an SN90 discounted reseller tier — see [Payment methods](#payment-methods)):
  - [ ] **Kimi-K3** — B300 nodes (`llm.kubetee.ai`)
  - [x] **GLM-5.2** — B200 nodes (`llm.kubetee.ai` + SN28)
  - [x] **DeepSeek-V4-Flash-0731** — B200/H200 nodes (`llm.kubetee.ai` + SN28)
  - [x] **Ornith-1.5-397B** — B200 NVFP4 (`llm.kubetee.ai` + SN28). First worldwide, in collaboration with SN28 sayGM (2026-08-20).
  - [ ] **SOTA embedding model**
  - [ ] **Specialised models for vectorization, LLM-as-judge, and document retrieval** — served through [NeMo Microservices](#nvidia-nemo-microservices--bittensor-subnet-integrations) (NeMo Retriever + Evaluator)
- [ ] Deploy 2 US clusters (one hotkey each, each cluster's nodes co-located in a single DC — one West Coast, one East Coast)
- [ ] Armada Server Multi-cluster Scheduler on the subnet-owner control plane; Armada Executor on each miner cluster
- [ ] Automate supply-chain CI (SAST, Trustee secrets, image CVE, IaC) and publish results (see [Debugging on the staging cluster](#debugging-on-the-staging-cluster))
- [ ] Binary Infrastructure validator gate (hotkey binding identity, Rancher readiness, HA, capacity, GPU/runtime wiring)
- [ ] Extend scoring with fresh TEE attestation, Armada job metrics, serving probes, workload identity, and KeyLease freshness
- [ ] KubeTEE-hosted validator offering: KubeTEE runs the validator code in a KubeTEE confidential cluster for operators without their own TEE infrastructure
- [ ] Validator Rancher v3 API access: a validator authenticates by **signing a challenge with its Bittensor hotkey**; an auth mechanism connected to Rancher verifies the signature and issues the narrow cluster/node-read plus guarded-cluster-delete role. Split reconciliation behind an operator-owned mutation credential/controller before describing validator scoring tokens as read-only
- [ ] Miner Rancher access on cluster creation: the miner authenticates with the same **hotkey-signed** flow, scoped **read-only** to their own cluster (the one carrying their `kubetee.ai/hotkey` label, bound to `cluster-readonly`) so the miner can observe their cluster (subnet owner manages via Fleet)
- [ ] Emissions rewards for miners providing confidential compute capacity (supply-side)
- [ ] Alpha / TAO paid jobs (demand-side) — compute priced at a resources price per hour, dynamic with Armada queue depth and wait time per job class
- [ ] Competitive pricing, supply side: implement the live Targon (SN4) payout feed to clamp the GPU price card (one publisher, all validators read), and the per-GPU price paid to miners
- [ ] Competitive pricing, demand side: scrape Lium (SN51) / Chutes (SN64) price feeds, compute per-class target price, score miners on price competitiveness
- [ ] Confidential job templates — NeMo / NIM / Blueprint, for subnet owners and approved integrators
- [x] **[Albedo SN97 competitive-distillation eval PoC](./docs/SN97-ALBEDO-POC.md)** (KubeTEE SN90 hosting SN97 king-of-the-hill duels — not coding agents) — **parked 2026-08-13**. First successful 100-sample duel 2026-08-09 ([artifacts](./docs/SN97-ALBEDO-POC.md#latest-successful-run-2026-08-09), [upstream PR](https://github.com/unarbos/albedo/pull/4)). Do not extend the KubeTEE-specific split topology.
  - [ ] **Revisit when Armada + CoCo Trustee are complete** — deploy upstream Albedo / Denrite **without modifications or architecture changes** (Armada `JobSubmitRequest` + attested `kata-qemu-nvidia-gpu-tdx-runtime-rs` / `kata-direct` + Trustee secrets). The parked fork’s LiteLLM king-register / split-gen-score / custom judge-api items are **not** the revisit path.

### Phase 1 — Expansion

- [ ] **Permissionless miner onboarding** — a self-service flow where a registered miner proves control of its own cluster and the `kubetee.ai/hotkey` binding is applied without operator involvement (today KubeTEE performs onboarding — see [Miner onboarding](#miner-onboarding)). Onboarding rate is **demand-driven**: new miner capacity is added to match proven Factory demand, not ahead of it. Spare GPUs on live clusters may go to [SN28](#sn28-saygm--idle-capacity-not-the-product); that does not justify onboarding extra miners.
- [ ] **Bond the registration price on chain** — set the subnet's `collateral_lock_share` and `collateral_drain_ratio` so a share of each registration is locked as collateral rather than burned. The drain ratio governs how long a miner stays accountable and can only be sized against observed per-miner emission, so both values are set in Phase 1 once that data exists; Phase 0 runs the [100 TAO deposit](#miner-deposit-registration-collateral) through the validator gate alone (see [Miner Deposit](./docs/MINER-DEPOSIT.md))
- [ ] More US + international clusters
- [ ] **Armada in TEE** — move the Phase 0 Server and Executors onto Kata + CoCo TEE pods, with [attestation-gated TLS](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#2-attestation-gated-tls-between-services) on the Server-to-Executor control channel (see [Armada Multi-Cluster Batch Scheduling](#armada-multi-cluster-batch-scheduling))
- [ ] Armada fair-use + gang scheduling hardening
- [ ] Automated TEE attestation cronjobs
- [ ] Validator scoring expansion: TEE attestation + Armada job metrics + infrastructure health (replacing the Early Access liveness stand-in)
- [ ] Apache Airflow + Metaflow Armada connectors — multi-step confidential pipelines (see [Workflow Orchestration](./docs/WORKFLOW-ORCHESTRATION.md))
- [ ] Jobs MCP server — deploy confidential jobs from an autonomous agent, a human chat client, or a pipeline orchestrator: browse templates, quote, submit to Armada, and track status and attestation; quoting grounded in the Phase 0 [Competitive Pricing](./docs/COMPETITIVE-PRICING.md) target price (see [Jobs MCP Server](#jobs-mcp-server))
- [ ] Optional [BitSec SN60](https://bitsec.ai/) one-time audit of SN90 validator/incentive code — a partnership, **not** the supply-chain CI gate (see [why SN60 is not the gate](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#why-bitsec-sn60-is-not-the-gate))
- [ ] Build documentation website

### Phase 2 — Paid Jobs

- [ ] USDC-on-BASE and **TAO-on-BASE** job billing (pull-based, per-epoch metering) — fiat and EVM-TAO billing layered on top of the Early Access Alpha / TAO resources-per-hour pricing. TAO itself is live on Base as of 2026-08-21 (Chainlink CCIP; [ForeverMoney SN98](https://x.com/forevermoney_ai/status/2090469070248235027))
- [ ] Automated USDC→TAO-on-BASE→Finney TAO→Alpha recycling (unused emissions recycled)

### Phase 3 — Job-Type Growth

- [ ] More job templates
- [ ] Multi-arch TEE expansion (additional confidential compute runtimes beyond Intel TDX)
- [ ] Additional confidential compute runtimes
- [ ] FIPS-140-3 on the FIPS-140-2 validated RKE2 baseline
- [ ] NIM Operator Kata Sandbox + Dynamo production-readiness — graduate NVIDIA's [experimental Kata Sandbox](https://docs.nvidia.com/nim-operator/latest/kata-sandbox.html) and [experimental Dynamo](https://docs.nvidia.com/nim-operator/latest/dynamo.html) support to production confidential deployments (KubeTEE working with the NVIDIA NIM Operator and Kata Containers teams)

---

## Research & Documentation

### Documentation
- [Miner Deposit — registration collateral](./docs/MINER-DEPOSIT.md) — the 100 TAO on-chain registration deposit, chain primitive, and runbooks
- [Node Registration](./docs/NODE-REGISTRATION.md) — Miner RKE2 node registration and `kubetee.ai/*` labels
- [GPU Node Requirements](./docs/GPU-NODE-REQUIREMENTS.md) — GPU/TEE hardware requirements
- [Cluster Naming Convention](./docs/CLUSTER_NAMING_CONVENTION.md) — `kubetee.ai/*` labels and Fleet GitOps targeting
- [FIPS-140-3 Target](./docs/FIPS-140-3.md) — RKE2 + Kata + CoCo FIPS stack research
- [Confidential Containers Certification](./docs/certification-confidential-containers.md) — CC standards and Kata runtime mapping
- [Deploying in a TEE — Challenge & debugging](./docs/TEE-DEPLOYMENT-AND-CICD.md) — why TEE deployment is hard, staging as a debug target if a workload fails, Kata guest debug off, CoCo Trustee attestation
- [Workflow Orchestration — Airflow & Metaflow](./docs/WORKFLOW-ORCHESTRATION.md) — orchestrating multi-step confidential pipelines on Armada
- [Tokenomics — Utility Token & DePIN Model](./docs/TOKENOMICS.md) — recycle vs burn, securities posture, TAO-on-BASE (CCIP), cross-subnet consumption loop, DePIN subsidy trajectory
- [Competitive Pricing & Miner Scoring](./docs/COMPETITIVE-PRICING.md) — pricing SN90 against Targon/Lium/Chutes and how price becomes weights
- [NeMo Microservices & Bittensor Subnet Integrations](./docs/NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md) — attestation-gated TLS, NIM Operator Kata/CoCo limits, SOTA Bittensor subnet substitutes per NeMo layer, and the Stage 0 supply-chain security gate
- [SN28 sayGM — idle-capacity channel](./docs/SN28-SAYGM.md) — live 2026-08-19; SN90 is not an inference subnet; GLM-5.2 48.25% / Flash-0731 20% below retail; first worldwide Ornith-1.5-397B with SN28 (2026-08-20)
- [SN28→SN90 Alpha Recycler](./docs/SN28-SN90-ALPHA-RECYCLE.md) — swap SN28 stake to SN90 Alpha and recycle
- [Albedo SN97 Eval PoC (KubeTEE SN90)](./docs/SN97-ALBEDO-POC.md) — parked 2026-08-13; 100-sample proof + artifacts; revisit when Armada + CoCo Trustee can run unmodified SN97
- [Release & Versioning](./RELEASE-AND-VERSIONING.md) — semantic versioning scheme, image tag mapping, release procedure

### External Resources
- [Armada](https://armadaproject.io/) | [Armada GitHub](https://github.com/armadaproject/armada) — multi-cluster batch scheduler
- [Apache Airflow](https://airflow.apache.org/) | [Metaflow](https://metaflow.org/) — pipeline orchestration for confidential Armada jobs
- [LiteLLM](https://github.com/BerriAI/litellm) ([docs](https://docs.litellm.ai/)) — the gateway: models, [MCP tool servers](https://docs.litellm.ai/docs/mcp_deployment), [A2A agents](https://docs.litellm.ai/docs/a2a), [fine-tuning](https://docs.litellm.ai/docs/fine_tuning), and multi-tenant governance behind one endpoint
- [Model Context Protocol](https://modelcontextprotocol.io/) — the agent- and chat-facing job interface
- [Kata Containers](https://katacontainers.io/) | [Confidential Containers](https://github.com/confidential-containers/confidential-containers)
- [NVIDIA NIM Operator](https://docs.nvidia.com/nim-operator/latest/) — [Kata Sandbox (Experimental)](https://docs.nvidia.com/nim-operator/latest/kata-sandbox.html) | [Dynamo (Experimental)](https://docs.nvidia.com/nim-operator/latest/dynamo.html)
- [RKE2 FIPS Support](https://docs.rke2.io/security/fips_support)

### Community & Support

- **GitHub**: [KubeTEE-AI/kubetee-subnet](https://github.com/KubeTEE-AI/kubetee-subnet)
- **Documentation**: [docs/](./docs/)
- **sayGM (SN28)**: [saygm.com](https://saygm.com/) — idle-capacity inference channel ([SN28-SAYGM.md](./docs/SN28-SAYGM.md)). Together we were the first to provide Ornith-1.5-397B worldwide.
- **Discord**: questions in the public channel, not DMs. **We never DM first.** Anyone in DMs claiming to be KubeTEE support, or pointing at a ticket server, is a scammer. Team members are listed in the pinned post.
- **X (Twitter)**: [@KubeTEEAI](https://x.com/KubeTEEAI)

---

**Built by the KubeTEE Community**

*Confidential compute for SOTA AI services and enhanced services for enterprises — secured by TEE, incentivized by Bittensor.*
