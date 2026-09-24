# SN28 sayGM — idle-capacity demand channel

**Status:** live on mainnet (2026-08-19).  
**Buyer gateway:** https://saygm.com/ · `https://api.saygm.com/v1`  
**This is not SN90's product.** SN90 hosts **SOTA AI services** for enterprises. Serving models to the general public is not the product. Factory services on the clusters come first. What goes to SN28 is **idle GPU headroom** that would otherwise sit warm and unused.

## Live offers (KubeTEE miner)

Buyer-visible SKUs on sayGM, served from `llm.kubetee.ai` (LiteLLM in TDX). GLM-5.2, GLM-5.3, GLM-5.3-Flash, and Ornith-1.5-397B (short name) land on Kata/TDX + NVIDIA CC.

| Buyer model | Miner offer | Pricing | Backend |
|---|---|---|---|
| `glm-5.2` | `kubetee/z-ai/glm-5.2` | dynamic | `glm-5-2-nvfp4-sglang` (B200, NVFP4) |
| `glm-5.3` | `kubetee/z-ai/glm-5.3` | dynamic | `glm-5-3-flash` sibling backend (see `nim/CLAUDE.md`) |
| `z-ai/glm-5.3-flash` | `kubetee/z-ai/glm-5.3-flash` | dynamic | `glm-5-3-flash-sglang-h200` (H200, FP8) |
| `ornith/ornith-1.5-397b` | `kubetee/ornith/ornith-1.5-397b` | dynamic (sole provider) | `ornith-1-5-397b-fp8-sglang-h200` (H200, FP8; retargeted 2026-08-28) |
| `xiaomi/mimo-v2.6-pro-ultraspeed` | `kubetee/xiaomi/mimo-v2.6-pro` | dynamic (sole provider; bootstrap 10% 2026-09-24) | `mimo-v2-6-pro-rl-sglang-b200-cc` (B200 CC, DFLASH spec decode; declared 2026-09-24) |

Pricing adjusts to the market; per-offer prices are visible on sayGM.

**First worldwide — Ornith-1.5-397B.** In collaboration with sayGM (SN28), KubeTEE was the first to provide [Ornith-1.5-397B](https://huggingface.co/ornith-ai/Ornith-1.5-397B-NVFP4) anywhere in the world (2026-08-20).

## Models, licenses, and eligibility

Every SKU offered through sayGM must clear a **license gate before it can be declared** — serving a model commercially on unlicensed terms is a hard blocker (precedents below). The offer set is also scope-limited: SN28 takes **idle GPU headroom from chat backends**. Video/image-generation models are Factory gateway SKUs, not sayGM offers.

**License status of every model we serve or have served (2026-09-21):**

| Model | License | MaaS/sayGM status |
|---|---|---|
| `z-ai/glm-5.2`, `glm-5.3`, `glm-5.3-flash` (zai-org) | Permissive (zai-org releases) | ✅ declared, serving |
| `ornith/ornith-1.5-397b` (Ornith) | Apache-2.0 lineage (Qwen3.5-base) | ✅ declared, serving |
| `xiaomi/mimo-v2.6-pro` (XiaomiMiMo, MiMo-V2.6-Pro-RL) | **MIT** (verified on HF 2026-09-24) | ✅ declared 2026-09-24 (`xiaomi/mimo-v2.6-pro-ultraspeed`) |
| `deepseek/deepseek-v4-flash-0731` | Permissive (DeepSeek) | ⚠️ withdrawn 2026-08-27 (`withdrawn_by_miner`) — not re-declared |
| `qwen/qwen3.8-flash-next` | **Qwen Community License 1.0 — requires a separate Qwen MaaS license for ANY commercial MaaS use (no revenue threshold)** | ❌ decommissioned 2026-09-04 (SKU + manifests, weights retained). Do not re-declare without a signed Qwen license |
| `moonshotai/kimi-k3`, `qwen/qwen3.5-397b-a17b`, `xiaomi/mimo-v2.5` | various | ❌ not in the offer set (backend gone or never offered; kimi is probe-only in the miner's local streaming check; MiMo-V2.5 superseded by the V2.6-Pro declare) |
| `black-forest-labs/flux.2-klein-4b` | Apache-2.0 | ✅ Factory gateway only (`/v1/images`) — not a sayGM SKU |
| `nvidia/Cosmos3-Super` (NIM + passthrough) | NVIDIA OpenMDW-1.1 (commercial OK) | ✅ Factory gateway only (`/cosmos3` passthrough) — not a sayGM SKU |
| `MiniMaxAI/MiniMax-H3` | **MiniMax H3 Community License — Applicable Territory excludes US/EU/UK/KR** | ✅ serving on the Factory gateway (`minimax/h3`, `/v1/videos`) **under written US authorization from MiniMax** (received 2026-09-21; see [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md)). Revocation of that authorization would require removing the deployment. Not a sayGM SKU (video generation, chat-network shape mismatch) |

**Rule of record:** a model enters the offer set only if (1) its license permits commercial MaaS use in the US without additional paperwork, or we hold written authorization (MiniMax-H3 model), and (2) it runs on an existing chat backend with idle headroom. When in doubt, the answer is no — the Qwen decommission is the cost of getting this wrong.

## What SN90 is — and is not

- **SN90 is not an inference subnet.** Same platform, better utilisation.
- Cluster AI services always have priority on capacity.
- SN28 is a demand channel for spare headroom. It is **not** the exclusive public-inference path — `llm.kubetee.ai` remains the Factory gateway.
- sayGM is also an **inference provider** on that gateway: the same models are listed on LiteLLM. If an in-cluster TEE backend is down, LiteLLM falls back to other **TEE-served** inference — [Chutes](https://chutes.ai/), [Phala](https://phala.network/), [Near AI](https://near.ai/) — not back through sayGM (that would loop). See [README — Inference providers and TEE fallbacks](../README.md#inference-providers-and-tee-fallbacks).
- New miner onboarding stays **demand-driven** ([README — Miner onboarding](../README.md#miner-onboarding)). Idle-capacity here means unused GPUs on clusters that are already live, not onboarding miners ahead of Factory demand.

## Free window (closed)

During the free window, buyers used **14,812,329,857** tokens (~15 billion). That load is what hardened the serving stack before the paid sayGM offers.

## LiteLLM provider + TEE fallbacks

sayGM is connected to `llm.kubetee.ai` as a provider: buyer SKUs and Factory `model` names are the same rows. **Primary** backends are in-cluster TEE. **Fallbacks** (HA, TEE-only): Chutes (SN64), Phala, Near AI. Do not register sayGM as a LiteLLM fallback for `kubetee/*` SKUs — Envoy already forwards sayGM → the gateway.

## Operator notes

- Phala CVM holds the LiteLLM key (`--kubetee`). `declare-product` is registry-only; a new SKU does not require a miner image bump when Envoy already forwards `kubetee` to `llm.kubetee.ai`.
- Flash listing: [taostat/gm-miner#193](https://github.com/taostat/gm-miner/pull/193) (docs, merged 2026-08-19).
- SN28 Alpha on hotkey `sn28` is swapped SN28→SN90 and recycled — [SN28-SN90-ALPHA-RECYCLE.md](./SN28-SN90-ALPHA-RECYCLE.md).
- Manifests and gateway wiring: `nim/CLAUDE.md` (gm-miner section).

## Community

- **X (Twitter)**: [@KubeTEEAI](https://x.com/KubeTEEAI)
- Questions in the public channel, not DMs. KubeTEE never DMs first.
- SN28→SN90 recycle (how to verify on-chain): [SN28-SN90-ALPHA-RECYCLE.md](./SN28-SN90-ALPHA-RECYCLE.md)
