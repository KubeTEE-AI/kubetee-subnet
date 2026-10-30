# SN28 sayGM — idle-capacity demand channel

**Status:** live on mainnet (2026-08-19).  
**Buyer gateway:** https://saygm.com/ · `https://api.saygm.com/v1`  
**This is not SN90's product.** SN90 hosts **SOTA AI services** for enterprises. Serving models to the general public is not the product. Factory services on the clusters come first. What goes to SN28 is **idle GPU headroom** that would otherwise sit warm and unused.

## Live offers (KubeTEE miner)

Buyer-visible SKUs on sayGM, served from `llm.kubetee.ai` (LiteLLM in TDX). GLM-5.2, GLM-5.3, and Ornith-1.5-397B (short name) land on Kata/TDX + NVIDIA CC.

| Buyer model | Miner offer | Pricing | Backend |
|---|---|---|---|
| `glm-5.2` | `kubetee/z-ai/glm-5.2` | dynamic | `glm-5-2-fp8-sglang-h200` (H200, FP8, michigan-97 — since 2026-10-12; was `glm-5-2-nvfp4-sglang` B200 NVFP4 until 2026-10-13, decommissioned) |
| `glm-5.3` | `kubetee/z-ai/glm-5.3` | dynamic | `glm-5-3-radixark-nvfp4-sglang-b200-cc` (B200, RadixArk NVFP4, `am-b200-59` — production since 2026-10-13; B200 FP8 build parked as fallback) |
| `ornith/ornith-1.5-397b` | `kubetee/ornith/ornith-1.5-397b` | dynamic (sole provider) | `ornith-1-5-397b-fp8-sglang-h200` (H200, FP8; retargeted 2026-08-28) |
| `deepseek-v4.1-flash` / `deepseek-v4.1-flash-tee` | `kubetee/deepseek/deepseek-v4.1-flash` (alias; `-1017` route `kubetee/deepseek/deepseek-v4.1-flash-1017` → `deepseek-v4.1-flash-1017-tee` DECLARED 2026-10-17 at 10% — standing, eligibility gated on the gm-miner worker image roll carrying `verified_models`/`TARGETS` + `-1017`) | dynamic | `deepseek-v4-1-flash-sglang-h200-cc` (H200, FP8, `am-h200-27`) — **DeepSeek-V4.1-Flash-1017 weights since 2026-10-17** (same `deepseek-v4.1-flash` source name kept during the dual-name transition so the baked gm-miner envoy gate keeps serving) |
| `xiaomi/mimo-v2.6-pro-ultraspeed` | `kubetee/xiaomi/mimo-v2.6-pro` | dynamic (sole provider; bootstrap 10% 2026-09-24) | `mimo-v2-6-pro-rl-sglang-b200-cc` (B200 CC, 2 replicas since 2026-10-13; DFLASH spec decode; declared 2026-09-24) |
| `mistral-large-4` / `mistral-large-4-tee` | `kubetee/mistralai/mistral-large-4` (sole provider) | dynamic | `mistral-large-4` (Mistral-Large-4-1T-A52B-**NVFP4**, SGLang, `na-us-dallas-132`; declared 2026-10-30) |

> **Buyer-id naming (mistral, hit 2026-10-30):** the buyer catalog ids are
> `mistral-large-4` / `mistral-large-4-tee` — **no `mistral/` prefix**. Sending
> `mistral/mistral-large-4-tee` returns `unknown model`. The prefix only lives in
> the registry route (`kubetee/mistralai/mistral-large-4` source → buyer product
> `mistral/mistral-large-4-tee`). Resolve ids from `GET /v1/models` on the buyer
> gateway first.

Pricing adjusts to the market; per-offer prices are visible on sayGM.

**First worldwide — Ornith-1.5-397B.** In collaboration with sayGM (SN28), KubeTEE was the first to provide [Ornith-1.5-397B](https://huggingface.co/ornith-ai/Ornith-1.5-397B-NVFP4) anywhere in the world (2026-08-20).

**MiniMax-Music3** (music + speech generation through the TTS/music pass-throughs, OPTION B 2026-10-08) and **MOSS-TTS** are also live on the gateway — text-to-music and text-to-speech alongside the video H3 serve.

## Models, licenses, and eligibility

Every SKU offered through sayGM must clear a **license gate before it can be declared** — serving a model commercially on unlicensed terms is a hard blocker (precedents below). The offer set is also scope-limited: SN28 takes **idle GPU headroom from chat backends**. Video/image-generation models are Factory gateway SKUs, not sayGM offers.

**License status of every model we serve or have served (2026-09-21):**

| Model | License | MaaS/sayGM status |
|---|---|---|
| `z-ai/glm-5.2`, `glm-5.3` (zai-org) | Permissive (zai-org releases) | ✅ declared, serving |
| `ornith/ornith-1.5-397b` (Ornith) | Apache-2.0 lineage (Qwen3.5-base) | ✅ declared, serving |
| `xiaomi/mimo-v2.6-pro` (XiaomiMiMo, MiMo-V2.6-Pro-RL) | **MIT** (verified on HF 2026-09-24) | ✅ declared 2026-09-24 (`xiaomi/mimo-v2.6-pro-ultraspeed`) |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | Nemotron (pending) | ⏳ evaluation-only pending commercial license grant |
| **MiniMax-Music3** (MiniMax) | MiniMax Community (music) | ✅ served via pass-through (2026-10-08) |
| `deepseek/deepseek-v4-flash-0731` | Permissive (DeepSeek) | ⚠️ withdrawn 2026-08-27 (`withdrawn_by_miner`) — not re-declared |
| `z-ai/glm-5.3-flash` | Permissive (zai-org) | ⚠️ withdrawn 2026-10-26 — removed from the offer set |
| `qwen/qwen3.8-flash-next` | **Qwen Community License 1.0 — requires a separate Qwen MaaS license for ANY commercial MaaS use (no revenue threshold)** | ❌ decommissioned 2026-09-04 (SKU + manifests, weights retained). Do not re-declare without a signed Qwen license |
| `moonshotai/kimi-k3`, `qwen/qwen3.5-397b-a17b`, `xiaomi/mimo-v2.5` | various | ❌ not in the offer set (backend gone or never offered; kimi is probe-only in the miner's local streaming check; MiMo-V2.5 superseded by the V2.6-Pro declare) |
| `mistralai/Mistral-Large-4-1T-A52B` (served NVFP4) | **Mistral Ecosystem Open-Weight License** (modified MIT — allows commercial use) **but §2 requires a separate commercial license for any "Model as a Service" use** | ⚠️ declared + serving sayGM 2026-10-30 (`mistral-large-4` / `mistral-large-4-tee`, sole provider) and Factory chat — **MaaS commercial license from Mistral REQUIRED before this is cleared** (exact clause + analysis below). Not cleared by the plain license. |
| `black-forest-labs/flux.2-klein-4b` | Apache-2.0 | ✅ Factory gateway only (`/v1/images`) — not a sayGM SKU |
| `nvidia/Cosmos3-Super` (NIM + passthrough) | NVIDIA OpenMDW-1.1 (commercial OK) | ✅ Factory gateway only (`/cosmos3` passthrough) — not a sayGM SKU |
| `MiniMaxAI/MiniMax-H3` | **MiniMax H3 Community License — Applicable Territory excludes US/EU/UK/KR** | ✅ Factory gateway (`minimax/h3`, `/v1/videos` — [H3-VIDEO-GENERATION-API.md](./H3-VIDEO-GENERATION-API.md)) **under written US authorization from MiniMax** (received 2026-09-21; see [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md)). Revocation of that authorization would require removing the deployment. **Also a declared sayGM offer AND buyer-routable** (`kubetee minimax/h3`, 10% floor). It is served on the buyer gateway's **video** path, not chat: `POST https://api.saygm.com/v1/videos` (with `X-GM-Providers: kubetee` + the buyer `SAYGM_API_KEY`) generates and settles — verified 2026-10-26, job `video_01M5VRRY3K7RPDWD0VDXF063ED` `completed`, `cost_nano_usd: 288000000`. Schema is `model, prompt, seconds, size, seed, image_reference` only (`task`/`aspect_ratio`/`duration` are rejected as `unsupported_video_parameter`). The **chat** surfaces do NOT route it: `POST /v1/chat/completions` returns `unknown model: minimax/h3` (message: "minimax/h3 is served on POST /v1/videos"), and the **worker data plane** rejects the source model (`missing or unsupported KubeTEE source model` — verified 2026-10-26 on the `997600e8…-8080s` worker, where chat models like `z-ai/glm-5.3` pass). So: buyer-video ✅, buyer-chat ✗, worker-data-plane ✗ (video, chat-network shape mismatch) — see "What SN90 is — and is not" below. |

**Rule of record:** a model enters the offer set only if (1) its license permits commercial MaaS use in the US without additional paperwork, or we hold written authorization (MiniMax-H3 model), and (2) it runs on an existing chat backend with idle headroom. When in doubt, the answer is no — the Qwen decommission is the cost of getting this wrong.

**⚠️ Mistral-Large-4 license gate is NOT cleared — the MaaS clause is triggered (verified 2026-10-30):** the served weights
(`mistralai/Mistral-Large-4-1T-A52B-NVFP4`, base `Mistral-Large-4-1T-A52B`) are
under the **Mistral Ecosystem Open-Weight License** (a modified MIT license). HF
tags it `license: other` (non-standard SPDX), so the tag alone is ambiguous — the
license text is what governs. It permits commercial use **except** MaaS. LICENSE
§2: *"If the Licensee or any of its affiliates operates a **Model as a Service**
business, the Licensee must enter into a separate commercial license with
Mistral before using the Model… for any commercial purpose."* MaaS is defined as
giving a third party access to the Model for inference via API/hosted endpoints
where they exercise meaningful control over the inputs/parameters.

**KubeTEE's use is MaaS:** `llm.kubetee.ai` + sayGM expose Mistral-Large-4 as a
hosted OpenAI-compatible inference API where buyers set the prompt and
parameters. No carve-out applies — not internal use, not via Mistral's official
products, not "mere relaying to models hosted by others" (we self-host the
weights), not an end-user product embedded in a specific feature. **This is the
Qwen class** (separate commercial MaaS license required). Under this doc's Rule
of record, the SKU is **not cleared** until a commercial license is in hand from
Mistral (`https://mistral.ai/contact/`). Treat obtaining that license (or
withdrawing the SKU) as an open action — do not present Mistral-Large-4 as a
cleared SKU.

**Operator decision 2026-10-30: the SKU is HELD LIVE during the commercial-license
negotiation with Mistral** (explicit user decision — the exposure is accepted
while the request is in flight; revisit if Mistral declines or stalls). Getting
the license: file via `https://mistral.ai/contact/` (LICENSE §2 names it as the
request path), describe the MaaS use case (self-hosted NVFP4 on B200 in TDX+CC
TEEs, exposed via `llm.kubetee.ai` + sayGM; retail-priced at Mistral's own API
list; no derivatives/fine-tuning), negotiate fee/revenue-share + attribution,
then flip this row to ✅ cleared with the agreement date (the MiniMax-H3
written-authorization pattern).

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
