# NeMo Microservices, Bittensor Subnet Integrations & the BitSec Security Gate

This document is the detailed reference behind the README [NVIDIA NeMo Microservices](../README.md#nvidia-nemo-microservices), [Bittensor Subnet Integrations](../README.md#bittensor-subnet-integrations-sota-confidential-ready), and [BitSec SN60](../README.md#bitsec-sn60--security-gate-for-ai-workload-promotion) sections. It covers: the NeMo stack on KubeTEE, the attestation-gated TLS protocol between services, the NVIDIA NIM Operator's experimental Kata/Dynamo support and its CoCo limitations, the SOTA Bittensor subnets that could replace or augment each NeMo layer inside a TEE, and the BitSec SN60 security gate design.

---

## 1. NVIDIA NeMo Microservices on KubeTEE

[NVIDIA NeMo Microservices](https://docs.nvidia.com/nemo/microservices/latest/about/index.html) are API-first, modular tools for customizing, evaluating, and securing LLMs and embedding models on Kubernetes. A goal of the KubeTEE AI Factory is to run the full NVIDIA AI stack — NeMo Microservices, NIM models, and AI Blueprints — inside Confidential Computing (Kata + CoCo TEE), scheduled as Armada batch jobs.

Each cluster therefore exposes a shared, high-availability NeMo Microservices deployment as **cluster-resident services that scheduled AI jobs call**. This is the distinction between a service and a job: Customizer, Evaluator, Guardrails, Retriever, and the model endpoints are long-lived and shared, while a job is a transient Armada workload that consumes them. A fine-tuning job dispatched to a miner cluster calls the local Customizer, an evaluation job calls the local Evaluator, and a RAG job calls the local Retriever — inside the cluster, without leaving the confidential boundary or crossing the public internet. Sharing one HA deployment per cluster also means the cost of standing up the stack is amortized across every job that lands there, rather than paid again per job.

---

## 2. Attestation-Gated TLS Between Services

Traffic between these services is secured by **attestation-gated TLS, not operator-issued mTLS** — a distinction that matters because the threat model excludes the host operator, so a certificate KubeTEE issued proves nothing about the workload holding it:

- **cert-manager** mints private keys into Kubernetes Secrets, so the keys exist in etcd and on the node. KubeTEE staff could impersonate either end, or sit in the middle. The wire is encrypted and the guarantee is zero.
- **A service mesh** (Linkerd, Istio, Calico's Istio integration) binds certificates to a pod's Kubernetes ServiceAccount, which authenticates *identity*, not *integrity*. Flip `runtimeClassName` from a confidential runtime to plain `nvidia` and the workload presents the same valid certificate over the same green mTLS — the mesh cannot tell a TEE workload from a non-TEE one. Its issuer key also lives in a Secret outside any TEE.
- **Host-level encryption** (Calico or Cilium WireGuard/IPsec) is a host-to-host tunnel with no per-workload identity, so it cannot express "refuse a peer that cannot attest," and it leaves the host-to-pod segments in the clear.

The general rule: any encryption layer whose keys are managed by the host fails here, because the host is the adversary being excluded. What KubeTEE runs instead:

1. Each service generates its keypair **inside the guest**; the private key never leaves the CVM.
2. A certificate is issued only against a valid TDX quote whose `report_data` commits to the **SHA-256** hash of that public key — SHA-256 rather than SHA-512 because TDX `report_data` is capped at 64 bytes.
3. The quote is verified through **Intel Trust Authority**, so the relying party checks an Intel signature rather than trusting a KubeTEE verifier, against an allowlist of expected MRTD/RTMR measurements.
4. Each side then refuses a peer that cannot present valid attestation — including one KubeTEE itself launched.

TLS is terminated **inside** the guest, so cleartext exists only in encrypted guest memory. The `report_data` binding in step 2 is what makes a certificate *mean* "this key lives inside an attested TEE" — without it a quote proves a TEE exists somewhere, not that the request entered it.

Inference servers generally cannot enforce client certificates themselves — SGLang has no way to make its HTTP server *require* one — so the attested terminator runs as a second container in the **same** Kata guest, requiring an attested client certificate on the way in and forwarding to the model server over guest loopback. Keeping the terminator inside the CVM is deliberate: everything in the guest is inside the TCB that has to be measured and published, which argues for the smallest possible proxy rather than a full service-mesh sidecar.

---

## 3. NIM Operator — Experimental Kata & Dynamo Support

The [NVIDIA NIM Operator](https://docs.nvidia.com/nim-operator/latest/) now ships **experimental** support for running NIM/NeMo workloads inside Kata sandboxes and for Dynamo-orchestrated inference graphs:

- **[Kata Sandbox Workloads (Experimental)](https://docs.nvidia.com/nim-operator/latest/kata-sandbox.html)** — deploys a `NIMService` with `runtimeClassName: kata-qemu-nvidia-gpu` so the NIM runs inside a Kata VM sandbox with hardware-isolated kernel and OS. NVIDIA notes this is a preview for testing only (not production), and that **Confidential Containers** support is planned for a future release.
- **[Dynamo (Experimental)](https://docs.nvidia.com/nim-operator/latest/dynamo.html)** — deploys Dynamo `DynamoGraphDeployment` CRDs (OpenAI-compatible frontend, multi-backend LLM serving, disaggregated prefill/decode) via the NIM Operator with `dynamo.enabled=true`.

> ⚠️ **KubeTEE does not use either path yet.** NeMo Microservices on KubeTEE run on the **stable** TEE runtime classes instead. **KubeTEE is working directly with the NVIDIA NIM Operator and Kata Containers teams** to harden Kata sandbox + CoCo integration and Dynamo's disaggregated serving graphs for production; graduating them is a Phase 3 item.

---

## 4. Kata / CoCo Limitations (NVIDIA)

The NeMo Microservices docs index does not itself list Kata/CoCo limits — the constraints come from the **NIM Operator** (which deploys NeMo Microservices as CRDs) and the **NVIDIA CoCo Reference Architecture**. They are the reason KubeTEE's current confidential path is the stable CoCo runtime classes rather than the NIM Operator's experimental Kata sandbox:

**NIM Operator Kata Sandbox (experimental)** — [Kata Sandbox docs](https://docs.nvidia.com/nim-operator/latest/kata-sandbox.html)
- **Not confidential computing.** The Kata sandbox runtime class is `kata-qemu-nvidia-gpu` and *"does not enable encryption"* — VM isolation only, no TEE encryption/attestation. The GPU Operator must run in **non-CC mode** (`nvidia.com/cc.mode=off`).
- **CoCo + NIMCache unsupported.** *"Confidential Containers and NIM Cache deployments have not been tested and are not supported in this release."* Only `NIMService` with the Kata sandbox has been tested; CoCo support is planned for a future NIM Operator release.
- **Preview only** — NVIDIA marks it *"experimental, not fully supported, not recommended for production."*

**NVIDIA CoCo Reference Architecture** (the stable `kata-qemu-nvidia-gpu-tdx` path KubeTEE uses) — [Limitations & Restrictions](https://docs.nvidia.com/datacenter/cloud-native/confidential-containers/latest/overview.html)
- **containerd only** — no CRI-O / dockerd for confidential workloads.
- **All GPUs on a host must be in CC mode** — configuring a subset is unsupported; for multi-GPU passthrough, all GPUs must be assigned to a single confidential VM.
- **No nested virtualization** — CoCo must be installed directly on the host, not inside a guest VM.
- **No PCI peer-to-peer (P2P) DMA** — IOMMUFD cannot map PCI BAR regions (QEMU logs warnings; GPU function is unaffected).
- **No host-side NVIDIA driver** — CoCo uses VFIO passthrough; host drivers interfere with VFIO binding (the GPU Operator manages the in-guest driver instead).

**NIM Operator (general)** — [Release Notes](https://docs.nvidia.com/nim-operator/latest/release-notes.html)
- **No multi-node NIM microservice config** — *"The Operator does not support configuring NIM microservices in a multi-node deployment"* (multi-node NIM v2.0 via Ray is a separate, newer path).
- **CC added incrementally** — Kata sandbox is the *"first foundational step"*; full CoCo encryption/attestation through the Operator is future work.

---

## 5. Bittensor Subnet Integrations (SOTA, Confidential-Ready)

Given the limitations above, KubeTEE's thesis is that **the Bittensor ecosystem already contains SOTA, verifiable substitutes** for several NeMo stack layers, and that running them inside Kata + CoCo TEE pods — instead of, or alongside, the NVIDIA stack — could sidestep those limitations while keeping workloads confidential. Each subnet below exposes a **verifiable feed** (public API + on-chain metagraph) and is a **potential partnership** that could replace or augment the corresponding NeMo component. These are candidate integrations and proposals, not shipping integrations:

| Subnet | Name | SOTA role | Could replace / augment (NeMo stack) | Confidential-computing fit |
|--------|------|-----------|--------------------------------------|----------------------------|
| SN56 | [Gradients](https://www.gradients.io/) (G.O.D) | AutoML tournaments — miners submit open-source SFT / DPO / GRPO training scripts; validators execute on standardized GPU infra and open-source the winners | NeMo Customizer (fine-tuning) | Training scripts execute inside KubeTEE TEE pods → confidential fine-tuning tournaments with open-source winning methods |
| SN120 | [Affine](https://www.affine.io/) | Incentivized RL ("reason mining") — miners submit on-chain model revisions; validators host inference and run challenger-vs-champion duels; winner-takes-all; sybil/decoy/copy/overfitting-proof | NeMo Customizer (RL / reasoning) | Validator inference + duels run in TEE; winning models bridge to Chutes (SN64) for confidential serving |
| SN97 | [Albedo](https://github.com/unarbos/distil) / [albedo](https://github.com/unarbos/albedo) (Distil) | Competitive **model distillation** (trajectory / knowledge distillation — not coding agents): miners commit ≤33B students distilled from a large teacher; validators score king-of-the-hill duels on a multi-axis composite; open HF checkpoints + public duel traces; upstream already serves the king at [chat.arbos.life](https://chat.arbos.life). **Active KubeTEE SN90 PoC** (2026-08-09): always-on king (4× H200, OpenAI `/v1/*` via `king_serve.py`) + challenger Jobs + shared judge → LiteLLM; next integration is registering that king Service as a LiteLLM model for in-cluster / `llm.kubetee.ai` inference. Details: [SN97-ALBEDO-POC.md](./SN97-ALBEDO-POC.md) · [PLAN.md](https://github.com/KubeTEE-AI-Blueprints/albedo/blob/kubetee-poc/kubetee/PLAN.md) · [unarbos/albedo#4](https://github.com/unarbos/albedo/pull/4). | NeMo Customizer (distillation) + Evaluator (duel / composite scoring) + model endpoints (serve the reigning king) | Distillation + duels in TEE; reigning king served as confidential (or staging) inference; open distilled checkpoints reusable as job templates |
| SN27 | [Orion](https://github.com/SILX-LABS/Orion) | Decentralized data subnet — campaign-driven discovery / generation / curation of model-ready training data with on-chain quality validation | NeMo Data Designer / data pipeline | Data provenance is on-chain; generation miners run in TEE for confidential data pipelines |
| SN22 | [Desearch](https://desearch.ai/) | Decentralized real-time web + X/Twitter search for AI agents; cited, context-rich results via API | NeMo Retriever / RAG grounding | Live retrieval runs as a confidential grounding step inside the TEE before generation |
| SN44 | [Score](https://github.com/score-technologies/turbovision) (TurboVision) | Decentralized computer vision — miners run CV models (object detection, keypoint detection, tracking) on live video/imagery and return structured, decision-ready annotations; validators benchmark on live data via lightweight hybrid validation (frame filtering, keypoint + homography checks, CLIP-based semantic verification). First deployment: Game State Recognition for football at 10–100× lower cost than manual annotation; generalizes to any camera feed | NVIDIA Video Search and Summarization blueprint (video analytics / structured video understanding) | CV inference + validation run inside KubeTEE TEE pods → confidential video analytics with attested structured outputs; sensitive footage stays in the enclave |
| SN64 | [Chutes](https://chutes.ai/) — Parallax (Jon Durbin) | Decentralized serverless inference + **Parallax** decentralized MoE training (surrogate experts, no all-to-all; ternary weights; Gated DeltaNet) across heterogeneous, non-colocated GPUs — within 0.6% of centralized baseline | Inference + distributed training | Chutes already runs a **fully TEE-only infrastructure stack**; Parallax trains frontier models on distributed confidential compute — a native fit for KubeTEE's decentralized TEE clusters |
| SN75 | [Hippius](https://hippius.com/) | Decentralized cloud storage — S3-compatible + IPFS pinning; Arion engine (Reed-Solomon k=10/m=20, CRUSH placement, self-healing) | Persistent storage (solves CoCo's **ephemeral-data-only** limitation) | **Already ships Confidential Compute** (AMD SEV-SNP encrypted VMs); drop-in S3 endpoint replacing/augmenting encrypted Longhorn + object store |
| SN118 | [Ditto](https://heyditto.ai/) | Open-source persistent memory / context layer for AI agents (Claude / Cursor / MCP); miners train the memory-retrieval "harness" | Agent memory / context management | Memory graph backed by confidential storage (e.g. Hippius) so agent context persists across confidential sessions |
| SN60 | [Bitsec.ai](https://bitsec.ai/) | Decentralized AI security — miners submit autonomous security agents that find high/critical-severity exploits in codebases & smart contracts; validators run them in isolated Docker sandboxes and score against benchmark ground truths | **Security gate** (new layer — no NeMo equivalent) | Planned pre-promotion analysis for AI workloads before they reach staging/production on SN90 — design concept, to be detailed during integration (see [BitSec SN60](#6-bitsec-sn60--security-gate-for-ai-workload-promotion) below) |

KubeTEE treats this as an **open set**: any Bittensor subnet with a SOTA, verifiable solution for a NeMo stack layer — data, training, retrieval, inference, storage, agent memory, or evaluation — is a potential partnership and candidate integration, with the workload adapted to run inside `kata-qemu-nvidia-gpu-tdx` / `kata-qemu-tdx` and its outputs attested and persisted on confidential storage. This is the Bittensor-native path to a confidential AI Factory that is **not locked to a single vendor's experimental stack**, and it is the concrete way KubeTEE could "work with the ecosystem" rather than waiting on the NIM Operator's CoCo roadmap.

---

## 6. BitSec SN60 — Security Gate for AI Workload Promotion

> 🧪 **Status: design concept**. The gate rules, thresholds, and tooling below are provisional and will be hardened during integration — a Phase 1 item.

[Bitsec.ai (SN60)](https://bitsec.ai/) is a decentralized security subnet: miners submit autonomous AI security agents that scan codebases and smart contracts for **high- and critical-severity** vulnerabilities, and validators run those agents in isolated, resource-limited Docker sandboxes, scoring them against benchmark ground truths (SCA-Bench / Smart Contract Audit Benchmark). BitSec already audits other Bittensor subnets' incentive mechanisms and smart-contract code (findings published as critical / high / medium), so it is a natural, verifiable security layer for SN90.

In this design, KubeTEE would use BitSec SN60 as a **mandatory security gate** that an AI workload must pass **before it is promoted to staging or production** clusters on SN90. The gate sits in front of the staging→production pipeline, not inside it:

```mermaid
flowchart LR
    WL["AI workload<br/>(NeMo/NIM/Blueprint job,<br/>subnet-integrated flow, or container image)"] -->|"submit source / image / IaC"| BS["BitSec SN60<br/>security agent analysis"]
    BS -->|"critical/high findings"| Fix["Remediate & resubmit"]
    Fix --> BS
    BS -->|"clean report (no critical/high, attested)"| Stg["Staging cluster (SN90)<br/>Kata + CoCo TEE"]
    Stg -->|"staging validation + attestation + uptime"| Prod["Production cluster (SN90)<br/>multi-cluster, one hotkey / DC"]
    BS -.->|"report published"| Audit["On-chain audit trail<br/>(verifiable)"]
```

**Proposed gate rules (design, subject to change during integration):**
- **Scope** — BitSec analyzes the workload's code (job template, model-serving code, subnet-integration glue, any on-chain/smart-contract code) and the container image it runs, plus the IaC/Helm values that deploy it.
- **Pass condition** — a workload is promoted to staging only with a **clean BitSec report** (no unresolved critical or high-severity findings). Findings are either remediated and resubmitted, or accepted as a documented risk with owner sign-off (production requires the clean report — no sign-off bypass for critical/high).
- **Verifiable** — the BitSec report is published and referenceable (BitSec posts summaries on X and detailed findings on its site), so the security posture of every workload running on SN90 is auditable, not claimed.
- **Re-run on change** — any material change to the workload (new image tag, new job template, new subnet integration) re-triggers the gate; promotion is per-revision, not once-and-done.
- **Confidentiality** — the gate runs on the workload's *code/image*, not on the confidential *data* it will process in production, so running BitSec does not require exposing production data or TEE contents. The analysis itself can run inside a KubeTEE TEE pod when the code under review is itself sensitive.

**Why a gate, not a scanner inside the cluster:** production SN90 clusters run confidential workloads under Kata + CoCo with attested, encrypted memory. A security agent *inside* the TEE would either see confidential data (breaking the trust boundary) or see nothing useful. Putting BitSec **before** promotion keeps the security analysis where it belongs — on the code/image, pre-deployment — and keeps the production TEE boundary intact. This is the Bittensor-native equivalent of a CI security stage, decentralized and incentivized via SN60.

---

## References

- [NVIDIA NeMo Microservices](https://docs.nvidia.com/nemo/microservices/latest/about/index.html)
- [NVIDIA NIM Operator](https://docs.nvidia.com/nim-operator/latest/) — [Kata Sandbox (Experimental)](https://docs.nvidia.com/nim-operator/latest/kata-sandbox.html) | [Dynamo (Experimental)](https://docs.nvidia.com/nim-operator/latest/dynamo.html) | [Release Notes](https://docs.nvidia.com/nim-operator/latest/release-notes.html)
- [NVIDIA Confidential Containers Reference Architecture](https://docs.nvidia.com/datacenter/cloud-native/confidential-containers/latest/overview.html)
- [Intel Trust Authority](https://www.intel.com/content/www/us/en/security/trust-authority.html)
- Bittensor subnets: [Gradients SN56](https://www.gradients.io/) · [Affine SN120](https://www.affine.io/) · [Albedo SN97](https://github.com/unarbos/distil) · [Orion SN27](https://github.com/SILX-LABS/Orion) · [Desearch SN22](https://desearch.ai/) · [Score SN44](https://github.com/score-technologies/turbovision) · [Chutes SN64](https://chutes.ai/) · [Hippius SN75](https://hippius.com/) · [Ditto SN118](https://heyditto.ai/) · [Bitsec.ai SN60](https://bitsec.ai/)
