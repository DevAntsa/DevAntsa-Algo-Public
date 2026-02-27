# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# DevAntsa Lab - Live Trading Framework

## Overview
Automated crypto futures trading framework for Binance Futures. Supports multiple strategies across bull and bear market regimes, all sweep-optimized and Monte Carlo validated on 5-year data (2021-2026). Built for prop firm trading (Crypto Fund Trader).

Framework ships with an example strategy (SMA crossover). Add your own by extending `StrategyBase`.

## Run Command
```
python -m DevAntsa_Lab.live_trading.engine.main_loop
```

## Architecture
- **main_loop.py** -- Core trading loop (dynamic tick interval, higher TF strategies gated)
- **signal_engine.py** -- Collects signals from all strategies
- **regime_gate.py** -- BTC EMA-50 slope classifier (display only, filtering DISABLED -- all strategies self-gate)
- **position_manager.py** -- Tracks open positions, enforces limits
- **risk_manager.py** -- Phase-based leverage, drawdown limits, kill switches
- **telegram_notifier.py** -- Notifications + commands (/positions, /status, /stats, /help)
- **console.py** -- Rich colored terminal output

## Adding Your Own Strategies

1. Create a new file in `strategies/` (e.g., `my_strategy.py`)
2. Subclass `StrategyBase` from `strategies/base.py`
3. Implement required methods:
   - `compute_indicators(df)` -- Add indicator columns to the OHLCV DataFrame
   - `check_entry(df)` -- Return a `Signal` when entry conditions met, else `None`
   - `check_exit(df, position)` -- Return an `ExitSignal` when position should close, else `None`
   - `calculate_trail(df, position)` -- Return updated trailing stop price, or `None`
4. Set class attributes: `name`, `regime`, `direction`, `assets`, `timeframe`
5. Register in `signal_engine.py` (import + add to strategies list)
6. Add config in `config.py` (risk overrides, leverage caps, asset mapping, timeframe)

See `strategies/example_sma_crossover.py` for a complete working example.

## Position Limits
- Configurable per regime (default: 6 bull + 9 bear = 15 max)
- Regime gate optional -- strategies can self-gate via SMA200
- Binance one-way mode: opposite directions on same asset blocked

## Risk Rules
- Per-strategy risk: configurable via STRATEGY_RISK_OVERRIDES in config.py
- Bear risk: STRATEGY_RISK_OVERRIDES * BEAR_PHASE_RISK_MULTIPLIER (phase scales risk)
  - BUILDING/ACCELERATING: 1.0x (full override)
  - PROTECTING: 0.75x | RECOVERY: 0.50x | SURVIVAL: 0.35x
- Daily DD limit: 3% (halt), 4% (close all)
- Total DD limit: 7%
- Kill switches: Sharpe < 0.5 after 20 trades, live DD > 1.5x backtest DD

## Dashboard
- **File:** `dashboard.py` (Streamlit app)
- **Run:** `streamlit run DevAntsa_Lab/live_trading/dashboard.py` (separate process from main_loop)
- **URL:** http://localhost:8502
- **Tech:** Streamlit + Plotly + TradingView embedded widget
- **Sections:** Header, key metrics, TradingView chart, system status, positions, strategy grid, equity curve, trades, stats

## Key Files
- `config.py` -- All parameters, leverage caps, strategy configs
- `strategies/base.py` -- StrategyBase class + indicator helpers
- `strategies/example_sma_crossover.py` -- Example strategy template
- `dashboard.py` -- Live trading dashboard (Streamlit)
- `data/state.json` -- Persisted positions and risk state
- `data/trades.csv` -- Trade journal log

## CFT Challenge (Crypto Fund Trader -- $200K 2-Phase)
- **Platform:** Bybit API (connect API key to CFT dashboard)
- **Phase 1:** 8% profit target, 5% daily DD, 10% total DD, min 5 trading days
- **Phase 2:** 5% profit target, 5% daily DD, 10% total DD, min 5 trading days
- **Live Stage:** 80% profit split, 5% daily DD, 10% total DD

## Branding
- Name: DevAntsa Lab
- Tagline: "Precision trading, systematic execution"
