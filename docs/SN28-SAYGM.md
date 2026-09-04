# SN28 sayGM — idle-capacity demand channel

**Status:** live on mainnet (2026-08-19).  
**Buyer gateway:** https://saygm.com/ · `https://api.saygm.com/v1`  
**This is not SN90's product.** SN90 hosts **SOTA AI services** for enterprises. Serving models to the general public is not the product. Factory services on the clusters come first. What goes to SN28 is **idle GPU headroom** that would otherwise sit warm and unused.

## Live offers (KubeTEE miner)

Buyer-visible SKUs on sayGM, served from `llm.kubetee.ai` (LiteLLM in TDX). GLM-5.2, GLM-5.3, GLM-5.3-Flash, and Ornith-1.5-397B (short name) land on Kata/TDX + NVIDIA CC. Discounts are vs sayGM retail, not an SN90 reseller tier. **Discounts are set dynamically by the matcher — they are not pinned in docs; see [the matcher Fleet bundle](https://github.com/pamanseau/kubetee-fleet/tree/main/infrastructure/saygm-discount-match/staging) or the ops canvas for the current position.**

| Buyer model | Miner offer | Pricing | Backend |
|---|---|---|---|
| `glm-5.2` | `kubetee/z-ai/glm-5.2` | matcher-managed (margin-recovery hold; see below) | `glm-5-2-nvfp4-sglang` (B200, NVFP4) |
| `glm-5.3` | `kubetee/z-ai/glm-5.3` | matcher-managed | `glm-5-3-flash` sibling backend (see `nim/CLAUDE.md`) |
| `z-ai/glm-5.3-flash` | `kubetee/z-ai/glm-5.3-flash` | matcher-managed | `glm-5-3-flash-sglang-h200` (H200, FP8) |
| `ornith/ornith-1.5-397b` | `kubetee/ornith/ornith-1.5-397b` | matcher-managed (sole provider) | `ornith-1-5-397b-fp8-sglang-h200` (H200, FP8; retargeted 2026-08-28) |

Pricing ranks shift with every matcher run (match-to-cheapest-qualifying-rival, never undercut; the share guard holds price while we lead traffic, the ladder walks it back up in bounded steps).</think>

**LiteLLM cost basis = sayGM net receive** (registry retail × (1−discount), all dimensions incl. cache-read), re-pinned via `sync.py --skip-gmcli` after the matcher moves a discount — the basis follows the matcher, so no number here either.

`deepseek/deepseek-v4-flash-0731` was withdrawn from the miner offer set on 2026-08-27 (`withdrawn_by_miner`). **`qwen/qwen3.8-flash-next` was withdrawn 2026-09-04 — LICENSE: the Qwen Community License 1.0 requires a separate Qwen license for any Model-as-a-Service commercial use (no revenue threshold).** Do not re-declare either. The 0731 SKU can still be served on `llm.kubetee.ai`; the qwen backend was decommissioned (STS deleted, PVCs retained).

**Auto-match.** Fleet CronJob `saygm-discount-match` in `kubetee-ops` is **live** — discounts are set **dynamically** every 15 min from the live registry field (match-to-cheapest-qualifying-rival, never undercut, engy-floor enforced, share guard + price ladder). **Do not pin discount numbers in documentation** — they move with the market. The current position is on the ops canvas (`saygm-price-position`). **GLM-5.2 is excluded from the matcher** (margin recovery, 2026-09-01): the rank-1 provider runs a script that mirrors/undercuts any exact match, so KubeTEE does not chase it. Re-adding GLM-5.2 to `values.yaml` `config.products` re-enables rank-1 defense for it. HTTP against the registry — no `gmcli` in-cluster. See `fleet-gitops/infrastructure/saygm-discount-match/staging/README.md`.

> ⚠️ **Matcher auth (one-time-use refresh tokens):** any operator query that consumes the in-cluster rotating refresh token without write-back (read-only Secret mount) leaves `saygm-discount-match-gmcli` dead (`AUTH: refresh_token rejected 401`). Re-seed with `gmcli login` + `match.py emit-seed` per the matcher README.

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
