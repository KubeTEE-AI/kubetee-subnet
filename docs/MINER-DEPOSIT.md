# Miner Deposit (Registration Collateral)

Every KubeTEE miner posts a **100 TAO deposit**, held as on-chain registration
collateral on its own mining hotkey. It exists so that a miner accepting
confidential workloads has capital committed to the SLA it agreed to, and it is
the same amount for every miner. This document is the full reference: what the
primitive is, what it can and cannot do, and the runbooks for the subnet owner,
miners, and validators.

Summary for the impatient: the deposit is **not** a fee, **not** custodial, and
**not** slashable. It sits on the miner's own hotkey — KubeTEE never holds it
and no KubeTEE key can move it — and the enforcement mechanism is a reversible
freeze rather than a confiscation.

---

## 1. What the chain actually provides

Subtensor v437 added registration collateral. Two subnet hyperparameters drive
it, and both are snapshot per miner at registration so changes are prospective
only — raising either can never retro-lock an incumbent.

**`collateral_lock_share` (p)** splits the floating registration price `T`:

```
burned  = (1 − p) × T          # recycled exactly as before
locked  = p × T                # staked to the registering hotkey, non-withdrawable
```

Stored as a `u16` where 65535 = 100%, capped at **62258 (≈95%)** so the burned
share always stays strictly positive. Default 0, which disables collateral
entirely.

**`collateral_drain_ratio` (k)** releases the lock as the hotkey earns:

```
released_this_tempo = min(locked − min_locked, k × emission)
```

`U64F64` fixed point, bounded **0 < k ≤ 10**, default 1.0. Zero is excluded by
design — with no other exit path, `k = 0` would make the lock permanently
unrecoverable, which is a burn with extra steps.

State is keyed by `(netuid, hotkey, coldkey)` — the bonded stake *position* —
so nominators on a miner's hotkey are never frozen by the operator's bond. The
lock survives deregistration and is credited against the requirement if the same
`(hotkey, coldkey)` re-registers, valued at the subnet's moving-average price
rather than spot (spot can be pumped inside a single block).

### The three things it is not

**Not slashable.** There is no confiscation extrinsic anywhere in the pallet.
Nothing can take a bond and nobody receives one. Enforcement works by validators
refusing to score a miner: emission goes to zero, the drain halts, and the
deposit **freezes** on the miner's own hotkey until scoring resumes. Because no
one is enriched by another miner's failure, the mechanism creates no incentive
to get rivals disqualified.

**Not expressible as "100 TAO" on chain.** `p` is a fraction of the floating
registration price, capped at 95%. If registration costs τ5, the chain can lock
at most τ4.75. Any deposit larger than that share is **voluntary** — the miner
calls `add_collateral` — and the only thing that makes it mandatory is
validators declining to score a miner who is short. That is a KubeTEE policy the
chain merely holds.

**Not denominated in TAO.** The lock is alpha. A TAO-denominated requirement is
therefore converted each cycle at the subnet's moving-average price, the same
EMA the pallet uses to value standing collateral.

---

## 2. KubeTEE's two layers

| Layer | Who sets it | What it does | When |
|---|---|---|---|
| Validator | Every validator | Enforces the 100 TAO floor by withholding score | **Phase 0** |
| Chain | Subnet owner, once | `p` and `k` make registration itself partly bonded | **Phase 1** |

The validator layer is what actually produces a 100 TAO deposit, because the
chain cannot express one. It ships first: it needs no chain change, is
reversible, and can run in measure-only mode.

The chain layer bonds a slice of the entry price automatically, on top of that.
It lands in [Phase 1](../README.md#phase-1--expansion) because `collateral_drain_ratio`
can only be sized against observed per-miner emission — see §3.

---

## 3. Owner runbook (chain layer — Phase 1)

> **Not applied in Phase 0.** This section is the prepared runbook for when the
> chain layer is enabled; `collateral_drain_ratio` is sized against real
> emission data first. Nothing below needs to run for the 100 TAO deposit to be
> enforced — that is the validator gate in §5.

Both extrinsics are owner-or-root, rate limited, and must be submitted outside
the weights window.

```bash
# Read current policy
btcli sudo get --netuid 90 --name collateral_lock_share
btcli sudo get --netuid 90 --name collateral_drain_ratio

# Set: p as a 0..1 fraction (or the raw u16), k as fixed-point decimal
btcli sudo set --netuid 90 --name collateral_lock_share  --value 0.75
btcli sudo set --netuid 90 --name collateral_drain_ratio --value 1.0
```

Out-of-range values fail with `CollateralLockShareTooHigh` (p > ≈95%) or
`CollateralDrainRatioOutOfBounds` (k ≤ 0 or k > 10).

### Choosing p

`0.75` is the standard bond and the right starting point for KubeTEE: it bonds
three-quarters of the entry price while leaving a real, floating burn that still
prices sybil registration. `0.83–0.9` is for subnets defending against
short-horizon score gaming, which is not KubeTEE's threat model — our scoring is
infrastructure attestation over long windows, not per-request quality that can
be farmed in a few tempos.

### Choosing k — deferred to Phase 1

`k` sets how long a miner stays accountable. Wind-down is `headroom ÷ k`
*measured in earned emission*, and the deterrence property is that an adversary
planning to farm and abandon a hotkey must collect roughly `T / (1 + k)` before
validators stop scoring them, just to break even. Lower `k` raises that bar and
lengthens the lockup; higher `k` releases faster.

**Both chain values are set in [Phase 1](../README.md#phase-1--expansion), not
now.** `k` is only meaningful against a real per-miner emission rate, and Phase 0
does not yet have one — picking a number before that would be guessing at the
single parameter that decides how long a miner's capital stays committed. Phase
0 therefore runs the deposit through the validator gate alone (§5), which needs
no chain change and is reversible.

When the emission data exists, size it directly: with expected emission `E` alpha
per tempo and a deposit `D` alpha, wind-down is `D / (k × E)` tempos — solve for
`k` against the term you want. The target is that an honest exit takes roughly
one rental term, so a miner who stops mining recovers the deposit over a period
comparable to the hardware commitment they made, not years. For scale: at
`k = 1`, a 100 TAO deposit against a miner earning the equivalent of τ1/day
implies about a 100-day wind-down, which is very likely too long.

### What p does to tokenomics

A locked alpha is not a recycled one, so a higher `p` means proportionally less
of each registration returning to unissued supply. See
[Tokenomics — Registration collateral changes where the registration fee goes](./TOKENOMICS.md#registration-collateral-changes-where-the-registration-fee-goes).

---

## 4. Miner runbook

Check standing:

```bash
btcli query miner-collateral --netuid 90 \
  --hotkey <ss58|name> --coldkey <ss58|name> --json
```

Returns `locked_alpha`, `min_locked_alpha`, `earned_alpha`, the `drain_ratio`
snapshot, and the derived `headroom_alpha`, `shortfall_alpha`, and
`releasable_work_alpha` (emission still needed to release the headroom).

Top up to the requirement. Free stake is used first; any shortfall is bought
with TAO. Always dry-run:

```bash
btcli tx add-collateral --netuid 90 --amount-alpha <amount> --dry-run
btcli tx add-collateral --netuid 90 --amount-alpha <amount> -w my_coldkey
```

Optionally set a self-maintaining floor. Below the floor, emission is *captured*
into the lock instead of released, so the bond refills itself:

```bash
btcli tx set-min-collateral --netuid 90 --amount-alpha <amount> -w my_coldkey
```

Setting the floor at the requirement is the low-maintenance choice: it keeps the
position compliant without manual top-ups as the alpha price drifts.

**A falling alpha price raises the alpha you must hold**, because the
requirement is pegged to TAO. Validators export every miner's coverage, so the
gap is visible before it becomes a problem.

---

## 5. Validator runbook

These settings define how the rebuilt validator should gate on the deposit.
In brief:

| Variable | Default | Meaning |
|---|---|---|
| `KUBETEE_COLLATERAL_REQUIRED_TAO` | `0` | Deposit in TAO; `0` disables the gate |
| `KUBETEE_COLLATERAL_ENFORCE` | `false` | Whether a delinquent miner is scored 0 |
| `KUBETEE_COLLATERAL_GRACE_CYCLES` | `3` | Cycles below the line before withholding |
| `KUBETEE_COLLATERAL_RECOVERY_MARGIN` | `0.05` | Extra coverage needed to clear |

Both inputs ride the metagraph read the validator already performs, so the gate
costs no extra chain calls. It requires `bittensor>=11.0.1`; 11.0.0 has no
collateral support at all.

**Grace and recovery exist so the gate cannot punish price movement.** A miner
that falls below the line keeps earning through the grace window rather than
losing a cycle to a price tick, and once withheld it must climb back slightly
*above* the line to clear — so a position parked exactly on the requirement
cannot flap in and out of scoring as the Alpha price wobbles.

The gate **fails open**: unreadable collateral or an unreadable price yields
`status=unknown` and the miner is scored normally, and an unreadable cycle
freezes the grace counter rather than advancing or resetting it. Treating a
missing value as a zero bond would zero the entire subnet the first time the
SDK, runtime, or price feed changed shape.

---

## 6. Rollout order

Enforcement must ship *after* miners can comply, or the first cycle zeroes
everyone.

1. **Measure.** Set `REQUIRED_TAO=100`, leave `ENFORCE=false`. Read
   `kubetee_miner_collateral_coverage` and
   `kubetee_miner_collateral_status{status="delinquent"}` to see exactly who
   would be affected.
2. **Announce.** Publish the requirement and the grace window; point miners at
   §4 above.
3. **Enforce.** Flip `ENFORCE=true` once coverage metrics show the fleet is
   compliant.
4. **Bond the entry price — Phase 1.** Set `collateral_lock_share` and
   `collateral_drain_ratio` on chain (§3), once `k` has been sized against real
   emission data. Steps 1–3 are Phase 0 and do not depend on this.

---

## 7. References

- [`subtensor/docs/guides/mining/collateral.mdx`](../../subtensor/docs/guides/mining/collateral.mdx) — upstream guide
- [`subtensor/pallets/subtensor/src/subnets/collateral.rs`](../../subtensor/pallets/subtensor/src/subnets/collateral.rs) — the implementation
- The collateral policy engine — to be implemented in the rebuilt validator (see [CLAUDE.md — Validator from scratch](../CLAUDE.md))
