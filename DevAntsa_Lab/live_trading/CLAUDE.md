# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# DevAntsa Lab - Live Trading System

## Overview
Automated crypto futures trading system running on Binance Futures Demo. 8 strategies across 3 market regimes (bull/sideways/bear), all walk-forward validated and sweep-optimized on 5-year data (2021-2026). Goal: validate for prop firm trading (Crypto Fund Trader).

## Location
Runtime: `C:\Users\luoto\MoneyGlich\moon-dev-ai-agents\DevAntsa_Lab\live_trading\`
Development: `C:\Users\luoto\MoneyGlich\DevAntsa-Lab\DevAntsa_Lab\live_trading\`
IMPORTANT: Both copies must stay in sync. Always update both after changes.

## Run Command
```
cd C:\Users\luoto\MoneyGlich\moon-dev-ai-agents
conda activate tflow
python -m DevAntsa_Lab.live_trading.engine.main_loop
```

## Architecture
- **engine/main_loop.py** — Core trading loop (dynamic tick interval, higher TF strategies gated)
- **engine/signal_engine.py** — Collects signals from all 8 v11 strategies
- **engine/regime_gate.py** — BTC EMA-50 slope classifier (display only, all strategies self-gate)
- **engine/position_manager.py** — Tracks open positions, enforces limits
- **engine/conflict_resolver.py** — Resolves conflicting signals on same asset
- **risk/risk_manager.py** — Phase-based leverage, drawdown limits, kill switches, portfolio exposure caps
- **risk/position_sizing.py** — Position size calculation from risk/stop/leverage
- **execution/binance_executor.py** — Binance Futures Demo API wrapper
- **notifications/telegram_notifier.py** — Notifications + commands (/positions, /status, /stats, /help)
- **utils/console.py** — Rich colored terminal output
- **data/state_manager.py** — JSON state persistence (positions, candle times)
- **strategies_v11/** — All 8 v11 strategy implementations + shared indicators
- **dashboard.py** — Live trading dashboard (Streamlit)

## 8 Strategies (Portfolio v11 — walk-forward validated, sweep-optimized, deployed 2026-03-05)

### Bull LONG (2 strategies)
| Strategy | Asset | TF | 5yr Return | Sharpe | DD | WF | Signal Family |
|----------|-------|----|-----------|--------|-----|-----|---------------|
| ElasticMultiSignal | SOL | 4h | +201.0% | 1.61 | -8.53% | 85% | 3-signal (CCI+WR+ROC) |
| DonchianModern | BTC | 4h | +58.0% | 1.35 | -5.60% | 103% | Donchian breakout |

### Sideways LONG (3 strategies)
| Strategy | Asset | TF | 5yr Return | Sharpe | DD | WF | Signal Family |
|----------|-------|----|-----------|--------|-----|-----|---------------|
| MultiSignalCCI | SOL | 4h | +135.3% | 1.92 | -3.88% | 85% | CCI+WR+ROC portfolio |
| DailyCCI | SOL | D | +41.3% | 1.38 | -3.70% | - | CCI(8) daily |
| EMABounce | ETH | 4h | +24.8% | 0.95 | -6.31% | 168% | EMA50 bounce |

### Bear SHORT (3 strategies)
| Strategy | Asset | TF | 5yr Return | Sharpe | DD | WF | Signal Family |
|----------|-------|----|-----------|--------|-----|-----|---------------|
| ExitMicroTune | ETH | 4h | +75.4% | 1.22 | -6.53% | - | Quality-stratified 4-signal |
| BCDExitTune | SOL | 4h | +est | 1.0+ | -5.00% | - | Type-stratified 4-signal |
| PanicSweepOpt | BTC | 4h | +26.6% | 1.17 | -5.08% | - | PanicCascade sweep-opt |

## Position Limits
- 2 bull + 3 sideways + 3 bear = 8 max concurrent
- Regime gate DISABLED (v11) — all strategies self-gate via SMA200
- Binance one-way mode: opposite directions on same asset blocked
- Signal priority: Bull > Sideways > Bear on same asset

## Risk Rules

### Per-Trade Risk
- Global risk scale: 0.85 (15% portfolio-level haircut on ALL risk)
- Per-strategy risk scale: ElasticMultiSignal 0.65x (SOL volatility)
- Per-signal risk via Signal.metadata["risk_pct"] (multi-signal strategies)
- Fallback risk from STRATEGY_RISK_OVERRIDES (0.5%-2.0%)

### DD-Budget Leverage (v11)
- Only strategies with backtest DD < 4% get leverage > 1.0x at prop level
- MultiSignalCCI: prop 1.5x (DD=3.88% * 0.85 * 1.5 = 4.95%)
- DailyCCI: prop 1.5x (DD=3.70% * 0.85 * 1.5 = 4.72%)
- All others: prop 1.0x (DD too high for safe leverage)
- Adaptive phase system further reduces leverage in drawdown (SURVIVAL=1.0x)

### Portfolio-Level Safety (v11)
- Per-asset exposure cap: SOL 6%, BTC 5%, ETH 5% of equity (prevents concentration)
- Aggregate exposure cap: 15% of equity max total risk across all positions
- DD action levels: -1.5% review, -2% reduce to 1/regime, -3% halt entries, -4% close all
- Kill switches: Total DD >= 7%, Sharpe < 0.5 after 20 trades, live DD > 1.5x backtest DD

### Bear Risk Scaling
- Bear risk = base * BEAR_PHASE_RISK_MULTIPLIER[phase]
- BUILDING/ACCELERATING: 1.0x | PROTECTING: 0.75x | RECOVERY: 0.50x | SURVIVAL: 0.35x

## Dashboard (updated 2026-03-05 for v11)
- **File:** `dashboard.py` (~1070 lines, single-file Streamlit app)
- **Run:** `streamlit run DevAntsa_Lab/live_trading/dashboard.py`
- **URL:** http://localhost:8502
- **Tech:** Streamlit + Plotly + TradingView embedded widget + streamlit-autorefresh
- **Theme:** Black + gold, glassmorphism cards, animated wave ribbons, TradingView-inspired
- **v11 updates:** 3-regime display (bull/sideways/bear), 8-strategy grid, cyan sideways badges, effective risk with GLOBAL_RISK_SCALE shown

## Branding
- Name: DevAntsa Lab
- Tagline: "Precision trading, systematic execution"

## Key Files
- `config.py` — All parameters, leverage caps, strategy configs, safety limits
- `strategies_v11/` — 8 strategy implementations + indicators.py
- `dashboard.py` — Live trading dashboard (Streamlit)
- `data/state.json` — Persisted positions and risk state
- `data/trades.csv` — Trade journal log

## CFT Challenge (Crypto Fund Trader — $200K 2-Phase)
- **Fee:** $1,250 one-time
- **Platform:** Bybit API (connect API key to CFT dashboard)
- **Phase 1:** 8% profit ($16K), 5% daily DD, 10% total DD, min 5 trading days
- **Phase 2:** 5% profit ($10K), 5% daily DD, 10% total DD, min 5 trading days
- **Live Stage:** 80% profit split, 5% daily DD, 10% total DD
- **Our safety margins:** Daily 3% vs 5% CFT (+2%), Total 7% vs 10% CFT (+3%)
- **Plan:** Demo validate first (20-30+ trades), then buy challenge

## Current Stage
Stage 2: Demo validation with Portfolio v11 (walk-forward validated, sweep-optimized).
Running on Binance Futures Demo. Need 20-30+ trades before prop firm.
Dashboard live at localhost:8502 for visual monitoring.

## Portfolio History
- v1 (2026-02): 3 bull + 2 bear + 3 sideways. Hit kill switch after 5 losing days.
- v2 (2026-02-18): 5 bull + 3 bear, all 5yr-validated. Avg bull S=0.99, bear S=0.40.
- v10 (2026-02-21): 6 bull + 9 bear, sweep-optimized, MC validated. Bull S=1.25, Bear S=1.19.
- v10 fixes (2026-02-23): Fill confirmation, exchange safety hardening (8 bugs fixed).
- v11 (2026-03-05): 2 bull + 3 sideways + 3 bear. 3-regime system. Walk-forward validated. DD-budget leverage. Portfolio-level safety caps. GLOBAL_RISK_SCALE=0.85. Multi-signal strategies with per-signal risk.
