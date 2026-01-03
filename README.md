# KubeTEE AI Bittensor Deep Research Agent Subnet

> Enterprise-Grade AI as a Service (AIaaS) with Trusted Execution Environment (TEE) on Decentralized Kubernetes Infrastructure

[![DeepResearch Leaderboard](https://img.shields.io/badge/DeepResearch-Ranked-blue)](https://huggingface.co/spaces/Ayanami0730/DeepResearch-Leaderboard)
[![FIPS-140-2](https://img.shields.io/badge/FIPS--140--2-Compliant-green)](https://docs.rke2.io/security/fips_support)
[![Confidential Computing](https://img.shields.io/badge/Confidential%20Computing-Enabled-brightgreen)](https://confidentialcomputing.io/)
[![Intel TDX](https://img.shields.io/badge/Intel%20TDX-Supported-lightgrey)](https://www.intel.com/content/www/us/en/developer/tools/tdx/overview.html)
[![Intel SGX](https://img.shields.io/badge/Intel%20SGX-Supported-blueviolet)](https://www.intel.com/content/www/us/en/architecture-and-technology/software-guard-extensions.html)
[![Trusted Execution Environment](https://img.shields.io/badge/Trusted%20Execution%20Environment-TEE-green)](https://en.wikipedia.org/wiki/Trusted_execution_environment)
[![NVIDIA](https://img.shields.io/badge/NVIDIA-GPU%20Optimized-green)](https://developer.nvidia.com/)
[![NVIDIA Incubated](https://img.shields.io/badge/NVIDIA-Incubated-76B900)](https://www.nvidia.com/)
[![CCC Member](https://img.shields.io/badge/Confidential%20Computing%20Consortium-Member-blue)](https://confidentialcomputing.io/)
[![OpenInfra](https://img.shields.io/badge/OpenInfra%20Foundation-Kata%20Containers-DA1A32)](https://openinfra.org/)

---

## About

**KubeTEE AI** is part of **NVIDIA Incubated Inception Program**, proud member of the [**Confidential Computing Consortium (CCC)**](https://confidentialcomputing.io/), and active participant in the **[OpenInfra Foundation](https://openinfra.org/)** ecosystem.

### Foundation & Community Partnerships

As part of NVIDIA's Inception Program, KubeTEE AI leverages cutting-edge NVIDIA technologies including NeMo Microservices, NIM models, and AI Blueprints to deliver enterprise-grade AI solutions. Our membership in the Confidential Computing Consortium reinforces our commitment to advancing hardware-based security technologies that protect data in use, including Intel TDX/SGX, and NVIDIA Hopper/Blackwell Confidential Computing capabilities.

**Direct Engineering Collaboration**: KubeTEE AI works directly with **INTEL** and **NVIDIA** engineers throughout the development and testing process of the NVIDIA technology stack. This close collaboration ensures optimal integration of confidential computing features, early access to emerging technologies, and validation of our implementation against the most stringent security and performance standards.

KubeTEE AI actively contributes to and builds upon the [OpenInfra Foundation's](https://openinfra.org/) open source infrastructure projects, particularly:
- **[Kata Containers](https://katacontainers.io/)**: Secure, lightweight CRI-compatible virtualized containers that provide the TEE foundation for our confidential computing infrastructure

We also leverage CNCF projects for cloud-native confidential computing:
- **[Confidential Containers (CoCo)](https://github.com/confidential-containers/confidential-containers)**: CNCF Sandbox project enabling transparent deployment of unmodified containers in Trusted Execution Environments (TEEs) with support for Intel TDX/SGX and other hardware platforms

**Mission**: To provide decentralized, enterprise-grade AI Deep Search Agent with privacy data and infrastructure of the highest standards of security, compliance, and performance—combining the power of NVIDIA's AI platform with the trust guarantees of Confidential Computing and the collaborative innovation 

**Key Differentiators**:
- 🔒 **Security-First**: TEE-enabled infrastructure with FIPS-140-2 certification and Kata Containers isolation
- 🚀 **NVIDIA-Powered**: Best-in-class AI models, microservices, and blueprints
- 🌐 **Decentralized**: Multi-cluster Kubernetes infrastructure across global regions
- 🏆 **Performance**: Ranked on DeepResearch Benchmark Leaderboard
- 🛡️ **Compliance**: CCC member driving confidential computing standards
- 🤝 **Open Source**: Built on OpenInfra Foundation projects with community-driven innovation

---

## Table of Contents

- [KubeTEE AI Bittensor Deep Research Agent Subnet](#kubetee-ai-bittensor-deep-research-agent-subnet)
  - [About](#about)
    - [Foundation \& Community Partnerships](#foundation--community-partnerships)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
    - [Performance \& Rankings](#performance--rankings)
    - [AI Deep Research Reports](#ai-deep-research-reports)
  - [Key Features](#key-features)
  - [The Enterprise AI Challenge: Problems We Solve](#the-enterprise-ai-challenge-problems-we-solve)
    - [The Current State of Enterprise AI](#the-current-state-of-enterprise-ai)
      - [1. **SMB Enterprises Locked Out of Advanced AI**](#1-smb-enterprises-locked-out-of-advanced-ai)
      - [2. **Regulated Enterprises Unable to Deploy AI Safely**](#2-regulated-enterprises-unable-to-deploy-ai-safely)
      - [3. **Private Data Processing Without Compromise**](#3-private-data-processing-without-compromise)
      - [4. **Data and Model Privacy Through Confidential Computing**](#4-data-and-model-privacy-through-confidential-computing)
      - [5. **Trust in Decentralized Infrastructure**](#5-trust-in-decentralized-infrastructure)
    - [The KubeTEE Value Proposition](#the-kubetee-value-proposition)
  - [KubeTEE AI vs Palantir: Enterprise AI Comparison](#kubetee-ai-vs-palantir-enterprise-ai-comparison)
    - [Key Differentiators](#key-differentiators)
    - [Complementary Use Cases](#complementary-use-cases)
    - [Target Market Positioning](#target-market-positioning)
    - [AI Agent Market: Big Tech Consolidation](#ai-agent-market-big-tech-consolidation)
  - [Architecture](#architecture)
    - [Infrastructure](#infrastructure)
      - [Kubernetes High Availability](#kubernetes-high-availability)
    - [Security \& Compliance](#security--compliance)
      - [Confidential Computing Features](#confidential-computing-features)
      - [Network Security](#network-security)
      - [Data Protection](#data-protection)
      - [Monitoring \& Audit](#monitoring--audit)
    - [Multi-Cluster Topology](#multi-cluster-topology)
      - [Subnet Owner Infrastructure](#subnet-owner-infrastructure)
      - [Miner Infrastructure](#miner-infrastructure)
  - [AI Technology Stack](#ai-technology-stack)
    - [Core Blueprints](#core-blueprints)
      - [1. NVIDIA AIQ Research Assistant](#1-nvidia-aiq-research-assistant)
      - [2. NVIDIA RAG Blueprint](#2-nvidia-rag-blueprint)
      - [3. NVIDIA Streaming Data to RAG](#3-nvidia-streaming-data-to-rag)
      - [4. NVIDIA NeMo Retriever Microservice](#4-nvidia-nemo-retriever-microservice)
      - [5. NVIDIA Data Flywheel](#5-nvidia-data-flywheel)
      - [6. NVIDIA Video Search and Summarization](#6-nvidia-video-search-and-summarization)
      - [Additional Services](#additional-services)
    - [NVIDIA NeMo Microservices](#nvidia-nemo-microservices)
    - [NVIDIA NIM Models](#nvidia-nim-models)
      - [Language Models](#language-models)
      - [Retrieval Models](#retrieval-models)
      - [Safety \& Vision Models](#safety--vision-models)
      - [Speech Recognition](#speech-recognition)
  - [Subnet Economics](#subnet-economics)
    - [Native Bittensor Multiple Incentive Mechanisms](#native-bittensor-multiple-incentive-mechanisms)
    - [Mechanism 0: Infrastructure (60% Emissions)](#mechanism-0-infrastructure-60-emissions)
    - [Mechanism 1: Open Source Competition (40% Emissions)](#mechanism-1-open-source-competition-40-emissions)
      - [GitHub Issues = Bounties](#github-issues--bounties)
      - [Emission Distribution](#emission-distribution)
      - [Bounty Lifecycle (Fully Automated)](#bounty-lifecycle-fully-automated)
      - [Security Scanning via Bitsec (Subnet 60)](#security-scanning-via-bitsec-subnet-60)
    - [Referrers / Integrators / Resellers: 50% Revenue Share (NO Emissions!)](#referrers--integrators--resellers-50-revenue-share-no-emissions)
    - [On-Chain Emission Configuration](#on-chain-emission-configuration)
    - [Staging vs Production](#staging-vs-production)
    - [Revenue Model](#revenue-model)
    - [Multi-Chain Payment Strategy: BASE + Bittensor EVM](#multi-chain-payment-strategy-base--bittensor-evm)
    - [Automated Buyback \& Burn (Deflationary Mechanism)](#automated-buyback--burn-deflationary-mechanism)
    - [Validation \& Scoring](#validation--scoring)
  - [Client Getting Started](#client-getting-started)
    - [Prerequisites](#prerequisites)
    - [Deployment Steps](#deployment-steps)
  - [For Miners (Open Source Competition)](#for-miners-open-source-competition)
    - [Development Process](#development-process)
  - [For Miners (Infrastructure)](#for-miners-infrastructure)
  - [Evaluation \& Benchmarks](#evaluation--benchmarks)
    - [Primary Benchmark](#primary-benchmark)
    - [Evaluation Criteria](#evaluation-criteria)
    - [Additional Planned Benchmarks](#additional-planned-benchmarks)
  - [Roadmap](#roadmap)
    - [Phase 1: Foundation (Current)](#phase-1-foundation-current)
    - [Phase 2: Launch](#phase-2-launch)
      - [Subnet 93 — Bitcast (Marketing \& Awareness)](#subnet-93--bitcast-marketing--awareness)
      - [Subnet 16 — BitAds (Affiliate \& Performance Marketing)](#subnet-16--bitads-affiliate--performance-marketing)
      - [Subnet 71 — LeadPoet (B2B Lead Intelligence)](#subnet-71--leadpoet-b2b-lead-intelligence)
    - [Phase 3: Enhancements](#phase-3-enhancements)
    - [Phase 4: Expansion](#phase-4-expansion)
      - [Subnet 22 — Desearch (Decentralized Web Search)](#subnet-22--desearch-decentralized-web-search)
      - [Subnet 60 — Bitsec (Security Scanning)](#subnet-60--bitsec-security-scanning)
    - [Phase 5: Subnet Integrations](#phase-5-subnet-integrations)
      - [Subnet 20 — Bounty Hunter (Decentralized Bounty Infrastructure)](#subnet-20--bounty-hunter-decentralized-bounty-infrastructure)
      - [Subnet 3 — Templar (Model Pre-Training)](#subnet-3--templar-model-pre-training)
      - [Subnet 37 — Aurelius (AI Alignment \& Safety)](#subnet-37--aurelius-ai-alignment--safety)
      - [Subnet 56 — Gradients (Decentralized Fine-Tuning)](#subnet-56--gradients-decentralized-fine-tuning)
      - [Data-Focused Subnets](#data-focused-subnets)
        - [Subnet 13 — Data Universe (Macrocosmos) ⭐ CRITICAL](#subnet-13--data-universe-macrocosmos--critical)
        - [Subnet 52 — Dojo (Tensorplex)](#subnet-52--dojo-tensorplex)
        - [Subnet 54 — MIID (Synthetic Identities)](#subnet-54--miid-synthetic-identities)
        - [Subnet 75 — Hippius (Decentralized Cloud Storage)](#subnet-75--hippius-decentralized-cloud-storage)
      - [Financial \& Trading Subnets](#financial--trading-subnets)
        - [Subnet 15 — BitQuant (DeFi Analytics)](#subnet-15--bitquant-defi-analytics)
        - [Subnet 79 — τaos (Financial Market Simulation)](#subnet-79--τaos-financial-market-simulation)
    - [AIQ Deep Research Agent — Subnet Data Pipeline](#aiq-deep-research-agent--subnet-data-pipeline)
  - [Research \& Documentation](#research--documentation)
    - [Deep Research Reports](#deep-research-reports)
    - [Community \& Support](#community--support)
  - [License](#license)

---

## Overview

KubeTEE AI provides Enterprise-Grade AI as a Service (AIaaS) featuring the world's best Open Source Deep Research Agent in a Trusted Execution Environment (TEE) on a Decentralized Multi-Clusters Kubernetes RKE2 FIPS-140-2 U.S. Federal Government Grade Security Decentralized Infrastructure.

### Performance & Rankings

**AI Deep Research Agents**: Ranked on [DeepResearch Benchmark Leaderboard](https://huggingface.co/spaces/Ayanami0730/DeepResearch-Leaderboard) using Open Source code and Fine-Tuned Open Source Models, part of the AGI Benchmarks.

**Benchmark Resources**:
- [Benchmark White Paper](https://arxiv.org/pdf/2506.11763)
- [Benchmark Website](https://deepresearch-bench.github.io/)
- [GitHub Deep Research Bench Code](https://github.com/Ayanami0730/deep_research_bench)

### AI Deep Research Reports

We used different AI Deep Research Agents to elaborate the Subnet Architecture:
- [Grok xAI Deep Research Report](./docs/Grok_XAI_Research.md)
- [Claude Deep Research Project Architecture Report](./docs/Claude_Deep_Research.md)

---

## Key Features

✅ **Enterprise-Grade Security**: FIPS-140-2 certified, TEE-enabled infrastructure  
✅ **Confidential Computing**: Intel TDX/SGX, NVIDIA Hopper/Blackwell PCIe Protected Mode  
✅ **Multi-Cluster**: Rancher Fleet-managed clusters across Americas, EU, Middle East, Africa, Asia  
✅ **Production-Ready**: High availability, automated monitoring, and audit trails  
✅ **Open Source**: Transparent development with community-driven improvements  
✅ **NVIDIA-Powered**: Best-in-class AI models and microservices  

---

## The Enterprise AI Challenge: Problems We Solve

### The Current State of Enterprise AI

Most small and medium-sized businesses (SMBs) and regulated enterprises face insurmountable barriers to adopting advanced AI:

#### 1. **SMB Enterprises Locked Out of Advanced AI**

**The Problem:**
- Enterprise AI solutions like Palantir cost $2M-$10M+ annually—prohibitive for SMBs
- Cloud AI services (OpenAI, Anthropic) require sending sensitive data to third parties
- Building in-house AI infrastructure requires $500K-$2M+ in initial investment and specialized talent
- Limited access to cutting-edge models and tools reserved for large enterprises

**KubeTEE's Solution:**
- **Pay-as-you-go pricing** with usage-based Alpha token economics—start small, scale as needed
- **One-command deployment** eliminates the need for large AI/DevOps teams
- **Enterprise-grade capabilities** at SMB-accessible prices
- **Best-in-class NVIDIA models** available to all, regardless of company size

#### 2. **Regulated Enterprises Unable to Deploy AI Safely**

**The Problem:**
- Healthcare (HIPAA), Finance (SOC2, PCI-DSS), Government (FedRAMP) face strict compliance requirements
- Public cloud AI services cannot guarantee data isolation and compliance
- Traditional solutions require extensive security audits and certifications
- Compliance burden makes AI adoption too risky or expensive

**KubeTEE's Solution:**
- **FIPS-140-2 certification** meets U.S. Federal Government security standards
- **Trusted Execution Environment (TEE)** with hardware-enforced isolation (Intel TDX/SGX, NVIDIA CC)
- **Confidential Computing Consortium member** driving industry security standards
- **Audit trails and monitoring** built-in for compliance reporting
- **Isolated namespaces** ensure complete tenant separation
- **mTLS Encrypted comminication** Ensure all network/cluster communications are secure

#### 3. **Private Data Processing Without Compromise**

**The Problem:**
- Enterprises cannot send proprietary data to public cloud AI services
- Customer PII, trade secrets, and sensitive documents exposed to third-party risks
- Data residency requirements (GDPR, data localization laws) restrict cloud AI usage
- No guarantee that data won't be used to train public models

**KubeTEE's Solution:**
- **On-infrastructure deployment** via decentralized Kubernetes clusters—data never leaves your control plane
- **Geographic sovereignty** with multi-region deployment (Americas, EU, Middle East, Africa, Asia)
- **Private namespaces** ensure complete data isolation between tenants
- **Bring Your Own LLM** with NeMo Microservices—deploy custom models on private data
- **Zero data leakage** to model providers or third parties

#### 4. **Data and Model Privacy Through Confidential Computing**

**The Problem:**
- Traditional cloud deployments expose data in memory during processing
- Insider threats and cloud provider access to sensitive data
- Model theft and intellectual property concerns
- No cryptographic guarantees that data remains private during inference

**KubeTEE's Solution:**
- **Hardware-enforced Trusted Execution Environment (TEE)** encrypts data in use, not just at rest and in transit
- **Intel TDX/SGX** creates isolated memory enclaves invisible to hypervisors and OS
- **NVIDIA Hopper/Blackwell Confidential Computing** protects GPU workloads during AI inference
- **Kata Containers** isolate workloads at the VM level with cryptographic validation
- **End-to-end encryption** from data ingestion through model inference to results

#### 5. **Trust in Decentralized Infrastructure**

**The Problem:**
- Centralized cloud providers represent single points of failure and control
- Vendor lock-in limits flexibility and negotiating power
- Concerns about cloud provider access to proprietary data and models
- No transparency into infrastructure operations and data handling
- Geopolitical risks and jurisdiction concerns

**KubeTEE's Solution:**
- **Decentralized multi-cluster architecture** eliminates single points of failure
- **Bittensor incentive mechanism** aligns infrastructure providers with customer success
- **Open source transparency**—inspect code, audit security, verify operations
- **Community validation** through Bittensor subnet ensures honest behavior
- **Geographic distribution** across multiple regions and providers reduces risk
- **Cryptographic verification** of workload integrity via Confidential Containers
- **Validator monitoring** provides objective quality and uptime metrics
- **No vendor lock-in**—open standards (Kubernetes, OpenInfra) enable migration

### The KubeTEE Value Proposition

KubeTEE AI uniquely combines **enterprise-grade security**, **decentralized trust**, and **SMB-accessible pricing** to democratize access to confidential AI infrastructure. We solve the "impossible triangle" that has prevented SMBs and regulated enterprises from adopting advanced AI:

```
        Enterprise Security
               /\
              /  \
             /    \
            /      \
           /        \
          /          \
         /____________\
    Affordable      Trustworthy
     Pricing       Decentralized
```

Traditional solutions force you to choose two:
- **Cloud AI**: Affordable + Decentralized ❌ Security
- **Palantir**: Security + Centralized ❌ Affordable
- **Build Your Own**: Security + Expensive ❌ Decentralized

**KubeTEE AI delivers all three.**

---

## KubeTEE AI vs Palantir: Enterprise AI Comparison

Understanding how KubeTEE AI compares to established enterprise solutions like Palantir helps position our value proposition for system integrators and enterprises.

| **Aspect** | **Palantir** | **KubeTEE AI** |
|-----------|--------------|----------------|
| **Business Model** | Proprietary, closed-source with high licensing fees ($2M+ annual contracts) | Open source, decentralized infrastructure with pay-as-you-go pricing |
| **Technology Stack** | Proprietary platforms (Gotham, Foundry, AIP) | Open source NVIDIA stack (NeMo, NIM, AI Blueprints) |
| **Infrastructure** | Cloud or on-premises deployment on customer infrastructure | Decentralized multi-cluster Kubernetes across global regions |
| **Security** | Government-grade security, compliance certifications | FIPS-140-2, TEE (Intel TDX/SGX, NVIDIA CC), Confidential Computing Consortium member |
| **AI Capabilities** | Proprietary AI/ML, recently added AIP (AI Platform) | Best-in-class NVIDIA AI models, #1 ranked Deep Research Agent |
| **Deployment Time** | 6-18 months typical implementation | One-command deployment via KubeTEE CLI |
| **Vendor Lock-in** | High - proprietary technology and data formats | None - open source, standards-based (Kubernetes, OpenInfra) |
| **Cost Structure** | Multi-million dollar upfront + annual licensing | Usage-based pricing with Alpha token economics |
| **Customization** | Limited - requires Palantir engineering engagement | Full control - fork, modify, deploy custom solutions |
| **Data Ownership** | Customer owned but platform-dependent | Customer owned with full control and portability |
| **Community** | Closed - Palantir employees only | Open - Bittensor community, NVIDIA ecosystem, OpenInfra Foundation |
| **Integration Approach** | Top-down, enterprise sales | Bottom-up, community integrators and solution providers |
| **Compliance** | FedRAMP, IL5, various government certifications | FIPS-140-2, working towards FedRAMP, CCC member |
| **Scalability** | Vertical scaling, centralized | Horizontal scaling, decentralized across global clusters |

### Key Differentiators

**Why Palantir?**
- Established reputation with government and Fortune 500
- Proven track record in complex data integration scenarios
- Deep domain expertise in defense and intelligence sectors
- Comprehensive support and professional services

**Why KubeTEE AI?**
- **10-100x Cost Savings**: Pay only for actual usage vs. multi-million dollar contracts
- **Zero Vendor Lock-in**: Open source stack, migrate anytime
- **Faster Time-to-Value**: Deploy in hours/days vs. months/years
- **Best-in-Class AI**: NVIDIA's cutting-edge models and microservices
- **Community-Driven Innovation**: Bittensor ecosystem accelerates development
- **Decentralized Resilience**: Multi-region infrastructure with no single point of failure
- **Distribution Channel**: System integrators can resell and customize

### Complementary Use Cases

KubeTEE AI and Palantir can coexist in enterprise environments:

- **Palantir**: Complex data integration, legacy system connectivity, defense/intelligence operations
- **KubeTEE AI**: AI workloads, deep research, RAG pipelines, LLM deployment, edge computing

### Target Market Positioning

**Palantir**: Large enterprises and government agencies with $10M+ AI budgets  
**KubeTEE AI**: 
- SMBs and mid-market enterprises ($100K-$5M AI budgets)
- System integrators building solutions for clients
- Bittensor community members monetizing AI services
- Organizations seeking open source alternatives
- Edge computing and multi-region deployments

### AI Agent Market: Big Tech Consolidation

The AI agent market is rapidly consolidating as Big Tech acquires emerging startups at massive valuations:

| **Acquisition** | **Buyer** | **Valuation** | **Date** | **Notable** |
|----------------|-----------|---------------|----------|-------------|
| **Manus AI** | Meta | **$2 Billion** | Dec 2025 | Claimed to outperform OpenAI Deep Research |
| Character.AI | Google | $2.7 Billion | 2024 | Conversational AI agents |
| Inflection AI | Microsoft | $650 Million | 2024 | Pi chatbot |

**Meta's Manus Acquisition** ([TechCrunch, Dec 29 2025](https://techcrunch.com/2025/12/29/meta-just-bought-manus-an-ai-startup-everyone-has-been-talking-about/)):
- Singapore-based AI startup founded by Chinese entrepreneurs
- Demo showed AI agent screening job candidates, planning vacations, analyzing portfolios
- Raised $75M from Benchmark at $500M valuation in April 2025
- Grew to $100M+ ARR with millions of users before acquisition
- Meta will integrate Manus agents into Facebook, Instagram, WhatsApp

**Why This Matters for KubeTEE AI**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AI AGENT MARKET CONSOLIDATION                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PROPRIETARY (Big Tech Owned)          OPEN SOURCE (KubeTEE Alternative)   │
│  ────────────────────────────          ─────────────────────────────────   │
│                                                                             │
│  • Manus (Meta) - $2B                  • KubeTEE Deep Research Agent       │
│  • Character.AI (Google) - $2.7B       • Decentralized, no single owner    │
│  • Inflection (Microsoft) - $650M      • Community-driven development      │
│  • OpenAI (Microsoft invested)         • TEE-secured, trustless            │
│  • Anthropic (Google/Amazon)           • No vendor lock-in                 │
│                                                                             │
│  Risk: Acquired startups become        Benefit: Open source can't be       │
│        locked into Big Tech            acquired—the network owns itself    │
│        ecosystems                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**KubeTEE's Decentralized Advantage**:
- ✅ **No platform lock-in** — Unlike Manus (now locked to Meta ecosystem)
- ✅ **Privacy-first** — TEE ensures data never leaves secure enclave
- ✅ **Open innovation** — Anyone can contribute and monetize
- ✅ **Censorship-resistant** — No single entity can shut it down

As Big Tech consolidates AI agents, KubeTEE AI represents the **decentralized alternative** for organizations that want cutting-edge Deep Research capabilities without platform dependency.

---

## Architecture

### Infrastructure

#### Kubernetes High Availability

**RKE2 Rancher Kubernetes**
- [FIPS-140-2](https://docs.rke2.io/security/fips_support) U.S. Federal Government Grade Security
- Fully conformant distribution focused on security and compliance

**Multi-Cluster Management**
- [Rancher Fleet](https://fleet.rancher.io/) GitOps-based Multi-Cluster Management
- Regional deployment: Americas, EU, Middle East, Africa, Asia
- Native integration with Rancher for unified management

**Rancher UI RBAC Management**
- Users/Miners access to isolated Kubernetes Namespaces
- Project-based resource isolation
- Fleet workspaces for multi-tenancy

### Security & Compliance

#### Confidential Computing Features

**Trusted Execution Environment (TEE)**
- Intel TDX/SGX
- NVIDIA Hopper/Blackwell PCIe Protected Mode
- Kata Containers for workload isolation
- Confidential Containers with Workload Identity Validation

#### Network Security
- Linkerd mTLS communication within the cluster
- Network Policies enforcement
- RBAC (Role-Based Access Control)

#### Data Protection
- **Rancher Longhorn**: Encrypted Storage with 3 Replicas
- Encrypted Container Repository
- External Secrets Manager (Vault)

#### Monitoring & Audit
- Prometheus Metrics
- Kubernetes Events tracking
- UpTime, QoS, and Performance monitoring
- ElasticSearch Audit logs

### Multi-Cluster Topology

#### Subnet Owner Infrastructure
- Global Multi-Cluster Control Plane with Rancher on Confidential Computing TEE
- Rancher Multi-Cluster Management with Fleet for GitOps
  - RKE2 Rancher Kubernetes with FIPS-140-2 deployment
  - Kata Containers (TEE)
  - [Confidential Containers](https://confidentialcontainers.org/docs/overview/) Operator

#### Miner Infrastructure
- RKE2 Rancher Kubernetes
- One Cluster per Miner (identified by hotkey/coldkey, not UID)
  - Regional deployment (One Region/Zone Control Plane with same region workers)
  - Cluster labeled with `kubetee.ai/` prefixed labels for permanent identification
  - Required labels: `kubetee.ai/continent`, `kubetee.ai/country`, `kubetee.ai/city`, `kubetee.ai/miner-hotkey`, `kubetee.ai/miner-coldkey`, `kubetee.ai/miner-uid`
- Kata Containers and CoCo Containers (TEE)
- Fleet Agent for automated deployments

**Important**: Clusters are labeled with `kubetee.ai/miner-hotkey` and `kubetee.ai/miner-coldkey` for permanent identification. These labels never change, while `kubetee.ai/miner-uid` can be updated if a miner deregisters and re-registers on the subnet.

---

## AI Technology Stack

### Core Blueprints

#### 1. NVIDIA AIQ Research Assistant

[NVIDIA AIQ Research Assistant Blueprint](https://github.com/KubeTEE-AI-Blueprints/aiq-research-assistant) - Best-in-class Open Source Tech Stack using Open Source Models

**Framework-Agnostic Architecture:**

Built on the [**NVIDIA NeMo Agent Toolkit**](https://github.com/NVIDIA/NeMo-Agent-Toolkit), an open-source library that is **framework-agnostic** and designed to efficiently connect and optimize teams of AI agents. The toolkit complements any existing agentic framework you're using and isn't tied to any specific framework, long-term memory, or data source.

**Supported Agentic Frameworks:**
- **[LangGraph](https://github.com/langchain-ai/langgraph)** & **[LangChain](https://github.com/langchain-ai/langchain)**: Primary framework used in AIQ for building the deep research agent with human-in-the-loop capabilities
- **[CrewAI](https://github.com/joaomdmoura/crewAI)**: Multi-agent collaboration framework
- **[LlamaIndex](https://github.com/run-llama/llama_index)**: Data framework for LLM applications
- **[Semantic Kernel](https://github.com/microsoft/semantic-kernel)**: Microsoft's AI orchestration framework
- **[Google Agent Development Kit (ADK)](https://github.com/google/agent-dev-kit)**: Google's framework for building AI agents
- **Custom Frameworks**: Integrate with any agentic framework of your choice

**Built-in Integrations:**
- **Observability Platforms**: Arize Phoenix, Weights & Biases (W&B) Weave, Langfuse, plus OpenTelemetry compatibility
- **Model Context Protocol (MCP)**: Full MCP support as both client and server
- **Memory Systems**: Mem0ai and custom memory solutions
- **Evaluation Tools**: RAGAS for RAG evaluation and built-in evaluation system
- **Storage**: Redis, MinIO, and custom data sources

**Key Capabilities:**
- 🔗 **Framework-Agnostic**: Works with your existing tools and frameworks
- 🔁 **Reusable Components**: Every agent, tool, and workflow exists as composable function calls
- ⚡ **Rapid Development**: Start with pre-built agents and customize to your needs
- 📈 **Profiling & Observability**: Track performance, tokens, timings, and execution flows
- 🧪 **Built-in Evaluation**: Validate and maintain accuracy of agentic workflows
- 💬 **User Interface**: Chat interface to interact with agents and debug workflows

This means developers can use **any agentic framework they prefer** (LangChain, CrewAI, LlamaIndex, Semantic Kernel, etc.) and easily extend, customize, and integrate the AIQ Research Assistant into their existing workflows and applications.

#### 2. NVIDIA RAG Blueprint

[NVIDIA RAG Blueprint](https://github.com/KubeTEE-AI-Blueprints/rag) - Enterprise RAG pipeline with industry-leading performance

![NVIDIA RAG Blueprint Architecture](https://assets.ngc.nvidia.com/products/api-catalog/build-an-enterprise-rag-pipeline/diagram.jpg)

**Key Components**:
- [NV-INGEST](https://github.com/KubeTEE-AI/nv-ingest) - Automated Ingestion of Enterprise Data
- NVIDIA Llama Nemotron VL 8B - [#1 OCRBench V2 Leaderboard](https://huggingface.co/spaces/ling99/OCRBench-v2-leaderboard)

#### 3. NVIDIA Streaming Data to RAG

[KubeTEE Streaming Data to RAG](https://github.com/KubeTEE-AI-Blueprints/streaming-data-to-rag) - Stream data ingestion ETL pipeline with [Context Aware RAG](https://github.com/KubeTEE-AI-Blueprints/context-aware-rag)

![Streaming Data to RAG Architecture](https://github.com/KubeTEE-AI-Blueprints/streaming-data-to-rag/raw/main/docs/arch-diagram.png)

#### 4. NVIDIA NeMo Retriever Microservice

[NVIDIA NeMo Retriever](https://developer.nvidia.com/nemo-retriever) - Sets new standards for enterprise RAG applications with first-place performance across three top visual document retrieval leaderboards:
- [ViDoRe V1 & V2](https://huggingface.co/spaces/vidore/vidore-leaderboard)
- [MTEB VisualDocumentRetrieval](https://huggingface.co/spaces/mteb/leaderboard)

#### 5. NVIDIA Data Flywheel

[NVIDIA Data Flywheel](https://github.com/KubeTEE-AI-Blueprints/data-flywheel) - Autonomous self-improvement through Reinforcement Learning (RL) from prompt response logs in ElasticSearch

#### 6. NVIDIA Video Search and Summarization

[NVIDIA Video Search and Summarization Blueprint](https://github.com/KubeTEE-AI-Blueprints/video-search-and-summarization) - Ingest massive volumes of live or archived videos and extract insights for summarization and interactive Q&A

**Key Capabilities**:
- 🎥 **Video Analytics AI Agent**: Natural language tasks for complex operations like video summarization and visual question-answering
- 🔍 **Multi-hop Reasoning**: Deeper contextual understanding with graph and vector databases
- 📊 **Scalable Architecture**: Efficient management of extensive video data with short-term (chat history) and long-term memory (vector/graph DB)

**Software Components**:
- **VLM**: Cosmos Reason1 7B for visual understanding
- **LLM**: Llama 3.1 70B/8B for language processing
- **Embeddings**: llama-3.2-nv-embedqa-1b-v2
- **Reranker**: llama-3.2-nv-rerankqa-1b-v2

**Supported GPU Topologies**: 8xH100, 8xH200, 8xB200

#### Additional Services

- [Tavily Web Search](https://www.tavily.com/) - Real-time web search capabilities
- Implement [Subnet 22 deSearch](https://desearch.ai/)

### NVIDIA NeMo Microservices

> Each cluster will provide a shared mTLS secure and High Availability NeMo Microservices infrastructure

[NVIDIA NeMo Microservices](https://docs.nvidia.com/nemo/microservices/latest/about/index.html) - API-first modular tools for customizing, evaluating, and securing LLMs and embedding models on Kubernetes with TEE

![NVIDIA NeMo Microservices Architecture](https://docs.nvidia.com/nemo/microservices/latest/_images/architecture-topology.png)

**Available Microservices**:

| Service | Description |
|---------|-------------|
| **NeMo Customizer** | Fine-tuning of LLMs and embedding models using full-supervised and parameter-efficient techniques |
| **NeMo Evaluator** | Comprehensive evaluation capabilities supporting academic benchmarks, custom evaluations, and LLM-as-a-Judge |
| **NeMo Guardrails** | Safety checks and content moderation protecting against hallucinations, harmful content, and vulnerabilities |
| **NeMo Data Designer** | (Early Access) High-quality synthetic dataset generation |
| **NeMo Auditor** | (Early Access) Security and harmful content auditing for models and agentic applications |
| **NeMo Data Store** | Default file storage compatible with Hugging Face Hub client (HfApi) |
| **NeMo Entity Store** | Management tools for namespaces, projects, datasets, and models |
| **NeMo Deployment Management** | API for deploying and managing NIM via NIM Operator |
| **NeMo NIM Proxy** | Unified endpoint for accessing all deployed NIM for inference |
| **NeMo Operator** | Manages custom resource definitions (CRDs) for fine-tuning jobs |

### NVIDIA NIM Models

#### Language Models
- NVIDIA Llama3.3 Nemotron 49B Super V1.5
- NVIDIA Llama3.3 70B Instruct
- Mixtral 8x22B Instruct 0.1

#### Retrieval Models
- NeMo Retriever Llama 3.2 Embedding NIM
- NeMo Retriever Llama 3.2 Reranking NIM
- NeMo Retriever Page Elements NIM
- NeMo Retriever Table Structure NIM
- NeMo Retriever Graphic Elements NIM
- NeMo Retriever OCR v1 NIM (Replaces PaddleOCR)
- NeMo Retriever Parse NIM

#### Safety & Vision Models
- Llama 3.1 NemoGuard 8B Content Safety NIM
- Llama 3.1 NemoGuard 8B Topic Control NIM
- Llama 3.2 11B Vision Instruct NIM
- Llama Nemotron Nano VL 8B

#### Speech Recognition
- NVIDIA Riva ASR NIM

---

## Subnet Economics

### Native Bittensor Multiple Incentive Mechanisms

KubeTEE AI uses the **native Bittensor Multiple Incentive Mechanisms** feature as documented at [docs.learnbittensor.org](https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets).

This provides:
- **Independent weight matrices** per mechanism
- **Separate bond pools** (independent Yuma Consensus)
- **On-chain emission splits** (transparent configuration)
- **Independent scoring** per mechanism

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              KubeTEE AI Multi-Mechanism Incentive Model                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ═══════════════════════════════════════════════════════════════════════   │
│   ║                 ON-CHAIN SUBNET EMISSIONS (100%)                    ║   │
│   ═══════════════════════════════════════════════════════════════════════   │
│                                    │                                        │
│                 ┌──────────────────┴──────────────────┐                     │
│                 ▼                                     ▼                     │
│       ┌─────────────────────┐           ┌─────────────────────┐            │
│       │   MECHANISM 0       │           │   MECHANISM 1       │            │
│       │   INFRASTRUCTURE    │           │   OPEN SOURCE       │            │
│       │      (60%)          │           │      (40%)          │            │
│       ├─────────────────────┤           ├─────────────────────┤            │
│       │ • K8s Infra         │           │ • Code Quality      │            │
│       │ • TEE Compliance    │           │ • Benchmarks        │            │
│       │ • Service QoS       │           │ • CI/CD             │            │
│       │ • Uptime            │           │ • Security fixes    │            │
│       └─────────────────────┘           └─────────────────────┘            │
│                 │                                     │                     │
│                 ▼                                     ▼                     │
│       ┌─────────────────────┐           ┌─────────────────────┐            │
│       │   Independent       │           │   Independent       │            │
│       │   Weight Matrix     │           │   Weight Matrix     │            │
│       │   & Bond Pool       │           │   & Bond Pool       │            │
│       └─────────────────────┘           └─────────────────────┘            │
│                                                                             │
│   ═══════════════════════════════════════════════════════════════════════   │
│   ║         RESELLERS: ON-CHAIN PAYMENTS (NO EMISSIONS!)                ║   │
│   ═══════════════════════════════════════════════════════════════════════   │
│                                                                             │
│       ┌─────────────────────────────────────────────────────────────────┐  │
│       │  RESELLERS / WHITE LABEL                                        │  │
│       │  ─────────────────────────────────────────────────────────────  │  │
│       │  ✗ NOT registered on Bittensor subnet (no emissions)           │  │
│       │  ✓ Register via KubeTEE CLI → Creates Rancher account          │  │
│       │  ✓ Coldkey/Hotkey with Alpha                                   │  │
│       │  ✓ Deposit Alpha/TAO to on-chain smart contract                │  │
│       │  ✓ Validators calculate usage & transfer each epoch            │  │
│       │  ─────────────────────────────────────────────────────────────  │  │
│       │  PAY 50% OF RETAIL → KubeTEE Owner Key                          │  │
│       │  Future: ERC-8004 / x.402 payment protocols                    │  │
│       └─────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Miners can participate in BOTH mechanisms simultaneously!** If you provide infrastructure AND contribute code improvements, you earn from both emission pools.

### Mechanism 0: Infrastructure (60% Emissions)

**Purpose**: Reward miners for providing Kubernetes infrastructure to serve user AI requests.

**Key Feature**: **Emissions are distributed per resources provided** (GPU nodes)

**⚠️ Mandatory Requirement**:
- **TEE Attestation** (Intel TDX/SGX, NVIDIA CC) must be proven — **no attestation = no emissions**

**Emission Allocation** (per node type with 8 GPUs):

| GPU Node Type | Base Weight | Description |
|---------------|-------------|-------------|
| **H100** | 1.0x | Base tier |
| **H200** | 1.5x | Higher memory bandwidth |
| **B200** | 2.0x | Next-gen Blackwell |
| **B300** | 2.5x | Top-tier Blackwell |

**Quality Multipliers** (applied to base weight):

| Criteria | Weight | Description |
|----------|--------|-------------|
| **Resource Utilization** | 35% | Most important — target 80% capacity (±5% tolerance) |
| **Uptime** | 30% | Target 99.9%+ availability |
| **Bandwidth** | 20% | Network throughput — 10Gbps baseline |
| **Latency** | 15% | Response time quality |

**⚠️ Resource Utilization Penalties**:
- **Above 85% capacity**: Penalized — cluster is overloaded, cannot serve additional requests
- **Below 75% capacity**: Penalized — underutilized, not contributing proportionally to subnet demand
- **Target: 80% capacity**: Optimal — ensures miners provide exactly what the subnet needs

**Benefits**:
- ✅ TEE compliance is enforced, not optional
- ✅ Clear incentive to provide higher-tier GPU nodes
- ✅ Resource utilization ensures balanced subnet capacity — no over/under provisioning

### Mechanism 1: Open Source Competition (40% Emissions)

**Purpose**: Reward miners for improving the KubeTEE tech stack and NVIDIA Blueprints.

**⚠️ NO "WINNER TAKES ALL"** — We use a **hybrid bounty + continuous contribution model** to avoid drama and ensure fair rewards for all contributors.

#### GitHub Issues = Bounties

**Bounties ARE GitHub Issues** in `KubeTEE-AI` organization repositories. Each bounty has a dedicated **hotkey where emissions accumulate** until the bounty is won.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GITHUB ISSUES = BOUNTIES                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Example GitHub Issue:                                                      │
│  ─────────────────────                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Issue #42: "Optimize batch inference pipeline"                     │    │
│  │                                                                     │    │
│  │  Labels: [bounty:hard] [category:optimization]                      │    │
│  │  Bounty Hotkey: 5FHneW46...abc123                                   │    │
│  │  Accumulated: 47.3 Alpha (receiving emissions each epoch)           │    │
│  │                                                                     │    │
│  │  Acceptance Criteria:                                               │    │
│  │  - [ ] Throughput improved by 2x                                    │    │
│  │  - [ ] All CI tests pass                                            │    │
│  │  - [ ] No memory regression                                         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  EMISSION FLOW:                                                             │
│  ─────────────                                                              │
│  Subnet → Open Source (40%) → Bounty Pool (60%) → Bounty Hotkeys            │
│                                                                             │
│  The longer a bounty stays open, the more emissions accumulate!             │
│  Hard/Epic bounties = bigger rewards (higher weight = more emissions/epoch) │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**GitHub Labels for Bounties**:

| Label | Type | Weight | Description |
|-------|------|--------|-------------|
| `bounty:easy` | Difficulty | 1x | Good for newcomers |
| `bounty:medium` | Difficulty | 2x | Standard tasks |
| `bounty:hard` | Difficulty | 4x | Complex improvements |
| `bounty:epic` | Difficulty | 8x | Major features |
| `category:bug-fix` | Category | Merged PR | Bug fixes |
| `category:feature` | Category | Bounty | New features |
| `category:documentation` | Category | Merged PR | Docs improvements |
| `category:benchmark` | Category | Bounty | Benchmark improvements |
| `category:security` | Category | Bounty | Security fixes |
| `category:optimization` | Category | Bounty | Performance optimizations |
| `category:testing` | Category | Merged PR | Test coverage |

#### Emission Distribution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OPEN SOURCE EMISSIONS (40% of subnet)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐         │
│  │   BOUNTY POOL    │   │   BENCHMARK      │   │   MERGED PRs     │         │
│  │      50%         │   │      30%         │   │      20%         │         │
│  └────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘         │
│           │                      │                      │                   │
│           ▼                      ▼                      ▼                   │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐         │
│  │ Bounty Hotkeys   │   │ Benchmark        │   │ PRs merged to    │         │
│  │ (weighted by     │   │ improvement      │   │ main branch      │         │
│  │  difficulty)     │   │ bonus            │   │                  │         │
│  └──────────────────┘   └──────────────────┘   └──────────────────┘         │
│                                                                             │
│  When bounty is WON → Accumulated emissions transfer to winner!             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Bounty Lifecycle (Fully Automated)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AUTOMATED BOUNTY VALIDATION FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. GITHUB ISSUE CREATED with bounty:* label                                │
│     └── System generates bounty hotkey (emissions start accumulating)       │
│                                                                             │
│  2. MINER SUBMITS PR with "Fixes #42" in commit                             │
│     └── PR linked to issue/bounty automatically                             │
│                                                                             │
│  3. AUTOMATED CI/CD PIPELINE (GitHub Actions)                               │
│     ├── Unit tests run                                                      │
│     ├── Integration tests run                                               │
│     ├── Benchmark tests run (if category:benchmark)                         │
│     └── PASS / FAIL                                                         │
│                                                                             │
│  4. AI CODE ANALYSIS (Subnet Owner Validator)                               │
│     ├── Code quality score (0-100)                                          │
│     ├── Security scan  BITSEC (SN60)                                        │
│     ├── Performance analysis                                                │
│     └── AI generates approval/rejection with reasoning                      │
│                                                                             │
│  5. SUBNET OWNER FINAL DECISION                                             │
│     ├── If CI PASS + AI Score >= 70 → AUTO-APPROVE                          │
│     ├── If CI FAIL → AUTO-REJECT                                            │
│     └── Edge cases → Subnet owner manual review                             │
│                                                                             │
│  6. PAYOUT                                                                  │
│     ├── Accumulated emissions transfer from bounty hotkey to winner         │
│     ├── GitHub Issue closed automatically                                   │
│     └── bounty:completed label added                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**How to Participate** (GitHub-Native Workflow):

1. **Browse bounties**: Go to [github.com/KubeTEE-AI](https://github.com/KubeTEE-AI) and look for issues with `bounty:*` labels
2. **Comment to claim** (optional): Comment "I'm working on this" to make aware how many are participating on this bounty
3. **Submit PR**: Include `Fixes #42` in your commit message to link to the issue
4. **Wait for validation**: CI/CD + Bitsec security scan + AI analysis run automatically
5. **Get paid**: If approved, accumulated emissions transfer to your hotkey!

**Automated Validation Criteria**:

| Check | Tool | Threshold |
|-------|------|-----------|
| Unit Tests | pytest | 100% pass |
| Integration Tests | pytest | 100% pass |
| Code Quality | AI Analysis (Claude/GPT) | Score >= 70/100 |
| **Security Scan** | **Bitsec (Subnet 60)** | **0 high/critical issues** |
| Test Coverage | Coverage.py | >= 80% (if tests added) |
| Documentation | AI Analysis | Required for new features |
| Benchmark Delta | DeepResearch Bench | >= 0% (no regression) |

#### Security Scanning via Bitsec (Subnet 60)

We integrate with **Bitsec (SN60)** for decentralized security auditing of code submissions. Bitsec uses AI to find code exploits and vulnerabilities in blockchain projects.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BITSEC (SUBNET 60) INTEGRATION                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CODE SUBMISSION                                                            │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                   BITSEC (SN60)                                     │    │
│  │                                                                     │    │
│  │   • AI-powered vulnerability detection                             │    │
│  │   • Smart contract security analysis                               │    │
│  │   • Code exploit finder                                            │    │
│  │   • Decentralized security network                                 │    │
│  │                                                                     │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  SECURITY REPORT                                                    │    │
│  │                                                                     │    │
│  │  Critical: 0  │  High: 0  │  Medium: 2  │  Low: 5                   │    │
│  │                                                                     │    │
│  │  Verdict: PASS (no critical/high issues)                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Benefits of Bitsec Integration**:
- 🔒 **Decentralized security** — No single point of failure
- 🤖 **AI-powered** — Advanced vulnerability detection
- ⚡ **Fast** — Automated scanning on every PR
- 🔗 **Bittensor native** — Subnet-to-subnet integration

**Why This Model Works**:
- ✅ **No drama** — Clear criteria, automated validation
- ✅ **No human in the loop** — Validators run automated checks
- ✅ **Fair for newcomers** — Easy bounties to start
- ✅ **Rewards consistency** — Continuous contributions add up
- ✅ **Multiple winners** — Not winner-takes-all
- ✅ **Transparent** — All bounties, submissions, and AI analysis public
- ✅ **Subnet owner authority** — Final decision on edge cases
- ✅ **Subnet integration** — Bitsec (SN60) for security, Gradients (SN56) for fine-tuning

### Referrers / Integrators / Resellers: 50% Revenue Share (NO Emissions!)

**⚠️ IMPORTANT**: Referrers do NOT use emissions and do NOT register on the Bittensor subnet!

Instead of a wholesale model where resellers charge different prices, we use a **unified pricing + referral revenue share model**:

- **All users pay the same retail price** (direct or via referrer)
- **Referrers earn 50% of revenue** from users they bring in
- **Simple, transparent, and fair** for everyone

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REFERRAL REVENUE SHARE MODEL (50%)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ACCESS CHANNELS (Same Retail Price for Everyone!)                         │
│   ─────────────────────────────────────────────────                         │
│                                                                             │
│   ┌─────────────┐    ┌──────────────────────┐    ┌──────────────────────┐   │
│   │   DIRECT    │    │  VIA REFERRER        │    │  VIA INTEGRATOR      │   │
│   │   USERS     │    │  (Affiliate)         │    │  (White-Label API)   │   │
│   └──────┬──────┘    └──────────┬───────────┘    └──────────┬───────────┘   │
│          │                      │                           │               │
│          │ Pay retail           │ Pay retail                │ Pay retail    │
│          │ price                │ price                     │ price         │
│          ▼                      ▼                           ▼               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    KUBETEE PAYMENT SYSTEM (BASE L2)                 │   │
│   │                                                                     │   │
│   │   Revenue Distribution (per user payment):                          │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │                                                             │   │   │
│   │   │   DIRECT USER:       100% → KubeTEE Owner                   │   │   │
│   │   │                                                             │   │   │
│   │   │   REFERRED USER:     50%  → KubeTEE Owner                   │   │   │
│   │   │                      50%  → Referrer/Integrator             │   │   │
│   │   │                                                             │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   BENEFITS:                                                                 │
│   • Same price for everyone → No customer confusion                         │
│   • Referrers get passive income → Strong incentive to promote              │
│   • Simple tracking → On-chain attribution                                  │
│   • Win-win-win → Users, referrers, and subnet all benefit                 │
│                                                                             │
│   Future Protocols: ERC-8004 (Decentralized Paymaster) / x.402              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Referrer Types**:

| Type | Description | Use Case |
|------|-------------|----------|
| **Affiliate** | Refers users via referral link/code | Content creators, influencers |
| **Integrator** | Embeds KubeTEE into their product | SaaS companies, AI platforms |
| **White-Label** | Rebrands KubeTEE for their customers | Enterprise resellers |

All referrer types earn the same **50% revenue share** on referred users.

**Referrer Requirements** (Very simple!):

| Requirement | Referrer | Miner (Infrastructure) |
|-------------|----------|------------------------|
| Hotkey/Coldkey | ✅ Yes | ✅ Yes |
| Wallet (for payouts) | ✅ Yes | ✅ Yes |
| Kubernetes Infrastructure | ❌ **NO!** | ✅ Yes |
| GPU/CPU | ❌ **NO!** | ✅ Yes |
| Technical Operations | ❌ **NO!** | ✅ Yes |
| Bittensor Subnet Registration | ❌ **NO!** | ✅ Yes (for emissions) |
| Register via KubeTEE CLI | ✅ Yes | Optional |

**Referrer Onboarding Flow**:

```bash
# 1. Create/import wallet
kubetee wallet create
# Or: kubetee wallet import --private-key <your_key>

# 2. Register as referrer
kubetee referrer register --name "My Company LLC" --payout-address 0x...
# → Creates referrer account
# → Generates unique referral code/link

# 3. Get your referral link
kubetee referrer link
# → https://kubetee.ai/signup?ref=ABC123
# → Or embed in API: X-KubeTEE-Referrer: ABC123

# 4. Share with your users/customers
# → They sign up and use KubeTEE normally
# → You earn 50% of their spend automatically

# 5. Check your earnings anytime
kubetee referrer earnings
# Shows: Total Referred Users, Total Revenue, Your Share (50%), Pending Payout

# 6. Withdraw your earnings (auto-payout or manual)
kubetee referrer withdraw
# → USDC sent to your payout address
```

**For Integrators (API-Based Referral)**:

```python
# Embed referrer attribution in API calls
import requests

response = requests.post(
    "https://api.kubetee.ai/v1/chat/completions",
    headers={
        "Authorization": "Bearer <user_api_key>",
        "X-KubeTEE-Referrer": "your_referrer_code"  # Links user to your account
    },
    json={
        "model": "nvidia/llama-3.1-nemotron-70b-instruct",
        "messages": [{"role": "user", "content": "Hello!"}]
    }
)
```

**Revenue Share Examples**:

| User Action | Price | Direct User | Referred User (50/50 Split) |
|-------------|-------|-------------|----------------------------|
| **Basic Subscription** | **$499/month** | $499 → KubeTEE | $249.50 → KubeTEE, **$249.50 → Referrer** |
| **Professional Subscription** | **$1,499/month** | $1,499 → KubeTEE | $749.50 → KubeTEE, **$749.50 → Referrer** |
| **Enterprise Subscription** | **$4,999/month** | $4,999 → KubeTEE | $2,499.50 → KubeTEE, **$2,499.50 → Referrer** |
| Extra H200 GPU hour | $2.00 | $2.00 → KubeTEE | $1.00 → KubeTEE, **$1.00 → Referrer** |
| 1K tokens usage | $0.02 | $0.02 → KubeTEE | $0.01 → KubeTEE, **$0.01 → Referrer** |

**Referrer Earnings Example**:
- Refer 10 Basic subscribers (RAG users, no GPU): 10 × $249.50 = **$2,495/month**
- Refer 5 Professional subscribers (H200 + fine-tuning): 5 × $749.50 = **$3,747.50/month**
- Refer 2 Enterprise subscribers: 2 × $2,499.50 = **$4,999/month**

**Scaling Your Referral Income**:

| Referred Subscribers | Tier | Monthly Revenue | Your 50% Share |
|---------------------|------|-----------------|----------------|
| 5 | Basic ($499) | $2,495 | **$1,247.50/month** |
| 10 | Basic ($499) | $4,990 | **$2,495/month** |
| 5 | Professional ($1,499) | $7,495 | **$3,747.50/month** |
| 10 | Professional ($1,499) | $14,990 | **$7,495/month** |
| 2 | Enterprise ($4,999) | $9,998 | **$4,999/month** |
| Mix: 10 Basic + 5 Pro | — | $12,485 | **$6,242.50/month** |

**Why USDC on BASE?**
- ✅ **Zero volatility** - Stable earnings for referrers
- ✅ **Deep liquidity** - Easy withdrawal to fiat
- ✅ **Low fees** - More profit, less gas
- ✅ **x402 compatible** - Future micropayment support

**Smart Contract (BASE L2)**:

The `KubeTEEReferral.sol` contract handles:
- Referrer registration and code generation
- User → Referrer attribution (permanent)
- Automatic 50% revenue split per transaction
- Epoch-based batch payouts to referrers

Reference: [Bittensor EVM Documentation](https://docs.learnbittensor.org/evm-tutorials/subnet-precompile)

### On-Chain Emission Configuration

The emission split is configured on-chain using `sudo_set_mechanism_emission_split`:

```python
# Only 2 mechanisms use emissions (Resellers use B2B wholesale, no emissions)
# Emission split vector (value / 65535 = percentage)
emission_split = [
    39321,  # Mechanism 0: Infrastructure = 60%
    26214,  # Mechanism 1: Open Source = 40%
    # Mechanism 2: Resellers = 0% (B2B wholesale, not emissions!)
]

subtensor.sudo_set_mechanism_emission_split(
    wallet=wallet,
    netuid=netuid,
    emission_split=emission_split,
)
```

**Emission vs On-Chain Payment Streams**:

| Revenue Stream | Type | Registration | Distribution |
|----------------|------|--------------|--------------|
| Infrastructure Emissions (60%) | Subnet Emissions | Bittensor subnet | Via Yuma Consensus |
| Open Source Emissions (40%) | Subnet Emissions | Bittensor subnet | Via Yuma Consensus |
| Reseller Payments | On-Chain Contract | KubeTEE CLI only | Validator epoch settlement → KubeTEE Owner |

**On-Chain Smart Contract**: `KubeTEEPayment.sol` deployed on Bittensor EVM handles all reseller deposits and epoch settlements.

Reference: [Bittensor Multi-Mechanism Docs](https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets)

### Staging vs Production

**Staging Environment** (Permissionless):
- Test applications, infrastructure, upgrades, benchmarks
- Gateway to Production environment
- Kata Containers Community Staging infrastructure

**Production Environment** (KYC Required):
- Multi-Clusters (one per data center per miner)
- Must pass Staging validation
- KYC mandatory for laws & regulations

### Revenue Model

**User Onboarding**:
1. Hotkey created for user to deposit alpha token
2. Users receive isolated Project/Namespace in Rancher
3. Access to deploy KubeTEE Blueprints

**Resource Accounting**:
- Validators track resource usage per epoch in user Project/namespaces
- Service metrics tracked per request:
  - Tokens processed (input + output)
  - GPU compute time
  - Request latency
  - Success/failure status
- Automatic deduction from user hotkey
- Transparent billing based on actual usage
- **50% of billing goes directly to the miner who served the request**

**Pricing Tiers** (USDC on BASE):

| Plan | Price | RAG Storage | RAG GPU | Custom Model GPU | Total GPUs | Fine-Tuning |
|------|-------|-------------|---------|------------------|------------|-------------|
| **Pay-as-you-go** | **Usage-based** | — | Shared | Shared | 0 | ❌ None |
| **Basic** | **$499/month** | 50GB | CPU | — | 0 | ❌ None |
| **Professional** | **$1,499/month** | 100GB | 1× H200 | 1× H200 | **2× H200** | ✅ Weekly |
| **Enterprise** | **$4,999/month** | 500GB | 1× H200 | 2× H200 | **3× H200** | ✅ Continuous |

**🆕 Pay-as-you-go with X.402 Protocol** (No subscription required):

Anyone can use KubeTEE AI services instantly via the [X.402 Protocol](https://www.x402.org/) — a payment standard enabling HTTP-native micropayments with USDC on BASE.

| Usage Type | Price |
|------------|-------|
| LLM Inference | $0.02 per 1K tokens |
| Embedding | $0.01 per 1K tokens |
| GPU Compute | $2.00 per H200 hour |

- ✅ **No KYC required** — permissionless access for everyone
- ✅ **Instant payments** — pay per request with USDC on BASE
- ✅ **No commitment** — use as much or as little as you need
- ✅ **Shared GPU inference** — access to KubeTEE NVIDIA NIM models
- ❌ No dedicated namespace or storage

> **Note**: Subscription tiers include 1 namespace and dedicated access to KubeTEE NVIDIA NIM models in TEE.

**Tier Details**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PRICING TIERS                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PAY-AS-YOU-GO (X.402 Protocol - No subscription)                          │
│  ────────────────────────────────────────────────                           │
│  ✅ Instant access via X.402 micropayments (USDC on BASE)                   │
│  ✅ No KYC required — permissionless for everyone                           │
│  ✅ Shared inference on KubeTEE NVIDIA NIM models                           │
│  ✅ Pay per request: $0.02/1K tokens, $2.00/GPU hour                        │
│  ❌ No dedicated namespace or storage                                       │
│  ❌ No custom fine-tuning                                                   │
│                                                                             │
│  ═══════════════════════════════════════════════════════════════════════    │
│                                                                             │
│  SUBSCRIPTION TIERS (dedicated resources):                                  │
│  ─────────────────────────────────────────                                  │
│  ✅ 1 dedicated namespace per user                                          │
│  ✅ Access to shared KubeTEE NVIDIA NIM/AIQ Blueprint models (TEE)          │
│  ✅ Shared inference on pre-trained models (Llama, Mistral, Nemotron, etc.) │
│                                                                             │
│  ═══════════════════════════════════════════════════════════════════════    │
│                                                                             │
│  BASIC ($499/month)                                                         │
│  ─────────────────                                                          │
│  ✅ RAG Blueprint with 50GB vector storage                                  │
│  ✅ RAG server on CPU (no dedicated GPU)                                    │
│  ✅ Shared inference on KubeTEE NVIDIA NIM models                           │
│  ✅ Community support                                                       │
│  ❌ No dedicated GPU                                                        │
│  ❌ No custom fine-tuning                                                   │
│                                                                             │
│  PROFESSIONAL ($1,499/month)                                                │
│  ────────────────────────────                                               │
│  ✅ RAG Blueprint with 100GB vector storage                                 │
│  ✅ 1× H200 GPU for RAG server (dedicated)                                  │
│  ✅ 1× H200 GPU for custom model inference (dedicated)                      │
│  ✅ Weekly custom model fine-tuning                                         │
│  ✅ Email support, 99.5% SLA                                                │
│  📊 Total: 2× H200 GPUs dedicated to your namespace                         │
│                                                                             │
│  ENTERPRISE ($4,999/month)                                                  │
│  ─────────────────────────                                                  │
│  ✅ RAG Blueprint with 500GB+ vector storage                                │
│  ✅ 1× H200 GPU for RAG server (dedicated)                                  │
│  ✅ 2× H200 GPU for custom model inference (dedicated, higher throughput)   │
│  ✅ Continuous fine-tuning (daily/on-demand)                                │
│  ✅ 24/7 priority support, 99.9% SLA                                        │
│  ✅ SSO/SAML, audit logs, custom integrations                               │
│  📊 Total: 3× H200 GPUs dedicated to your namespace                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    SHARED KUBETEE INFRASTRUCTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  All users share access to KubeTEE's NVIDIA NIM/AIQ Blueprint models        │
│  running in a secure TEE (Trusted Execution Environment):                   │
│                                                                             │
│  🔒 SHARED MODELS (TEE Protected):                                          │
│  ─────────────────────────────────                                          │
│  • nvidia/llama-3.1-nemotron-70b-instruct                                   │
│  • nvidia/llama-3.3-70b-instruct                                            │
│  • mistralai/mistral-large-2-instruct                                       │
│  • nvidia/nv-embedqa-e5-v5                                                  │
│  • nvidia/nv-rerankqa-mistral-4b-v3                                         │
│  • + More NIM models as they become available                               │
│                                                                             │
│  These models run on KubeTEE's shared H200 cluster with:                    │
│  • Hardware-enforced isolation (Intel TDX, NVIDIA CC)                       │
│  • No data persistence between requests                                     │
│  • Attestation-verified execution                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**GPU Pricing** (for additional usage beyond subscription):

| Resource | Unit | Price (USDC) |
|----------|------|--------------|
| **NVIDIA H200 GPU** | Per hour | **$2.00/hour** |
| Tokens Processed | Per 1K tokens | $0.02 |
| RAG Storage | Per GB/month | $0.03 |
| Embedding | Per 1K tokens | $0.01 |

**Professional Tier Value Calculation**:
- 2× H200 GPUs (730 hours/month each): 2 × 730 × $2.00 = **$2,920 value**
- 100GB RAG storage: 100 × $0.03 = **$3 value**
- Weekly fine-tuning (~4 hours/week × 4): 16 × $2.00 = **$32 value**
- **Total value: ~$2,955** → You pay **$1,499/month** (49% discount!) ✅

**Enterprise Tier Value Calculation**:
- 3× H200 GPUs (730 hours/month each): 3 × 730 × $2.00 = **$4,380 value**
- 500GB RAG storage: 500 × $0.03 = **$15 value**
- Continuous fine-tuning (~20 hours/week × 4): 80 × $2.00 = **$160 value**
- **Total value: ~$4,555** → You pay **$4,999/month** ✅

**Example Monthly Bills**:

| User Type | Subscription | Additional Usage | Total |
|-----------|--------------|------------------|-------|
| Basic user (light RAG) | $499 | — | **$499** |
| Basic user + tokens | $499 | 1M tokens ($20) | **$519** |
| Pro user (included) | $1,499 | — | **$1,499** |
| Pro user + extra GPU | $1,499 | 50 GPU-hours ($100) | **$1,599** |

**Referrer Revenue Share** (50% of all revenue):
- Referrers earn **50% of subscription + usage revenue** from referred users
- Basic subscriber: $499 × 50% = **$249.50/month per referral**
- Pro subscriber: $1,499 × 50% = **$749.50/month per referral**
- Enterprise subscriber: $4,999 × 50% = **$2,499.50/month per referral**

**Integration Options**:
- Bring Your Own LLM to KubeTEE with NeMo Microservices
  - NimCache
  - NimService
  - Private Microservices

**Distribution Strategy & Community Value**:

KubeTEE AI provides the Bittensor community with a **production-ready commodity service** that members can offer directly to their customers and integrate into enterprise environments. This creates significant value for the ecosystem:

- **Turnkey Enterprise AI**: Community members can resell or integrate KubeTEE's enterprise-grade AI as a Service without building infrastructure from scratch
- **Target Market**: System integrators, AI consultants, and solution providers within the Bittensor community and beyond
- **Revenue Opportunity**: Miners earn 50% of service revenue + emission rewards
- **Enterprise Adoption**: Provides Bittensor with a compliant, security-certified offering that meets enterprise requirements (FIPS-140-2, TEE, KYC)
- **Value Chain**: Miners provide infrastructure (earn 50% revenue) → Validators ensure quality → Community integrators deliver to end customers

This model transforms the Bittensor subnet from a purely mining-focused network into a **go-to-market channel** where community members can monetize their relationships and domain expertise by offering world-class AI infrastructure to their customer base.

### Multi-Chain Payment Strategy: BASE + Bittensor EVM

KubeTEE AI implements a **hybrid multi-chain payment architecture** optimized for different use cases:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KUBETEE MULTI-CHAIN PAYMENT STRATEGY                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     BITTENSOR NETWORK                               │   │
│   │                                                                     │   │
│   │   KubeTEE α Token ◄──AMM──► TAO                                    │   │
│   │         │                                                          │   │
│   │         ▼                                                          │   │
│   │   KubeTEEPayment.sol (Bittensor EVM)                               │   │
│   │   └── Reseller epoch settlements                                   │   │
│   │   └── B2B wholesale payments                                       │   │
│   │   └── Validator consensus                                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              │ Bridge (LayerZero/Wormhole)                  │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        BASE L2 (Coinbase)                           │   │
│   │                                                                     │   │
│   │   wKUBETEE (Wrapped) ──► Uniswap V3 / Aerodrome Liquidity          │   │
│   │         │                                                          │   │
│   │         ▼                                                          │   │
│   │   x402 Protocol Integration                                        │   │
│   │   └── HTTP 402 micropayments                                       │   │
│   │   └── AI agent autonomous payments                                 │   │
│   │   └── Per-request billing                                          │   │
│   │                                                                     │   │
│   │   ERC-8004 Agent Standard                                          │   │
│   │   └── Agent-to-agent discovery                                     │   │
│   │   └── Reputation and trust                                         │   │
│   │   └── Autonomous AI workflows                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why BASE for L2?**

| Factor | BASE Advantage |
|--------|----------------|
| **x402 Protocol** | Native support for HTTP micropayments (10.5M+ transactions) |
| **ERC-8004** | AI agent payment standard (Google A2A extended) |
| **Coinbase Users** | 100M+ direct access, no bridge friction |
| **DeFi TVL** | 46% of all L2 DeFi (~$4.6B) |
| **AI Ecosystem** | Virtuals, agent projects; AI x Crypto mindshare |
| **Gas Costs** | Sub-cent transactions for micropayments |

**Payment Model Comparison**:

| Model | Network | Best For | Settlement |
|-------|---------|----------|------------|
| **Emissions** | Bittensor Subnet | Miners (infra + code) | Per block |
| **Reseller Epoch** | Bittensor EVM | B2B wholesale | Per epoch |
| **x402 Micropay** | BASE L2 | AI agents, retail | Instant |
| **ERC-8004 Agents** | BASE L2 | AI-to-AI autonomous | Instant |

**Roadmap**:
1. ✅ Phase 1: Bittensor native emissions + reseller epoch payments
2. 🔜 Phase 2: Deploy wKTEE on BASE, Uniswap V3 liquidity
3. 🔜 Phase 3: x402 Protocol integration for API micropayments  
4. 🔜 Phase 4: ERC-8004 agent marketplace registration

Reference: [x402 Protocol](https://www.x402.org/) | [ERC-8004](https://www.erc8021.com/) | [BASE](https://base.org/)

### Automated Buyback & Burn (Deflationary Mechanism)

KubeTEE implements an **automated daily buyback and burn** mechanism that converts reseller USDC revenue to Alpha tokens and burns them, creating deflationary pressure.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DAILY BUYBACK & BURN FLOW                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [STEP 1] COLLECT USDC (BASE L2)                                          │
│   ─────────────────────────────────────────────────────────────────────    │
│   Reseller payments accumulate in KubeTEEReseller.sol                       │
│   Transferred to KubeTEEBuybackBurn.sol daily                               │
│                                    │                                        │
│                                    ▼                                        │
│   [STEP 2] SWAP USDC → wTAO (Chainlink Automation)                         │
│   ─────────────────────────────────────────────────────────────────────    │
│   Chainlink Keepers trigger daily at 00:00 UTC                              │
│   Swap via Uniswap V3 with 2% max slippage                                  │
│                                    │                                        │
│                                    ▼                                        │
│   [STEP 3] BRIDGE wTAO → TAO                                               │
│   ─────────────────────────────────────────────────────────────────────    │
│   Bridge wTAO from BASE to native TAO on Bittensor                          │
│                                    │                                        │
│                                    ▼                                        │
│   [STEP 4] SWAP TAO → ALPHA (Bittensor Bot)                                │
│   ─────────────────────────────────────────────────────────────────────    │
│   buyback_bot.py monitors TAO arrivals                                      │
│   Swaps TAO → Alpha via subnet native AMM                                   │
│                                    │                                        │
│                                    ▼                                        │
│   [STEP 5] 🔥 BURN ALPHA                                                    │
│   ─────────────────────────────────────────────────────────────────────    │
│   Send Alpha to burn address (unrecoverable):                               │
│   5C4hrfjw9DjXZTzV3MwzrrAr9P1MJhSrvWGWqi1eSuyUpnhM                        │
│                                                                             │
│   ════════════════════════════════════════════════════════════════════     │
│   RESULT: Deflationary pressure on Alpha token                              │
│   More reseller usage = More Alpha burned = Higher Alpha value              │
│   ════════════════════════════════════════════════════════════════════     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Automation Stack**:

| Component | Technology | Purpose |
|-----------|------------|---------|
| Daily trigger | Chainlink Automation | Decentralized, reliable scheduling |
| USDC→wTAO swap | Uniswap V3 (BASE) | Best liquidity, low slippage |
| Bridge | wTAO Bridge | Cross-chain transfer |
| TAO→Alpha swap | Bittensor AMM | Native subnet liquidity |
| Burn execution | buyback_bot.py | Off-chain monitoring & execution |

**Kubernetes Deployment (Fleet GitOps)**:

The buyback bot is deployed to Kubernetes using Fleet GitOps:

```
fleet-gitops/apps/buyback-bot/
├── fleet.yaml                    # Fleet configuration
├── manifests/
│   ├── namespace.yaml            # kubetee-system namespace
│   ├── configmap.yaml            # Bot configuration + script
│   ├── secret.yaml               # Wallet secrets (use ExternalSecrets!)
│   ├── deployment.yaml           # Bot deployment
│   ├── service.yaml              # Metrics service + ServiceMonitor
│   ├── grafana-dashboard.yaml    # Grafana dashboard
│   └── kustomization.yaml
└── overlays/
    └── staging/                  # Staging-specific config
```

**Deployment Steps**:

```bash
# 1. Create wallet for buyback operations
btcli wallet new_coldkey --wallet.name buyback
btcli wallet new_hotkey --wallet.name buyback --wallet.hotkey default

# 2. Store wallet in Vault (production)
vault kv put secret/kubetee/buyback-wallet \
  coldkey="$(cat ~/.bittensor/wallets/buyback/coldkey)" \
  coldkeypub="$(cat ~/.bittensor/wallets/buyback/coldkeypub)" \
  hotkey="$(cat ~/.bittensor/wallets/buyback/hotkeys/default)"

# 3. Update KUBETEE_NETUID in configmap.yaml
# 4. Commit and push - Fleet auto-deploys!

# 5. Monitor
kubectl logs -f -n kubetee-system deployment/buyback-bot
kubectl port-forward -n kubetee-system svc/buyback-bot 9090:9090
# View metrics at http://localhost:9090/metrics
```

**Prometheus Metrics**:

| Metric | Description |
|--------|-------------|
| `buyback_tao_balance` | Current TAO balance |
| `buyback_alpha_balance` | Current Alpha balance |
| `buyback_tao_swapped_total` | Total TAO swapped (counter) |
| `buyback_alpha_burned_total` | Total Alpha burned (counter) |
| `buyback_last_swap_timestamp` | Unix timestamp of last swap |
| `buyback_last_burn_timestamp` | Unix timestamp of last burn |

**Alerts** (via PrometheusRule):
- `BuybackBotNoSwaps` - No swaps in 48 hours
- `BuybackBotNoBurns` - No burns in 48 hours
- `BuybackBotHighRestarts` - Pod restarting frequently

**Configuration**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `minBuybackAmount` | $100 USDC | Minimum to trigger buyback |
| `maxSlippageBps` | 200 (2%) | Maximum swap slippage |
| `buybackInterval` | 24 hours | Time between buybacks |
| `MIN_TAO_THRESHOLD` | 0.1 TAO | Min TAO to trigger swap |
| `MIN_ALPHA_THRESHOLD` | 0.1 Alpha | Min Alpha to trigger burn |

### Validation & Scoring

**Infrastructure Validation**:
- Prometheus Metrics and Kubernetes Events
- UpTime monitoring
- Quality of Service (QoS) metrics
- Performance benchmarks

**Revenue Validation**:
- Service usage tracking per miner per user
- Token and GPU time accounting
- Revenue calculation per epoch
- 50% miner share calculation and distribution

**AI Agent Validation**:
- Benchmark performance on hidden test set
- Code quality assessment via AI Agent analysis
- CI/CD pipeline compliance
- Security vulnerability scans

---

## Client Getting Started

### Prerequisites

**Information Required**:
- Region (Americas, EU, Middle East, Africa, Asia)
- Organization Name (for SSL certificate)
- Customer WALLET.NAME, WALLET.HOTKEY

### Deployment Steps

Using the KubeTEE CLI (one command deployment):

1. **Create Hotkey**: Create Bittensor coldkey and hotkey
2. **Deposit Funds**: Deposit Alpha (TAO → Alpha) from customer coldkey to KubeTEE hotkey
3. **Setup Access**: Create username and password with Project/Namespace in Rancher UI
4. **Get Config**: Download the Kube Config file
5. **Deploy**: Deploy RAG and AIQ Helm charts with `username.kubetee.ai` for the frontend

---

## For Miners (Open Source Competition)

### Development Process

**Miners are incentivized to improve the Subnet Tech Stack and Blueprints**

1. **Create Repository**: Fork public repository on GitHub
2. **Register Coldkey/Hotkey to the subnet**: using Bittensor CLI (BTCLI)
3. **Register Repository**: Using KUBETEECTL to the miner hotkey
4. **CI/CD Setup**: Automated deployment when committed to the staging branch
5. **Code Analysis**: Pass AI Agent analysis for code compliance
6. **Security Checks**: Pass CI workflow for vulnerability & basic tests
7. **Staging Deploy**: Pass Staging deployment without errors
8. **Benchmarking**: Pass benchmarks and receive scoring

## For Miners (Infrastructure)

**Minimum For Staging Permissionless Participation**:

- ✅ INTEL TDX Compatible node with NVIDIA H100/H200
- ✅ BIOS TDX/SGX Enabled
- ✅ Kernel TDX/SGX Enabled
- ✅ RKE2 Rancher Kubernetes cluster
- ✅ One Cluster per Miner (labeled with `kubetee.ai/` prefixed labels)
- ✅ Same Regional deployment (Control Plane and Workers in same Region/Zone)
- ✅ Cluster registered with Rancher for Fleet management
- ✅ Cluster must be labeled with required labels:
  - `kubetee.ai/continent`, `kubetee.ai/country`, `kubetee.ai/city` (geographic identification)
  - `kubetee.ai/miner-hotkey`, `kubetee.ai/miner-coldkey` (permanent miner identification)
  - `kubetee.ai/miner-uid` (current UID, updateable)

**For Production Participation**:

- ✅ KYC compliance (for legal & regulatory requirements)
- ✅ Successfully passed Staging validation

---

## Evaluation & Benchmarks

### Primary Benchmark

[Deep Research Bench](https://github.com/Ayanami0730/deep_research_bench)

> [!IMPORTANT]  
> An evaluation benchmark dataset created by [NVIDIA NeMo Data Designer](https://docs.nvidia.com/nemo/microservices/latest/generate-synthetic-data/index.html) will not be available publicly and only accessible to validators in a TEE environment to ensure that the benchmark scoring cannot be gamed.

### Evaluation Criteria

Comprehensive evaluation across all deployment tiers with focus on:
- **Code Quality**: Clean, maintainable, and well-documented code
- **Benchmark Performance**: Scores on Deep Research Bench and additional benchmarks
- **Infrastructure Reliability**: Uptime, fault tolerance, disaster recovery
- **Security Compliance**: TEE validation, audit logs, vulnerability assessments
- **Service Quality Metrics**: Consistant benchmarks scores

### Additional Planned Benchmarks

- [ ] [ARC-AGI-3-Agents](https://github.com/KubeTEE-AI/ARC-AGI-3-Agents)
- [ ] [REKA Research Eval](https://github.com/KubeTEE-AI/research-eval)
- [ ] [YDC Deep Research Evals](https://github.com/KubeTEE-AI/ydc-deep-research-evals)
- [ ] [SN 22 Search Eval](https://github.com/KubeTEE-AI/ai-search-benchmark)
- [ ] [Perplexity Search Eval](https://github.com/KubeTEE-AI/search_evals)

---

## Roadmap

### Phase 1: Foundation (Current)

- [x] RKE2 Kubernetes cluster deployment
- [x] Linkerd mTLS
- [x] Rancher Fleet Multi-Cluster Management
  - [x] GitOps workflow setup
  - [x] Cluster registration automation
  - [x] Fleet GitRepo configurations
- [x] NeMo Microservices deployment
- [x] RAG Blueprint installation
  - [x] [CyborgDB](https://www.cyborg.co/) Vector Database for End-to-End Encrypted Confidential AI
  - [x] Ingest Data of all kinds
- [x] AIQ Agent Blueprint installation
- [x] NVIDIA Flywheel Blueprint installation
  - [x] Integrate NVIDIA Data Flywheel for autonomous model self-improvement via RL
- [ ] Implement the validator component
  - [ ] Container needs to be run in a TEE environment and workload validated
- [ ] Develop the KUBETEECTL CLI
- [ ] Build documentation website

### Phase 2: Launch

- [ ] Create slides for presentation
- [ ] Podcasts to raise awardness
- [ ] Monitor and stabilize subnet

#### Subnet 93 — Bitcast (Marketing & Awareness)

> *The Decentralized Creators Economy Powered by Bittensor*

Integration with [Bitcast](https://bitcast.network) for KubeTEE marketing and community awareness:

- [ ] Create educational content about KubeTEE's TEE infrastructure
- [ ] Produce video explainers on Confidential AI and secure model deployment
- [ ] Incentivize content creators to explain KubeTEE use cases
- [ ] Cross-subnet promotion for mainstream user onboarding
- [ ] Leverage Bitcast's no-GPU, login-level participation model for community growth

**Benefits**: Tap into Bitcast's decentralized content creator network to drive awareness, educate potential miners and resellers, and accelerate adoption without traditional marketing costs.

#### Subnet 16 — BitAds (Affiliate & Performance Marketing)

> *Decentralized Performance Marketing on Bittensor*

Integration with [BitAds](https://bitads.ai) for affiliate/referral marketing and performance-based advertising:

- [ ] Integrate BitAds for referrer/affiliate tracking and payouts
- [ ] Create KubeTEE advertising campaigns on decentralized ad network
- [ ] Track referral conversions via BitAds performance metrics
- [ ] Pay affiliates in Alpha tokens via BitAds infrastructure
- [ ] Cross-promote with other Bittensor subnets via BitAds network

**How It Connects to Referrer Model**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BITADS (SN16) INTEGRATION                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                     ┌─────────────────┐                │
│  │   BitAds        │                     │   KubeTEE       │                │
│  │   (SN16)        │ ◀────────────────── │   Referrers     │                │
│  │                 │                     │                 │                │
│  │ • Ad Campaigns  │                     │ • 50% Rev Share │                │
│  │ • Click Track   │ ──────────────────▶ │ • User Signup   │                │
│  │ • Conversions   │                     │ • Attribution   │                │
│  └─────────────────┘                     └─────────────────┘                │
│                                                                             │
│  Use Cases:                                                                 │
│  ──────────                                                                 │
│  1. Affiliate Links → BitAds tracks → KubeTEE signup → 50% revenue share   │
│  2. Ad Campaigns → BitAds network → New user acquisition                   │
│  3. Performance Metrics → Optimize referrer payouts                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Subnet 71 — LeadPoet (B2B Lead Intelligence)

> *Decentralized B2B Lead Data Intelligence on Bittensor*

Integration with [LeadPoet](https://leadpoet.com/) for B2B lead generation and intelligence:

- [ ] Integrate LeadPoet for enterprise lead identification
- [ ] Access decentralized B2B contact and company data
- [ ] Leverage AI-powered lead scoring and enrichment
- [ ] Target enterprise customers for KubeTEE AI services

**Benefits**: Tap into LeadPoet's decentralized B2B intelligence network to identify and qualify enterprise prospects for KubeTEE's confidential AI infrastructure services.

**Benefits**: 
- Decentralized affiliate tracking (no middleman)
- Performance-based payouts (pay for conversions, not impressions)
- Native Bittensor integration (Alpha token payouts)
- Cross-subnet visibility (reach other Bittensor communities)

### Phase 3: Enhancements

- [ ] MCP servers for community projects
- [ ] Add Tools and MCP servers
- [ ] Improve Design UI interface for chatting with AI agent to launch AI Agents

### Phase 4: Expansion

- [ ] Expand benchmark suites
- [ ] Scale to additional regions

#### Subnet 22 — Desearch (Decentralized Web Search)

> *AI-powered decentralized search with real-time access to X, Reddit, Arxiv, and the web*

Integration with [Desearch](https://desearch.ai) to replace Tavily and other centralized web search APIs:

- [ ] Replace Tavily API with Desearch for Deep Research web searches
- [ ] Integrate real-time X (Twitter) search for current events research
- [ ] Add Reddit search for community insights and discussions
- [ ] Enable Arxiv search for academic paper retrieval
- [ ] Use Desearch's Rizzy Agent for automated research workflows

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DESEARCH (SN22) INTEGRATION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CURRENT: Centralized Search APIs                                           │
│  ─────────────────────────────────                                          │
│  Deep Research Agent → Tavily API → Web Results                             │
│                      → Google API → Web Results                             │
│                                                                             │
│  FUTURE: Decentralized Desearch (SN22)                                      │
│  ─────────────────────────────────────                                      │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │   KubeTEE       │    │    Desearch     │    │   Data Sources  │          │
│  │   Deep Research │───▶│     (SN22)      │───▶│                 │          │
│  │                 │    │                 │    │ • Web crawl     │          │
│  │ Research query  │    │ • AI-powered    │    │ • X/Twitter     │          │
│  │ Agent workflow  │    │ • Real-time     │    │ • Reddit        │          │
│  │                 │    │ • Decentralized │    │ • Arxiv papers  │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘          │
│                                                                             │
│  Benefits vs Tavily/Google:                                                 │
│  ─────────────────────────                                                  │
│  • Decentralized (no single point of failure/censorship)                   │
│  • Native Bittensor (pay in TAO/Alpha, not USD)                            │
│  • Real-time social data (X, Reddit integration)                           │
│  • Academic focus (Arxiv integration)                                      │
│  • AI-powered ranking (not just keyword matching)                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Rizzy Agent Integration**:
Desearch's Rizzy Agent can power automated research workflows, potentially enhancing KubeTEE's Deep Research capabilities with live AI agents.

#### Subnet 60 — Bitsec (Security Scanning)

> *AI-powered vulnerability detection for blockchain and code security*

Integration with [Bitsec](https://bitsec.ai) for decentralized security scanning of bounty submissions:

- [x] Integrate Bitsec API for automated code security analysis
- [x] Add BitsecSecurityScanner to bounty validation pipeline
- [ ] Enable subnet-to-subnet synapse communication for security scans
- [ ] Implement continuous security monitoring for deployed code
- [ ] Cross-subnet security attestation

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Bitsec (SN60) Integration                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌─────────────────┐    ┌──────────────────┐    │
│  │   Bounty    │    │    Bitsec       │    │   Validation     │    │
│  │ Submission  │───▶│    (SN60)       │───▶│    Result        │    │
│  │             │    │                 │    │                  │    │
│  │  PR Code    │    │ AI Vulnerability│    │ PASS: 0 critical │    │
│  │   Diff      │    │   Detection     │    │ FAIL: issues     │    │
│  └─────────────┘    └─────────────────┘    └──────────────────┘    │
│                                                                     │
│  Security Levels:                                                   │
│  • Critical: Immediate rejection                                   │
│  • High: Immediate rejection                                       │
│  • Medium: Warning, manual review option                           │
│  • Low: Informational, auto-approve allowed                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Benefits**: Decentralized security auditing, AI-powered vulnerability detection, no single point of failure, native Bittensor integration.

### Phase 5: Subnet Integrations

#### Subnet 20 — Bounty Hunter (Decentralized Bounty Infrastructure)

> *Decentralized bounty and task completion network on Bittensor*

Explore integration with Bounty Hunter (SN20) to enhance or replace our GitHub Issues-based bounty system:

- [ ] Evaluate Bounty Hunter's task distribution and reward mechanisms
- [ ] Explore cross-subnet bounty posting for KubeTEE open source tasks
- [ ] Integrate bounty verification and payout infrastructure
- [ ] Potential migration from GitHub Issues to decentralized bounty platform
- [ ] Cross-subnet bounty discovery (attract contributors from other subnets)

**Potential Architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BOUNTY HUNTER (SN20) INTEGRATION                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CURRENT: GitHub Issues + Emissions                                         │
│  ─────────────────────────────────                                          │
│  GitHub Issue → Bounty Hotkey → Emissions Accumulate → Winner Paid          │
│                                                                             │
│  POTENTIAL: Bounty Hunter Integration                                       │
│  ────────────────────────────────────                                       │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │   KubeTEE       │    │  Bounty Hunter  │    │   Contributor   │          │
│  │   Bounties      │───▶│     (SN20)      │◀───│   Discovery     │          │
│  │                 │    │                 │    │                 │          │
│  │ Post tasks      │    │ • Task matching │    │ Find bounties   │          │
│  │ Define rewards  │    │ • Verification  │    │ from across     │          │
│  │ Set criteria    │    │ • Payout mgmt   │    │ Bittensor       │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘          │
│                                                                             │
│  Benefits:                                                                  │
│  • Decentralized bounty discovery (beyond just GitHub watchers)            │
│  • Cross-subnet contributor pool                                           │
│  • Native Bittensor payout infrastructure                                  │
│  • Potential for AI-powered task matching                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Exploration Areas**:
- How does SN20 handle bounty verification vs our AI + CI/CD approach?
- Can we post KubeTEE bounties to SN20 for broader visibility?
- Hybrid model: GitHub Issues for transparency + SN20 for discovery?

#### Subnet 3 — Templar (Model Pre-Training)

> *Decentralized pre-training of foundation models using distributed compute*

Integration with [Templar](https://github.com/templar-ai) to create custom models that outperform or replace NVIDIA Llama3.3 Nemotron 49B Super V1.5:

- [ ] Evaluate Templar's Gauntlet incentive mechanism for KubeTEE model training
- [ ] Pre-train custom Deep Research model optimized for KubeTEE use cases
- [ ] Create TEE-native model variants with security attestation built-in
- [ ] Collaborate with Templar + Gradients for end-to-end training pipeline
- [ ] Deploy custom Covenant-style models as alternatives to NVIDIA NIM

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CUSTOM MODEL TRAINING PIPELINE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐              │
│  │   Templar   │    │    Gradients    │    │    KubeTEE      │              │
│  │   (SN3)     │───▶│     (SN56)      │───▶│  TEE Deployment │              │
│  │             │    │                 │    │                 │              │
│  │ Pre-train   │    │  Fine-tune      │    │ Secure          │              │
│  │ 72B+ Model  │    │  for KubeTEE    │    │ Inference       │              │
│  └─────────────┘    └─────────────────┘    └─────────────────┘              │
│                                                                             │
│  Target Models:                                                             │
│  ─────────────                                                              │
│  1. KubeTEE-Research-72B     → Outperform Nemotron 49B on DeepResearch     │
│  2. KubeTEE-Agent-7B         → Optimized agent model for tool use          │
│  3. KubeTEE-RAG-13B          → Specialized RAG/retrieval model             │
│  4. Customer Fine-Tuned      → Custom models for enterprise clients        │
│                                                                             │
│  Benefits vs NVIDIA NIM:                                                    │
│  ───────────────────────                                                    │
│  • No vendor lock-in (decentralized training)                              │
│  • Lower cost (distributed compute)                                        │
│  • TEE-native security (attestation from training to inference)            │
│  • Custom optimization (not generic pre-trained weights)                   │
│  • Open source (community can verify and contribute)                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Templar's Gauntlet Mechanism**:
- Distributed participants submit gradient updates
- Two-stage filtering: statistical analysis + performance validation
- Permissionless: anyone can join by providing compute
- Compensation proportional to contribution quality

**Collaboration Pipeline** (Templar + Gradients + KubeTEE):
1. **Templar (SN3)**: Pre-train base model from scratch (e.g., 72B parameters)
2. **Gradients (SN56)**: Post-training fine-tuning for KubeTEE use cases
3. **KubeTEE**: TEE validation + deployment + inference

#### Subnet 37 — Aurelius (AI Alignment & Safety)

> *Decentralized protocol for surfacing and verifying alignment failures in LLMs*

Explore integration with [Aurelius](https://aurelius.ai) for AI safety verification and red-teaming of KubeTEE models:

- [ ] Integrate Aurelius for adversarial testing of KubeTEE Deep Research models
- [ ] Use Aurelius to verify alignment of custom fine-tuned models
- [ ] Generate structured safety datasets for model improvement
- [ ] Red-team models before production deployment
- [ ] Continuous alignment monitoring for deployed agents

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AURELIUS (SN37) INTEGRATION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │   KubeTEE       │    │    Aurelius     │    │   Safety        │          │
│  │   Models        │───▶│     (SN37)      │───▶│   Report        │          │
│  │                 │    │                 │    │                 │          │
│  │ • Research-72B  │    │ • Adversarial   │    │ • Alignment     │          │
│  │ • Agent-7B      │    │   prompts       │    │   failures      │          │
│  │ • RAG-13B       │    │ • Red-teaming   │    │ • Safety score  │          │
│  │ • Custom models │    │ • Interpretabil │    │ • Improvement   │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘          │
│                                                                             │
│  Use Cases:                                                                 │
│  ──────────                                                                 │
│  1. Pre-deployment: Verify model alignment before production               │
│  2. Continuous: Monitor deployed models for alignment drift                │
│  3. Fine-tuning: Generate datasets to improve model safety                 │
│  4. Audit: Provide alignment attestation for enterprise clients            │
│                                                                             │
│  Aurelius Components:                                                       │
│  • Miners (Prompters): Generate adversarial prompts                        │
│  • Validators (Auditors): Verify and score outputs                         │
│  • Tribunate: Dynamic rules layer for evaluation                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Benefits**:
- 🛡️ **Decentralized red-teaming** — No single point of bias
- 📊 **Structured datasets** — Reproducible alignment artifacts
- 🔍 **Interpretability** — Understand why models fail
- ✅ **Safety attestation** — Prove model alignment to clients

#### Subnet 56 — Gradients (Decentralized Fine-Tuning)

> *Simplifying AI training, making it accessible to all through Bittensor's decentralized network*

Integration with [Gradients](https://gradients.ai) to replace NVIDIA NeMo microservices with decentralized TEE-based fine-tuning:

- [ ] Evaluate Gradients for on-demand gradient computation within TEE environments
- [ ] Replace centralized NVIDIA fine-tuning microservice with Gradients subnet
- [ ] Implement secure model fine-tuning pipeline using Gradients + KubeTEE TEE
- [ ] Enable privacy-preserving model customization for enterprise clients
- [ ] Cross-subnet orchestration for training → deployment workflow

**Architecture Vision**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Decentralized AI Pipeline                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌─────────────────┐    ┌──────────────────┐    │
│  │  Gradients  │    │    KubeTEE      │    │   Deployment     │    │
│  │   (SN56)    │───▶│  TEE Validation │───▶│   & Inference    │    │
│  │             │    │                 │    │                  │    │
│  │ Fine-Tuning │    │ Secure Training │    │ Production AI    │    │
│  │ Computation │    │  Attestation    │    │   Services       │    │
│  └─────────────┘    └─────────────────┘    └──────────────────┘    │
│                                                                     │
│  Benefits:                                                          │
│  • No NVIDIA vendor lock-in for fine-tuning                        │
│  • Decentralized compute for cost efficiency                       │
│  • TEE attestation ensures training integrity                      │
│  • Privacy-preserving: data never leaves TEE                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Benefits**: Eliminate dependency on centralized NVIDIA microservices, reduce costs through decentralized compute, maintain security via TEE attestation throughout the training pipeline.

---

#### Data-Focused Subnets

These subnets provide critical datasets for fine-tuning and pre-training the AIQ Deep Research agent:

##### Subnet 13 — Data Universe (Macrocosmos) ⭐ CRITICAL

> *World's largest open social dataset—55B+ rows of real-time social and web content*

Integration with [Data Universe](https://www.macrocosmos.ai/sn13) for real-time grounding data:

- [ ] Integrate Gravity API for on-demand social data scraping
- [ ] Use 55B+ row HuggingFace dataset for pre-training grounding
- [ ] Real-time X/Twitter, Reddit feeds for research agent context
- [ ] MCP integration for Claude-compatible data pipelines
- [ ] Prevent research agent hallucination via current events grounding

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATA UNIVERSE (SN13) INTEGRATION                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │   Gravity API   │    │  55B+ Dataset   │    │   KubeTEE AI    │          │
│  │                 │    │  (HuggingFace)  │    │                 │          │
│  │ • Real-time     │    │ • X/Twitter     │    │ • Grounding     │          │
│  │   scraping      │───▶│ • Reddit        │───▶│   Layer         │          │
│  │ • On-demand     │    │ • Web content   │    │ • RAG context   │          │
│  │   queries       │    │ • Sentiment     │    │ • Fine-tuning   │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘          │
│                                                                             │
│  Why Critical:                                                              │
│  • Prevents hallucination via real-time grounding                          │
│  • Largest open social dataset in the world                                │
│  • MCP integration for Claude compatibility                                │
│  • Macrocosmos ecosystem synergy (pairs with SN01 Apex)                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

##### Subnet 52 — Dojo (Tensorplex)

> *Community-generated multi-modal AI training data with human validation*

Integration with [Dojo](https://tensorplex.ai) for high-quality training samples:

- [ ] Integrate Dojo for human-validated training data generation
- [ ] Crowdsource training samples for KubeTEE-specific use cases
- [ ] Multi-modal data collection (text, image, structured)
- [ ] Quality assurance via community validation
- [ ] Generate domain-specific training datasets for enterprise clients

**Use Cases**:
- Generate high-quality Q&A pairs for research agent fine-tuning
- Collect human preferences for RLHF alignment
- Validate AI outputs via community consensus

##### Subnet 54 — MIID (Synthetic Identities)

> *Synthetic identity generation for compliance testing and security validation*

Integration with MIID for secure compliance testing:

- [ ] Generate synthetic identities for KYC/AML testing
- [ ] Privacy-preserving test data for enterprise demos
- [ ] Compliance testing without real user data exposure
- [ ] Security validation using synthetic attack vectors
- [ ] TEE-protected synthetic data generation

**Why Important**:
- Enterprise clients need compliance testing without real data risk
- Synthetic identities enable realistic but safe security audits
- Pairs with TEE for privacy-preserving compliance workflows

##### Subnet 75 — Hippius (Decentralized Cloud Storage)

> *Decentralized storage infrastructure for AI datasets and model artifacts*

Integration with [Hippius](https://hippius.com) for decentralized storage:

- [ ] Store large training datasets (55B+ rows) on decentralized storage
- [ ] Model checkpoint storage with content-addressable retrieval
- [ ] Reduce centralized cloud storage dependency (S3, GCS)
- [ ] Geographic distribution for latency optimization
- [ ] Immutable storage for model versioning and audit trails

**Architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HIPPIUS (SN75) INTEGRATION                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │   Training      │    │    Hippius      │    │   Deployment    │          │
│  │   Datasets      │    │    (SN75)       │    │   Retrieval     │          │
│  │                 │    │                 │    │                 │          │
│  │ • SN13 social   │───▶│ • Decentralized │───▶│ • Model         │          │
│  │ • SN52 Dojo     │    │ • Immutable     │    │   checkpoints   │          │
│  │ • Embeddings    │    │ • Geo-dist      │    │ • Embeddings    │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

#### Financial & Trading Subnets

These subnets provide specialized financial data and analytics for enterprise research capabilities:

##### Subnet 15 — BitQuant (DeFi Analytics)

> *Decentralized DeFi analysis with sensitive market data protection*

Integration with BitQuant for financial research capabilities:

- [ ] Integrate BitQuant for DeFi/crypto market analysis
- [ ] Sensitive market data processing within TEE
- [ ] Financial research agent fine-tuning data
- [ ] Real-time trading signal analysis
- [ ] Privacy-preserving quant strategies in TEE

**TEE Synergy**:
- Market data and trading signals protected in TEE
- Quant strategies remain confidential during execution
- Compliance-friendly financial AI with attestation

##### Subnet 79 — τaos (Financial Market Simulation)

> *Financial market simulation with model IP protection*

Integration with τaos for advanced financial modeling:

- [ ] Financial market simulation for research agent training
- [ ] Model IP protection via TEE-based inference
- [ ] Backtesting frameworks for financial strategies
- [ ] Synthetic market data generation
- [ ] Risk modeling with confidential compute

**Use Cases**:
- Train research agents on financial scenarios
- Protect proprietary trading models during inference
- Generate synthetic market data for fine-tuning

---

### AIQ Deep Research Agent — Subnet Data Pipeline

The following diagram shows how data-focused subnets feed into the AIQ Deep Research Agent:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AIQ DEEP RESEARCH AGENT                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐    ┌──────────────────────────────────────────────┐  │
│  │  REASONING CORE  │◄───│  SN01 Apex (agentic traces)                  │  │
│  │  (Fine-tuned LLM)│◄───│  SN03 Templar (pre-training)                 │  │
│  └────────┬─────────┘    │  SN56 Gradients (fine-tuning)                │  │
│           │              └──────────────────────────────────────────────┘  │
│           │                                                                 │
│  ┌────────▼─────────┐    ┌──────────────────────────────────────────────┐  │
│  │  GROUNDING LAYER │◄───│  SN13 Data Universe (55B social posts)       │  │
│  │  (RAG + Vector)  │◄───│  SN22 Desearch (summarized web data)         │  │
│  └────────┬─────────┘    │  SN52 Dojo (human-validated samples)         │  │
│           │              └──────────────────────────────────────────────┘  │
│           │                                                                 │
│  ┌────────▼─────────┐    ┌──────────────────────────────────────────────┐  │
│  │  VERIFICATION    │◄───│  SN37 Aurelius (alignment safety)            │  │
│  │  (Safety layer)  │◄───│  SN60 Bitsec (security scanning)             │  │
│  └────────┬─────────┘    └──────────────────────────────────────────────┘  │
│           │                                                                 │
│  ┌────────▼─────────┐    ┌──────────────────────────────────────────────┐  │
│  │  STORAGE LAYER   │◄───│  SN75 Hippius (decentralized storage)        │  │
│  └────────┬─────────┘    └──────────────────────────────────────────────┘  │
│           │                                                                 │
│  ┌────────▼─────────┐    ┌──────────────────────────────────────────────┐  │
│  │  FINANCIAL INTEL │◄───│  SN15 BitQuant (DeFi analysis)               │  │
│  │  (Domain-specific│◄───│  SN79 τaos (market simulation)               │  │
│  │   research)      │    └──────────────────────────────────────────────┘  │
│  └──────────────────┘                                                       │
│                                                                             │
│           ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼ ▼                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │              KubeTEE AI / dStack TEE (Intel TDX)                     │  │
│  │         Confidential Training → Inference → Deployment              │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Research & Documentation

### Deep Research Reports

We leverage cutting-edge AI research agents to continuously improve our architecture:

- **[Grok xAI Deep Research Report](./docs/Grok_XAI_Research.md)**  
  Analysis of gaps and opportunities in the Bittensor ecosystem, market trends, and competitive landscape

- **[Claude Deep Research Project Architecture Report](./docs/Claude_Deep_Research.md)**  
  Comprehensive architectural analysis and recommendations for the KubeTEE subnet

### Community & Support

- **GitHub**: [KubeTEE-AI-Blueprints](https://github.com/KubeTEE-AI-Blueprints)
- **Documentation**: [docs/](./docs/)
- **Discord**: Coming soon
- **Twitter**: Coming soon

---

## License

See [LICENSE](LICENSE) for details.

---

**Built with ❤️ by the KubeTEE Community**

*Empowering Bittensor decentralized AI with enterprise-grade security and performance*