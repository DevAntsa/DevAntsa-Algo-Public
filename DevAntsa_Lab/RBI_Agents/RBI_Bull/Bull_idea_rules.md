# Bull Market Strategy Rules v18

## CRITICAL LEARNINGS (BATCHES 15-22)

### WHAT WORKS - DEPLOYABLE (Sharpe >2.0)
| Strategy | Asset | Return% | Sharpe | MaxDD% | Trades |
|----------|-------|---------|--------|--------|--------|
| CascadeHighMomentum | SOL-4h | 14.0% | **3.22** | -3.07% | 43 |
| ElasticReclaim | SOL-4h | 15.47% | **3.21** | -3.57% | 49 |
| ApexCloseEma | BTC-4h | 11.43% | **2.67** | -2.10% | 38 |
| CascadeDipReclaim | BTC-4h | 10.16% | **2.15** | -2.89% | 30 |
| ApexMomentumThreshold | BTC-4h | 32.25% | **2.03** | -5.72% | 30 |

### SILVER TIER (Sharpe 1.5-2.0) - Paper Trading
| Strategy | Asset | Return% | Sharpe | MaxDD% | Trades |
|----------|-------|---------|--------|--------|--------|
| ExponentialMomentumTrail | BTC-4h | 75.57% | **1.53** | -11.50% | 32 |

### WHAT FAILED - BATCHES 17-21 (DO NOT REPEAT)
| Approach | Result | Why It Failed |
|----------|--------|---------------|
| Wide stops (4.0x/3.0x ATR) | Sharpe 0.7-0.9 | Catches trend BUT more noise |
| High momentum (>0.020) | Sharpe <1.0 | Signal starvation |
| Life-changing return focus | 333% return, -38% DD | Undeployable risk |
| 1h timeframe | Negative Sharpe 60%+ | Too noisy |
| Variations of winners | Sharpe 1.0-1.5 | Originals outperform |
| Volume-based 3-condition | 0 trades | Too restrictive on 4h |
| Candle patterns (engulf) | <10 trades | Patterns rare on 4h |
| NEW patterns vs proven | Sharpe 1.6 max | Proven archetypes best |
| **HYBRID 3-condition** | 0-3 trades | ElasticRebound failed |
| **Volume + HH + extra** | Sharpe 1.45 max | Still below threshold |
| **ATR surge filters** | 5 trades only | Statistically unreliable |
| **HH_2/HH_3 lookback** | 0 trades | Too restrictive on 4h |
| **EMA dip 0.995/0.998** | 0-5 trades | Dip depth too specific |

### KEY INSIGHTS (v18)
- **Batch 22 SUCCESS**: ApexMomentumThreshold achieved Sharpe 2.03 on BTC-4h (GOLD TIER)
- **Parameter micro-optimization WORKS**: Close > EMA15 + Mom4 > 0.010 = deployable
- **HH lookback variations FAILED**: HH_2, HH_3 caused 0 trades (too restrictive)
- **EMA dip depth variations FAILED**: 0.995/0.998 multipliers = 0-5 trades
- **Volume filters kill trade count**: 20-40 trades vs 60+ for pure HH+Mom
- **BTC-4h MOST RELIABLE**: All top 5 strategies have BTC-4h as best Sharpe asset
- **Proven archetypes UNBEATEN**: CascadeHighMomentum 3.22 Sharpe remains #1 after 22 batches

---

## PROVEN ARCHETYPES (RANKED BY SHARPE)

### TIER 1 - LEGENDARY (Sharpe >2.5)

#### 1. CascadeHighMomentum (BEST - Sharpe 3.22)
```
HH = High[-1] > High[-2]
Mom4 = (Close[-1] / Close[-4] - 1) > 0.010
Entry = HH AND Mom4
Stop: 2.5x ATR initial, 2.0x ATR trail
```
- Works on: SOL, BTC, AVAX, BNB, DOGE, ETH (6 assets)
- Logic: HH confirms trend, 4-bar momentum filters noise
- Trades: 32-44 on 4h

#### 2. ElasticReclaim (Sharpe 3.21)
```
Dipped = Low[-2] < EMA15[-2]
Reclaimed = Close[-1] > Close[-2]
Entry = Dipped AND Reclaimed
Stop: 2.5x ATR initial, 2.0x ATR trail
```
- Works on: SOL, BTC, BNB, AVAX (4 assets)
- Logic: EMA bounce = support, close reclaim = momentum return
- Trades: 45-55 on 4h

#### 3. ApexCloseEma (Sharpe 2.67)
```
EMA_12 = Close.ewm(12).mean()
Mom4 = (Close / Close.shift(4) - 1) > 0.010
Entry = Close > EMA_12 AND Mom4
Stop: 2.5x ATR initial, 2.0x ATR trail
```
- Best: BTC-4h (11.43%, Sharpe 2.67, DD -2.10%)
- Lowest drawdown profile

### TIER 2 - SOLID (Sharpe 1.5-2.5)

#### 4. DualSpanMomentum (Sharpe 2.15)
```
Spread = (EMA_8 - EMA_21) / EMA_21
Entry = Spread > 0.006 AND Spread > Spread.shift(2) * 1.2
```

#### 5. CascadeDipReclaim (Sharpe 2.15)
```
EMA_12 = Close.ewm(12).mean()
Dipped = Low.shift(1) < EMA_12.shift(1) * 0.995
Reclaimed = Close > EMA_12
Entry = Dipped AND Reclaimed
```

---

## ASSET TIERS (v17)

### TIER 1 - DEPLOY ALL STRATEGIES
| Asset | Sharpe Range | Notes |
|-------|--------------|-------|
| BTC-USD-4h | 1.4-2.7 | **MOST RELIABLE**, consistent Sharpe, lowest DD |
| SOL-USD-4h | 0.7-3.2 | Highest returns but volatile Sharpe |

### TIER 2 - SELECTIVE DEPLOYMENT
| Asset | Sharpe Range | Notes |
|-------|--------------|-------|
| AVAX-USD-4h | 1.5-2.2 | Best for high-return |
| BNB-USD-4h | 1.8-2.5 | Lowest DD, conservative |

### TIER 3 - VALIDATION ONLY
| Asset | Sharpe Range | Notes |
|-------|--------------|-------|
| DOGE-USD-4h | 1.2-2.0 | Momentum strategies only |
| ETH-USD-4h | 1.4-1.9 | Conservative |
| ADA-USD-4h | 1.0-1.8 | Borderline |
| DOT-USD-4h | 0.8-1.5 | Inconsistent |

### DO NOT DEPLOY (EXCLUDED)
| Asset | Reason |
|-------|--------|
| XRP-USD | NEGATIVE return on ALL strategies (100% failure) |
| MATIC-USD | Sharpe <1.0 consistently |
| LINK-USD | Too volatile, inconsistent |

---

## MANDATORY RULES (v17)

### Entry Conditions
1. **EXACTLY 2 conditions** (3+ causes 0 trades)
2. **Momentum threshold**: 0.008-0.015 (NOT higher)
3. **Avoid**: Percentile ranking, volume filters, 3+ conditions

### Stop Configuration (PROVEN - DO NOT CHANGE)
```
Initial_stop = 2.5 * ATR_14
Trailing_stop = Highest_high - 2.0 * ATR_14
```

### Targets
| Metric | Minimum | Optimal |
|--------|---------|---------|
| Sharpe | >1.5 | >2.0 |
| MaxDD | <15% | <5% |
| Trades | >20 | 30-50 |
| Timeframe | 4h only | 4h only |

---

## OPTIMAL PARAMETERS (v17)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Mom 4-bar | > 0.010 | PROVEN BEST |
| Mom 3-bar | > 0.008 | Short momentum |
| Mom 5-bar | > 0.012 | Medium momentum |
| EMA short | 12-15 | Pullback detection |
| EMA long | 21 | Trend filter |
| ATR period | 14 | Standard |
| Initial stop | 2.5x ATR | Room to breathe |
| Trail stop | 2.0x ATR | Lock profits |

### WHAT TO AVOID
| Parameter | Why |
|-----------|-----|
| Mom > 0.020 | Signal starvation |
| Wide stops 4.0x+ | Hurts Sharpe |
| 3+ conditions | Zero trades on 80% assets |
| 1h timeframe | Negative Sharpe |
| Volume filters | Kills trade count to <10 |

---

## QUALITY TIERS (v17)

| Tier | Sharpe | DD | Trades | Deploy? |
|------|--------|-----|--------|---------|
| **LEGENDARY** | >2.5 | <5% | >30 | YES |
| GOLD | >2.0 | <10% | >25 | YES |
| SILVER | >1.5 | <15% | >20 | MAYBE |
| BRONZE | >1.0 | <20% | >15 | NO |
| FAILED | <1.0 | Any | Any | NO |

**Sharpe is PRIMARY metric. Return is SECONDARY.**
**Minimum 20 trades required for reliable Sharpe measurement.**

---

## IDEA FORMAT (v17)

```
[NEW_IDEA]
LONG ONLY. Condition1. Condition2. ATR_14 = ATR(14).
Entry = Cond1 AND Cond2.
Initial_stop = 2.5 * ATR_14. Trailing_stop = Highest_high - 2.0 * ATR_14.
```

### GOOD Example:
```
[NEW_IDEA]
LONG ONLY. HH = High > High.shift(1). Mom_4 = (Close / Close.shift(4)) - 1.
ATR_14 = ATR(14). Entry = HH AND Mom_4 > 0.010.
Initial_stop = 2.5 * ATR_14. Trailing_stop = Highest_high - 2.0 * ATR_14.
```

### BAD Example:
```
[NEW_IDEA]
LONG ONLY. Mom_6 > 0.025 AND Vol > 2.0x AND EMA > Close.  # 3 conditions = 0 trades
Initial_stop = 4.0 * ATR_14.  # TOO WIDE
```

---

## BATCH GENERATION RULES

### DO THIS
1. Base on PROVEN archetypes (HH+Mom, EMA Dip Reclaim)
2. Use EXACTLY 2 entry conditions
3. Keep momentum thresholds 0.008-0.015
4. Use standard stops (2.5x/2.0x ATR)
5. Target 30-50 trades on 4h

### DO NOT DO THIS
1. Chase high returns (>100%) at expense of Sharpe
2. Use wide stops (4.0x+)
3. Add 3+ conditions (causes 0 trades)
4. Use 1h timeframe
5. Add volume filters (kills trade count)
6. Include XRP, MATIC in expectations
7. Trust high Sharpe with <20 trades

---

## BUGS TO WATCH

| Bug | Symptom | Fix |
|-----|---------|-----|
| Zero trades | CSV shows 0 trades | Reduce to 2 conditions |
| Signal starvation | <10 trades on 4h | Loosen thresholds |
| High Sharpe trap | Sharpe >2.0 but <10 trades | IGNORE - unreliable |
| MyStrategy name | Wrong filename | force_strategy_name() |

---

## NEXT BATCH STRATEGY

**CRITICAL AFTER 21 BATCHES:**
- HYBRID approach maxed at Sharpe 1.45 (still below threshold)
- Volume filters consistently reduce trade count to unreliable levels
- Proven archetypes STILL UNBEATEN after 21 batches

**BATCH 22 RESULTS**: Parameter micro-optimization SUCCESS
- ApexMomentumThreshold: Sharpe 2.03 BTC-4h (GOLD TIER - NEW WINNER)
- HH_2/HH_3 lookback: FAILED (0 trades)
- EMA dip depth 0.995/0.998: FAILED (0-5 trades)
- EMA15 + Mom4 > 0.010: CONFIRMED OPTIMAL

**FOCUS FOR BATCH 23**: Further refinement of working patterns
1. **ApexMomentumThreshold variations**: Test on more assets
2. **EMA period fine-tuning**: EMA13, EMA14, EMA16 around optimal EMA15
3. **Momentum threshold fine-tuning**: 0.009, 0.011 around optimal 0.010

**AVOID (PROVEN FAILURES):**
- NEW patterns (Batch 20: max Sharpe 1.60)
- HYBRID approaches (Batch 21: max Sharpe 1.45)
- HH_2/HH_3 lookback variations (Batch 22: 0 trades)
- EMA dip depth variations (Batch 22: 0-5 trades)
- Volume filters (kills trade count)
- 3+ conditions (causes 0 trades)

---

**Last Updated**: 2026-01-26 (Post Batch 22)
**GOLD+ Count**: 5 (CascadeHighMomentum, ElasticReclaim, ApexCloseEma, CascadeDipReclaim, ApexMomentumThreshold)
**Batches Tested**: 22
**Best Sharpe Achieved**: 3.22 (CascadeHighMomentum SOL-4h)
**Lines**: ~290
