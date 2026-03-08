"""
Live Trading Configuration -- Portfolio v11 (8 strategies, 3 regimes)
=====================================================================
Deployed: 2026-03-05. All strategies walk-forward validated and sweep-optimized.
Bull (2): ElasticMultiSignal (SOL), DonchianModern (BTC)
Sideways (3): MultiSignalCCI (SOL-4h), DailyCCI (SOL-D), EMABounce (ETH)
Bear (3): ExitMicroTune (ETH), BCDExitTune (SOL), PanicSweepOpt (BTC)

v11 upgrades from v10:
    - 3-regime system (bull/sideways/bear) vs 2-regime (bull/bear)
    - Sideways = record strategies (MultiSignalCCI S=1.92, DailyCCI S=1.38)
    - Multi-signal portfolio per strategy (CCI+WR+ROC) with per-signal risk
    - Walk-forward validated: all WF > 70%
    - Signal.metadata["risk_pct"] = dynamic risk per signal type
    - Partial cascade via ExitSignal.metadata["update_metadata"]
"""

from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Global Risk Scale (portfolio-level dampener for CFT safety)
# Applied to ALL risk calculations. 0.85 = 15% haircut.
# ---------------------------------------------------------------------------
GLOBAL_RISK_SCALE = 0.85

# Per-strategy risk scale multipliers (applied on top of GLOBAL_RISK_SCALE)
# ElasticMultiSignal gets 0.65x because SOL is volatile and it's multi-signal
STRATEGY_RISK_SCALE = {
    "ElasticMultiSignal": 0.65,
}

# ---------------------------------------------------------------------------
# Regime Allocation (40/35/25 -- three regimes)
# Bull and sideways produce returns; bear hedges drawdowns.
# ---------------------------------------------------------------------------
REGIME_ALLOCATION = {
    "bull": 0.40,
    "sideways": 0.35,
    "bear": 0.25,
}

# ---------------------------------------------------------------------------
# Concurrent Position Limits (2 bull + 3 sideways + 3 bear = 8 max)
# ---------------------------------------------------------------------------
MAX_POSITIONS_PER_REGIME = {
    "bull": 2,
    "sideways": 3,
    "bear": 3,
}
MAX_TOTAL_POSITIONS = 8

# ---------------------------------------------------------------------------
# Risk Per Trade -- 0.5% global default (prop firm conservative)
# v11 strategies carry per-signal risk in Signal.metadata["risk_pct"].
# This is the fallback if metadata doesn't specify risk.
# ---------------------------------------------------------------------------
RISK_PER_TRADE = 0.005

# Per-strategy risk overrides (fallback values -- actual risk comes from
# Signal.metadata["risk_pct"] for multi-signal strategies)
STRATEGY_RISK_OVERRIDES = {
    # Bull (2)
    "ElasticMultiSignal":  0.015,   # SOL-4h, 3 signals (1.5/1.0/0.7%)
    "DonchianModern":      0.011,   # BTC-4h, S=1.35
    # Sideways (3)
    "MultiSignalCCI":      0.020,   # SOL-4h, 3 signals (2.0/1.0/0.5%)
    "DailyCCI":            0.020,   # SOL-D, S=1.38
    "EMABounce":           0.010,   # ETH-4h, S=0.95
    # Bear (3)
    "ExitMicroTune":       0.012,   # ETH-4h, 4 signals (quality-stratified)
    "BCDExitTune":         0.012,   # SOL-4h, 4 signals (type-stratified)
    "PanicSweepOpt":       0.020,   # BTC-4h, S=1.17
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

# Bear strategies: phase multiplier applied to risk.
BEAR_PHASE_RISK_MULTIPLIER = {
    "SURVIVAL":      0.35,
    "RECOVERY":      0.50,
    "BUILDING":      1.0,
    "ACCELERATING":  1.0,
    "PROTECTING":    0.75,
}

# ---------------------------------------------------------------------------
# Per-Strategy Leverage Caps (DD-Budget Optimized)
# Formula: max_prop_leverage = floor(DD_BUDGET / (backtest_DD * GLOBAL_RISK_SCALE), 0.25)
# DD_BUDGET = 7% personal limit. Only strategies with backtest DD < 4% get >1x.
# Effective max DD at cap: strategy_DD * risk_scale * leverage < 7%
# ---------------------------------------------------------------------------
STRATEGY_LEVERAGE_CAPS = {
    # Bull (2)
    "ElasticMultiSignal":  {"prop": 1.0, "funded": 1.5, "personal": 2.0},  # DD=8.53%*0.65rs=5.54%@1x
    "DonchianModern":      {"prop": 1.0, "funded": 1.5, "personal": 2.0},  # DD=5.60%*0.85=4.76%@1x
    # Sideways (3) -- low DD = leverage opportunity
    "MultiSignalCCI":      {"prop": 1.5, "funded": 2.0, "personal": 2.5},  # DD=3.88%*0.85*1.5=4.95%
    "DailyCCI":            {"prop": 1.5, "funded": 2.0, "personal": 2.5},  # DD=3.70%*0.85*1.5=4.72%
    "EMABounce":           {"prop": 1.0, "funded": 1.5, "personal": 2.0},  # DD=6.31%*0.85=5.36%@1x
    # Bear (3)
    "ExitMicroTune":       {"prop": 1.0, "funded": 1.5, "personal": 2.0},  # DD=6.53%*0.85=5.55%@1x
    "BCDExitTune":         {"prop": 1.0, "funded": 1.5, "personal": 2.0},  # DD=5.00%*0.85=4.25%@1x
    "PanicSweepOpt":       {"prop": 1.0, "funded": 1.5, "personal": 2.0},  # DD=5.08%*0.85=4.32%@1x
}

# ---------------------------------------------------------------------------
# Strategy -> Asset Mapping (Portfolio v11)
# ---------------------------------------------------------------------------
STRATEGY_ASSETS = {
    # Bull (2)
    "ElasticMultiSignal":  ["SOLUSDT"],    # SOL-4h
    "DonchianModern":      ["BTCUSDT"],    # BTC-4h
    # Sideways (3)
    "MultiSignalCCI":      ["SOLUSDT"],    # SOL-4h
    "DailyCCI":            ["SOLUSDT"],    # SOL-D
    "EMABounce":           ["ETHUSDT"],    # ETH-4h
    # Bear (3)
    "ExitMicroTune":       ["ETHUSDT"],    # ETH-4h
    "BCDExitTune":         ["SOLUSDT"],    # SOL-4h
    "PanicSweepOpt":       ["BTCUSDT"],    # BTC-4h
}

# Timeframe per strategy (kline interval string)
STRATEGY_TIMEFRAMES = {
    # Bull (2)
    "ElasticMultiSignal":  "240",    # 4h
    "DonchianModern":      "240",    # 4h
    # Sideways (3)
    "MultiSignalCCI":      "240",    # 4h
    "DailyCCI":            "D",      # daily
    "EMABounce":           "240",    # 4h
    # Bear (3)
    "ExitMicroTune":       "240",    # 4h
    "BCDExitTune":         "240",    # 4h
    "PanicSweepOpt":       "240",    # 4h
}

# ---------------------------------------------------------------------------
# Signal Priority -- Bull > Sideways > Bear on same asset
# ---------------------------------------------------------------------------
REGIME_PRIORITY = {"bull": 0, "sideways": 1, "bear": 2}

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

# Backtest max DD baselines (5yr-validated, positive decimals)
BACKTEST_MAX_DD = {
    # Bull (2)
    "ElasticMultiSignal":  0.0853,  # -8.53% on SOL-4h
    "DonchianModern":      0.0560,  # -5.60% on BTC-4h
    # Sideways (3)
    "MultiSignalCCI":      0.0388,  # -3.88% on SOL-4h
    "DailyCCI":            0.0370,  # -3.70% on SOL-D
    "EMABounce":           0.0631,  # -6.31% on ETH-4h
    # Bear (3)
    "ExitMicroTune":       0.0653,  # -6.53% on ETH-4h
    "BCDExitTune":         0.0500,  # -5.00% on SOL-4h (estimated)
    "PanicSweepOpt":       0.0508,  # -5.08% on BTC-4h
}

# ---------------------------------------------------------------------------
# Binance Futures Demo Connection
# ---------------------------------------------------------------------------
BINANCE_FUTURES_DEMO = True
BINANCE_BASE_URL = "https://demo-fapi.binance.com"
BINANCE_MARGIN_TYPE = "CROSSED"

# ---------------------------------------------------------------------------
# Portfolio-Level Safety (CFT Foolproofing)
# ---------------------------------------------------------------------------
# Max notional exposure per asset as fraction of equity.
# SOL has 4 strategies (ElasticMultiSignal, MultiSignalCCI, DailyCCI, BCDExitTune).
# Cap prevents concentrated SOL blowup from killing the account.
MAX_ASSET_EXPOSURE_PCT = {
    "SOLUSDT": 0.06,   # 6% of equity max across all SOL strategies
    "BTCUSDT": 0.05,   # 5% of equity max across all BTC strategies
    "ETHUSDT": 0.05,   # 5% of equity max across all ETH strategies
}
MAX_ASSET_EXPOSURE_DEFAULT = 0.05  # fallback for unlisted assets

# Max aggregate notional (all positions combined) as fraction of equity.
# At 8 positions with avg 1% risk, aggregate ~8% notional is normal.
# This caps extreme scenarios where multiple high-risk signals fire together.
MAX_AGGREGATE_EXPOSURE_PCT = 0.15  # 15% of equity max total risk exposure

# ---------------------------------------------------------------------------
# Operational
# ---------------------------------------------------------------------------
ACCOUNT_MODE = "prop"
LOG_DIR = str(_BASE_DIR / "data" / "logs")
STATE_FILE = str(_BASE_DIR / "data" / "state.json")
TRADE_LOG_FILE = str(_BASE_DIR / "data" / "trades.csv")
