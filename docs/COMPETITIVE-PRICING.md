# Competitive Pricing & Miner Scoring

This document is the full design behind the README [Validator Scoring & Attestation](../README.md#validator-scoring--attestation) → [Competitive Pricing](../README.md#competitive-pricing) subsection. It covers how SN90 (KubeTEE) keeps its compute priced competitively against the other Bittensor compute subnets — **Targon (SN4)**, **Lium (SN51)**, and **Chutes (SN64)** — and how that competitive price signal feeds miner weights.

> **Status — the Targon supply-side payout feed and the Taostats
> compensation feed are implemented and live (v1).** The Bittensor validator
> v1 reads `https://stats.targon.com/api/miners` each cycle, takes the
> **highest** miner `$/card` per GPU class, and clamps the GPU price card downward
> (fail-soft: live → cache → card). It also fetches TAO/USD from the
> (fail-soft: live → cache → card). It also fetches TAO/USD from the
> Taostats API and reads alpha→TAO directly from the on-chain metagraph
> (`mg.price`, zero delay) to size the miner share in USD; a Taostats
> feed failure skips the cycle and the previous on-chain weights persist
> (fail-closed). See `validator/targon_payout_feed.py` and
> `validator/price_feed.py` for the running code.
>
> **Not implemented.** Nothing scrapes Lium or Chutes. No per-job-class target
> price is computed, no miner is scored on price competitiveness, and Armada
> queue depth is not measured. The demand-side half of the formula below is
> unbuilt — read those sections as the design to build toward.
>
> **Two different price feeds — do not confuse them.** A compensation
> price-feed module fetches TAO/USD from Taostats and reads alpha→TAO from
> the on-chain metagraph (`mg.price`) each cycle so scoring can size the
> miner share in USD; a feed failure skips the cycle.
> That is *compensation* pricing (how much Alpha a miner earns), not
> *competitive* pricing (whether a miner's delivered compute is priced
> against the market). Note the opposite failure contracts: the Taostats
> feed decides whether weights are computable at all and so fails
> **closed**, while the Targon feed only refines a committed card and so fails
> **soft**. See [README → What Ships Today](../README.md#what-ships-today).

---

## Why competitive pricing matters

SN90 sells confidential compute. Its competitors are not other inference subnets in the abstract — they are three specific subnets that already sell GPU/CPU compute or inference, each with a public, machine-readable feed. Two of them expose a **demand-side** price (what customers pay to rent or consume compute) and one exposes a **supply-side** payout (what the network pays a miner per unit of compute). SN90 must stay competitive on **both sides**: priced so customers do not route to Lium/Chutes, and paying miners enough that they do not migrate to Targon. If SN90 prices far above its demand-side competitors, the [cross-subnet consumption loop](./TOKENOMICS.md) never spins up. If it pays miners far below Targon's per-card payout, miners leave and capacity exits. If it prices far below everyone, miners subsidize customers below cash cost and the [DePIN subsidy ratio](./TOKENOMICS.md) never crosses over.

The validator's job is therefore not just to check that miners are alive — it is to score miners on whether they **deliver compute at a price that is competitive with the other compute subnets**. The price is not set by the owner; it is **discovered each epoch from competitor data and SN90's own demand**, and miners are scored against it.

## The three competitor subnets

Each competitor exposes a **verifiable** signal — a public API (supply-side payout for Targon, demand-side listing prices for Lium/Chutes) and on-chain metagraph data for emission/attestation proof. In the design, the validator pulls both and cross-checks them.

| Subnet | Operator | What it sells | Verifiable feed | Verifiable on-chain source |
|--------|----------|---------------|-----------------|----------------------------|
| **Targon (SN4)** | Manifold Labs | Confidential GPU/CPU compute + OpenAI-compatible inference, TEE-attested (Intel TDX + NVIDIA CC) | `https://stats.targon.com/api/miners` — per-miner emission **payout** by `compute_type` (e.g. H200) and `cards` (GPU count); attestation errors via Epistula-signed `/attest/error/{miner_id}` | Bittensor metagraph — SN4 emission share, miner count, attestation state |
| **Lium (SN51)** | Datura-ai | Decentralized GPU rental marketplace (raw GPU pods) | `https://lium.io/api` REST API + Python SDK/CLI — real-time node pricing by GPU type | Bittensor metagraph — SN51 emission share, provider count |
| **Chutes (SN64)** | Chutes | Inference / subscription endpoints (an example AI-service consumer of SN90) | Chutes API — per-token and subscription inference pricing | Bittensor metagraph — SN64 emission share, EMA price |

All three are read-only, public feeds. The validator never authenticates as a customer; it scrapes published pricing the same way a price-comparison site would, and it reads the metagraph for the on-chain emission/attestation cross-check. None of this is trust-based — a competitor could lie on a listing, but the on-chain emission share and the metagraph are independently verifiable by anyone.

### What each feed gives us

- **Targon (SN4)** — the closest direct competitor: confidential GPU compute, TEE-attested. Targon no longer uses a bidding/auction system; its public stats API (`https://stats.targon.com/api/miners`) exposes each miner's **emission payout by compute class and card count** (e.g. `compute_type=H200`, `cards=8`, `payout=...`), plus attestation-error state behind Epistula-signed headers. This is a **supply-side** signal — what the network pays a miner per unit of confidential compute — and it is the benchmark SN90 must keep miner compensation competitive with, or miners migrate to SN4. It is also an attestation benchmark: Targon's per-miner attestation-error feed is the same "no valid attestation → no emissions" posture SN90 adopts.
- **Lium (SN51)** — the **raw GPU rental** benchmark: per-GPU-type hourly pricing on a marketplace, no confidentiality premium. This is the floor for *non-confidential* GPU rental (the **demand-side** price customers pay to rent a bare GPU pod); the gap between Lium's rental price and Targon's per-card payout is the confidential-compute premium the market pays.
- **Chutes (SN64)** — the **demand-side** inference benchmark, and one example of the AI-service consumers in the loop: Chutes pays fiat for inference and swaps TAO for SN90 Alpha to consume SN90 compute. Chutes' own inference pricing is the ceiling the end-customer will bear, which bounds what SN90 can charge any inference consumer and still let them keep a margin. SN90 serves subnets and AI services generally — Chutes is the concrete feed the design names, not the only consumer.

### Live Targon benchmark (8-card GPU nodes)

The Targon stats API returns each miner's per-epoch emission **payout** by `compute_type` and `cards`. As of this writing, every Targon GPU miner runs an **8-card node** — the same form factor SN90 requires — so the per-8-card-node payout is the direct supply-side benchmark for SN90 miner compensation. Current live values (fetched from `GET https://stats.targon.com/api/miners`):

| `compute_type` | TEE | GPU | Payout / 8-card node / epoch | Per GPU |
|-----------------|-----|-----|-------------------------------|---------|
| `TDX-BLACKWELL-NVIDIA-B300` | Intel TDX | B300 | 64 | 8.0 |
| `TDX-BLACKWELL-NVIDIA-B200` | Intel TDX | B200 | 52 | 6.5 |
| `TDX-HOPPER-NVIDIA-H200` | Intel TDX | H200 | 28 | 3.5 |
| `TDX-VM-NVIDIA-H200` | Intel TDX (VM) | H200 | 27.84 | 3.48 |
| `TDX-HOPPER-NVIDIA-H100` | Intel TDX | H100 | 24 | 3.0 |
| `TDX-VM-NVIDIA-RTX6000B` | Intel TDX (VM) | RTX 6000 Blackwell | 16 | 2.0 |
| `SEV-CPU-AMD-EPYC-V4` | AMD SEV | CPU (1-card node) | 0.2 | 0.2 |

The payout is in TAO emission units per epoch; the validator normalizes to a per-GPU-hour figure at runtime using the current TAO price and epoch length. The **durable signal is the relative ranking**, which tracks the confidential-compute market's valuation of newer / higher-memory GPUs: B300 pays ~2.7× H100 per card, B200 ~2.2× H100, H200 ~1.17× H100. Two H200 variants appear (`TDX-HOPPER` GPU-passthrough vs `TDX-VM` virtualized) at near-identical payout (~28), so Targon prices the GPU model, not the virtualization mode. SN90's per-8-card-node emission must sit in this band — paying an 8-card H100 node roughly what Targon pays it (~24), an 8-card B200 node roughly ~52, an 8-card B300 node roughly ~64 — or miners migrate to SN4. In the design, the validator's `targon_payout_per_gpuhr[c]` input (see [formula](#the-target-price-formula-design)) is read live from this endpoint each epoch rather than hardcoded.

> **This is to be read live.** The committed `DEFAULT_USD_CARD` —
> H100 $4.00, H200 $5.50, B200 $8.00, B300 $10.00, RTX6000 $2.50 per GPU-hour —
> is the **target max**. With the Targon payout feed enabled, the validator will pull
> the numbers above from `stats.targon.com` each hour and let them clamp the
> card downward. See the next section.

## The live payout feed (spec)

The validator will not treat the table above as a frozen snapshot. Each
class is repriced from Targon's actual payouts, subject to two bounds.

### One publisher, many readers

If every validator polled Targon independently they would sample at different
moments, derive different prices, and set different weights for identical
fleets — consensus divergence for no benefit. Instead the **subnet-owner
validator** polls Targon, builds a snapshot, and publishes it to a public
object on [Hippius (SN75)](https://docs.hippius.com/storage/s3/integration)
S3; every other validator reads that object. Roles are self-configuring: a
validator holding `KUBETEE_HIPPIUS_SECRET_KEY` publishes, any other reads.

The payload is unsigned. It is public aggregate data from a public API, so it
needs no confidentiality, and three things carry the integrity weight instead:
the S3 write credential is the access control, TLS is the authenticated
channel, and the cap and floor bound the damage. Even a fully
attacker-controlled object cannot move a class outside
`[floor_frac x card, card]`. **The bucket policy must grant public READ
only** — public write would hand a passer-by the price input for every
validator on the subnet.

### How a class is priced

Targon lists several `compute_type` variants per GPU class at *different*
payouts (`TDX-HOPPER-NVIDIA-H200` pays 3.50/card, `TDX-VM-NVIDIA-H200` pays
3.16), so they must collapse into one number. The feed takes the **highest**
miner `$/card` in that class — what the best-paid SN4 node of that GPU type
earns — then still clamps to `[floor_frac × card, card]`. A low-paying
variant (e.g. TDX-VM) no longer pulls the class down.

Two bounds then apply, both enforced in the payout-feed price derivation:

- **Cap at the card.** The committed card is the target *max*: a live payout
  can only pull SN90 pay **down** toward SN4, never above it. If Targon raised
  B300 to $12.00, SN90 would stay at $10.00.
- **Floor at `floor_frac x card`** (default 0.75, `KUBETEE_TARGON_PRICE_FLOOR_FRAC`).
  A class can be a single Targon node — B200 is exactly one today — so without
  a floor one miner could drag a whole class down. It doubles as the bound
  that makes an unauthenticated feed safe to consume.

### The card itself is published too (and envelope-bounded)

The card is a **consensus parameter**, not a local preference: two validators
pricing the same fleet from different cards set different weights for it. While
the card was compiled in, every re-card meant a fleet-wide image rollout and the
subnet disagreed with itself until the last validator upgraded. So the owner
publishes the card to a **separate object** (`price-card.json`) in the same
bucket — separate because a rarely-changing owner decision and an hourly
observation should not share an epoch or a cadence.

Neither the bucket nor either object name should be configurable. Every validator has
to read the objects the *owner* writes, so an env var there could only ever
point one validator at different data and have it price a fleet differently —
the divergence the shared object exists to remove. Both should be pinned in code.

This is the one place the reasoning above could have eaten itself. The payout
snapshot is safe while unsigned *because the card bounds it*; shipping the card
over that same unsigned channel would put the bound under the same control as the
value it bounds, and `[floor_frac x card, card]` would stop meaning anything. So a
published card is never trusted as-is — a `clamp_to_envelope` check holds every
class inside `[0.8x, 1.25x]` of the **compiled-in** `DEFAULT_USD_CARD`:

| Class | Compiled-in | Published card may set |
|-------|-------------|------------------------|
| H100 | $4.00 | $3.20 – $5.00 |
| H200 | $5.50 | $4.40 – $6.875 |
| B200 | $8.00 | $6.40 – $10.00 |
| B300 | $10.00 | $8.00 – $12.50 |
| RTX6000 | $2.50 | $2.00 – $3.125 |

The compiled-in card stays the trust root; it just stopped being the value. A
hostile object can retune pay within the band but cannot zero it or mint
arbitrary emission, and moving outside the band is deliberately a code change.

Two details exist for consensus rather than security, and both are easy to
"simplify" wrongly. The envelope is anchored to the compiled-in default and
**not** to the operator's `KUBETEE_GPU_USD_PRICES` override — an operator-specific
anchor would have two honest validators clamp the same published card to
different numbers, which is the precise divergence the shared object exists to
remove. For the same reason, a class the card omits falls back to the
compiled-in price, not the local one.

A class with no usable live price falls back to the card, which covers both a
`0.00` payout and a class Targon does not list.

### Losing a source: fatal at startup, survivable afterwards

The Targon clamp is always on: SN4 payouts may pull pay *down* toward the
live feed, floored at `KUBETEE_TARGON_PRICE_FLOOR_FRAC` of the card. The card
is what every validator prices with in the first place. Every validator
therefore reads `price-card.json` on every cycle, and the degradation rules
differ by *when* the failure happens:

| Situation | Behavior |
|-----------|----------|
| Targon unreachable (publisher) | Read `payout.json` instead — the last published snapshot is real observed data |
| Store also unreachable | Keep the last known snapshot from the previous epoch (cached on disk) |
| Card unreadable, one already held | Keep the previous epoch's card, log `price card unavailable`, **still set weights** |
| Card unreadable at **startup**, nothing cached | **Refuse to start** (`CardUnavailableError`, exit 2) |

The asymmetry is the point. A validator that has never held a card has never
agreed with the subnet on what a GPU-hour is worth, and scoring a fleet off the
compiled-in anchor would set real weights from a number the owner may have
retuned long ago — silently. Once it holds a card the opposite applies: a
skipped cycle denies miners emission for a fault entirely on the validator's
side, so an outage costs the previous epoch's prices rather than the cycle.

Both the payout snapshot and the card are cached in the scoring state file
(`payout_cache` / `price_card_cache`), so this survives a restart and a store
outage does not compound into a validator that cannot boot. The startup failure
is usually transient, so it exits non-zero for the supervisor to retry rather
than demanding an operator fix.

A cached card is re-clamped to the envelope on every read, not just when it is
fetched: clamping is a property of *consuming* a card, so one that was
in-envelope when written cannot drift out of one by being replayed from disk
under a changed anchor.

### Effect at the values measured on 2026-07-26

| Class | Live per card | Card | Effective | Change |
|-------|---------------|------|-----------|--------|
| H100 | 3.0000 | 3.00 | 3.0000 | — |
| **H200** | **3.2922** | **3.50** | **3.2922** | **−5.9%** |
| B200 | 6.5000 | 6.50 | 6.5000 | — |
| B300 | 8.0000 | 8.00 | 8.0000 | — |

Only H200 used to move under the old **average**, because it was the only
class whose variants disagreed: 7 TDX-HOPPER nodes at 3.50 against 11 TDX-VM
nodes at 3.16 averaged to 3.2922. The feed now takes the **highest** miner
rate in the class (3.50 for that snapshot), so H200 sits at the card instead
of a pay cut from TDX-VM nodes. Caps still apply: live above the card is
clamped down.

### Failure behaviour

Pricing degrades **live → last known → card**, and no branch skips a cycle.
Last-known pricing is persisted beside the reliability state (so it survives a
crash or restart) and **never expires**: a long Targon outage is surfaced as
`kubetee_targon_price_age_seconds` and a per-cycle warning rather than
silently jumping prices back up to the ceiling. Because the cap means stale
data can only ever *overpay* relative to SN4, holding it indefinitely is the
safe direction.

Since nothing authenticates the object, validation is the only content gate
and rejects the whole snapshot on any violation: wrong version, unknown GPU
class, non-positive price, an epoch older than the last accepted one
(rollback), or an epoch more than two hours in the future. That last bound
exists *because* of the monotonicity rule — without it, one bogus write would
permanently deny every later legitimate snapshot.

## The price SN90 targets

The validator computes a **target price** per SN90 job class (e.g. H100/H200/B200/B300 GPU-hour, CPU-hour, per-token inference) each epoch. The target is a function of three inputs:

1. **The compute needed** — the job class (GPU type, GPU-hours, CPU-hours, or per-token). Price is computed *per class*, not as a single flat number.
2. **Competitor signals for the same class** — Targon's per-miner **payout** by `compute_type`/`cards` (supply-side, from `stats.targon.com`) and Lium's and Chutes's **listing prices** (demand-side), each cross-checked against the on-chain metagraph that epoch.
3. **SN90 demand** — Armada queue depth and scheduling wait time for that job class. High unmet demand means the price can rise; empty queues mean it should fall.

### The target-price formula (design)

For a job class `c` each epoch, the validator normalizes the three competitor signals to a common unit (effective $/GPU-hour or emissions-per-GPU-hour) before combining them:

```
supply_benchmark[c]    = targon_payout_per_gpuhr[c]            # from stats.targon.com (supply-side)
demand_benchmark[c]   = mean( lium[c], chutes[c] )            # demand-side listing prices
competitor_avg[c]     = mean( supply_benchmark[c], demand_benchmark[c] )
demand_pressure[c]    = f( armada_queue_depth[c], wait_time[c] )  # 0..1, higher = more demand

target_price[c] = competitor_avg[c]
                * ( 1 + alpha * demand_pressure[c] )      # demand pulls price up
                * confidential_premium[c]                # TEE/CoCo premium vs Lium baseline
```

Where:

- `targon_payout_per_gpuhr[c]` is derived from the stats API: per-miner `payout` divided by `cards` and normalized to a per-GPU-hour figure using the epoch length — the supply-side anchor that keeps SN90 miner compensation competitive with SN4. **This term is the first to be implemented** ([above](#the-live-payout-feed-spec)); the demand-side terms below are not.
- `alpha` is a published, bounded coefficient (the glide path, not surprise) — the same "programmatic commitment, not discretion" posture as the [no-treasury](./TOKENOMICS.md) policy.
- `confidential_premium[c]` is bounded by the observed Targon-payout-vs-Lium-rental gap, so SN90 never claims a premium larger than the market already pays for confidentiality.
- The formula is **monotonic and published** — anyone can recompute the target price from the same public feeds and confirm the validator used it. No discretionary pricing.

### Wash consumption (open question)

`demand_pressure[c]` is the one term a miner can influence by submitting its own jobs: fake queue depth raises the target price for everyone, which makes every miner easier to score at-or-below target. The [tokenomics boundary conditions](./TOKENOMICS.md) require self-consumption to be **economically neutral**, so this term needs a defense before it can bear weight — candidates are charging the submitter the target price (so wash spend costs real Alpha), excluding a miner's own jobs from the demand signal it benefits from, or capping `alpha` low enough that the gain never exceeds the spend. **Unresolved.**

## How the price signal becomes weights

The target price is a **scoring input**, not a bill. Miners do not pay it; they are scored on how their delivered compute compares to it. Each epoch, per miner:

1. **Capacity score** — the miner's capacity/health score, unchanged by this design. Note that the planned starting point is **infrastructure-readiness only** (gated by a `PROBATION` → `EARNING` reliability machine); fresh TEE attestation and Armada job metrics are themselves still planned gates, so this step is not as rich as it reads.
2. **Price-competitiveness score** — for each job class the miner served, compare the miner's effective price (emissions earned ÷ compute delivered, normalized to the same units as the competitor feeds) to `target_price[c]`:
   - At or below target → full credit (competitive).
   - Modestly above target → reduced credit (priced out of the market).
   - Far above target → zero credit for that class (would lose demand to Targon/Lium/Chutes).

The final weight is the capacity score gated by the price-competitiveness score: **a miner with perfect attestation but a price 2× the competitor average scores low**, because the subnet would lose demand to SN4/SN51/SN64 if that miner set the market price. This is what "competitive with the other subnets" means mechanically — the weight vector rewards miners that keep SN90 in the competitive band.

### What is NOT scored

- The validator does **not** set a price floor or ceiling by fiat. The target is discovered, not decreed.
- The validator does **not** favor miners for undercutting below the target — that would re-introduce the below-cash-cost race the subsidy ratio is meant to avoid. At-or-below-target is full credit; lower is not better.
- The validator does **not** score on competitor emission share directly — that is a network-health metric, not a per-miner score. It is published as a KPI alongside the [subsidy ratio](./TOKENOMICS.md).

## Data sources & verifiability

| Signal | Source | How the validator reads it | How anyone verifies it |
|--------|--------|----------------------------|-------------------------|
| Targon payout (supply-side) — **to be read live** | `https://stats.targon.com/api/miners` | read-only GET, no auth — per-miner `payout`/`compute_type`/`cards`; owner validator publishes the derived snapshot, others read it | same public endpoint, or the published snapshot object |
| Lium price (demand-side) | `https://lium.io/api` | read-only REST | same public endpoint |
| Chutes price (demand-side) | Chutes API | read-only scrape | same public endpoint |
| Competitor emission/attestation | Bittensor metagraph | `btcli subnets metagraph` / SDK | any Bittensor indexer (TaoStats, etc.) |
| SN90 demand | Armada queues | queue depth + wait time per job class | Armada metrics |
| Target price | computed | published formula over the above | recompute from the same feeds |

Every input is either a public API or on-chain data. The validator would publish the scraped competitor payouts/prices and the computed target price each epoch as Prometheus metrics, so the weight vector stays auditable end-to-end: anyone could confirm the validator scored miners against the real market signals, not a number it invented. The Targon row is the first to be read (see the status note at the top); the rest of the table describes what each source would supply.

The Targon row is designed to meet that auditability bar: metrics such as `kubetee_targon_live_usd_per_card` and `kubetee_effective_usd_per_card` should expose the live and post-clamp figures per class, `kubetee_pricing_source` should say whether the cycle priced off the feed, the cache, or the card, and `kubetee_targon_price_age_seconds` should say how stale that was. Anyone can recompute all of it from the same public endpoint or the published snapshot.

## Roadmap alignment

- **Phase 0 (shipped):** the USD price card plus a Taostats TAO/USD +
  on-chain alpha→TAO feed (compensation price feed) that denominates the
  miner emission share in USD each cycle. This is the *compensation* half
  — it keeps SN90 miner pay in the Targon band.
- **Phase 0 (shipped):** the **live Targon supply-side read**
  (payout feed), published once by the owner validator and consumed by all
  others, clamping the card downward toward what SN4 actually pays. The card is
  not a frozen snapshot.
- **Phase 0 (planned extension):** add the demand-side half — Lium/Chutes
  scraping, target-price computation, and price-competitiveness weighting — and
  use that target price as the **resources price per hour** for Alpha / TAO
  paid jobs (demand-side billing, dynamic per the job queues). The initial
  miner score is limited to infrastructure readiness.
- **Phase 1 (Expansion):** add TEE-attestation + Armada-job-metrics + health scoring.
- **Phase 2 (Paid Jobs):** layer **USDC-on-BASE and TAO-on-BASE billing** on top of the Phase 0 resources-per-hour pricing, plus USDC→TAO-on-BASE→Finney TAO→Alpha recycling. TAO is live on Base as a Chainlink CCIP-bridged ERC-20 (2026-08-21; [ForeverMoney SN98](https://x.com/forevermoney_ai/status/2090469070248235027)).
- **Phase 3 (Job-Type Growth):** extend the price formula to new job classes as new workload types come online.

## References

- [Targon (SN4)](https://targon.com) — confidential compute marketplace
- [Targon Stats API docs](https://stats.targon.com/docs) — per-miner payout by `compute_type`/`cards` + attestation-error endpoints (supply-side signal). `api/miners` is the documented, machine-readable source and the one we consume. 
- [Hippius (SN75) S3](https://docs.hippius.com/storage/s3/integration) — decentralized object store hosting the published payout snapshot
- [Lium (SN51) docs](https://docs.lium.io/intro) — GPU rental marketplace
- [Lium SDK](https://docs.lium.io/developers/sdk) — REST API + Python SDK
- [Bittensor metagraph](https://docs.bittensor.com/) — on-chain emission/attestation data
- [Tokenomics — Utility Token & DePIN Model](./TOKENOMICS.md) — subsidy ratio, crossover, wash-consumption defenses
