"""
Live Trading Configuration -- Framework
=========================================
Replace the example strategy config with your own strategy configs.
Infrastructure settings (risk, leverage, kill switches) are ready to use.
"""

from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Regime Allocation (65/35 -- no sideways)
# Bull strategies produce returns in trend, bear strategies hedge drawdowns.
# ---------------------------------------------------------------------------
REGIME_ALLOCATION = {
    "bull": 0.65,
    "bear": 0.35,
}

# ---------------------------------------------------------------------------
# Concurrent Position Limits
# ---------------------------------------------------------------------------
MAX_POSITIONS_PER_REGIME = {
    "bull": 6,
    "bear": 9,
}
MAX_TOTAL_POSITIONS = 15

# ---------------------------------------------------------------------------
# Risk Per Trade -- 0.5% global default (prop firm conservative)
# ---------------------------------------------------------------------------
RISK_PER_TRADE = 0.005

# Per-strategy risk overrides -- replace with your own strategies
STRATEGY_RISK_OVERRIDES = {
    "ExampleSMACrossover": 0.005,    # SOL-4h, conservative default
}

# ---------------------------------------------------------------------------
# Daily Risk Limits (Prop Firm -- Crypto Fund Trader)
# ---------------------------------------------------------------------------
DAILY_DD_LIMIT_FIRM = 0.05
DAILY_DD_LIMIT_PERSONAL = 0.03
TOTAL_DD_LIMIT_FIRM = 0.10
TOTAL_DD_LIMIT_PERSONAL = 0.07

DD_ACTION_REVIEW = 0.015       # -1.5% -> review which regime is losing
DD_ACTION_REDUCE = 0.02        # -2%   -> reduce to 1 position per regime
DD_ACTION_STOP_DAY = 0.03      # -3%   -> STOP trading for the day
DD_ACTION_CLOSE_ALL = 0.04     # -4%   -> close all positions

# ---------------------------------------------------------------------------
# Adaptive Leverage Phases (equity-based)
# ---------------------------------------------------------------------------
LEVERAGE_PHASES = [
    # (equity_ratio_min, equity_ratio_max, leverage, risk_per_trade)
    (0.00, 0.95, 1.0, 0.0025),   # SURVIVAL (<95%)
    (0.95, 1.00, 1.5, 0.004),    # RECOVERY (95-100%)
    (1.00, 1.05, 2.0, 0.005),    # BUILDING (100-105%)  <- start here
    (1.05, 1.10, 2.5, 0.0065),   # ACCELERATING (105-110%)
    (1.10, 9.99, 1.5, 0.004),    # PROTECTING (>110%)
]

DEFAULT_LEVERAGE = 2.0

# Bear strategies: phase multiplier applied to STRATEGY_RISK_OVERRIDES.
# In BUILDING/ACCELERATING: full override risk. Scale down when losing.
BEAR_PHASE_RISK_MULTIPLIER = {
    "SURVIVAL":      0.35,   # heavy drawdown -> cut to 35% of override
    "RECOVERY":      0.50,   # recovering -> 50% of override
    "BUILDING":      1.0,    # normal -> full override risk
    "ACCELERATING":  1.0,    # winning -> full override risk
    "PROTECTING":    0.75,   # protect profits -> 75% of override
}

# ---------------------------------------------------------------------------
# Per-Strategy Leverage Caps -- replace with your own strategies
# ---------------------------------------------------------------------------
STRATEGY_LEVERAGE_CAPS = {
    "ExampleSMACrossover": {"prop": 2.0, "funded": 2.5, "personal": 3.0},
}

# ---------------------------------------------------------------------------
# Strategy -> Asset Mapping -- replace with your own strategies
# ---------------------------------------------------------------------------
STRATEGY_ASSETS = {
    "ExampleSMACrossover": ["SOLUSDT"],    # SOL-4h
}

# Timeframe per strategy (kline interval string in minutes)
STRATEGY_TIMEFRAMES = {
    "ExampleSMACrossover": "240",    # 4h
}

# ---------------------------------------------------------------------------
# Signal Priority -- Bull > Bear on same asset
# ---------------------------------------------------------------------------
REGIME_PRIORITY = {"bull": 0, "bear": 1}

# ---------------------------------------------------------------------------
# Kill Switch Rules
# ---------------------------------------------------------------------------
KILL_SWITCH = {
    "daily_dd_pct": 0.03,
    "total_dd_pct": 0.07,
    "weekly_dd_pct": 0.15,
    "min_sharpe_after_n_trades": 0.5,
    "min_trades_for_sharpe": 20,
    "max_dd_vs_backtest_ratio": 1.5,
    "max_consecutive_losing_days": 5,
}

# Backtest max DD baselines -- replace with your own strategies
BACKTEST_MAX_DD = {
    "ExampleSMACrossover": 0.050,    # placeholder
}

# ---------------------------------------------------------------------------
# Binance Futures Demo Connection
# ---------------------------------------------------------------------------
BINANCE_FUTURES_DEMO = True
BINANCE_BASE_URL = "https://demo-fapi.binance.com"
BINANCE_MARGIN_TYPE = "CROSSED"

# ---------------------------------------------------------------------------
# Operational
# ---------------------------------------------------------------------------
ACCOUNT_MODE = "prop"
LOG_DIR = str(_BASE_DIR / "data" / "logs")
STATE_FILE = str(_BASE_DIR / "data" / "state.json")
TRADE_LOG_FILE = str(_BASE_DIR / "data" / "trades.csv")
