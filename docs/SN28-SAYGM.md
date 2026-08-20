# SN28 sayGM — idle-capacity demand channel

**Status:** live on mainnet (2026-08-19).  
**Buyer gateway:** https://saygm.com/ · `https://api.saygm.com/v1`  
**This is not SN90's product.** SN90 is a confidential AI compute platform. Serving models is not the product. AI Factory workloads on the clusters come first. What goes to SN28 is **idle GPU headroom** that would otherwise sit warm and unused.

## Live offers (KubeTEE miner)

Buyer-visible SKUs on sayGM, served from `llm.kubetee.ai` (LiteLLM in TDX) onto Kata/TDX + NVIDIA CC backends. Discounts are vs sayGM retail, not an SN90 reseller tier.

| Buyer model | Miner offer | Discount vs retail | Backend |
|---|---|---|---|
| `glm-5.2` | `kubetee/z-ai/glm-5.2` | **48.25%** | `glm-5-2-nvfp4-sglang` (B200, NVFP4) |
| `deepseek/deepseek-v4-flash-0731` | `kubetee/deepseek/deepseek-v4-flash-0731` | **20%** | `dsv4-0731-sglang-h200` (H200, FP8-DSpark) |

Do **not** declare `moonshotai/kimi-k3`, `qwen/qwen3.5-397b-a17b`, or `xiaomi/mimo-v2.5` even if `/v1/models` still lists them.

Chutes TEE SKUs (`zai-org/GLM-5.2-TEE`, `deepseek-ai/DeepSeek-V4-Flash-0731-TEE`) are different products. KubeTEE traffic is the ids above.

## What SN90 is — and is not

- **SN90 is not an inference subnet.** Same platform, better utilisation.
- Cluster AI workloads always have priority on capacity.
- SN28 is a demand channel for spare headroom. It is **not** the exclusive public-inference path — `llm.kubetee.ai` remains the Factory gateway.
- New miner onboarding stays **demand-driven** ([README — Miner onboarding](../README.md#miner-onboarding)). Idle-capacity here means unused GPUs on clusters that are already live, not onboarding miners ahead of Factory demand.

## Free window (closed)

During the free window, buyers used **14,812,329,857** tokens (~15 billion). That load is what hardened GLM-5.2 and Flash-0731 before the paid sayGM offers.

## Operator notes

- Phala CVM holds the LiteLLM key (`--kubetee`). `declare-product` is registry-only; a new SKU does not require a miner image bump when Envoy already forwards `kubetee` to `llm.kubetee.ai`.
- Flash listing: [taostat/gm-miner#193](https://github.com/taostat/gm-miner/pull/193) (docs, merged 2026-08-19). Registry accepted `kubetee/deepseek/deepseek-v4-flash-0731` the same day.
- SN28 Alpha on hotkey `sn28` is swapped SN28→SN90 and recycled — [SN28-SN90-ALPHA-RECYCLE.md](./SN28-SN90-ALPHA-RECYCLE.md).
- Manifests and gateway wiring: `nim/CLAUDE.md` (gm-miner section).

## Community

Questions in the public channel, not DMs. KubeTEE never DMs first.
