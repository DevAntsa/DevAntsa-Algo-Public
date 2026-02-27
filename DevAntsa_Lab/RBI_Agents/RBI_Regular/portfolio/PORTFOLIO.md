# Regime Portfolio - Algo Trading Strategy Collection

## Architecture

Deploy multiple strategies simultaneously, each designed for a specific market regime.
Entry conditions self-gate: strategies only fire in their target regime and sit in cash otherwise.

## Regime Buckets

### Bull Market -- LIVE DEPLOYMENT GUIDE v10 (Feb 21, 2026)

**Goal:** Catch explosive breakouts and strong trends. LONG only.
**Self-gates by:** Requiring strong upward momentum + volume + trend alignment. These conditions never fire in bear/sideways.
**Direction:** LONG ONLY. All entries use `self.buy()`.
**Timeframe:** 4h (5 strategies), 1h (1 strategy: DualROCAlignment).
**Exchange:** Bybit perpetual futures (via CFT prop firm). Commission: 0.001 (0.1% per side, 1.67x buffer over Bybit taker 0.06%).
**Backtest period:** ~5 years (Jan 2021 - Feb 2026), $1M starting cash.

#### Strategy Overview

| # | Strategy | Asset | Return | Sharpe | Max DD | Trades | WR |
|---|----------|-------|--------|--------|--------|--------|----|
| 1 | **SteepeningSlopeBreakout** | **SOL-4h** | +34.8% | **1.48** | -3.3% | 170 | 51% |
| 2 | **DualROCAlignment** | **BTC-1h** | +61.6% | 1.21 | -6.7% | 72 | 53% |
| 3 | **DirectionalIgnition** | BTC-4h | +17.0% | **1.23** | **-2.7%** | 36 | 53% |
| 4 | **ATRExpansionBreakout** | BTC-4h | +35.2% | 1.22 | -3.6% | 96 | 59% |
| 5 | **DIBreakoutPyramid** | BTC-4h | **+82.1%** | **1.23** | -6.7% | 156 | 47% |
| 6 | **TripleMomentum** | **SOL-4h** | +15.0% | 1.13 | -2.9% | 49 | 57% |

Asset concentration: BTC 4/6 (67%), SOL 2/6 (33%). All 6 Sharpe > 1.0 (100%).
Portfolio (equal weight): **+41.0% (5yr), ~7.1% annualized, -2.1% historical DD.**

#### Per-Strategy Specifications

[Strategy implementations are proprietary]

#### Position Sizing Formula

All strategies use the same formula:
```
size = risk_pct / (stop_atr_mult * ATR / price)
size = clamp(size, min=0.01, max=0.50)   // fraction of equity
```
Example: strategy on SOL at $150, ATR=$3:
- stop_dist = 2.5 * $3 = $7.50
- size = 0.005 / ($7.50 / $150) = 0.005 / 0.05 = **10% of equity per unit**

#### Signal Descriptions

[Strategy entry/exit conditions are proprietary]

#### Monte Carlo Risk Analysis (v10, 5000 sims, trade-level shuffling)

| Metric | Value |
|--------|-------|
| Portfolio Return (historical) | **+41.0%** |
| Portfolio DD (bar-level, historical) | -2.05% |
| Portfolio DD (sequential trades) | -5.20% |
| Total trades across 6 strategies | 579 |
| Overall win rate | 52.0% |
| Mean trade P&L (% of portfolio) | +0.42% |
| Worst single trade | -3.45% |
| Best single trade | +16.71% |

| Monte Carlo DD Percentile | Value |
|--------------------------|-------|
| Best case (min DD) | -1.65% |
| Median | -3.58% |
| 75th worst-case | -4.44% |
| 90th worst-case | -5.48% |
| **95th worst-case** | **-6.19%** |
| 99th worst-case | -8.02% |
| Absolute worst | -11.28% |

| CFT DD Limit | Probability of Breach |
|-------------|----------------------|
| -5% (soft) | 15.9% |
| **-6% (CFT)** | **6.0%** |
| -8% (hard) | 1.0% |
| -10% | 0.1% |

#### Capital Allocation (Monte Carlo validated)

| Allocation Tier | Equity % | 95th worst-case DD | CFT -6% breach prob | Verdict |
|-----------------|----------|-------------------|---------------------|---------|
| **Conservative** | **81%** | -5.0% | ~0% | **Recommended for prop firm eval** |
| Aggressive | 97% | -6.0% | ~5% | Max return, tight to CFT limit |

Equal weight: divide total allocation by 6 strategies.
- At 81%: **~13.5% equity per strategy**
- At 97%: ~16.2% equity per strategy

#### Per-Strategy Risk Contribution (from Monte Carlo)

| Strategy | Trades | WR | Avg Win | Avg Loss | Worst Trade | Max Consec Losses |
|----------|--------|----|---------|----------|-------------|-------------------|
| SteepeningSlopeBreakout | 170 | 51% | +0.65% | -0.25% | -0.73% | 9 |
| DualROCAlignment | 72 | 53% | +2.01% | -0.44% | -3.45% | 9 |
| DirectionalIgnition | 36 | 53% | +1.33% | -0.48% | -1.12% | 3 |
| ATRExpansionBreakout | 96 | 59% | +1.00% | -0.55% | -2.48% | 7 |
| DIBreakoutPyramid | 156 | 47% | +1.78% | -0.57% | -1.59% | 10 |
| TripleMomentum | 49 | 57% | +0.71% | -0.24% | -0.53% | 5 |

*Avg Win/Loss as % of total portfolio equity. Worst Trade = single worst trade impact on portfolio.*

#### Maximum Concurrent Risk

| Strategy | Max units x Risk/unit | Max risk at full pyramid |
|----------|----------------------|-------------------------|
| SteepeningSlopeBreakout | 2 x 0.5% | 1.0% |
| DualROCAlignment | 3 x 0.5% | 1.5% |
| DirectionalIgnition | 1 x 1.0% | 1.0% |
| ATRExpansionBreakout | 2 x 1.0% | 2.0% |
| DIBreakoutPyramid | 2 x 0.7% | 1.4% |
| TripleMomentum | 2 x 0.5% | 1.0% |
| **Theoretical max (all fully pyramided)** | **12 positions** | **7.9%** |

All 6 never fully pyramid simultaneously in practice. BTC and SOL breakouts rarely align.
Historical worst concurrent DD (bar-level): **-2.05%** (Dec 20, 2022).

#### Strategy Value Ranking (leave-one-out Monte Carlo, 1000 sims each)

If dropped, how much does 95th worst-case DD change? Negative delta = strategy adds risk protection.

| Strategy | 95th DD without it | Delta vs baseline -6.19% | Verdict |
|----------|-------------------|--------------------------|---------|
| DIBreakoutPyramid | -5.14% | +1.05% | **MOST VALUABLE** -- biggest return contributor |
| SteepeningSlopeBreakout | -6.69% | -0.50% | **BEST DIVERSIFIER** -- SOL independence |
| TripleMomentum | -6.25% | -0.06% | Marginal positive -- SOL diversification |
| ATRExpansionBreakout | -6.07% | +0.12% | Moderate value |
| DirectionalIgnition | -6.09% | +0.09% | Moderate value |
| DualROCAlignment | -6.04% | +0.15% | Least impactful (but only 1h strategy) |

#### Correlation Matrix (bar-by-bar equity returns)

```
                    Stp_Sl  ROC_Al  Dir_Ig  ATR_Ex  DI_Brk  Tri_Mo
SteepenSlope          1.00    0.03    0.07    0.08    0.10    0.47
DualROCAlignment      0.03    1.00    0.05    0.11    0.14   -0.00
DirectionalIgnition   0.07    0.05    1.00    0.45    0.43    0.12
ATRExpansionBreak     0.08    0.11    0.45    1.00    0.61    0.09
DIBreakoutPyramid     0.10    0.14    0.43    0.61    1.00    0.10
TripleMomentum        0.47   -0.00    0.12    0.09    0.10    1.00
```

**Key correlation pairs (concurrent DD risk):**
- ATRExpansionBreakout <-> DIBreakoutPyramid: r=0.61 (MODERATE -- both BTC-4h momentum)
- SteepeningSlopeBreakout <-> TripleMomentum: r=0.47 (MODERATE -- both SOL, different signal families)
- DirectionalIgnition <-> ATRExpansionBreakout: r=0.45 (MODERATE)
- DirectionalIgnition <-> DIBreakoutPyramid: r=0.43 (MODERATE)
- All other pairs < 0.15 (LOW -- genuinely independent)

**Most independent strategies:** SteepeningSlopeBreakout (r < 0.12 with all BTC strats) and DualROCAlignment (r < 0.14 with everything).

#### Bench Strategies (5 reserve, for rotation if a deployed strategy underperforms)

| Bench | Strategy | Sharpe | Why benched |
|-------|----------|--------|-------------|
| 1 | StructuralReclaim | 1.15 | r=0.60 with deployed BTC strats. **First alternate for slot 5.** |
| 2 | VortexSpread | 1.15 | r=0.83 with DIBreakoutPyramid (same trade). |
| 3 | DualDonchianBreakout | 1.14 | r=0.79 with VolumePrecursor. |
| 4 | RelativeBreakout | 1.00 | Lowest Sharpe. 252 trades = noisier. |
| 5 | VolumePrecursor | 1.03 | Lowest BTC-4h Sharpe. 337 trades = highest noise. |

#### Full Research Portfolio (11 strategies, 10 signal families)

| # | Strategy | Asset | Return | Sharpe | Max DD | Trades | Deployed? |
|---|----------|-------|--------|--------|--------|--------|-----------|
| 1 | DIBreakoutPyramid | BTC-4h | +82.1% | 1.23 | -6.66% | 156 | YES (#5) |
| 2 | DirectionalIgnition | BTC-4h | +17.0% | 1.23 | -2.73% | 36 | YES (#3) |
| 3 | DualROCAlignment | BTC-1h | +61.6% | 1.21 | -6.68% | 72 | YES (#2) |
| 4 | DualDonchianBreakout | BTC-4h | +60.0% | 1.14 | -7.67% | 205 | Bench |
| 5 | ATRExpansionBreakout | BTC-4h | +35.2% | 1.22 | -3.55% | 96 | YES (#4) |
| 6 | RelativeBreakout | BTC-4h | +48.7% | 1.00 | -7.08% | 252 | Bench |
| 7 | SteepeningSlopeBreakout | SOL-4h | +34.8% | 1.48 | -3.3% | 170 | YES (#1) |
| 8 | VolumePrecursor | BTC-4h | +35.4% | 1.03 | -6.6% | 337 | Bench |
| 9 | StructuralReclaim | BTC-4h | +30.6% | 1.15 | -3.7% | 186 | Bench |
| 10 | VortexSpread | ALL 3 | +65.2% BTC | 1.15 | -5.1% BTC | 183 | Bench |
| 11 | TripleMomentum | SOL-4h | +15.0% | 1.13 | -2.9% | 49 | YES (#6) |

**Version History:**
v10 (Feb 21): TripleMomentum deployed as 6th (198 BT sweep). AcceleratingSlope rejected (r=0.846).
v9 (Feb 20): VortexSpread added. MC v9: 95th DD=-7.74% (10-strat research portfolio).
v8: 3 swept from B16 (303 BT). First SOL strategy. v7: DualROC swept (288 BT).
v6: DirectionalIgnition swept (294 BT). v5: ATRExpansion swept (342 BT). WF validated.

### Sideways Market (DEPRIORITIZED)
**Status:** 6 batches, ~100 strategies, zero qualifiers. Deprioritized.
Bull+bear self-gating = flat in sideways = zero DD. No sideways strategies needed.

### Bear Market - Shorts (9 strategies, diversity-optimized, avg Sharpe: 1.19)
**Goal:** Profit from downtrends and crashes. Short-only strategies with strict bear entry conditions.
**Self-gates by:** Requiring price < SMA200 (or SMA230), declining momentum, breakdown signals. These never fire in bull markets.
**Direction:** SHORT ONLY. All entries use `self.sell()`.
**Timeframe:** 4h MANDATORY. Every 1h short tested negative over 5 years.
**Exchange:** Bybit (via CFT prop firm). Commission: 0.001 (0.1% per trade, 1.67x buffer over Bybit taker 0.06%).
**Backtest period:** ~5 years (Jan 2021 - Feb 2026), $1M starting cash.

#### Strategy Overview

| # | Strategy | Asset | Return | Sharpe | Max DD | Trades | WR |
|---|----------|-------|--------|--------|--------|--------|----|
| 1 | StructuralFade | ETH-4h | +18.7% | 1.46 | -1.24% | 33 | 70% |
| 2 | **BearishLowerHigh** | ETH-4h | **+56.7%** | **1.44** | -3.45% | 108 | 56% |
| 3 | AccelBreakdown | ETH-4h | +69.5% | 1.35 | -4.90% | 121 | 58% |
| 4 | EMARejectionADX | ETH-4h | +13.6% | 1.21 | -1.64% | 61 | 56% |
| 5 | **MFIDistribution** | ETH-4h | **+40.4%** | **1.12** | -4.01% | 49 | 55% |
| 6 | **PanicAcceleration** | BTC-4h | **+26.6%** | **1.19** | -2.62% | 63 | 57% |
| 7 | ExpansionBreakdown | BTC-4h | +15.4% | 0.79 | -2.51% | 40 | 57% |
| 8 | **WorseningMomentum** | **SOL-4h** | **+51.2%** | **1.13** | **-4.66%** | 80 | 54% |
| 9 | **ExpandingBodyBear** | **SOL-4h** | **+18.4%** | **1.07** | **-2.86%** | 51 | 59% |

Asset concentration: ETH 5/9 (56%), BTC 2/9 (22%), SOL 2/9 (22%). 8/9 Sharpe > 1.0 (89%).

#### Per-Strategy Specifications

[Strategy implementations are proprietary]

#### Signal Descriptions

[Strategy entry/exit conditions are proprietary]

#### Monte Carlo Risk Analysis (5000 sims, trade-level shuffling)

| Metric | Value |
|--------|-------|
| Portfolio Return (historical) | **+34.5%** |
| Portfolio DD (bar-level, historical) | -1.65% |
| Portfolio DD (sequential trades) | -7.45% |
| Total trades across 9 strategies | 606 |
| Overall win rate | 57.3% |
| Mean trade P&L (% of portfolio) | +0.51% |
| Worst single trade | -3.20% |
| Best single trade | +8.68% |

| Monte Carlo DD Percentile | Value |
|--------------------------|-------|
| Best case (min DD) | -2.16% |
| Median | -4.56% |
| 75th worst-case | -5.59% |
| 90th worst-case | -6.91% |
| **95th worst-case** | **-7.83%** |
| 99th worst-case | -10.27% |
| Absolute worst | -14.84% |

| CFT DD Limit | Probability of Breach |
|-------------|----------------------|
| -5% (soft) | 37.5% |
| **-6% (CFT)** | **18.8%** |
| -8% (hard) | 4.5% |
| -10% | 1.3% |

#### Per-Strategy Risk Contribution (from Monte Carlo)

| Strategy | Trades | WR | Avg Win | Avg Loss | Worst Trade | Max Consec Losses |
|----------|--------|----|---------|----------|-------------|-------------------|
| StructuralFade | 33 | 70% | +1.05% | -0.56% | -1.12% | 2 |
| BearishLowerHigh | 108 | 56% | +1.67% | -0.96% | -2.47% | 3 |
| AccelBreakdown | 121 | 58% | +1.88% | -1.21% | -3.20% | 5 |
| EMARejectionADX | 61 | 56% | +0.59% | -0.24% | -1.01% | 3 |
| MFIDistribution | 49 | 55% | +2.27% | -0.95% | -2.76% | 3 |
| PanicAcceleration | 63 | 57% | +1.23% | -0.66% | -1.83% | 3 |
| ExpansionBreakdown | 40 | 57% | +1.02% | -0.47% | -1.10% | 3 |
| WorseningMomentum | 80 | 54% | +1.80% | -0.71% | -1.71% | 4 |
| ExpandingBodyBear | 51 | 59% | +1.15% | -0.76% | -2.28% | 4 |

*Avg Win/Loss as % of total portfolio equity. Worst Trade = single worst trade impact on portfolio.*

#### Correlation Matrix (bar-by-bar equity returns)

```
                     Struct  Bearis  AccelB  EMARej  MFIDis  PanicA  Expans  Worsen  Expand
 StructuralFade         1.00    0.37    0.34    0.29    0.06    0.22    0.11    0.16    0.05
BearishLowerHigh       0.37    1.00    0.69    0.18    0.55    0.29    0.23    0.26    0.17
AccelBreakdown         0.34    0.69    1.00    0.18    0.47    0.27    0.24    0.32    0.21
EMARejectionADX        0.29    0.18    0.18    1.00    0.10    0.08    0.04    0.08    0.03
MFIDistribution        0.06    0.55    0.47    0.10    1.00    0.17    0.25    0.26    0.16
PanicAcceleration      0.22    0.29    0.27    0.08    0.17    1.00    0.28    0.16    0.17
ExpansionBreakdown     0.11    0.23    0.24    0.04    0.25    0.28    1.00    0.25    0.16
WorseningMomentum      0.16    0.26    0.32    0.08    0.26    0.16    0.25    1.00    0.40
ExpandingBodyBear      0.05    0.17    0.21    0.03    0.16    0.17    0.16    0.40    1.00
```

**Key correlation pairs (concurrent DD risk):**
- BearishLowerHigh <-> AccelBreakdown: r=0.69 (HIGH -- both ETH momentum breakdown)
- BearishLowerHigh <-> MFIDistribution: r=0.55 (HIGH -- both ETH structural)
- AccelBreakdown <-> MFIDistribution: r=0.47 (MODERATE)
- WorseningMomentum <-> ExpandingBodyBear: r=0.40 (MODERATE -- both SOL but different signal families)

**Most independent strategy:** EMARejectionADX (r < 0.29 with everything, avg r=0.10). If any strategy were dropped, this one would hurt the most.

#### Market Regime Performance (NOT crash-dependent)

The portfolio earns profit in ALL market conditions, not just crashes:

| Period | Regime | Trades | PnL | Avg PnL/Trade | Strategies Active |
|--------|--------|--------|-----|---------------|-------------------|
| May 2021 crash (64K->29K) | BEAR | 26 | +16.7% | +0.64% | 9/9 |
| Nov 2021 top decline | BEAR | 45 | +30.8% | +0.68% | 9/9 |
| Slow bleed 2022 | BEAR | 42 | +12.2% | +0.29% | 9/9 |
| LUNA/3AC crash | BEAR | 28 | +30.4% | +1.09% | 9/9 |
| FTX crash | BEAR | 41 | +29.9% | +0.73% | 9/9 |
| **Sideways 2023 (26K-27K)** | **SIDEWAYS** | **63** | **+4.0%** | +0.06% | 8/9 |
| Post-ETF consolidation (73K-62K) | MIXED | 43 | -0.4% | -0.01% | 9/9 |
| **Summer Chop 2024 (55K-65K)** | **SIDEWAYS** | **48** | **+38.8%** | **+0.81%** | **9/9** |
| ATH + correction 2025 | MIXED | 89 | +41.8% | +0.47% | 9/9 |
| Late 2025 | MIXED | 70 | +44.6% | +0.64% | 9/9 |
| Early 2026 | MIXED | 28 | +27.5% | +0.98% | 7/9 |

**Crash vs Non-crash split:** 54% PnL from crashes, 46% from non-crash. Nearly 50/50.
**All years profitable:** 2021 +16%, 2022 +115%, 2023 +17%, 2024 +49%, 2025 +86%, 2026 +27%.
**89% of months have trades.** Only 7 dry months in 61, longest gap 2 months.
**61% winning months**, avg win +10.8% vs avg loss -2.2%.

#### Per-Strategy Crash Dependence

| Strategy | Crash PnL | Non-crash PnL | Crash % | Verdict |
|----------|-----------|---------------|---------|---------|
| StructuralFade | +14.1% | +4.6% | 76% | **CRASH-HEAVY** |
| BearishLowerHigh | +31.4% | +25.3% | 55% | BALANCED |
| AccelBreakdown | +27.1% | +42.4% | 39% | **SPREAD** |
| EMARejectionADX | +5.3% | +8.3% | 39% | **SPREAD** |
| MFIDistribution | +16.6% | +23.8% | 41% | BALANCED |
| PanicAcceleration | +17.8% | +8.8% | 67% | **CRASH-HEAVY** |
| ExpansionBreakdown | +9.1% | +6.3% | 59% | BALANCED |
| WorseningMomentum | +38.1% | +13.2% | 74% | **CRASH-HEAVY** |
| ExpandingBodyBear | +8.7% | +9.7% | 47% | BALANCED |

#### Dropped Strategies (and why)

| Strategy | Reason Dropped |
|----------|---------------|
| StructuralBreakdown | r=0.88 with AccelBreakdown (nearly identical entries). AccelBreakdown has higher Sharpe. |
| EscalatingPanic | r=0.66 with PanicAcceleration (same signal family). PanicAcceleration has higher Sharpe. |
| DualBreakdown | S=0.48 (worst in portfolio). Replaced by better strategies. |
| DualPlunge | S=0.67. Replaced by WorseningMomentum S=1.13 (same SOL slot, 69% higher Sharpe). |

## Deployment Plan (Crypto Fund Trader)

### Bull Allocation (Monte Carlo v10, 5000 sims)

Deploy 6 unique-entry strategies. Two allocation tiers:
- **97% aggressive** (guarantees <6% DD at 95th worst-case, 6.0% breach probability)
- **81% conservative** (guarantees <5% DD at 95th worst-case)
- 6 deployed strategies, 5 benched (reserve for rotation if one underperforms)
- 95th worst-case DD: **-6.19%** at 100% allocation
- Max concurrent risk: 12 positions (6 strats x 2 units), 7.9% theoretical max (rarely all fire simultaneously)

### Bear Allocation (Monte Carlo validated)

Deploy all 9 bear strategies at **77% allocation** (guarantees <6% DD at 95th worst-case).
- 9 deployed strategies, equal capital share (77% / 9 = ~8.6% each)
- 95th worst-case DD: -7.83%. CFT -6% breach probability: 18.8%.

### Combined Operation

1. Run bull + bear strategies simultaneously on same account
2. At any given time, only one regime will have active positions (others self-gated)
3. Bull 81% + Bear 77% allocation doesn't stack -- they're mutually exclusive by self-gating
4. Use the LOWER of the two allocations (77%) as the global capital allocation for safety

## Qualification Criteria Per Regime

| Metric | Bull | Sideways | Bear |
|--------|------|----------|------|
| Return % | > 10% | > 5% | > 5% |
| Sharpe | > 0.8 | > 1.0 | > 0.8 |
| Max DD | > -8% | > -5% | > -8% |
| Trades | >= 20 | >= 50 | >= 20 |
| Direction | Long only | Long only | Short only |
