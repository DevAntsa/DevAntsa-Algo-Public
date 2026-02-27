# RBI Bear 15-Minute Agent - Claude Code Reference

## My Role
I am Claude Code, assisting with the **Bear 15-Minute Strategy System**. My job is to:
1. Add trading strategy ideas to `ideas_bear_15min.txt` (No removing any text)
2. Review backtest results and report winners
3. Update rules/prompts when needed
4. Never run the agent myself - admin (DevAntsa) handles that

## Key Files

| File | Purpose |
|------|---------|
| `Bear15min_rules.md` | **MAIN REFERENCE** — Current alpha, lessons learned, strategy guidelines |
| `BEAR_MARKET_IDEA_RULES.md` | Detailed bear strategy archetypes, parameter specs, DO's/DON'Ts |
| `ideas_bear_15min.txt` | Ideas file with header rules + strategy ideas |
| `rbi_agent_pp_multi_devantsa_bear_15min.py` | The RBI agent with prompts for Grok-4 |
| `multi_data_tester_15min.py` | Tests strategies across all 4 bear 15m assets |
| `results_bear_15min/` | CSV results from backtests |
| `rbi_regime_bear/` | 15m bear period data (BTC, ETH, SOL, BNB) |
| `DevAntsa_Best_Bear/` | Saved winning strategies |

## Key Paths (all relative to `RBI_Bear/`)

```
RBI_Bear/
  rbi_agent_pp_multi_devantsa_bear_15min.py   # Main agent
  multi_data_tester_15min.py                   # Multi-asset tester (writes to results_bear_15min/)
  ideas_bear_15min.txt                         # Strategy ideas input
  Bear15min_rules.md                            # MAIN REFERENCE — rules, alpha, lessons
  BEAR_MARKET_IDEA_RULES.md                    # Detailed bear archetypes reference
  results_bear_15min/                          # CSV results output
  rbi_regime_bear/                             # Data folder
    BTC-USD-15m.csv
    ETH-USD-15m.csv
    SOL-USD-15m.csv
    BNB-USD-15m.csv
  backtest_stats_bear_15min.csv                # Stats tracker (auto-generated)
  backtest_stats_bear_15min_crypto.csv         # Crypto tier stats (auto-generated)
  processed_ideas_bear_15min.log               # Processed ideas log (auto-generated)
```

## Current State (Pre-Batch 1 — No validated winners on 15m yet)

### Bear Market Strategy Approach
- **PURE SHORT ONLY** — no LONG strategies
- SHORT archetypes: Failed rally, breakdown continuation, overbought exhaustion, momentum divergence
- Commission: 0.055% per trade (0.11% round-trip on Bybit taker) - Crypto Fund Trader
- EXACTLY 2 conditions per strategy (prevents signal starvation)
- Target: 30-100 trades on 15m data
- 4 assets: BTC, ETH, SOL, BNB (15m bear period data)

### Validated from 1h testing (to adapt for 15m)
- RSICapitulation (LONG): SOL +1.60%, BNB +0.83% on 15m already

### Full details in `Bear15min_rules.md`

## How to Review Results

When asked to review results:
1. Read CSVs from `results_bear_15min/`
2. Find strategies with positive returns
3. Report for each winner's best asset: **Return%, Max DD%, Sharpe, Trade count**
4. A valid winner needs: Return > Max DD (for algo swarm), Trades 30-100, Sharpe > 0.3, 2+ assets positive

## Important Rules

1. **Never name strategies** - names mess up Grok-4 research
2. **Batch size**: 18 ideas (18 parallel threads)
3. **Don't run the agent** - admin monitors terminal
4. **Paste reviews in chat** - never create new files for results
5. **Keep ideas concise** - don't over-prescribe, let Grok-4 research
6. **PURE SHORT only** - no LONG strategies in bear system
