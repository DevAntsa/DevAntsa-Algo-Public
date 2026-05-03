# Changelog

All notable changes to this framework. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-05-03

First public tagged release. The framework matches the v12 portfolio that was deployed live to a Crypto Fund Trader $200K prop account on 2026-04-04.

### Added
- Bybit V5 USDT Perpetual Futures executor with native order amendment, JSON body POSTs, and X-BAPI auth
- Binance Futures executor (demo) for environment validation
- Three-regime gating system (bull / sideways / bear) with BTC EMA-50 slope classifier
- Conflict resolver for one-way mode same-asset opposite-direction signals
- Multi-layer risk architecture: per-strategy %, per-asset cap, aggregate cap, DD-Mod feedback, graduated daily close-all
- DD-Mod feedback controller (Hsieh & Barmish 2017) — quadratic risk scaler guarantees bounded DD
- Graduated daily close-all (1.5% / 2.0% / 2.5%) — winner of 14-config sweep on 5-year data
- Position reconciliation every tick (eliminates ghost positions on exchange disconnects)
- Atomic trailing stop modification (place-first-then-cancel)
- RBI (Research-Backtest-Iterate) AI strategy factory with composite scoring and walk-forward gating
- Liquidation collector (Bybit V5 + Binance + OKX WebSocket streams)
- Streamlit war-room dashboard with live TradingView charts, equity curve, position grid, FNG card
- Telegram bot — entry/exit alerts, trail updates, daily summaries, threshold alerts (FNG 35/50/80), command interface (/positions, /status, /stats)
- systemd deployment scaffold (auto-restart on crash, auto-start on reboot)
- Walk-forward validation harness (80/20 split + retention ratio gate)
- Monte Carlo risk validation (5,000-sim portfolio bootstrap)
- Multi-account split optimizer (1024-combo backtest sweep)
- Macro correlation analysis tool (6 factors × all trades)

### Validated
- 5-year walk-forward backtest 2021-01-13 → 2026-02-17, 1,030 trades, every year profitable
- Sharpe 2.23, Return +808%, Max DD -12.56%, Win Rate 55.1%, Profit Factor 1.76
- Monte Carlo 5,000 sims: median DD -10.20%, 95th-pct worst DD -14.92%
- Stage 0 equivalence test: 44,715 ticks, 714 trades, 0 violations (signal match, bars_held correctness, no mid-bar evaluation, no duplicate signals, TP1/TP2 partials, trailing stop monotonicity, conflict resolution)

### Notes
- Strategy implementations in `live_trading/strategies/` are proprietary and not included; the framework ships one example strategy (`example_sma_crossover.py`)
- Default config targets a $200K Crypto Fund Trader prop account on Bybit Demo (api-demo.bybit.com)
- All risk numbers above are backtest figures; live performance will vary
