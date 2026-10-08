# What Alpha Buys Today — Verifiable Compute Access

This is the demand-side snapshot behind the token model in
[Tokenomics — Utility Token & DePIN Model](./TOKENOMICS.md): what SN90 Alpha
actually buys on the live Factory surface, as of **2026-10-08**. The
utility-token claim is only as good as the consumption behind it, so the
catalogue is stated here in economic terms: SN90 Alpha buys **confidential
compute access** on real hardware, at published prices, with the delivered
service verifiable.

## The Factory's live surface

| Compute service class | Example SKUs on `llm.kubetee.ai` | Hardware per serve |
|---|---|---|
| Large-model inference | GLM-5.2, GLM-5.3, GLM-5.3-Flash, Ornith-1.5-397B | 8× B200 / 8× H200 |
| Any-to-any multimodal understanding (text / image / video / audio → text, reasoning + tools) | **Nemotron-3-Nano-Omni** (live 2026-10-08, eval-only pending license) | 1× H100 |
| Generation (images / video+audio) | FLUX.2-klein-4B, MiniMax-H3 (`/v1/videos`) | 1–2× H200 |
| Speech synthesis | Magpie-TTS-Zeroshot, MOSS-TTS-v1.5 | 1× H100 |

## Why this supports the token model

Two properties matter for the token model in [TOKENOMICS.md](./TOKENOMICS.md):

1. **The compute is attested, so the access is real property, not a metered
   favor.** Every serve above runs in a Kata TDX + NVIDIA CC guest with CoCo
   attestation and client-facing nonce-bound TDX quotes
   ([Client-Facing Attestation](./CLIENT-FACING-ATTESTATION.md)) — a consumer
   pays for *provable* confidential execution, which is what makes Alpha a
   digital commodity with programmatic utility rather than a points system.
2. **Demand-side measurement already exists.** The LiteLLM gateway's virtual
   keys, hierarchical budgets, and spend tracking are the metering surface for
   Phase 2 resources-per-hour billing (see
   [Subnet Economics](../README.md#subnet-economics)); per-token and
   per-GPU-hour prices are the published price card the
   [Competitive Pricing](./COMPETITIVE-PRICING.md) machinery scores miners
   against. Consumption measured today is the denominator of the
   [DePIN subsidy trajectory](./TOKENOMICS.md#depin-subsidy-trajectory).

## Licensing boundary

Research-licensed SKUs (e.g. Nemotron-3-Nano-Omni before its commercial
grant, Breeze-TTS-2) are **evaluation-only** and are deliberately excluded from
the paid surface — the utility claim is built on services SN90 is actually
licensed to sell.

---

See also: [Nemotron-3-Nano-Omni Multimodal API](./NEMOTRON-OMNI-MULTIMODAL-API.md) ·
[H3 Video Generation API](./H3-VIDEO-GENERATION-API.md) ·
[Tokenomics — Utility Token & DePIN Model](./TOKENOMICS.md)
