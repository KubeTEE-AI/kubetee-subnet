# SN28 sayGM — idle-capacity demand channel

**Status:** live on mainnet (2026-08-19).  
**Buyer gateway:** https://saygm.com/ · `https://api.saygm.com/v1`  
**This is not SN90's product.** SN90 hosts **SOTA AI services** for enterprises. Serving models to the general public is not the product. Factory services on the clusters come first. What goes to SN28 is **idle GPU headroom** that would otherwise sit warm and unused.

## Live offers (KubeTEE miner)

Buyer-visible SKUs on sayGM, served from `llm.kubetee.ai` (LiteLLM in TDX). GLM-5.2, GLM-5.3, GLM-5.3-Flash, and Ornith-1.5-397B (short name) land on Kata/TDX + NVIDIA CC. Discounts are vs sayGM retail, not an SN90 reseller tier. **Discounts are dynamic — set automatically against the live market; they are never pinned in docs.**

| Buyer model | Miner offer | Pricing | Backend |
|---|---|---|---|
| `glm-5.2` | `kubetee/z-ai/glm-5.2` | dynamic | `glm-5-2-nvfp4-sglang` (B200, NVFP4) |
| `glm-5.3` | `kubetee/z-ai/glm-5.3` | dynamic | `glm-5-3-flash` sibling backend (see `nim/CLAUDE.md`) |
| `z-ai/glm-5.3-flash` | `kubetee/z-ai/glm-5.3-flash` | dynamic | `glm-5-3-flash-sglang-h200` (H200, FP8) |
| `ornith/ornith-1.5-397b` | `kubetee/ornith/ornith-1.5-397b` | dynamic (sole provider) | `ornith-1-5-397b-fp8-sglang-h200` (H200, FP8; retargeted 2026-08-28) |

Pricing adjusts automatically to the live market.</think>

**LiteLLM cost basis = sayGM net receive** (registry retail × (1−discount), all dimensions incl. cache-read), re-pinned via `sync.py --skip-gmcli` whenever a discount moves.

`deepseek/deepseek-v4-flash-0731` was withdrawn from the miner offer set on 2026-08-27 (`withdrawn_by_miner`). Do not re-declare it. The 0731 SKU can still be served on `llm.kubetee.ai`.

**Auto-match.** A private Fleet CronJob (`kubetee-ops`) keeps offers price-competitive — discounts are set **dynamically** from the live market. **Do not pin discount numbers in documentation** — they move with the market.

**First worldwide — Ornith-1.5-397B.** In collaboration with sayGM (SN28), KubeTEE was the first to provide [Ornith-1.5-397B](https://huggingface.co/ornith-ai/Ornith-1.5-397B-NVFP4) anywhere in the world (2026-08-20).

## What SN90 is — and is not

- **SN90 is not an inference subnet.** Same platform, better utilisation.
- Cluster AI services always have priority on capacity.
- SN28 is a demand channel for spare headroom. It is **not** the exclusive public-inference path — `llm.kubetee.ai` remains the Factory gateway.
- sayGM is also an **inference provider** on that gateway: the same models are listed on LiteLLM. If an in-cluster TEE backend is down, LiteLLM falls back to other **TEE-served** inference — [Chutes](https://chutes.ai/), [Phala](https://phala.network/), [Near AI](https://near.ai/) — not back through sayGM (that would loop). See [README — Inference providers and TEE fallbacks](../README.md#inference-providers-and-tee-fallbacks).
- New miner onboarding stays **demand-driven** ([README — Miner onboarding](../README.md#miner-onboarding)). Idle-capacity here means unused GPUs on clusters that are already live, not onboarding miners ahead of Factory demand.

## Free window (closed)

During the free window, buyers used **14,812,329,857** tokens (~15 billion). That load is what hardened GLM-5.2 and Flash-0731 before the paid sayGM offers.

## LiteLLM provider + TEE fallbacks

sayGM is connected to `llm.kubetee.ai` as a provider: buyer SKUs and Factory `model` names are the same rows. **Primary** backends are in-cluster TEE. **Fallbacks** (HA, TEE-only): Chutes (SN64), Phala, Near AI. Do not register sayGM as a LiteLLM fallback for `kubetee/*` SKUs — Envoy already forwards sayGM → the gateway.

## Operator notes

- Phala CVM holds the LiteLLM key (`--kubetee`). `declare-product` is registry-only; a new SKU does not require a miner image bump when Envoy already forwards `kubetee` to `llm.kubetee.ai`.
- Flash listing: [taostat/gm-miner#193](https://github.com/taostat/gm-miner/pull/193) (docs, merged 2026-08-19). Registry accepted `kubetee/deepseek/deepseek-v4-flash-0731` the same day; offer withdrawn 2026-08-27.
- SN28 Alpha on hotkey `sn28` is swapped SN28→SN90 and recycled — [SN28-SN90-ALPHA-RECYCLE.md](./SN28-SN90-ALPHA-RECYCLE.md).
- Manifests and gateway wiring: `nim/CLAUDE.md` (gm-miner section).

## Community

- **X (Twitter)**: [@KubeTEEAI](https://x.com/KubeTEEAI)
- Questions in the public channel, not DMs. KubeTEE never DMs first.
- SN28→SN90 recycle (how to verify on-chain): [SN28-SN90-ALPHA-RECYCLE.md](./SN28-SN90-ALPHA-RECYCLE.md)
