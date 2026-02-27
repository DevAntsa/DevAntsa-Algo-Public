# BEAR MARKET STRATEGY IDEA CREATION RULES

**Market Context:** Bear markets (2022 crypto winter -95% crash)
**Primary Goal:** Capital preservation + small gains while market bleeds
**Secondary Goal:** Profit from fear spikes and failed rallies
**Validated Timeframes:** 15m (BEST), 1h (GOOD), avoid 4h/1d

---

## DIRECTIONAL BIAS: 60% SHORT / 40% LONG

### SHORT STRATEGIES (60% of ideas)
Bear markets trend DOWN. Most profits come from shorting failed rallies, not catching bounces.

**Archetypes:**
1. **Failed Rally Shorts** (25% of ideas)
   - Price rallies into resistance (SMA, previous high, Fib level)
   - Volume dries up on rally (< 1.0x average)
   - RSI hits overbought (> 65-75) but price fails to break resistance
   - Momentum divergence (price higher high, RSI lower high)
   - Entry: Price rejection from resistance + volume decline

2. **Breakdown Continuation** (20% of ideas)
   - Price breaks major support level
   - Retest of broken support (now resistance)
   - Failed retest + increasing volume = short entry
   - Target: Next support level or measured move

3. **Overbought Exhaustion** (10% of ideas)
   - RSI > 70 on 15m/1h in bear market = extreme overbought
   - Stochastic > 80 + bearish divergence
   - Volume climax on rally (2.0x+ average) = exhaustion
   - Entry: First rejection candle after overbought peak

4. **Gap Down Continuation** (5% of ideas)
   - Overnight gap down > 2%
   - Failed gap fill attempt (price tries to fill, volume weak)
   - Short on failure to reclaim gap level

### LONG STRATEGIES (40% of ideas)
Only trade the strongest oversold reversals. Quick in, quick out.

**Archetypes:**
1. **Capitulation Bounce** (20% of ideas)
   - RSI < 25-30 + Volume spike (2.2x+ average)
   - Consecutive red days (3-4+) + momentum < -0.055
   - Close > previous low (rejection of lower lows)
   - Entry: First green candle after capitulation

2. **Support Zone Bounce** (10% of ideas)
   - Test of major support (previous low, BB lower, round number)
   - Bullish reversal candle (long wick, green close)
   - Volume confirmation (> 1.8x average)
   - Entry: Close above support + volume

3. **Extreme Deviation Mean Reversion** (10% of ideas)
   - Close < SMA(50) * 0.86-0.92 (severe deviation)
   - BB lower band (2.0-2.5 std dev)
   - RSI < 30
   - Target: Mean (SMA, BB mid) not new highs

---

## PARAMETER SPECIFICATIONS

### ENTRY INDICATORS (SHORTS)

**Resistance Levels:**
- SMA periods: 20, 50, 100 (bear market = price below all SMAs)
- Failed breakout: Close > High.rolling(N).max() then Close < entry level within 1-3 bars
- Fibonacci retracements: 38.2%, 50%, 61.8% of recent decline

**Overbought Signals:**
- RSI(14) thresholds: > 65-75 (anything above 65 is overbought in bear)
- Stochastic(14,3): > 75-85
- Volume decline on rally: < 0.8-1.0x rolling average

**Momentum Divergence:**
- Price makes higher high, RSI makes lower high
- MACD histogram declining while price rising
- Momentum(10-14) < 0.02 during rally (weak momentum)

### ENTRY INDICATORS (LONGS)

**Oversold Signals:**
- RSI(14): < 25-33 (lower than sideways < 35-45)
- RSI(7): < 20-28 for extreme entries
- Stochastic(14,3): < 15-25

**Volume Confirmation:**
- Panic spike: > 2.0-2.5x rolling(20) average
- Capitulation bar: Volume > 2.5x AND Close > Low * 1.015

**Support Levels:**
- Previous swing lows: Low.rolling(10-20).min()
- Bollinger Lower: Close.rolling(20).mean() - (2.0-2.5) * std
- Round numbers: $20, $50, $100, $1000, etc.

### RISK MANAGEMENT (ALL STRATEGIES)

**Stop Loss:**
- SHORT stops (TIGHT): 2.5-3.2x ATR(14) - bear rallies can be violent
- LONG stops (MEDIUM): 2.8-3.5x ATR(14) - need room for volatility

**Take Profit:**
- SHORT targets: 4.0-6.0x stop distance (bears trend longer)
- LONG targets: 3.5-4.6x stop distance (quick exits on bounces)
- Alternative: Target support/resistance levels, BB mid, SMA

**Max Holding Period:**
- SHORT: 24-48 bars (let losers prove themselves, cut winners on support)
- LONG: 18-28 bars (quick scalps, don't overstay bounces)
- 15m: 18-25 bars (5-6 hours)
- 1h: 22-28 bars (1 day)
- 4h: AVOID (tested poorly)

**Position Sizing:**
- Risk: 0.5-1.0% per trade (bear markets = higher risk)
- Reduce size on 4h/1d (not recommended timeframes)

---

## CRITICAL DO'S AND DON'TS

### ✅ DO:

1. **SHORT failed rallies** - Price rallies are selling opportunities, not breakouts
2. **Use volume divergence** - Declining volume on rally = weak rally = short
3. **Target previous support levels** - They become resistance in downtrends
4. **Trade 15m and 1h timeframes** - Validated in testing (+1.60% and +1.04%)
5. **Exit longs FAST** - 18-28 bars max, take profits at resistance
6. **Scale into shorts** - Add to winners as price breaks supports
7. **Use tight stops on longs** - Bear market bounces fail fast
8. **Require volume confirmation** - Both directions need volume validation
9. **Respect the trend** - Bias should be 60% short, 40% long
10. **Look for consecutive red days** - 3-4+ red days = oversold bounce setup

### ❌ DON'T:

1. **DON'T chase breakouts** - In bear markets, breakouts fail 80% of the time
2. **DON'T hold longs overnight** - Overnight gaps down are common
3. **DON'T use 4h or 1d timeframes** - Testing showed -0.71% and 0% returns
4. **DON'T ignore volume** - Low volume rallies = fake rallies = short setups
5. **DON'T expect V-bottom reversals** - Bear markets grind down slowly
6. **DON'T use wide stops on shorts** - Bear rallies are sharp but brief
7. **DON'T fight the trend** - Don't try to call the bottom with majority longs
8. **DON'T use momentum indicators for longs** - Momentum stays negative, use RSI/oversold
9. **DON'T trade BTC dominance** - Focus on high-beta alts (SOL, AVAX) for bigger moves
10. **DON'T expect high Sharpe ratios** - Bear markets = choppy, Sharpe 0.8-1.2 is good

---

## EXAMPLE SHORT STRATEGY (FAILED RALLY)

```
[NEW_IDEA]
ARCHETYPE: Failed Rally Breakdown / Resistance Rejection
SHORT ONLY. SMA_50 = Close.rolling(50).mean(). High_20 = High.rolling(20).max(). RSI_14 = RSI(14). ATR_14 = ATR(14). Vol_avg = Volume.rolling(20).mean(). Momentum_10 = Close.pct_change(10). Entry = Close > High_20.shift(1) * 0.995 AND Close < SMA_50 * 1.05 AND RSI_14 > 68 AND Volume < 0.85 * Vol_avg AND Momentum_10 < 0.025. Stop = 2.8 * ATR_14. TP = 5.0 * stop_dist. Risk 0.75%. Max hold = 32 bars.
```

**Logic:** Price rallies to 20-bar high near SMA50 resistance, RSI overbought, but volume declining and momentum weak. This is a fake rally. Short when price fails to break resistance.

---

## EXAMPLE LONG STRATEGY (CAPITULATION BOUNCE)

```
[NEW_IDEA]
ARCHETYPE: Oversold RSI Reversal / Capitulation Bounce
LONG ONLY. RSI_14 = RSI(14). Momentum_fast = Close.pct_change(7). SMA_50 = Close.rolling(50).mean(). ATR_14 = ATR(14). Vol_avg = Volume.rolling(20).mean(). Entry = RSI_14 < 28 AND Momentum_fast < -0.055 AND Close < SMA_50 * 0.92 AND Volume > 2.2 * Vol_avg. Stop = 3.0 * ATR_14. TP = 4.5 * stop_dist. Risk 0.5%. Max hold = 25 bars.
```

**Logic:** (Validated winner from testing) Extreme oversold + panic volume + deviation from mean = high probability bounce. Exit quickly before next leg down.

---

## DIVERSITY REQUIREMENTS

For a batch of 18 bear market ideas:
- **11 SHORT ideas** (60%)
  - 4-5 Failed Rally Shorts
  - 3-4 Breakdown Continuations
  - 2-3 Overbought Exhaustion
  - 1 Gap Down Continuation

- **7 LONG ideas** (40%)
  - 3-4 Capitulation Bounces
  - 2 Support Zone Bounces
  - 1-2 Extreme Deviation Mean Reversions

Vary parameters by 10-20% between similar ideas:
- RSI thresholds: 25, 27, 30, 33 (not all 28)
- Volume multipliers: 2.0x, 2.2x, 2.5x (not all 2.2x)
- ATR stops: 2.5x, 2.8x, 3.0x, 3.2x (not all 3.0x)

---

## BACKTESTING SUCCESS CRITERIA

**Per Asset/Timeframe:**
- Return: **> 0%** (beating -95% market is the bar)
- Sharpe Ratio: **> 0.8** (bear markets are choppy)
- Max Drawdown: **< 2.0%**
- Trades: **5-25 per asset** (not 0, not 200)
- Win Rate: **> 35%** (R:R compensates for low win rate)

**Multi-Asset Passing Rate:**
- **> 40%** of assets must be profitable
- **> 60%** of assets must have Sharpe > 0.5
- At least **3 assets** with return > 1.0%

---

## VALIDATED WINNERS FROM TESTING

✅ **RSICapitulation (LONG)** - SOL-USD-15m: +1.60%, 18 trades, Sharpe 1.09
✅ **RSICapitulation (LONG)** - SOL-USD-1h: +1.04%, 19 trades, Sharpe 0.86
✅ **RSICapitulation (LONG)** - BNB-USD-15m: +0.83%, 3 trades, Sharpe 1.27

**Note:** All validated strategies were LONG bounces. SHORT strategies not yet tested but theoretically stronger in bear markets.

---

## NOTES

- Bear markets last 6-18 months typically
- Expect 60-80% of days to be red
- Overnight risk is HIGH (use day-trading stops)
- Psychological bias: Everyone wants to call the bottom (don't)
- Best edge: SHORT failed rallies + LONG extreme capitulation
- Commission matters: 200+ trades = death, aim for 10-30 trades per asset
