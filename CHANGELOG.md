# Changelog

All notable changes to this framework. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-05-10

Multi-account framework + SMC strategy class + sizing-scaler infrastructure. Internal v15+SMC stack now live across two CFT prop accounts ($300K combined effective capital). Strategy implementations remain proprietary.

### Added
- **StrategyBase adapter pattern** (`strategies_smc/_adapters.py`) — wraps R&D-format strategy engines into the StrategyBase interface that signal_engine expects. Demonstrates how to integrate a strategy whose detection logic uses a different API surface (e.g., AI-generated R&D output) without rewriting the engine.
- **Per-cell config-flag gating** — same conditional-registration pattern from v15, extended for SMC strategy class (3 cells, individual flags + master enable).
- **State path env override** — `STATE_FILE` and `TRADE_LOG_FILE` in config.py now read from env vars with fallback to canonical paths. Enables multi-account deployments where each loop instance writes to its own state.json / trades.csv.
- **Multi-account systemd service template** (`scripts/devantsa-loop-acct2.service.template`) — example second-instance service file showing env-var pattern for parallel deployment with separate API keys, ACCOUNT_INDEX, state files.
- **Pulse-deep audit upgrade** — added SMC strategy registration check, count-mismatch detection (catches half-flipped flag state), and 5 backup file presence checks (revert-path validation).
- **Telegram account labeling** — `ACCOUNT_INDEX` env var prefixes every alert with `[Acct #N]` so multiple instances can share one bot/chat without confusion.

### Validated
- v15+SMC stack live across two parallel accounts (Account #1 $200K + Account #2 $100K = $300K). Both running same code, scaled risk-pct per equity, separate state/trade logs, 1-second jitter between entries.
- 12-check pre-flight audit passes for both accounts (SMC registration, real-data check_entry, exit/trail/cooldown logic, state freshness, env config integrity).
- Multi-account memory footprint: 56 MB per loop instance (linear scaling, ~50 instances fit on a single CPX22).
- Methodology layer: 13 banked R&D rules now in production. Notably Rule 11 (pre-deploy regime + correlation checks), Rule 12 (vision-filter blind validation — falsified one false-positive +39% Sharpe overlay before integration), Rule 13 (launch-regime sample bias — first 30-90 days of any new account is regime-conditional, not random).

### Changed
- Risk architecture documented as 5 layers (added multi-account dispersion as 5th layer)
- Aggregate exposure cap auto-applied when v15 flags enabled: 15% → 18%
- README updated to reflect 22 production slots + 3 SMC cells = 25 total active strategy classes

### Notes
- All strategy implementations remain in the proprietary repo
- Default config: all v15 + SMC + scaler flags OFF — pull this release into a v12 deployment without behavior change
- Per ramp discipline, full-sizing (100% risk-pct) requires F2 simulator confirmation OR 90 days clean live OR per-slot tripwire-green 30 days

## [0.2.0] — 2026-05-06

Framework expansion to support multi-slot portfolio additions behind config flags. The internal v15 portfolio expansion (5 new strategy slots) is wired into this framework but the strategy implementations remain proprietary.

### Added
- **Lifecycle hook** `StrategyBase.on_position_closed(asset, exit_time)` — called by main_loop after every exit (normal exit, graduated close-all, kill switch). Strategies override to track per-asset cooldown timers.
- **Conditional strategy registration** in `signal_engine.py` — feature-flag pattern lets new strategies be wired into the engine while default-OFF, allowing safe staged rollouts. Existing v12 baseline behavior preserved bit-for-bit when all new flags are OFF.
- **On-chain metrics data feed** (`data_feeds/onchain_metrics.py`) — fetches BTC active addresses, transaction count, hash rate, mempool size, transaction fees from the public blockchain.com API plus DEX volume from DefiLlama. Daily resolution, 12h TTL cache, fail-safe to stale cache on outage. Generic data feed; consumer strategies are proprietary.
- **Multi-account entry jitter** (`risk/multi_account_jitter.py`) — `ACCOUNT_INDEX` env var routes per-account entry-time offsets so simultaneous fills across N accounts get N×jitter spacing. Mitigates correlated-fill alpha haircut when running the same strategy slate across multiple prop firm accounts.
- **Per-slot tripwire monitor** (`risk/v15_tripwires.py`) — counts entries per strategy in a rolling window, compares against expected monthly fire counts, surfaces alerts on >2× over- or <0.5× under-firing during the first-month monitoring window.
- **Auto-applied portfolio limits** in `config.py` — when any new-slot flag flips True, MAX_TOTAL_POSITIONS, MAX_AGGREGATE_EXPOSURE_PCT, and MAX_POSITIONS_PER_REGIME widen automatically to accommodate the expanded slate.

### Validated
- Internal v15 portfolio backtest gauntlet 8/9 PASS at portfolio level. Sharpe 2.23 → 3.03, Return +808% → +1083%, Max DD -12.56% → -11.00% (better) over the same 5-year window. Metrics are backtest-only; per the framework's R&D precision-review discipline, deploy ships at 50% sizing with conservative ramp protocol.
- 33/33 smoke tests PASS across new strategy ports (tests assert framework integration: indicator population, signal direction, cooldown gating, exit logic, trailing-stop direction-awareness).
- v12 baseline behavior verified bit-for-bit unchanged when v15 flags are OFF (live deploy preserved an open production position through restart).

### Notes
- All v15 strategy implementations remain in the proprietary repo; the public framework ships the hook surface, the data feed, and the configuration scaffolding only
- Default config: all new flags OFF — pull this release into a v12 deployment without behavior change
- Per the project's deploy discipline, full-sizing ramp requires either F2 simulator confirmation (bar-by-bar unrealized DD tracking) or 90 days of live data with no -8% portfolio drawdown breach

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
