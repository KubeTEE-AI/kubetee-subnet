# NVIDIA NeMo Platform, Bittensor Subnet Integrations & the Stage 0 Security Gate

This public reference complements the [NVIDIA NeMo & Bittensor Subnet Integrations](../README.md#nvidia-nemo-platform--bittensor-subnet-integrations) overview. It explains the intended architecture, trust boundaries, and partnership candidates. Deployment settings, implementation checklists, and operational procedures belong in internal engineering documentation.

---

## 1. NVIDIA NeMo Platform on KubeTEE

[NVIDIA NeMo Platform](https://docs.nvidia.com/nemo-platform/documentation/kubernetes-deployment/setup) provides self-managed Kubernetes capabilities for customizing, evaluating, and securing LLM and agent applications. It carries forward the former standalone NeMo Microservices suite; Customizer, Evaluator, Guardrails, and Retriever remain useful capability categories. [NVIDIA NIM](https://docs.nvidia.com/nim/) supplies model inference and is a separate serving layer.

KubeTEE's objective is to combine these capabilities with independently developed AI services inside confidential clusters. Shared services can support multiple customer workloads, while transient jobs perform specific training, evaluation, or retrieval tasks. The goal is a broader confidential AI service portfolio—not presumed compatibility with every upstream component.

A key design principle is service locality: workloads should access supporting services within the same trust domain rather than crossing the public internet unnecessarily. Persistent services and short-lived jobs therefore play complementary roles.

---

## 2. Attestation-Gated Confidential Communication

Confidential workloads require protection against a potentially untrusted host operator, not only network interception. Standard workload certificates or host-managed tunnels alone cannot establish that the correct software is running inside genuine confidential hardware.

KubeTEE's trust model combines remote attestation with service credentials issued only to approved workloads. Confidential inference can then establish protected communication with its approved peers. Encrypted memory protects sensitive processing, while attestation provides evidence of the execution environment.

This distinction matters for customers:

- **Identity alone is insufficient.** A valid service account or ordinary workload certificate does not prove execution inside the expected confidential environment.
- **Host-managed encryption is insufficient.** An encrypted connection can still terminate in an environment controlled by the operator being excluded.
- **Attestation supports workload integrity.** Approved measurements and policies determine whether credentials should be released.
- **Credentials should not expose confidential processing.** Secrets and decrypted content must remain within the documented trust boundary.

The architectural pattern is service-to-service protection based on attested workload identity. See [East-west attested mTLS](./EAST-WEST-ATTESTED-MTLS.md) for the implementation design.

---

## 3. NVIDIA Kata and Confidential-Computing Compatibility

NVIDIA and Kata Containers provide multiple sandboxing technologies, but a VM sandbox is not automatically a confidential virtual machine. Deployment suitability depends on hardware-backed memory protection, attestation, GPU support, and the maturity of the specific integration path.

KubeTEE evaluates each NVIDIA component independently. Support for a particular runtime or NIM deployment method must not be generalized into support for all NeMo services.

The public compatibility principles are:

- Preserve hardware-backed confidentiality rather than accepting VM isolation alone.
- Verify GPU and storage behavior under the intended confidential runtime.
- Treat preview integration paths as evaluation work, not production guarantees.
- Deploy only after the particular service, runtime, and attestation policy pass acceptance testing.

The relevant upstream references are the [NIM Operator](https://docs.nvidia.com/nim-operator/latest/), its [Kata Sandbox documentation](https://docs.nvidia.com/nim-operator/latest/kata-sandbox.html), and the [NVIDIA Confidential Containers reference architecture](https://docs.nvidia.com/datacenter/cloud-native/confidential-containers/latest/overview.html).

---

## 4. Ecosystem Capabilities

The Bittensor ecosystem offers competing implementations of capabilities that can complement the AI stack. KubeTEE evaluates them as potential partners or technology sources—not as drop-in NeMo replacements by virtue of their category.

Candidate areas include:

| Capability | Example subnet | Proposed contribution |
|---|---|---|
| Fine-tuning | [Gradients SN56](https://www.gradients.io/) | Open, competitive model-customization methods |
| Reinforcement learning and reasoning | [Affine SN120](https://www.affine.io/) | Competitive production and evaluation of reasoning models |
| Search and grounding | [Desearch SN22](https://desearch.ai/) | Real-time web and social-information discovery for agents |
| Knowledge-enhanced retrieval | *Candidate to be determined* | Graph-supported retrieval for cross-document reasoning |
| Video understanding | [Score SN44](https://github.com/score-technologies/turbovision) | Structured visual analysis suitable for searchable video workflows |
| Inference and training | [Chutes SN64](https://chutes.ai/) | Decentralized inference and training capacity, including confidential workloads |
| Confidential storage | [Hippius SN75](https://hippius.com/) | Durable storage for approved confidential workloads |
| Safety and alignment detection | [Trishool SN23](https://github.com/TrishoolAI/trishool-phase2) | Detection capabilities for policy, safety, and alignment evaluation |
| Security hardening | [RedTeam SN61](https://github.com/RedTeamSubnet/RedTeam) | Challenge-derived methods and evaluation material for security defenses |

These are partnership proposals rather than shipping integrations. Compatibility with confidential execution must be evaluated for each specific service. An attested evaluation process does not itself attest an external production service, and an external API must not silently enlarge the trust boundary of a confidential workload.

---

## 5. The Bittensor Subnet-NeMo Mapping

Given the capabilities above, each NeMo service and supporting AI capability has one or more Bittensor subnet candidates whose work could complement it inside a TEE. These are partnership and integration proposals—not drop-in replacements or shipping integrations. Compatibility, confidential execution, and current service availability must be assessed individually for every candidate.

| Subnet | Project & what it produces | SOTA value | Replaces / augments | Integration fit (inside KubeTEE TEE) |
|---|---|---|---|---|
| — → SN70 | [NVIDIA NeMo Switchyard](https://github.com/NVIDIA-NeMo/Switchyard) → **potential replacement: [Fugal](https://www.fugalai.com/)** | Switchyard supplies routing algorithms that select efficient or capable models using request and tool-execution context. Fugal supplies trained, hardware-attested LLM router heads (benchmarked by miners inside Intel TDX VMs) | Model-selection strategy for the LiteLLM gateway; **Fugal earns the replacement only by proving SOTA head-to-head against Switchyard** | Evaluate Switchyard's tool-aware strategy as the baseline against Fugal and fixed efficient/capable models. Fugal is also a potential confidential-evaluation partner; its TDX proofs cover benchmark execution, not automatic confidentiality of production requests |
| SN92 | [REAX](https://reax.co/) — Decision Models | Independently verified decision models for prompt-complexity and task-type classification | Prompt-oriented model routing across configurable task tiers | Evaluate a JEV-compatible classifier as an explicit routing option; its decision output selects a KubeTEE model for confidential inference |
| SN11 | [TrajectoryRL](https://trajrl.com/) | Competition-produced agent skills alongside programs that combine models into fusion policies | Agent skills for the planned Hub; candidate model-selection methods | Select individual skills after artifact, license, security, and compatibility review; executable miner policies remain separate from ordinary Hub skill packages |
| SN121 | [sundae_bar](https://www.sundaebar.ai/) | Business-workflow skill bundles evaluated on fixed-base agents across multiple scenarios | Agent skills for the planned Hub | Review selected enterprise skills and their evaluation results against KubeTEE models and agents before publication through the planned Hub |
| SN56 | [Gradients](https://www.gradients.io/) | AutoML tournaments for LLM fine-tuning (open-source SFT/DPO/GRPO scripts, decentralized judge network, held-out eval) | NeMo Customizer (fine-tuning service) | Fine-tune jobs run inside the TEE; the winning checkpoint's weights + eval scores are attested artifacts — "models trained by the network, on confidential data" |
| SN120 | [Affine](https://www.affine.io/) | Incentivized RL / verifiable post-training — "reason mining": challenger-vs-champion model duels, pruning challenger scores with environmental verification | NeMo Customizer (RL/DPO path) + NeMo Evaluator (model-vs-model evaluation) | RL training runs in TEE; duels produce verifiable quality deltas rather than reputation — an always-current SOTA reasoning-model lane |
| SN22 | [Desearch](https://desearch.ai/) | Decentralized web + X/Twitter search for AI agents (bitAgent web-search subnet: indexed live web + Twitter firehose, structured search API) | NeMo Retriever (information retrieval) + AI-Q Research Agent (online lookups) | Retrieval-augmented pre-pass: Desearch API calls run as a confidential web/X lookup inside the TEE before generation |
| — | *Candidate TBD* | **GraphRAG** — knowledge-graph-enhanced retrieval: entities/relations are extracted into a graph over ingested corpora, queries traverse multi-hop reasoning paths (not just vector similarity), and answers are synthesized with citations; validators score retrieval accuracy and answer quality | NeMo Retriever / RAG | Graph build + multi-hop retrieval + generation run inside the TEE; the knowledge graph, retrieved paths, and citations stay in the enclave |
| SN44 | [Score](https://github.com/score-technologies/turbovision) (TurboVision) | Decentralized computer vision — miners run CV models (object detection, keypoint detection, tracking) on live video/imagery and return structured, decision-ready annotations; validators benchmark on live data via lightweight hybrid validation (frame filtering, keypoint + homography checks, CLIP-based semantic verification). First deployment: Game State Recognition for football; generalizes to other camera feeds | NVIDIA Video Search and Summarization blueprint (video analytics / structured video understanding) | CV inference + validation run inside KubeTEE TEE pods → confidential video analytics with attested structured outputs; sensitive footage stays in the enclave |
| SN28 | [sayGM](https://saygm.com/) | Idle-capacity inference marketplace; KubeTEE miner SKUs forward to `llm.kubetee.ai`. Connected as a LiteLLM **inference provider** (same `model` names on the gateway) | Inference (provider + demand channel) | Inbound path is live (TDX + NVIDIA CC). LiteLLM HA fallbacks go to other TEE networks (Chutes, Phala, Near AI) — not back through sayGM |
| SN64 | [Chutes](https://chutes.ai/) — Parallax (Jon Durbin) | Decentralized serverless inference + **Parallax** decentralized MoE training (surrogate experts, ternary weights, Gated DeltaNet) across heterogeneous, non-colocated GPUs | Inference + distributed training; **LiteLLM TEE fallback** | Chutes already runs a **fully TEE-only infrastructure stack**; Parallax trains frontier models on distributed confidential compute — a native fit for KubeTEE's decentralized TEE clusters and a fallback when in-cluster TEE is down |
| SN75 | [Hippius](https://hippius.com/) | Decentralized cloud storage — S3-compatible + IPFS pinning; Arion engine (Reed-Solomon, CRUSH placement, self-healing) | Persistent storage (solves CoCo's **ephemeral-data-only** limitation) | **Already ships Confidential Compute** (AMD SEV-SNP encrypted VMs); drop-in S3 endpoint for approved confidential workloads |
| SN23 | [Trishool](https://github.com/TrishoolAI/trishool-phase2) | AI guardrail models & alignment audits — Input Guard / Output Guard for LLM endpoints, the Halo classifier, HaloGuard EU, and the Petri alignment-auditing agent | NeMo Guardrails (input/output rails, jailbreak + injection detection, content moderation) | Evaluate the detector stack as independent trained classifiers running as TEE rail services; every verdict carries the attested detector identity (model/policy measurement) |
| SN61 | [RedTeam](https://github.com/RedTeamSubnet/RedTeam) | Subnet-owner product distilled from the CTF challenges (detection, exploitation, mitigation) — the protection/detection software the team derives from what the competitions surface, plus the challenge-derived exploit/jailbreak corpus | NeMo Guardrails (custom rails) + evaluation (adversarial testing) | Evaluate the owner product as versioned rail releases in TEE and use suitable challenge material for adversarial testing; no need to evaluate individual miners or submissions |

The routing and Agent Skills Hub capabilities above are **planned**, not customer-facing availability announcements. KubeTEE will announce availability once gateway compatibility, client integration, confidential-service acceptance testing, and supply review are complete.

**Agent Skills Hub availability:** selected hub packages will be independently reviewed for compatibility, security, attribution, and usefulness; no subnet marketplace will be imported wholesale. As of November 15, 2026, SN11 currently burns miner emissions and SN121 pauses competition rewards between Challenges. Both require current artifact and supply verification before dependency or production claims.

**Guardrails track (active proposal):** the SN23 and SN61 rows above are more than generic ecosystem candidates — a dedicated proposal evaluates both detector stacks inside KubeTEE TEEs as the **NeMo Guardrails detector layer in front of LiteLLM**. The full rail-orchestration and detector pipeline would run inside a confidential workload, with attested confidential communication between LiteLLM and the rail services. No ordinary operator-issued workload certificate would establish this trust boundary. The integration remains an engineering proposal, not a shipping guardrail service, and it does not replace the existing LiteLLM gateway protections until independent security and streaming validation is complete.

**Agent routing versus guardrails:** the Switchyard, REAX, and Fugal rows above are model-selection candidates; the SN23 and SN61 track is a separate input/output safety and security pipeline. Neither should be described as the other.

KubeTEE treats this as an **open set**: any Bittensor subnet with a SOTA, verifiable solution for a NeMo stack layer — data, training, retrieval, inference, storage, guardrails, or evaluation — is a potential partnership and candidate integration, with suitable workloads adapted to run inside TEE and outputs attested and persisted on approved confidential storage. This is the Bittensor-native path to a confidential AI Factory that is **not locked to a single vendor's experimental stack**.

---

## 6. Stage 0 — Supply-Chain Security Gate

> **Status: design reference (manual/advisory practice).** The following describes supply-chain security, not a staging promotion workflow. See [Deploying in a TEE](./TEE-DEPLOYMENT-AND-CICD.md#supply-chain-ci).

Before an AI service or third-party agent capability enters a confidential environment, review both its artifacts and its supply chain. Confidential execution protects data during approved processing; it does not make untrusted code safe.

The review covers:

- source and dependency security;
- container and artifact integrity;
- infrastructure and deployment-policy safety;
- secrets handling and attestation requirements;
- behavioral evaluation against the intended workload.

New artifacts or substantive changes require renewed evaluation. Production policy does not waive a failing security gate. Review infrastructure must not receive confidential production content merely to scan public or build-time artifacts.

---

## Public References

- [NVIDIA Documentation Hub](https://docs.nvidia.com/)
- [NVIDIA NeMo Platform](https://docs.nvidia.com/nemo-platform/documentation/kubernetes-deployment/setup)
- [Former NeMo Microservices suite — sunset notice](https://catalog.ngc.nvidia.com/orgs/nvidia/nemo-microservices/collections/nemo-microservices/-)
- [LiteLLM Auto Routing](https://docs.litellm.ai/docs/proxy/auto_routing) · [Decision-model classifiers](https://docs.litellm.ai/docs/auto_router/decision_classifiers)
- [NVIDIA NeMo Switchyard](https://github.com/NVIDIA-NeMo/Switchyard) · [Switchyard routing overview](https://github.com/NVIDIA-NeMo/Switchyard/blob/main/docs/routing_algorithms/overview.md)
- [REAX SN92](https://reax.co/) · [Decision Models](https://decisionmodels.io/) · [Fugal SN70](https://www.fugalai.com/)
- [TrajectoryRL SN11](https://trajrl.com/) · [sundae_bar SN121](https://www.sundaebar.ai/)
- [NVIDIA NIM Operator](https://docs.nvidia.com/nim-operator/latest/) · [NVIDIA Confidential Containers architecture](https://docs.nvidia.com/datacenter/cloud-native/confidential-containers/latest/overview.html)
- [Intel Trust Authority](https://www.intel.com/content/www/us/en/security/trust-authority.html)
- Other ecosystem candidates: [sayGM SN28](https://saygm.com/) · [Gradients SN56](https://www.gradients.io/) · [Affine SN120](https://www.affine.io/) · [Desearch SN22](https://desearch.ai/) · [Score SN44](https://github.com/score-technologies/turbovision) · [Chutes SN64](https://chutes.ai/) · [Hippius SN75](https://hippius.com/)
- TEE inference alternatives: [Phala](https://phala.network/) · [Near AI](https://near.ai/)
