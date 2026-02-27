# Bear 15-Minute Strategy Rules

### DO NOT REMOVE THESE TOP RULES ###
1. Your job is only to add ideas into C:\Users\anton\MoneyGlich\moon-dev-ai-agents\DevAntsa_Lab\RBI_Agents\RBI_Bear\ideas_bear_15min.txt WITH the correct format. DO NOT REMOVE ANY TEXT FROM THE FILE UNLESS ASKED TO.
2. You only edit prompts or agent file if asked. C:\Users\anton\MoneyGlich\moon-dev-ai-agents\DevAntsa_Lab\RBI_Agents\RBI_Bear\rbi_agent_pp_multi_devantsa_bear_15min.py
3. We are creating PURE SHORT strategies for algo trading in crypto for bear market periods. SHORT ONLY — no LONG strategies.
4. When asked to review results I want every winning strategie's best performing asset's stats. Return%, Buy_Hold%, Max DD%, Sharpe, Trade count. Always include Buy_Hold_% so we can compare if SHORT strategy beats short-and-hold.
5. We update this file with newest alpha. Grok-4 RBI agent researches ideas, backtests, optimizes on 15min crypto bear data.
6. When creating ideas never name the idea ANYTHING. Names mess up Grok-4 research.
7. Add ideas in batches of 18 total (18 AI threads run simultaneously).
8. Never run the agent yourself - admin (DevAntsa) monitors terminal.
9. Review results from CODE: C:\Users\anton\MoneyGlich\moon-dev-ai-agents\DevAntsa_Lab\RBI_Strategy_Code CSV RESULTS: C:\Users\anton\MoneyGlich\moon-dev-ai-agents\DevAntsa_Lab\RBI_Agents\RBI_Bear\results_bear_15min
10. Paste review into chat, never create new files.

---

## PROGRESS SUMMARY (Post-Batch 3)

- **Batch 1**: 0/17 winners. "Overbought at premium" = overtrading (100-800 trades).
- **Batch 2**: 1 marginal winner (ExtremeStochDecline BNB +16.9%, doesn't beat 52% short-and-hold). 0 beating target.
- **Batch 3**: 0/17 winners. Capitulation pattern (2 conditions) from 4h = failed on 15m. 7/17 had 350-778 trades (overtrading), 4/17 had 0 trades (starvation).
- **PIVOT**: Expert from live trading loop provided design principles. Complete rewrite for Batch 4.
- **Batch 4**: 18 ideas using EXPERT design — 3+ conditions, fixed 1-1.5% TP, max 30-50 bars, no trailing stop, BTC focus.

**Cumulative: 52 strategies tested, 0 beating short-and-hold. Batch 4 uses expert-validated design.**

---

## COMMISSION & FRICTION MATH (Expert-validated)

- 0.055% per trade taker fee (0.11% round-trip in backtest)
- Real friction with slippage: ~0.10% round-trip (0.04% fee + 0.01-0.02% slippage)
- **REJECT any strategy with avg profit-per-trade < 0.4%** (friction kills it)
- Profit targets must be >= 0.8%, ideally 1-1.5%
- PRIMARY ASSET: BTC (no conflicts in live loop during bear)
- Secondary: ETH, SOL, BNB (cross-validation only)

---

## SUCCESS CRITERIA (Updated with Expert Input)

A strategy is a WINNER if:
- **Positive Sharpe** (>0.3 preferred, >0.5 ideal)
- **Return > Max Drawdown** (required for algo swarm deployment)
- **Trades: 30-120** on 15m data (~35,000 bars = full year 2022)
- **Avg profit-per-trade >= 0.4%** (Expectancy_% column in CSVs)
- **BTC must be positive** (primary deployment asset)
- **Max DD < 15%** (live kill switch fires at 1.5x backtest DD)

---

## BATCH 1 RESULTS — KEY LEARNINGS

### Closest to Winner
- **RollingDivergence**: BTC +3.39% (DD -3.63%, Sharpe 0.73, 46 trades), SOL +4.69% (DD -3.78%, Sharpe 0.52, 29 trades). 2/4 positive. Best balanced.
- **EMAWeakRally**: SOL +15.80% (DD -5.21%, Sharpe 1.39, 20 trades). 3x ratio but only 20 trades and 1/4 positive.
- **PremiumStochastic**: ETH +12.74% (DD -13.38%, Sharpe 0.82, 173 trades). Overtrading but ETH edge notable.

### What Worked (Batch 1)
1. **Momentum divergence** = best archetype (RollingDivergence closest to winner)
2. **SOL** = strongest SHORT asset in bear markets (best result in 5/6 top strategies)
3. **Weak momentum filter** (pct_change < 0.015) pairs well with price-level conditions
4. **EMA/SMA premium + fast RSI** = good combo when thresholds are tight enough

### What Failed (Batch 1)
1. **Overtrading** — 10/17 strategies had 100-800 trades (RSI > 65, Stoch > 75 fire constantly on 15m)
2. **Close > SMA * 0.995** = proximity too loose, fires on almost every candle
3. **Pure overbought without price-level filter** = overtrades badly
4. **Double-oscillator entries** (RSI + Stoch together) = too correlated
5. **Volume entries** = unreliable on demo data
6. **Retest logic too strict** — RetestFailure (3-5 trades), RetestBreakdown (0-2 trades)

---

## SHORT STRATEGY ARCHETYPES (Batch 4+ — Expert-Validated 3+ Condition Design)

**CRITICAL**: All ideas MUST have 3+ entry conditions. Pick 1+ from each category:
- **Category A — Breakdown structure**: Close < Low(N), Close < SMA * discount, EMA alignment
- **Category B — Momentum confirmation**: Momentum < threshold, RSI < threshold, MACD falling
- **Category C — Volume/volatility confirmation**: Volume > Nx avg, ATR expanding

### Archetype 1 — Breakdown + Momentum + Volume (~8 ideas)
- Close < Low(14-30).shift(1) + Momentum < threshold + Volume > 1.8-2.5x avg
- The 3-condition version of our best Batch 3 structure
- Breakdown provides structure, momentum confirms direction, volume validates conviction

### Archetype 2 — SMA Discount + Momentum + Volume (~5 ideas)
- Close < SMA(20-100) * 0.97-0.99 + Momentum < threshold + Volume > Nx avg
- Price well below moving average + already crashing + panic selling

### Archetype 3 — Trend Alignment + Momentum + RSI (~3 ideas)
- EMA(20) < EMA(50) + Momentum < threshold + RSI < 35
- Trend confirmed bearish + crash in progress + oversold extreme

### Archetype 4 — Triple Momentum Confirmation (~2 ideas)
- Momentum(short) < threshold + Momentum(long) < threshold + Volume > Nx avg
- Multi-timeframe momentum alignment (e.g., 10-bar AND 30-bar both crashing)

---

## PARAMETER SPECIFICATIONS (Batch 4+ — Expert-Validated)

### ENTRY INDICATORS — SHORTS (3+ required per idea)

| Indicator | Threshold | Category |
|-----------|-----------|----------|
| Momentum(14-30) | < -0.03 to -0.06 | B - Momentum |
| RSI(14) | < 30-40 | B - Momentum |
| MACD histogram | < 0 AND declining | B - Momentum |
| Volume vs avg | > 1.8-2.5x rolling(20-25) avg | C - Confirmation |
| ATR expanding | ATR > ATR.shift(5) | C - Confirmation |
| Low(14-30) | Close < Low.shift(1) | A - Structure |
| SMA(20-100) | Close < SMA * 0.97-0.99 | A - Structure |
| EMA alignment | EMA(20) < EMA(50) | A - Structure |

### RISK MANAGEMENT (Expert-validated for 15m SHORT)

- **Stop loss**: 1.5-2.0x ATR(14) — tighter than 4h, matching smaller TP
- **Take profit**: SINGLE fixed target at 1.0-1.5% below entry (NO multi-tier)
- **Max hold**: 30-50 bars (7.5-12.5 hours — bear moves reverse fast on 15m)
- **NO trailing stop** — 15m bear moves don't trend long enough
- **Risk per trade**: 0.35-0.50% of equity
- **3+ entry conditions** (extremely selective = fewer but higher quality trades)

---

## WHAT DOESN'T WORK (52 strategies across 3 batches, 0 winners)

### Approach 1 — "Overbought at premium" (Batch 1-2): 0/35 winners
1. RSI > 65-70 + Close > SMA = overtrades (200+ trades)
2. Double-oscillator entries (RSI+Stoch) = too correlated, no edge

### Approach 2 — "Capitulation with 2 conditions" (Batch 3): 0/17 winners
3. Momentum(7-14) < -0.03 to -0.04 with only 2 conditions = 400-778 trades (overtrading)
4. Momentum(20-40) < -0.04 to -0.06 with only 2 conditions = 355-473 trades
5. Close < Low(N) + Volume > 2.0x (2 conditions) = 0 trades (starvation)
6. 2-tier TP (4x/7x ATR) = holds too long, catches bounce-backs on 15m
7. Max hold 64-85 bars = too long, bear moves on 15m reverse within 30-50 bars
8. Stop 2.7x ATR = too wide for 15m where targets are 1-1.5%

### Key insight from expert:
- **2 conditions is fundamentally too loose on 15m** — either overtrades or starves
- **Need 3+ conditions** to be selective enough for profitable 15m SHORT
- **Quick exits (1-1.5% target, 30-50 bar max)** — don't hold for home runs
- **No trailing stop** — bear moves don't trend on 15m

---

## BEST ASSETS FOR BEAR SHORTS (Live Loop Context)

**PRIMARY: BTC** — No existing bear strategy on BTC. Bull strategies (ElasticReclaim, MomentumAcceleration) get regime-gated in bear, freeing the asset slot. Best fit for deployment.
**SECONDARY: ETH** — ConfluentMomentum already holds SHORT 4H. A 15m SHORT ETH could be blocked when that's in position. Use for cross-validation only.
**SECONDARY: SOL** — Already used by 4 strategies (3 LONG + 1 SHORT). Crowded. Use for cross-validation only.
**ALTERNATIVE: DOGE, AVAX, LINK** — No conflicts at all, but lower liquidity = more slippage.

---

## DEPLOYED TO LIVE TRADING (Bear Strategies)

| Strategy | Asset | Direction | Timeframe |
|----------|-------|-----------|-----------|
| ConfluentMomentum | ETHUSDT | SHORT | 4h |
| SurgeBreakdown | SOLUSDT | SHORT | 1h |

**Next candidates**: 15m bear SHORT strategies from this system (once validated).

---

## LIVE LOOP COMPATIBILITY RULES (From Expert / System Architect)

1. **Closed-bar only** — entries at candle close, exchange stop handles intra-bar
2. **3+ condition entries** — 2 is too loose on 15m (proven by 52 failures)
3. **ATR stops only** — 1.5-2.0x ATR, no fixed %
4. **Single stop price** — one ATR-based SL placed on exchange at entry
5. **NO trailing stop** — 15m bear moves don't trend long enough
6. **Single fixed TP** — 1.0-1.5% below entry, close entire position (NO multi-tier)
7. **has_trailing_stop = False** — recommended for 15m bear
8. **Max hold 30-50 bars** — if it hasn't worked by then, the move is over
9. **Regime gate** — Bear SHORT strategies are self-filtering (ungated)
10. **Kill switch** — fires at backtest DD x 1.5. Keep DD < 15%
11. **15m = 4 evals/hour** — system fetches 200 bars for indicator warm-up
12. **One direction per asset** — BTC is free for SHORT in bear (bull strats gated)

---

## IDEA TEMPLATE (Batch 4+)

```
[NEW_IDEA]
ARCHETYPE: SHORT [Descriptive name]
SHORT ONLY. [3+ conditions with specific thresholds]. Stop = entry + 1.5-2.0 * ATR_14. TP = entry * 0.99 (fixed 1% target). Size based on 0.40% risk. Max hold 40 bars. NO trailing stop.
Target 30-120 trades on ~35000 bars of 15m data. Commission: 0.055% per trade (Bybit). Avg profit >= 0.4%.
```
