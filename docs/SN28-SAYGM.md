# SN28 sayGM — idle-capacity demand channel

**Status:** live on mainnet (2026-08-19).  
**Buyer gateway:** https://saygm.com/ · `https://api.saygm.com/v1`  
**This is not SN90's product.** SN90 hosts **SOTA AI services** for enterprises. Serving models to the general public is not the product. Factory services on the clusters come first. What goes to SN28 is **idle GPU headroom** that would otherwise sit warm and unused.

## Live offers (KubeTEE miner)

Buyer-visible SKUs on sayGM, served from `llm.kubetee.ai` (LiteLLM in TDX). GLM-5.2, GLM-5.3-Flash, and Ornith-1.5-397B (short name) land on Kata/TDX + NVIDIA CC. Discounts are vs sayGM retail, not an SN90 reseller tier.

| Buyer model | Miner offer | Discount vs retail | Backend |
|---|---|---|---|
| `glm-5.2` | `kubetee/z-ai/glm-5.2` | **40% — margin recovery** (2026-09-01: 50%→40%, extending the day's 62.88%→50% margin-recovery sequence) | `glm-5-2-nvfp4-sglang` (B200, NVFP4) |
| `glm-5.3` | `kubetee/z-ai/glm-5.3` | **10.35%** (matcher-held, live rank war — field grew 2→3 offers 2026-09-02; matcher crept 10.1%→10.25%→10.35% in one hour) | `glm-5-3-flash` sibling backend (see `nim/CLAUDE.md`) |
| `z-ai/glm-5.3-flash` | `kubetee/z-ai/glm-5.3-flash` | **60%** | `glm-5-3-flash-sglang-h200` (H200, FP8) |
| `qwen/qwen3.8-flash-next` | `kubetee/qwen/qwen3.8-flash-next` | **5%** (matcher-held rank-1; was 15% pre-2026-09-01) | `qwen38-flash-next-fp8-sglang-h200` (H200, FP8) |
| `ornith/ornith-1.5-397b` | `kubetee/ornith/ornith-1.5-397b` | **50%** (first worldwide, 2026-08-20; 15%→50% 2026-08-27) | `ornith-1-5-397b-fp8-sglang-h200` (H200, FP8; retargeted 2026-08-28) |

**Four of five offers rank 1** on the registry pricing field (glm-5.2 deliberately ranks 4 of 8 — margin recovery, see below). Auto-matched discounts are match-to-cheapest-rival (never undercut), computed via the `match.py` blend logic.

**LiteLLM cost basis = sayGM net receive** (registry retail × (1−discount), all dimensions incl. cache-read), re-pinned 2026-09-02 via `sync.py --skip-gmcli`. Qwen's basis uses **registry** retail ($0.16 in / $0.16 cache-read per Mtok) — not OpenRouter's ($0.15/$0.016, a 10× cache mismatch). GLM-5.3's basis follows the matcher: re-pin after it moves the discount.

`deepseek/deepseek-v4-flash-0731` was withdrawn from the miner offer set on 2026-08-27 (`withdrawn_by_miner`). Do not re-declare it. The SKU can still be served on `llm.kubetee.ai`.

**Auto-match (GLM-5.3, Flash, Qwen, Ornith).** Fleet CronJob `saygm-discount-match` in `kubetee-ops` is **live** (re-activated 2026-09-01, 70% cap, match-never-undercut). **GLM-5.2 is excluded from the matcher and held at a fixed 40%** (margin recovery, 2026-09-01: 50%→40%): the rank-1 provider runs a script that mirrors/undercuts any exact match, so KubeTEE does not chase it. The earlier same-day sequence was 50%→62.85% (rank-1 match)→62.88% (rank-2, +0.05% above leader)→**50%→40%** for margin recovery. Re-adding GLM-5.2 to `values.yaml` `config.products` re-enables rank-1 defense for it. HTTP against the registry — no `gmcli` in-cluster. See `fleet-gitops/infrastructure/saygm-discount-match/staging/README.md`.

> ⚠️ **Matcher auth re-seed needed (2026-09-01):** an operator query consumed the in-cluster rotating refresh token without write-back (read-only Secret mount), leaving `saygm-discount-match-gmcli` dead (`AUTH: refresh_token rejected 401`). Re-seed with `gmcli login` + `match.py emit-seed` per the matcher README. GLM-5.2's 40% must be declared **by hand** (`gmcli declare-product --discount-pct 40`) once re-logged-in — it is excluded from the matcher.

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
