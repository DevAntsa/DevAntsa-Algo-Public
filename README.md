<p align="center">
  <img src="DevAntsa.png" width="180" alt="DevAntsa Lab">
</p>

<h1 align="center">DevAntsa Lab</h1>

<p align="center">
  <strong>Precision trading, systematic execution</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/framework-BYOS-blue" alt="Bring Your Own Strategies">
  <img src="https://img.shields.io/badge/regimes-bull%20%2B%20bear-green" alt="Bull + Bear">
  <img src="https://img.shields.io/badge/exchange-Binance%20Futures-yellow" alt="Binance Futures">
  <img src="https://img.shields.io/badge/timeframe-4h-orange" alt="4h Timeframe">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

Automated crypto futures trading framework with regime-aware execution, Monte Carlo-validated risk management, and a full live trading infrastructure. Built for prop firm trading on Crypto Fund Trader ($200K accounts via Bybit API).

**Strategy implementations are proprietary. This repo provides the full trading infrastructure -- bring your own strategies.**

## Architecture

```
DevAntsa_Lab/
|
|-- live_trading/               # Live execution system
|   |-- engine/                 # Core trading loop, signal engine, regime gate
|   |   |-- main_loop.py       # Dynamic tick interval, timeframe gating
|   |   |-- signal_engine.py   # Strategy iteration + signal collection
|   |   |-- regime_gate.py     # BTC EMA-50 slope classifier
|   |   |-- position_manager.py
|   |   `-- conflict_resolver.py
|   |-- execution/              # Binance Futures API executor
|   |   `-- binance_executor.py # Fill verification, position reconciliation
|   |-- strategies/             # Strategy implementations
|   |   |-- base.py             # StrategyBase + indicator library
|   |   `-- example_sma_crossover.py  # Example strategy template
|   |-- risk/                   # Position sizing, risk management, kill switches
|   |-- notifications/          # Telegram alerts
|   |-- dashboard.py            # Streamlit war room dashboard
|   |-- config.py               # All parameters and strategy configs
|   `-- trade_journal.py        # Trade logging and P&L matching
|
`-- RBI_Agents/                 # Research-Backtest-Iterate strategy factory
    `-- RBI_Regular/            # AI-powered strategy generation + backtesting
        |-- rbi_agent_pp_multi_devantsa.py  # Bull strategy agent
        |-- rbi_bear.py                     # Bear strategy agent
        `-- portfolio/                      # Portfolio metrics + Monte Carlo results
```

## Bring Your Own Strategies

The framework ships with a textbook SMA crossover example. Build your own:

```python
# strategies/my_strategy.py
from DevAntsa_Lab.live_trading.strategies.base import (
    StrategyBase, Signal, ExitSignal, calculate_atr, calculate_ema,
)

class MyStrategy(StrategyBase):
    name = "MyStrategy"
    regime = "bull"           # "bull" or "bear"
    direction = "LONG"        # "LONG" or "SHORT"
    assets = ["BTCUSDT"]
    timeframe = "240"         # 4h candles

    def compute_indicators(self, df):
        self.compute_common_indicators(df)  # ATR_14
        # Add your indicators here
        return df

    def check_entry(self, df):
        # Return Signal(...) when entry conditions met, else None
        return None

    def check_exit(self, df, position):
        # Return ExitSignal(...) when position should close, else None
        return None

    def calculate_trail(self, df, position):
        # Return updated trailing stop price, or None
        return None
```

Then register it:
1. Import in `signal_engine.py` and add to the strategies list
2. Add config entries in `config.py` (risk overrides, leverage caps, asset mapping)

See `strategies/example_sma_crossover.py` for a complete 250-line working example with adaptive trailing stops.

## Portfolio Results (Proprietary Strategies)

The proprietary strategies deployed on this framework achieved the following on 5-year backtests (Jan 2021 - Feb 2026):

### Bull LONG (6 strategies, avg Sharpe 1.25)

| Strategy | Asset | Return | Sharpe | Max DD | Trades |
|----------|-------|--------|--------|--------|--------|
| SteepeningSlopeBreakout | SOL-4h | +34.8% | 1.48 | -3.3% | 170 |
| DualROCAlignment | BTC-1h | +61.6% | 1.21 | -6.7% | 72 |
| DirectionalIgnition | BTC-4h | +17.0% | 1.23 | -2.7% | 36 |
| ATRExpansionBreakout | BTC-4h | +35.2% | 1.22 | -3.6% | 96 |
| DIBreakoutPyramid | BTC-4h | +82.1% | 1.23 | -6.7% | 156 |
| TripleMomentum | SOL-4h | +7.8% | 1.14 | -1.4% | 49 |

### Bear SHORT (9 strategies, avg Sharpe 1.19)

| Strategy | Asset | Return | Sharpe | Max DD | Trades |
|----------|-------|--------|--------|--------|--------|
| StructuralFade | ETH-4h | +18.7% | 1.46 | -1.2% | 33 |
| BearishLowerHigh | ETH-4h | +56.7% | 1.44 | -3.4% | 108 |
| AccelBreakdown | ETH-4h | +69.5% | 1.35 | -4.3% | 121 |
| EMARejectionADX | ETH-4h | +13.6% | 1.21 | -1.6% | 61 |
| MFIDistribution | ETH-4h | +40.4% | 1.12 | -4.0% | 49 |
| PanicAcceleration | BTC-4h | +26.6% | 1.19 | -2.6% | 63 |
| ExpansionBreakdown | BTC-4h | +15.4% | 0.79 | -2.5% | 40 |
| WorseningMomentum | SOL-4h | +51.2% | 1.13 | -4.7% | 80 |
| ExpandingBodyBear | SOL-4h | +18.4% | 1.07 | -2.9% | 51 |

### Monte Carlo Risk (5,000 simulations per portfolio)

| Metric | Bull (6) | Bear (9) |
|--------|----------|----------|
| 95th worst-case DD | -6.19% | -7.83% |
| Safe allocation (<6% DD) | 97% | 77% |
| Bear NOT crash-dependent | -- | 50/50 crash vs non-crash PnL |

Combined safe allocation: **77%** (bear is the binding constraint).

## RBI Agent System

The Research-Backtest-Iterate (RBI) system is an AI-powered strategy factory:

1. **Research** -- LLM (Grok-4-Fast) generates trading strategy ideas from prompts
2. **Backtest** -- Each idea is automatically coded, backtested on 5-year OHLCV data (BTC/ETH/SOL, 1h+4h), and scored on a composite metric (Sharpe, return, drawdown, win rate)
3. **Iterate** -- Top performers are optimized over 6 iterations with parameter sweeps
4. **Qualify** -- Strategies passing thresholds (Sharpe > 0.8, DD > -8%, trades >= 20) graduate to `winners/`
5. **Deploy** -- Manual sweep optimization and Monte Carlo validation before adding to the live portfolio

**17 batches completed (bull), 14 batches (bear).** 69 bull winners, 43 bear winners produced.

## Live Trading Features

- **Regime-aware**: Bull strategies go long, bear strategies go short. All strategies self-gate via SMA200.
- **Risk management**: Per-strategy risk overrides (0.5-1.5%), phase-based scaling, daily DD halt (3%), total DD kill switch (7%).
- **Exchange safety**: Fill verification on every order, position reconciliation every tick, atomic stop modification (place-first-then-cancel), targeted stop cancellation for shared assets.
- **Dashboard**: Streamlit war room with TradingView live charts, glassmorphism UI, equity curve, strategy grid, real-time P&L.
- **Telegram**: Entry/exit alerts, daily summaries, command interface (/positions, /status, /stats).

## Risk Controls

| Control | Personal Limit | CFT Limit | Buffer |
|---------|---------------|-----------|--------|
| Daily drawdown | 3% | 5% | +2% |
| Total drawdown | 7% | 10% | +3% |
| Leverage | 1-2.5x | 100x | 97.5x |
| MC 95th DD (bull) | -6.19% | -10% | +3.81% |
| MC 95th DD (bear) | -7.83% | -10% | +2.17% |

## Setup

```bash
# Clone
git clone https://github.com/DevAntsa/DevAntsa-Algo-Public.git
cd DevAntsa-Algo-Public

# Environment
conda create -n tflow python=3.10
conda activate tflow
pip install -r requirements.txt

# Configuration
cp .env_example .env
# Edit .env with your API keys (Binance, Telegram, OpenRouter)

# Run live trading
python -m DevAntsa_Lab.live_trading.engine.main_loop

# Run dashboard (separate terminal)
streamlit run DevAntsa_Lab/live_trading/dashboard.py
```

## Tech Stack

- **Python 3.10** with backtesting.py, pandas, pandas_ta, numpy
- **Binance Futures API** (demo + live)
- **Streamlit + Plotly + TradingView** for dashboard
- **Grok-4-Fast via OpenRouter** for RBI strategy generation
- **Telegram Bot API** for notifications

---

<p align="center">
  <sub>Built by DevAntsa | Systematic crypto trading</sub>
</p>
