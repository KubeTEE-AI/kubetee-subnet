# Competitive Pricing & Miner Scoring

This document is the full design behind the README [Validator Scoring & Attestation](../README.md#validator-scoring--attestation) → [Competitive Pricing](../README.md#competitive-pricing) subsection. It covers how SN90 (KubeTEE) keeps its compute priced competitively against the other Bittensor compute subnets — **Targon (SN4)**, **Lium (SN51)**, and **Chutes (SN64)** — and how that competitive price signal feeds miner weights.

> **Status:** competitive pricing is an **Early Access (Phase 0)** scoring dimension — it is required to price the Alpha / TAO **compute units (CU)** consumers pay for compute (demand-side), and it doubles as a miner-scoring input. The target price is **competitive** (benchmarked vs Targon/Lium/Chutes) and **dynamic according to the job queues** (Armada queue depth + the 75% utilization target). The shipping Early Access validator scores node liveness only until the price feeds are wired (see the [Early Access stand-in](../SUBNET.md) caveat). This document is the design target.

---

## Why competitive pricing matters

SN90 sells confidential compute. Its competitors are not other inference subnets in the abstract — they are three specific subnets that already sell GPU/CPU compute or inference, each with a public, machine-readable feed. Two of them expose a **demand-side** price (what customers pay to rent or consume compute) and one exposes a **supply-side** payout (what the network pays a miner per unit of compute). SN90 must stay competitive on **both sides**: priced so customers do not route to Lium/Chutes, and paying miners enough that they do not migrate to Targon. If SN90 prices far above its demand-side competitors, the [cross-subnet consumption loop](./TOKENOMICS.md) never spins up. If it pays miners far below Targon's per-card payout, miners leave and capacity exits. If it prices far below everyone, miners subsidize customers below cash cost and the [DePIN subsidy ratio](./TOKENOMICS.md) never crosses over.

The validator's job is therefore not just to check that miners are alive — it is to score miners on whether they **deliver compute at a price that is competitive with the other compute subnets**, while keeping the subnet's own fleet at a healthy utilization. The price is not set by the owner; it is **discovered each epoch from competitor data and SN90's own utilization**, and miners are scored against it.

## The three competitor subnets

Each competitor exposes a **verifiable** signal — a public API (supply-side payout for Targon, demand-side listing prices for Lium/Chutes) and on-chain metagraph data for emission/attestation proof. The validator pulls both and cross-checks them.

| Subnet | Operator | What it sells | Verifiable feed | Verifiable on-chain source |
|--------|----------|---------------|-----------------|----------------------------|
| **Targon (SN4)** | Manifold Labs | Confidential GPU/CPU compute + OpenAI-compatible inference, TEE-attested (Intel TDX + NVIDIA CC) | `https://stats.targon.com/api/miners` — per-miner emission **payout** by `compute_type` (e.g. H200) and `cards` (GPU count); attestation errors via Epistula-signed `/attest/error/{miner_id}` | Bittensor metagraph — SN4 emission share, miner count, attestation state |
| **Lium (SN51)** | Datura-ai | Decentralized GPU rental marketplace (raw GPU pods) | `https://lium.io/api` REST API + Python SDK/CLI — real-time node pricing by GPU type | Bittensor metagraph — SN51 emission share, provider count |
| **Chutes (SN64)** | Chutes | Inference / subscription endpoints (an example AI-workload consumer of SN90) | Chutes API — per-token and subscription inference pricing | Bittensor metagraph — SN64 emission share, EMA price |

All three are read-only, public feeds. The validator never authenticates as a customer; it scrapes published pricing the same way a price-comparison site would, and it reads the metagraph for the on-chain emission/attestation cross-check. None of this is trust-based — a competitor could lie on a listing, but the on-chain emission share and the metagraph are independently verifiable by anyone.

### What each feed gives us

- **Targon (SN4)** — the closest direct competitor: confidential GPU compute, TEE-attested. Targon no longer uses a bidding/auction system; its public stats API (`https://stats.targon.com/api/miners`) exposes each miner's **emission payout by compute class and card count** (e.g. `compute_type=H200`, `cards=8`, `payout=...`), plus attestation-error state behind Epistula-signed headers. This is a **supply-side** signal — what the network pays a miner per unit of confidential compute — and it is the benchmark SN90 must keep miner compensation competitive with, or miners migrate to SN4. It is also an attestation benchmark: Targon's per-miner attestation-error feed is the same "no valid attestation → no emissions" posture SN90 adopts.
- **Lium (SN51)** — the **raw GPU rental** benchmark: per-GPU-type hourly pricing on a marketplace, no confidentiality premium. This is the floor for *non-confidential* GPU rental (the **demand-side** price customers pay to rent a bare GPU pod); the gap between Lium's rental price and Targon's per-card payout is the confidential-compute premium the market pays.
- **Chutes (SN64)** — the **demand-side** inference benchmark, and one example of the AI-workload consumers in the loop: Chutes pays fiat for inference and swaps TAO for SN90 Alpha to consume SN90 compute. Chutes' own inference pricing is the ceiling the end-customer will bear, which bounds what SN90 can charge any inference consumer and still let them keep a margin. SN90 serves subnets and AI workloads generally — Chutes is the concrete feed the validator scrapes today, not the only consumer.

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

The payout is in TAO emission units per epoch; the validator normalizes to a per-GPU-hour figure at runtime using the current TAO price and epoch length. The **durable signal is the relative ranking**, which tracks the confidential-compute market's valuation of newer / higher-memory GPUs: B300 pays ~2.7× H100 per card, B200 ~2.2× H100, H200 ~1.17× H100. Two H200 variants appear (`TDX-HOPPER` GPU-passthrough vs `TDX-VM` virtualized) at near-identical payout (~28), so Targon prices the GPU model, not the virtualization mode. SN90's per-8-card-node emission must sit in this band — paying an 8-card H100 node roughly what Targon pays it (~24), an 8-card B200 node roughly ~52, an 8-card B300 node roughly ~64 — or miners migrate to SN4. The validator's `targon_payout_per_gpuhr[c]` input (see [formula](#the-target-price-formula-design)) is read live from this endpoint each epoch, not hardcoded.

## The price SN90 targets

The validator computes a **target price** per SN90 job class (e.g. H100/H200/B200/B300 GPU-hour, CPU-hour, per-token inference) each epoch. The target is a function of four inputs the user specified:

1. **The compute needed** — the job class (GPU type, GPU-hours, CPU-hours, or per-token). Price is computed *per class*, not as a single flat number.
2. **Competitor signals for the same class** — Targon's per-miner **payout** by `compute_type`/`cards` (supply-side, from `stats.targon.com`) and Lium's and Chutes's **listing prices** (demand-side), each cross-checked against the on-chain metagraph that epoch.
3. **SN90 demand** — Armada queue depth and scheduling wait time for that job class. High unmet demand means the price can rise; empty queues mean it should fall.
4. **The 75% utilization target** — the equilibrium anchor. SN90 aims to keep its fleet at an **average of 75% of capacity**. Below 75%, price is pushed down to attract demand and fill capacity; at 75%, price sits at the competitor average; above 75%, price is pushed up to ration demand and preserve headroom.

### The target-price formula (design)

For a job class `c` each epoch, the validator normalizes the three competitor signals to a common unit (effective $/GPU-hour or emissions-per-GPU-hour) before combining them:

```
supply_benchmark[c]    = targon_payout_per_gpuhr[c]            # from stats.targon.com (supply-side)
demand_benchmark[c]   = mean( lium[c], chutes[c] )            # demand-side listing prices
competitor_avg[c]     = mean( supply_benchmark[c], demand_benchmark[c] )
demand_pressure[c]    = f( armada_queue_depth[c], wait_time[c] )  # 0..1, higher = more demand
utilization[c]        = used_capacity[c] / total_capacity[c]     # 0..1, measured this epoch
util_gap[c]           = utilization[c] - 0.75                   # signed; 0 at target

target_price[c] = competitor_avg[c]
                * ( 1 + alpha * demand_pressure[c] )      # demand pulls price up
                * ( 1 + beta * util_gap[c] )              # below 75% -> discount; above -> premium
                * confidential_premium[c]                # TEE/CoCo premium vs Lium baseline
```

Where:

- `targon_payout_per_gpuhr[c]` is derived from the stats API: per-miner `payout` divided by `cards` and normalized to a per-GPU-hour figure using the epoch length — the supply-side anchor that keeps SN90 miner compensation competitive with SN4.
- `alpha`, `beta` are published, bounded coefficients (the glide path, not surprise) — the same "programmatic commitment, not discretion" posture as the [no-treasury](./TOKENOMICS.md) policy.
- `confidential_premium[c]` is bounded by the observed Targon-payout-vs-Lium-rental gap, so SN90 never claims a premium larger than the market already pays for confidentiality.
- The formula is **monotonic and published** — anyone can recompute the target price from the same public feeds and confirm the validator used it. No discretionary pricing.

### Why 75% utilization

75% is the standard cloud-utilization equilibrium: high enough that the fleet is earning (not sitting idle), low enough that there is headroom to absorb a demand spike without instantly rationing. It is the single knob that balances the [DePIN subsidy trajectory](./TOKENOMICS.md):

- **Below 75%** → subsidy is wasted on idle capacity → target price drops to pull demand in → utilization rises.
- **At 75%** → equilibrium → target price ≈ competitor average → consumers fund the miner budget through the pool (the crossover condition).
- **Above 75%** → demand exceeds comfortable capacity → target price rises to ration → miners earn more per unit, subsidy ratio falls, the post-crossover deflationary regime engages.

The 75% target is also the **wash-consumption defense**: a miner that spins up fake jobs to inflate its utilization score pushes the subnet above 75%, which *raises* the target price and makes the miner's own wash spend more expensive — the same "make self-consumption economically neutral" principle from the tokenomics boundary conditions.

## How the price signal becomes weights

The target price is a **scoring input**, not a bill. Miners do not pay it; they are scored on how their delivered compute compares to it. Each epoch, per miner:

1. **Capacity score** — the existing TEE-attestation + Armada-job-metrics + infrastructure-health score (unchanged).
2. **Price-competitiveness score** — for each job class the miner served, compare the miner's effective price (emissions earned ÷ compute delivered, normalized to the same units as the competitor feeds) to `target_price[c]`:
   - At or below target → full credit (competitive).
   - Modestly above target → reduced credit (priced out of the market).
   - Far above target → zero credit for that class (would lose demand to Targon/Lium/Chutes).
3. **Utilization contribution** — miners whose utilization sits near the 75% subnet target (not gaming it up, not idling) get a small bonus; miners far above (likely wash) or far below (idle) get none.

The final weight is the capacity score gated by the price-competitiveness score: **a miner with perfect attestation but a price 2× the competitor average scores low**, because the subnet would lose demand to SN4/SN51/SN64 if that miner set the market price. This is what "competitive with the other subnets" means mechanically — the weight vector rewards miners that keep SN90 in the competitive band.

### What is NOT scored

- The validator does **not** set a price floor or ceiling by fiat. The target is discovered, not decreed.
- The validator does **not** favor miners for undercutting below the target — that would re-introduce the below-cash-cost race the subsidy ratio is meant to avoid. At-or-below-target is full credit; lower is not better.
- The validator does **not** score on competitor emission share directly — that is a network-health metric, not a per-miner score. It is published as a KPI alongside the [subsidy ratio](./TOKENOMICS.md).

## Data sources & verifiability

| Signal | Source | How the validator reads it | How anyone verifies it |
|--------|--------|----------------------------|-------------------------|
| Targon payout (supply-side) | `https://stats.targon.com/api/miners` | read-only GET, no auth — per-miner `payout`/`compute_type`/`cards` | same public endpoint |
| Targon attestation errors | `https://stats.targon.com/api/miners/attest/error/{id}` | Epistula-signed GET (hotkey auth) | same endpoint with a signed hotkey |
| Lium price (demand-side) | `https://lium.io/api` | read-only REST | same public endpoint |
| Chutes price (demand-side) | Chutes API | read-only scrape | same public endpoint |
| Competitor emission/attestation | Bittensor metagraph | `btcli subnets metagraph` / SDK | any Bittensor indexer (TaoStats, etc.) |
| SN90 utilization | Armada + Prometheus | queue depth, wait time, capacity | Armada metrics + Prometheus (read-only) |
| SN90 demand | Armada queues | queue depth per job class | Armada metrics |
| Target price | computed | published formula over the above | recompute from the same feeds |

Every input is either a public API or on-chain data. The validator publishes the scraped competitor payouts/prices and the computed target price each epoch as Prometheus metrics, so the weight vector is auditable end-to-end: anyone can confirm the validator scored miners against the real market signals, not a number it invented.

## Roadmap alignment

- **Phase 0 (Early Access, current):** add the competitive-pricing dimension — competitor feed scraping, target-price computation, price-competitiveness weighting, and the 75% utilization target — and use that target price as the **compute-unit (CU) price** for Alpha / TAO paid jobs (demand-side billing, dynamic per the job queues). The shipping validator scores node liveness only until the price feeds are wired.
- **Phase 1 (Expansion):** add TEE-attestation + Armada-job-metrics + health scoring.
- **Phase 2 (Paid Jobs):** layer **USDC-on-BASE fiat billing** on top of the Phase 0 compute-unit pricing, plus referrer / reseller revenue share and USDC→TAO→Alpha recycling.
- **Phase 3 (Job-Type Growth):** extend the price formula to new job classes as new workload types come online.

## References

- [Targon (SN4)](https://targon.com) — confidential compute marketplace
- [Targon Stats API docs](https://stats.targon.com/docs) — per-miner payout by `compute_type`/`cards` + attestation-error endpoints (supply-side signal)
- [Lium (SN51) docs](https://docs.lium.io/intro) — GPU rental marketplace
- [Lium SDK](https://docs.lium.io/developers/sdk) — REST API + Python SDK
- [Bittensor metagraph](https://docs.bittensor.com/) — on-chain emission/attestation data
- [Tokenomics — Utility Token & DePIN Model](./TOKENOMICS.md) — subsidy ratio, crossover, wash-consumption defenses
