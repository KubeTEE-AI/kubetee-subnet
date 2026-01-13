# Lifetime Score with Decay: GitHub PR Scoring Model for Bittensor Subnets

## Executive Summary

This document outlines a **Lifetime Score with Decay** emission model for rewarding GitHub PR contributions in Bittensor subnets. The model addresses the core developer concern: ensuring that effort invested in complex PRs is fairly rewarded over time, regardless of ecosystem growth and competition.

### Core Principle

> "Your contribution value persists but gradually fades, like academic citations"

- Each PR earns **permanent scoring rights** that generate daily emissions
- Scores **decay slowly** (5% monthly recommended) to keep ecosystem dynamic
- **Decay floor** (30% recommended) ensures historical contributions never become worthless
- System rewards **quality over quantity** while remaining fair to newcomers

---

## Table of Contents

1. [High-Level Philosophy](#high-level-philosophy)
2. [Architecture Overview](#architecture-overview)
3. [Component Deep Dive](#component-deep-dive)
4. [Economic Dynamics](#economic-dynamics)
5. [Design Parameters](#design-parameters)
6. [Implementation Considerations](#implementation-considerations)
7. [Appendix: Visual Examples](#appendix-visual-examples)

---

## High-Level Philosophy

### The Academic Citation Analogy

Like academic papers:
- A groundbreaking paper earns citations for years
- Newer papers eventually supersede it
- Original work is never forgotten, just naturally weighted less over time

Your PR contribution:
- Earns you **permanent scoring rights**
- Decays slowly (keeping you relevant for months/years)
- Requires **occasional new contributions** to maintain position
- **Never drops to zero** (minimum floor ensures perpetual recognition)

### Key Benefits

#### For Developers
✅ **Fair compensation**: Complex PRs earn more than quick fixes  
✅ **Predictable income**: Transparent, calculable share percentages  
✅ **Long-term rewards**: Months of daily emissions vs one-time payment  
✅ **Protection from dilution**: Total earnings exceed one-time models even with competition  

#### For the Ecosystem
✅ **Dynamic competition**: Decay prevents early-miner dominance  
✅ **Quality incentives**: Importance multipliers reward substantial work  
✅ **Newcomer friendly**: New miners can meaningfully compete  
✅ **Sustainable growth**: System scales as subnet matures  

---

## Architecture Overview

### Contribution Lifecycle

```
PR Merged → Score Added → Decay Begins → Maintain/Grow
    │           │              │              │
    Day 0      Day 0         Day 30+        Ongoing
    
"I completed   "My lifetime   "Score slowly   "I contribute
 complex PR"    score grows"   decreases"      again"
```

### Mathematical Flow

```
Initial State:    Lifetime Score = 0

After PR Merge:   Score = 0 + 4.5 = 4.5
                  (based on importance, quality, temporal factors)

Month 1:          Score = 4.5 × 0.95 = 4.28
Month 2:          Score = 4.28 × 0.95 = 4.06
Month 3:          Score = 4.06 × 0.95 = 3.86
...
Month 12:         Score = 4.5 × (0.95)^12 = 2.44

After Another PR: Score = 2.44 + 3.8 = 6.24
(Month 12)        (old decayed + new contribution)
```

### Daily Emission Distribution

```
Total Subnet Emission: 1000 TAO/day (example)
Total Network Lifetime Score: 245.7

Your Lifetime Score: 45.3
Your Daily Share: (45.3 / 245.7) × 1000 = 184 TAO/day

This continues EVERY DAY until:
- Your score decays monthly (5%)
- You contribute more (score increases)
- Network dynamics change
```

---

## Component Deep Dive

### 1. Score Calculation per PR

Each merged PR contributes to your lifetime score based on:

#### Formula
```
PR_Score = Importance_Weight × Quality_Score × Temporal_Decay × Overlap_Penalty
```

#### Components

**Importance Weight** (0.3x - 5.0x)
- **Critical** (5.0x): Security vulnerabilities, consensus bugs
- **High** (3.0x): Major features, performance improvements
- **Medium** (1.5x): Standard features, refactoring
- **Low** (0.8x): Documentation, minor fixes
- **Trivial** (0.3x): Typos, formatting

**Quality Score** (0-100 scale)
- Code quality: Static analysis, complexity metrics
- Test coverage: New tests, edge cases covered
- Documentation: Inline comments, README updates
- Review process: Feedback incorporation, iteration quality

**Temporal Decay** (0.1-1.0)
- Measures time from issue creation to PR merge
- Incentivizes fast response to critical issues
- Example: Exponential decay with 48-hour half-life
  - 0 hours old: 1.0x (100% value)
  - 48 hours old: 0.5x (50% value)
  - 96 hours old: 0.25x (25% value)
  - 200+ hours old: 0.1x (floor)

**Overlap Penalty** (0.1-1.0)
- First PR to solve an issue: 1.0x (full credit)
- Duplicate solutions: 0.1x (minimal credit)
- Note: Only one PR wins per issue

#### Example Calculation

```
PR: "Add privacy layer feature"
├─ Importance: HIGH (3.0x)
├─ Quality: 92/100 (0.92)
├─ Temporal Decay: 0.85 (merged 5 days after issue created)
├─ Overlap: 1.0 (first solution)
└─ Final Score: 3.0 × 0.92 × 0.85 × 1.0 = 2.35
```

### 2. Lifetime Score Accumulation

Your lifetime score is the sum of all your PR scores with decay applied.

#### Example Journey

```
Month 0: Start
│
│  PR #1: Security Fix (Critical)
│  Score Added: 4.05
├──● Total Lifetime Score: 4.05
│
Month 1: (Natural 5% decay)
├──● Total Score: 3.85
│
Month 2: New PR
│  PR #2: Feature Addition (High)
│  Score Added: 2.42
├──● Total Score: 3.65 + 2.42 = 6.07
│
Month 3: (Decay)
├──● Total Score: 5.77
│
Month 4: No contribution
├──● Total Score: 5.48 (continued decay)
│
Month 5: Major Feature
│  PR #3: Major Refactor (High)
│  Score Added: 2.42
├──● Total Score: 5.21 + 2.42 = 7.63
│
Month 6-12: Regular contributions
├──● Total Score: Ranges 8-12
│   (maintaining through periodic PRs)
```

### 3. Decay Mechanics

#### Decay Timeline (Single PR)

```
Score Over 24 Months (5% monthly decay, 30% floor)

Month 0:  5.0  (100%)  ← PR just merged
Month 6:  3.7  (74%)   ← Still very relevant
Month 12: 2.7  (54%)   ← Half-life reached
Month 18: 2.0  (40%)   ← Approaching floor
Month 24: 1.5  (30%)   ← Floor reached (never decays further)
```

#### Decay Floor Rationale

**Without Floor**: Score eventually reaches zero
- Problem: Historical contributions become worthless
- Long-term earnings: Diminish to nothing

**With Floor (30%)**: Score stabilizes at minimum value
- Benefit: Permanent recognition of contribution
- Long-term earnings: Perpetual passive income stream

#### Lifetime Earnings Comparison

```
No Floor:
├─ Year 1: 24,000 TAO
├─ Year 2: 12,000 TAO  
├─ Year 3: 6,000 TAO
├─ Year 4: 3,000 TAO
└─ Year 5+: ~0 TAO

With 30% Floor:
├─ Year 1: 24,000 TAO
├─ Year 2: 15,000 TAO
├─ Year 3: 10,000 TAO
├─ Year 4: 8,000 TAO
└─ Year 5+: ~7,200 TAO/year FOREVER
```

### 4. Competitive Dynamics

#### Non-Overlapping PRs (Typical Case)

Multiple miners work on different issues simultaneously. Each earns independent scores.

```
24-Hour Epoch Example:

Hour 0:   Miner A merges Critical PR
          Score: 5.0 (Critical × 1.0 decay)
          
Hour 6:   Miner B merges High PR
          Score: 3.75 (High × 0.75 decay for age)
          
Hour 18:  Miner C merges Medium PR
          Score: 0.9 (Medium × 0.6 decay)

Result: All three earn simultaneously based on contribution quality
```

#### Overlapping PRs (Same Issue)

When multiple PRs solve the same issue, only the first merged receives full credit.

```
Issue: "Fix consensus bug" (Critical importance)

Hour 0:   Issue created
Hour 8:   Miner A's PR merged (first solution)
          Score: 4.25 (Critical × 0.85 decay × 1.0 winner)
          
Hour 10:  Miner B's PR merged (duplicate solution)
          Score: 0.4 (Critical × 0.81 decay × 0.1 penalty)
          
Note: Issue is closed. Miner B gets minimal credit for 
      concurrent work, but primary reward goes to first solver.
```

#### Parallel Major Features (Complementary Work)

```
Feature Request: "Add privacy layer"

Component A (Frontend): Miner X - Score: 2.25
Component B (Backend):  Miner Y - Score: 2.85  
Component C (Tests):    Miner Z - Score: 1.05

All complementary, no overlap penalty.
Total ecosystem benefit: 6.15 score units added.
```

---

## Economic Dynamics

### Multi-Miner Ecosystem Evolution

#### Example: 5 Miners Over 6 Months

```
Month 0:
Miner A: 8.0 (early adopter, large contribution)
Total Network Score: 8.0

Month 2:
Miner A: 7.2 (decayed)
Miner B: 5.0 (joined with significant PR)
Miner C: 2.3 (joined with smaller contribution)
Total Network Score: 14.5

Month 4:
Miner A: 6.5 (decayed but added small PR)
Miner B: 5.4 (added PR, net growth)
Miner C: 2.1 (decayed, no new work)
Miner D: 4.0 (joined with major feature)
Miner E: 1.5 (joined recently)
Total Network Score: 19.5

Month 6:
Miner A: 6.8 (stable with periodic contributions)
Miner B: 8.2 (very active, now leading)
Miner C: 1.8 (decayed, inactive)
Miner D: 4.5 (steady growth)
Miner E: 2.7 (consistent contributions)
Total Network Score: 24.0
```

#### Key Observations

**Miner A (Pioneer)**
- Started strong, maintains good position
- Doesn't need constant hustle
- Periodic work keeps them relevant
- Outcome: Sustainable long-term position

**Miner B (Active Contributor)**
- Joined later but overtook original pioneer
- Consistent high-quality contributions
- System rewards sustained effort
- Outcome: Meritocracy in action

**Miner C (Inactive)**
- Made initial contribution
- Went inactive, score decayed significantly
- Still earning (1.8 score) but much less
- Outcome: Passive income reduces over time

**Miners D & E (Newcomers)**
- Can meaningfully compete despite late entry
- Not overwhelmed by historical dominance
- Fair chance to establish themselves
- Outcome: Ecosystem remains accessible

### Daily Emission Distribution (Snapshot)

```
Today's Network State:
Total Lifetime Score: 24.0
Subnet Daily Emission: 1000 TAO

Individual Calculations:

Miner A (6.8 score):
├─ Share: 6.8 / 24.0 = 28.3%
└─ Daily Emission: 283 TAO

Miner B (8.2 score):
├─ Share: 8.2 / 24.0 = 34.2%
└─ Daily Emission: 342 TAO

Miner C (1.8 score):
├─ Share: 1.8 / 24.0 = 7.5%
└─ Daily Emission: 75 TAO

Miner D (4.5 score):
├─ Share: 4.5 / 24.0 = 18.8%
└─ Daily Emission: 188 TAO

Miner E (2.7 score):
├─ Share: 2.7 / 24.0 = 11.3%
└─ Daily Emission: 113 TAO
```

### Developer Concern: "More Devs = Less for Me?"

#### The 5-Day PR Scenario

**Your PR Details:**
- Work Duration: 5 days
- Importance: HIGH (3.0x)
- Quality Score: 92/100
- Temporal Decay: 0.85
- **Earned Score: 2.35**

**Current Network State:**
- Total Score: 24.0
- Your New Score: 2.35
- New Total: 26.35
- Your Share: 8.9%

#### Income Projection (If You Stop Contributing)

```
Month 1:  8.9% × 1000 = 89 TAO/day × 30 = 2,670 TAO
Month 2:  8.5% × 1000 = 85 TAO/day × 30 = 2,550 TAO
Month 3:  8.1% × 1000 = 81 TAO/day × 30 = 2,430 TAO
Month 4:  7.7% × 1000 = 77 TAO/day × 30 = 2,310 TAO
Month 5:  7.3% × 1000 = 73 TAO/day × 30 = 2,190 TAO
Month 6:  6.9% × 1000 = 69 TAO/day × 30 = 2,070 TAO
...
Month 12: 5.1% × 1000 = 51 TAO/day × 30 = 1,530 TAO

Total Year 1: ~23,000 TAO
```

#### Model Comparison

**One-Time Payment Model:**
```
You get: 1,000 TAO (done, finished)
```

**Lifetime Score Model:**
```
Month 1-3:   7,650 TAO
Month 4-6:   6,570 TAO
Month 7-9:   5,490 TAO
Month 10-12: 4,680 TAO
─────────────────────
Total Year 1: 24,390 TAO (24x more!)
```

**Even With Network Growth (Dilution):**
```
Scenario: Network doubles in size (your % cut in half)

You still earn: ~12,000 TAO in Year 1
This is 12x better than one-time payment!
```

#### The Math Works in Your Favor

```
Lifetime Model Advantages:
✅ Daily passive income for months/years
✅ Total earnings 10-20x one-time payment
✅ Protected by decay floor (perpetual minimum)
✅ Quality work earns proportionally more forever

One-Time Model Problems:
❌ Single payment, then nothing
❌ Vulnerable to competition at moment of merge
❌ No long-term value recognition
❌ Encourages quantity over quality
```

### Competitive Scenario: Parallel Work

```
Week 1:
You:      Reserve "Add Privacy Layer" (High, ~7 days)
Miner X:  Reserve "Fix API Bug" (Medium, ~2 days)

Day 2:
Miner X:  PR merged
          Score: 1.28
          Network Total: 25.28
          Miner X Share: 5.1%
          Miner X Income: 51 TAO/day

Day 7:
You:      PR merged
          Score: 2.55
          Network Total: 26.55
          Your Share: 9.6%
          Your Income: 96 TAO/day
          
          Miner X now earning: 48 TAO/day
          (slightly diluted by your entry)
```

**Key Insight:**

Your complex PR earned **2x** their score
- Your daily income is **2x** theirs
- Over 6 months, you earn **2x** total
- System correctly rewards effort proportionally

**This is NOT winner-takes-all:**
- Both miners earn simultaneously
- Your bigger contribution = bigger share
- Fair to both effort levels
- Encourages diverse contribution types

---

## Design Parameters

### Critical Design Decisions

#### 1. Decay Rate

**Options:**

| Rate | Half-Life | Philosophy | Best For |
|------|-----------|------------|----------|
| **2%/month** | ~24 months | Veteran-friendly | Mature subnets, stability |
| **5%/month** | ~12 months | **Balanced [RECOMMENDED]** | Most subnets |
| **10%/month** | ~6 months | New-miner friendly | Young subnets, rapid iteration |

**Trade-offs:**

**Fast Decay (10%/month)**
- ✅ New miners competitive quickly
- ✅ Dynamic, active ecosystem
- ❌ Veterans must contribute frequently
- ❌ Less passive income stability

**Slow Decay (2%/month)**
- ✅ Rewards long-term commitment
- ✅ Stable passive income
- ❌ Hard for newcomers to catch up
- ❌ Can become stagnant

**Balanced (5%/month) - RECOMMENDED**
- ✅ Fair to veterans and newcomers
- ✅ Encourages periodic contribution
- ✅ Long enough for passive benefits
- ✅ Short enough to stay dynamic

#### 2. Decay Floor

**Options:**

| Floor | Perpetual Value | Philosophy |
|-------|-----------------|------------|
| **50%** | High historical recognition | Strong founder advantage |
| **30%** | **Balanced [RECOMMENDED]** | Fair legacy reward |
| **10%** | Minimal legacy benefit | Merit-focused |
| **0%** | Eventually zero | Pure current contribution |

**Recommendation: 30%**
- Recognizes historical importance
- Prevents veteran contributors from hitting zero
- Maintains some passive income for pioneers
- Still allows newcomers to compete

#### 3. Decay Frequency

**Options:**

| Frequency | Pros | Cons |
|-----------|------|------|
| **Daily** | Smooth continuous decay | High computation overhead |
| **Weekly** | Less computation | Acceptable granularity |
| **Monthly** | **Simplest [RECOMMENDED]** | Clear, predictable |

**Recommendation: Monthly**
- Aligns with human planning cycles
- Reduces computational overhead
- Clear, predictable for miners
- Easy to communicate and visualize

### Recommended Configuration

```yaml
# Subnet Emission Settings
daily_subnet_emission: 1000  # TAO per day

# Score Decay Settings
decay_rate: 0.05  # 5% monthly
decay_frequency: monthly
decay_floor: 0.30  # Never below 30% of original

# PR Scoring Weights
importance_weights:
  critical: 5.0
  high: 3.0
  medium: 1.5
  low: 0.8
  trivial: 0.3

# Temporal Decay (for PR submission speed)
temporal_decay_model: exponential
temporal_half_life_hours: 48
temporal_floor: 0.1

# Anti-Gaming
minimum_merge_delay_hours: 1
overlap_penalty: 0.1  # Duplicate solutions get 10%
quality_threshold: 30  # Minimum score to qualify
```

---

## Implementation Considerations

### Validator Consensus Layer

Validators must reach consensus on:

1. **PR Score Calculation**
   - Importance classification
   - Quality assessment
   - Temporal decay at merge time
   - Overlap detection

2. **Lifetime Score Updates**
   - Adding new PR scores
   - Applying monthly decay
   - Enforcing decay floor

3. **Emission Distribution**
   - Calculating miner shares
   - Distributing daily emissions
   - Handling edge cases

### Consensus Flow

```
GitHub PR Merged
       │
       ▼
Validators Calculate Score
       │
       ├─ Validator 1: 2.4 ✓ (20% stake)
       ├─ Validator 2: 2.4 ✓ (35% stake)
       ├─ Validator 3: 2.3 ✓ (25% stake)
       └─ Validator 4: 3.1 ✗ (20% stake - outlier)
       │
       ▼
Stake-Weighted Consensus: 2.38
       │
       ▼
Update Miner's Lifetime Score
       │
       ▼
Calculate New Emission Shares
```

### Anti-Gaming Mechanisms

**Minimum Merge Time**
- PRs merged <1 hour after submission: 0.5x penalty
- Prevents self-approval gaming

**Code Churn Penalty**
- Reverted commits within 7 days: -50% score
- Discourages rushed, low-quality work

**Duplicate Detection**
- Similarity check against existing code
- >80% similarity = disqualified
- Prevents copy-paste contributions

**Validator Collusion Detection**
- Statistical analysis of validator score correlations
- Outliers face stake slashing
- Encourages honest evaluation

### State Management

**On-Chain Storage Requirements:**
- Miner lifetime scores (per miner)
- Monthly decay timestamps
- PR history and scores (for audit)
- Total network score (for share calculation)

**Update Frequency:**
- PR merge: Immediate score update
- Decay application: Monthly batch
- Emission distribution: Daily calculation

### Edge Cases

**Miner Inactivity**
- Score continues to decay even if inactive
- Reaches floor and stabilizes
- Can return anytime and rebuild score

**Network Growth**
- New miners don't retroactively affect old scores
- Only affects share percentage, not absolute score
- Historical contributors protected by decay floor

**Subnet Emission Changes**
- If subnet total emission changes, all shares scale proportionally
- Example: Emission doubles from 1000→2000 TAO/day
- All miners' daily TAO doubles (shares unchanged)

---

## Appendix: Visual Examples

### Decay Rate Comparison

#### 5% Monthly Decay (Recommended)

```
Score Over Time:

5.0 ●
    │ ╲___
2.5 │     ●●●●●___________
    │                     
1.5 │                     ●●●●●● (floor at 30%)
    └────────────────────────────────► Months
    0       12      24      36

Half-life: ~12 months
Final floor: 1.5 (30% of 5.0)
```

#### 10% Monthly Decay (Faster)

```
Score Over Time:

5.0 ●
    │ ╲___
2.5 │   ●●●___
    │         ●●●●___
1.5 │               ●●●●● (floor at 30%)
    └────────────────────────────────► Months
    0     6    12    18    24

Half-life: ~6 months
More dynamic, favors recent work
```

#### 2% Monthly Decay (Slower)

```
Score Over Time:

5.0 ●
    │ ╲_______________
2.5 │                 ●●●●●●●●●●●____
    │                                
1.5 │                                ●● (floor at 30%)
    └────────────────────────────────────────► Months
    0         24        48        72

Half-life: ~24 months
Strong historical contributor advantage
```

### PR Importance Hierarchy

```
Emission Weight Multipliers:

CRITICAL (5.0x) ●━━━━━━━━━━━━━━━━━━━━━━━━━
Security bugs   │ 2.5x more than High
Consensus fixes │

HIGH (3.0x)     ●━━━━━━━━━━━━━━━
Major features  │ 2x more than Medium
Performance     │

MEDIUM (1.5x)   ●━━━━━━━
Standard work   │ ~2x more than Low
Refactoring     │

LOW (0.8x)      ●━━━━━
Documentation   │ 2.7x more than Trivial
Minor fixes     │

TRIVIAL (0.3x)  ●━
Typos, format   │ Baseline
```

### Temporal Decay Example

```
Exponential Decay (48h half-life):

Value
  │
1.0│●
   │ ╲
0.5│  ●
   │   ╲___
0.2│       ●●●___
   │             ●●●●●
0.1│                  ●●●●●●● (floor)
   └────────────────────────────────► Hours
   0    48   96   144  192  240

Incentivizes fast response to issues
Critical bugs should be fixed immediately
```

### 24-Hour Epoch Example

```
Timeline:

Hour 0    Hour 6    Hour 12   Hour 18   Hour 24
  │         │         │         │         │
  ●─────────┼─────────┼─────────┼─────────┤
  PR1       │         │         │         │  Score: 5.0
  Critical  │         ●─────────┼─────────┤  (First, full value)
            │         PR2       │         │  Score: 3.75
            │         High      │         │  (Slight decay)
            │                   │    ●────┤  
            │                   │    PR3  │  Score: 0.9
            │                   │    Med  │  (Late submission)

All three miners earn independently
Quality and timing both matter
No zero-sum competition
```

---

## Conclusion

The **Lifetime Score with Decay** model provides:

### For Developers
✅ **Fair long-term compensation** for complex contributions  
✅ **Protection from dilution** through persistent score accumulation  
✅ **Predictable income streams** with transparent calculations  
✅ **Quality rewards** via importance multipliers  

### For Subnets
✅ **Sustainable growth** as ecosystem expands  
✅ **Dynamic competition** preventing early-miner dominance  
✅ **Merit-based distribution** encouraging quality over quantity  
✅ **Newcomer accessibility** while respecting historical contributions  

### Key Economic Insight

**Your 5-day complex PR can earn 10-20x more than a one-time payment model**, even with significant ecosystem growth and competition.

This is achieved through:
1. **Daily persistent emissions** over months/years
2. **Proportional rewards** matching effort investment
3. **Decay floor protection** ensuring perpetual minimum income
4. **Fair dilution dynamics** where total earnings vastly exceed temporary share reductions

---

## Quick Reference

### Recommended Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Decay Rate | 5%/month | Balanced dynamics |
| Decay Floor | 30% | Fair legacy reward |
| Decay Frequency | Monthly | Simple, predictable |
| Temporal Half-Life | 48 hours | Urgency incentive |
| Critical Weight | 5.0x | Security priority |
| High Weight | 3.0x | Feature importance |
| Overlap Penalty | 0.1x | Winner-takes-most |

### Key Formulas

**PR Score:**
```
Score = Importance × Quality × Temporal_Decay × Overlap_Penalty
```

**Monthly Decay:**
```
New_Score = Old_Score × 0.95
(never below floor: Original_Score × 0.30)
```

**Daily Emission:**
```
Miner_TAO = (Miner_Score / Total_Network_Score) × Daily_Subnet_Emission
```

---

**Document Version:** 1.0  
**Last Updated:** January 2026  
**Status:** Design Specification

