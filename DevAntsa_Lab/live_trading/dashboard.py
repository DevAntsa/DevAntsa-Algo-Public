"""
DevAntsa Lab -- Live Trading Dashboard
=======================================
Portfolio v11 war room: single-page Streamlit app for monitoring 8 strategies
across bull/sideways/bear regimes on Binance Futures Demo.

Run separately from main_loop:
    streamlit run DevAntsa_Lab/live_trading/dashboard.py

Architecture:
    - TradingView embedded chart: truly live via JS websocket (zero flicker)
    - st.fragment(run_every=30s): lightweight text/HTML only (no Plotly in fragment)
    - Equity curve: static Plotly outside fragment (only changes on page load)
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so relative imports work
# ---------------------------------------------------------------------------
_DASHBOARD_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _DASHBOARD_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from DevAntsa_Lab.live_trading.config import (
    STRATEGY_ASSETS, STRATEGY_TIMEFRAMES, STRATEGY_RISK_OVERRIDES,
    BACKTEST_MAX_DD, KILL_SWITCH, MAX_TOTAL_POSITIONS,
    MAX_POSITIONS_PER_REGIME, STATE_FILE, TRADE_LOG_FILE,
    DAILY_DD_LIMIT_PERSONAL, TOTAL_DD_LIMIT_PERSONAL,
    DD_ACTION_REVIEW, DD_ACTION_REDUCE, DD_ACTION_STOP_DAY, DD_ACTION_CLOSE_ALL,
    GLOBAL_RISK_SCALE, STRATEGY_RISK_SCALE,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REFRESH_SECONDS = 60

BULL_STRATEGIES = ["ElasticMultiSignal", "DonchianModern"]
SIDEWAYS_STRATEGIES = ["MultiSignalCCI", "DailyCCI", "EMABounce"]
BEAR_STRATEGIES = ["ExitMicroTune", "BCDExitTune", "PanicSweepOpt"]
ALL_STRATEGIES = BULL_STRATEGIES + SIDEWAYS_STRATEGIES + BEAR_STRATEGIES

STRATEGY_REGIME = {}
for s in BULL_STRATEGIES:
    STRATEGY_REGIME[s] = "bull"
for s in SIDEWAYS_STRATEGIES:
    STRATEGY_REGIME[s] = "sideways"
for s in BEAR_STRATEGIES:
    STRATEGY_REGIME[s] = "bear"

BACKTEST_SHARPE = {
    # Bull
    "ElasticMultiSignal": 1.61, "DonchianModern": 1.35,
    # Sideways
    "MultiSignalCCI": 1.92, "DailyCCI": 1.38, "EMABounce": 0.95,
    # Bear
    "ExitMicroTune": 1.22, "BCDExitTune": 1.10, "PanicSweepOpt": 1.17,
}

BACKTEST_RETURN = {
    # Bull
    "ElasticMultiSignal": 201.0, "DonchianModern": 58.0,
    # Sideways
    "MultiSignalCCI": 135.3, "DailyCCI": 41.3, "EMABounce": 24.8,
    # Bear
    "ExitMicroTune": 75.4, "BCDExitTune": 45.0, "PanicSweepOpt": 45.8,
}

ASSET_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
TV_SYMBOLS = {"BTC": "BINANCE:BTCUSDT.P", "ETH": "BINANCE:ETHUSDT.P", "SOL": "BINANCE:SOLUSDT.P"}
ASSET_COLORS = {"BTC": "#F7931A", "ETH": "#627EEA", "SOL": "#9945FF"}
TV_GREEN = "#089981"
TV_RED = "#F23645"
TV_AMBER = "#FFC107"
TV_CYAN = "#00BCD4"

CHART_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
    font=dict(family='Inter', color='#787B86', size=11),
    xaxis=dict(gridcolor='#1A1A1A', showgrid=True),
    yaxis=dict(gridcolor='#1A1A1A', side='right'),
    margin=dict(l=0, r=60, t=10, b=30),
    showlegend=False, hovermode='x unified',
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="DevAntsa Lab", page_icon="", layout="wide",
                   initial_sidebar_state="collapsed")

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    html, body { background: #000000 !important; }
    .stApp {
        background: transparent !important;
        color: #D1D4DC;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    h1 { color: #F8F9FD !important; font-size: 1.5rem !important; font-weight: 500 !important;
         margin-bottom: 1.5rem !important; letter-spacing: -0.02em; font-family: 'Inter', sans-serif !important; }
    h2, h3 { color: #D1D4DC !important; font-weight: 500 !important; font-family: 'Inter', sans-serif !important; }
    .stButton > button { background: rgba(0,0,0,0.6); color: #FFFFFF; border: 1px solid rgba(255,255,255,0.06);
        border-radius: 4px; font-weight: 500; font-size: 0.875rem; font-family: 'Inter', sans-serif; padding: 0.5rem 1rem;
        backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); transition: all 0.2s ease; }
    .stButton > button:hover { background: rgba(26,26,26,0.8); border-color: rgba(255,255,255,0.1); }
    hr { border-color: rgba(255,255,255,0.04) !important; margin: 2rem 0; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1800px; position: relative; z-index: 1; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}

    .card { background: rgba(10,10,10,0.5); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.03); border-radius: 8px; padding: 16px; margin-bottom: 8px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.02); }
    .live-dot { display: inline-block; width: 10px; height: 10px; background-color: #089981;
                border-radius: 50%; animation: pulse 2s infinite; margin-right: 6px; vertical-align: middle;
                box-shadow: 0 0 8px rgba(8,153,129,0.6), 0 0 20px rgba(8,153,129,0.2); }
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(8,153,129,0.6), 0 0 8px rgba(8,153,129,0.6); }
        70% { box-shadow: 0 0 0 10px rgba(8,153,129,0), 0 0 20px rgba(8,153,129,0.1); }
        100% { box-shadow: 0 0 0 0 rgba(8,153,129,0), 0 0 8px rgba(8,153,129,0.6); }
    }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 0.7rem;
             font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; font-family: 'Inter', sans-serif; }
    .badge-bull { background: rgba(8,153,129,0.15); color: #089981; box-shadow: 0 0 8px rgba(8,153,129,0.1); }
    .badge-sideways { background: rgba(0,188,212,0.15); color: #00BCD4; box-shadow: 0 0 8px rgba(0,188,212,0.1); }
    .badge-bear { background: rgba(242,54,69,0.15); color: #F23645; box-shadow: 0 0 8px rgba(242,54,69,0.1); }
    .badge-neutral { background: rgba(120,123,134,0.15); color: #787B86; }
    .badge-building { background: rgba(0,188,212,0.15); color: #00BCD4; box-shadow: 0 0 8px rgba(0,188,212,0.1); }
    .badge-accelerating { background: rgba(255,193,7,0.15); color: #FFC107; box-shadow: 0 0 8px rgba(255,193,7,0.1); }
    .badge-protecting { background: rgba(8,153,129,0.15); color: #089981; box-shadow: 0 0 8px rgba(8,153,129,0.1); }
    .badge-recovery { background: rgba(255,193,7,0.15); color: #FFC107; }
    .badge-survival { background: rgba(242,54,69,0.15); color: #F23645; box-shadow: 0 0 8px rgba(242,54,69,0.15); }
    .badge-normal { background: rgba(8,153,129,0.15); color: #089981; }
    .badge-review { background: rgba(255,193,7,0.15); color: #FFC107; }
    .badge-reduce { background: rgba(255,152,0,0.15); color: #FF9800; }
    .badge-stop-day { background: rgba(242,54,69,0.15); color: #F23645; }
    .badge-close-all { background: rgba(183,28,28,0.2); color: #FF1744; box-shadow: 0 0 12px rgba(255,23,68,0.15); }
    .badge-active { background: rgba(8,153,129,0.15); color: #089981; box-shadow: 0 0 8px rgba(8,153,129,0.1); }
    .badge-watching { background: rgba(120,123,134,0.08); color: #4A4D57; }
    .positive { color: #089981 !important; font-weight: 500; }
    .negative { color: #F23645 !important; font-weight: 500; }
    .dim { color: #787B86; }

    .metric-card { background: rgba(10,10,10,0.5); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
                   border: 1px solid rgba(255,255,255,0.03); border-top: 1px solid rgba(247,147,26,0.15);
                   border-radius: 8px; padding: 14px 18px; text-align: center;
                   box-shadow: 0 4px 24px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.02);
                   transition: border-color 0.3s ease, box-shadow 0.3s ease; }
    .metric-card:hover { border-top-color: rgba(247,147,26,0.3);
                         box-shadow: 0 4px 30px rgba(0,0,0,0.4), 0 0 20px rgba(247,147,26,0.03); }
    .metric-label { color: #787B86; font-size: 0.7rem; font-weight: 500; text-transform: uppercase;
                    letter-spacing: 0.06em; margin-bottom: 6px; font-family: 'Inter', sans-serif; }
    .metric-value { color: #F8F9FD; font-size: 1.4rem; font-weight: 600; font-family: 'Inter', sans-serif;
                    text-shadow: 0 0 20px rgba(248,249,253,0.08); }
    .metric-delta { font-size: 0.75rem; font-weight: 500; margin-top: 4px; }

    .strat-card { background: rgba(10,10,10,0.5); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
                  border: 1px solid rgba(255,255,255,0.03); border-radius: 6px; padding: 12px 14px;
                  border-left: 3px solid; min-height: 120px; box-shadow: 0 2px 16px rgba(0,0,0,0.2);
                  transition: box-shadow 0.3s ease, transform 0.2s ease; }
    .strat-card:hover { transform: translateY(-1px); box-shadow: 0 4px 24px rgba(0,0,0,0.3); }
    .strat-card-bull { border-left-color: #089981; }
    .strat-card-bull:hover { box-shadow: 0 4px 24px rgba(0,0,0,0.3), 0 0 12px rgba(8,153,129,0.06); }
    .strat-card-sideways { border-left-color: #00BCD4; }
    .strat-card-sideways:hover { box-shadow: 0 4px 24px rgba(0,0,0,0.3), 0 0 12px rgba(0,188,212,0.06); }
    .strat-card-bear { border-left-color: #F23645; }
    .strat-card-bear:hover { box-shadow: 0 4px 24px rgba(0,0,0,0.3), 0 0 12px rgba(242,54,69,0.06); }

    .pos-table { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 0.82rem; }
    .pos-table th { color: #787B86; font-size: 0.7rem; font-weight: 500; text-transform: uppercase;
                    letter-spacing: 0.05em; padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.04); text-align: left; }
    .pos-table td { color: #D1D4DC; padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.02); }
    .pos-table tr:hover td { background-color: rgba(255,255,255,0.02); }

    .progress-bar-track { background: rgba(255,255,255,0.04); border-radius: 3px; height: 6px; width: 100%; margin-top: 6px; }
    .progress-bar-fill { height: 6px; border-radius: 3px; transition: width 0.3s; box-shadow: 0 0 6px currentColor; }

    .ticker-card { background: rgba(10,10,10,0.5); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
                   border: 1px solid rgba(255,255,255,0.03); border-radius: 8px; padding: 14px 18px;
                   box-shadow: 0 4px 24px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.02);
                   transition: box-shadow 0.3s ease; }
    .ticker-card:hover { box-shadow: 0 4px 30px rgba(0,0,0,0.4); }
    .kill-banner { background: rgba(183,28,28,0.2); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
                   border: 1px solid rgba(242,54,69,0.3); border-radius: 6px; padding: 12px 20px;
                   text-align: center; color: #FF1744; font-weight: 600; font-size: 0.95rem; margin-bottom: 16px;
                   box-shadow: 0 0 30px rgba(242,54,69,0.1); animation: killPulse 3s ease-in-out infinite; }
    @keyframes killPulse {
        0%, 100% { box-shadow: 0 0 30px rgba(242,54,69,0.1); }
        50% { box-shadow: 0 0 40px rgba(242,54,69,0.2); }
    }
    .empty-state { text-align: center; padding: 30px 20px; color: #4A4D57; font-size: 0.85rem; }

    /* Radio tabs styling */
    div[data-testid="stRadio"] > div { flex-direction: row !important; gap: 4px !important; }
    div[data-testid="stRadio"] > div > label {
        background: rgba(10,10,10,0.5) !important; backdrop-filter: blur(8px) !important;
        -webkit-backdrop-filter: blur(8px) !important; border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: 4px !important; padding: 6px 16px !important; color: #787B86 !important;
        font-size: 0.8rem !important; font-weight: 600 !important; font-family: 'Inter', sans-serif !important;
        cursor: pointer !important; transition: all 0.2s ease !important; }
    div[data-testid="stRadio"] > div > label:hover { border-color: rgba(255,255,255,0.1) !important; color: #D1D4DC !important; }
    div[data-testid="stRadio"] > div > label[data-checked="true"] {
        border-color: rgba(247,147,26,0.4) !important; color: #F8F9FD !important;
        background: rgba(247,147,26,0.08) !important; box-shadow: 0 0 12px rgba(247,147,26,0.1) !important; }
    div[data-testid="stRadio"] > div > label > div:first-child { display: none !important; }
    div[data-testid="stRadio"] > label { display: none !important; }

    .header-bar {
        display: flex; justify-content: space-between; align-items: center;
        padding: 16px 20px 14px 20px;
        background: rgba(10,10,10,0.5);
        backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(255,255,255,0.03);
        border-radius: 10px;
        margin-bottom: 16px;
        position: relative;
        overflow: hidden;
    }
    .header-bar::after {
        content: ''; position: absolute; bottom: 0; left: 10%; width: 80%; height: 1px;
        background: linear-gradient(90deg, transparent, rgba(247,147,26,0.3), transparent);
    }
    .header-title {
        font-size: 1.8rem; font-weight: 700; letter-spacing: -0.03em;
        font-family: 'Inter', sans-serif;
        background: linear-gradient(135deg, #F7931A 0%, #F8F9FD 50%, #F7931A 100%);
        background-size: 200% 200%;
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text;
        animation: headerShimmer 8s ease-in-out infinite;
    }
    @keyframes headerShimmer {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }
    .header-subtitle {
        color: #4A4D57; font-size: 0.68rem; font-weight: 400; letter-spacing: 0.08em;
        text-transform: uppercase; margin-top: 2px; font-family: 'Inter', sans-serif;
    }
    .header-live-pill {
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(8,153,129,0.1); border: 1px solid rgba(8,153,129,0.25);
        border-radius: 20px; padding: 4px 12px 4px 8px;
        box-shadow: 0 0 12px rgba(8,153,129,0.1);
    }
    .header-live-pill span.live-text {
        color: #089981; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
        font-family: 'Inter', sans-serif;
    }
    .header-chip {
        display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 0.65rem;
        font-weight: 500; letter-spacing: 0.04em; font-family: 'Inter', sans-serif;
        background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
        color: #787B86;
    }
    .header-chip-accent {
        background: rgba(247,147,26,0.08); border: 1px solid rgba(247,147,26,0.2);
        color: #F7931A;
    }

    /* Flowing wave ribbons (layer 1 - warm gold) */
    .wave-bg {
        position: fixed; top: -20%; left: -20%; width: 140%; height: 140%;
        pointer-events: none; z-index: 0;
        background:
            radial-gradient(ellipse 1100px 120px at 15% 25%, rgba(247,147,26,0.14) 0%, transparent 70%),
            radial-gradient(ellipse 800px 80px at 55% 45%, rgba(200,140,40,0.09) 0%, transparent 70%),
            radial-gradient(ellipse 600px 150px at 80% 70%, rgba(180,120,20,0.10) 0%, transparent 70%),
            radial-gradient(ellipse 900px 90px at 35% 85%, rgba(247,147,26,0.07) 0%, transparent 70%),
            radial-gradient(ellipse 700px 70px at 65% 15%, rgba(160,110,30,0.06) 0%, transparent 70%);
        filter: blur(40px);
        animation: waveFloat 35s ease-in-out infinite;
    }
    @keyframes waveFloat {
        0%, 100% { transform: translate(0, 0) rotate(0deg); }
        25% { transform: translate(3%, -2%) rotate(0.5deg); }
        50% { transform: translate(-2%, 3%) rotate(-0.3deg); }
        75% { transform: translate(1%, -1%) rotate(0.2deg); }
    }

    /* Flowing wave ribbons (layer 2 - dark gold/charcoal, counter-moving) */
    .mesh-bg {
        position: fixed; top: -20%; left: -20%; width: 140%; height: 140%;
        pointer-events: none; z-index: 0;
        background:
            radial-gradient(ellipse 1200px 100px at 70% 20%, rgba(200,150,50,0.10) 0%, transparent 70%),
            radial-gradient(ellipse 700px 160px at 25% 55%, rgba(60,50,30,0.18) 0%, transparent 70%),
            radial-gradient(ellipse 900px 80px at 50% 80%, rgba(247,147,26,0.07) 0%, transparent 70%),
            radial-gradient(ellipse 750px 110px at 10% 40%, rgba(80,60,20,0.14) 0%, transparent 70%),
            radial-gradient(ellipse 850px 60px at 85% 60%, rgba(140,100,30,0.08) 0%, transparent 70%);
        filter: blur(45px);
        animation: meshFloat 28s ease-in-out infinite reverse;
    }
    @keyframes meshFloat {
        0%, 100% { transform: translate(0, 0) rotate(0deg); }
        25% { transform: translate(-3%, 2%) rotate(-0.4deg); }
        50% { transform: translate(2%, -3%) rotate(0.3deg); }
        75% { transform: translate(-1%, 1%) rotate(-0.2deg); }
    }

    /* Noise texture overlay */
    .noise-overlay {
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        pointer-events: none; z-index: 0; opacity: 0.05;
        background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 512 512' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
        background-repeat: repeat; background-size: 512px 512px;
    }
</style>
""", unsafe_allow_html=True)

# Background overlays
st.markdown(
    '<div class="wave-bg"></div><div class="mesh-bg"></div><div class="noise-overlay"></div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Data Loading (for fragment -- lightweight, no chart OHLCV needed)
# ---------------------------------------------------------------------------
def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


@st.cache_resource(ttl=300)
def _get_executor():
    try:
        from DevAntsa_Lab.live_trading.execution.binance_executor import BinanceExecutor
        return BinanceExecutor()
    except Exception:
        return None


def _load_live_data() -> dict:
    """Load only lightweight data needed by the fragment (no OHLCV)."""
    data = {"state": None, "wallet": None, "equity": None, "tickers": {}, "api_ok": False}

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data["state"] = json.load(f)
        except Exception:
            pass

    executor = _get_executor()
    if executor:
        data["api_ok"] = True
        data["wallet"] = _safe(lambda: executor.get_wallet_balance())
        data["equity"] = _safe(lambda: executor.get_equity())
        for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
            data["tickers"][sym] = _safe(lambda s=sym: executor.get_ticker(s))

    return data


def _load_trades() -> tuple:
    """Load trades data (for static equity curve section)."""
    if not os.path.exists(TRADE_LOG_FILE):
        return None, None
    try:
        from DevAntsa_Lab.live_trading.trade_journal import load_trades, match_trades
        raw = load_trades()
        if raw.empty:
            return raw, None
        closed, _ = match_trades(raw)
        return raw, closed
    except Exception as e:
        import traceback
        print(f"[Dashboard] _load_trades error: {e}")
        traceback.print_exc()
        # Fallback: read CSV directly
        try:
            raw = pd.read_csv(TRADE_LOG_FILE, parse_dates=["timestamp"])
            raw["date"] = raw["timestamp"].dt.date
            return raw, None
        except Exception:
            return None, None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt_money(val, sign=False):
    if val is None:
        return "---"
    s = f"${val:,.2f}"
    if sign and val >= 0:
        s = f"+{s}"
    return s


def _fmt_pct(val, sign=False):
    if val is None:
        return "---"
    s = f"{val:.2f}%"
    if sign and val >= 0:
        s = f"+{s}"
    return s


def _pnl_class(val):
    if val is None:
        return "dim"
    return "positive" if val >= 0 else "negative"


def _determine_phase(equity, starting):
    if starting is None or starting <= 0 or equity is None:
        return "BUILDING"
    ratio = equity / starting
    if ratio < 0.95:
        return "SURVIVAL"
    elif ratio < 1.00:
        return "RECOVERY"
    elif ratio < 1.05:
        return "BUILDING"
    elif ratio < 1.10:
        return "ACCELERATING"
    return "PROTECTING"


def _dd_action(daily_dd_pct):
    if daily_dd_pct is None:
        return "NORMAL"
    dd = abs(daily_dd_pct)
    if dd >= DD_ACTION_CLOSE_ALL:
        return "CLOSE_ALL"
    elif dd >= DD_ACTION_STOP_DAY:
        return "STOP_DAY"
    elif dd >= DD_ACTION_REDUCE:
        return "REDUCE"
    elif dd >= DD_ACTION_REVIEW:
        return "REVIEW"
    return "NORMAL"


def _regime_color(regime):
    return {"bull": TV_GREEN, "sideways": TV_CYAN, "bear": TV_RED}.get(regime, "#787B86")


# ---------------------------------------------------------------------------
# STATIC: Header
# ---------------------------------------------------------------------------
def render_header():
    risk_scale_pct = int(GLOBAL_RISK_SCALE * 100)
    st.markdown(
        '<div class="header-bar">'
        # Left: title + live pill
        '<div style="display:flex;align-items:center;gap:14px;flex-shrink:0;">'
        '<div>'
        '<div style="display:flex;align-items:center;gap:12px;">'
        '<span class="header-title">DevAntsa Lab</span>'
        '<div class="header-live-pill">'
        '<span class="live-dot" style="width:7px;height:7px;margin:0;"></span>'
        '<span class="live-text">LIVE</span>'
        '</div>'
        '</div>'
        '<div class="header-subtitle">Precision trading, systematic execution</div>'
        '</div>'
        '</div>'
        # Right: info chips
        '<div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">'
        '<span class="header-chip header-chip-accent">v11</span>'
        '<span class="header-chip">8 strategies</span>'
        '<span class="header-chip">3 regimes</span>'
        f'<span class="header-chip">Risk {risk_scale_pct}%</span>'
        '<span class="header-chip">Binance Demo</span>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# STATIC: TradingView Chart (truly live -- JS websocket, zero flicker)
# ---------------------------------------------------------------------------
def render_tradingview_chart(asset="BTC"):
    """Embed TradingView Advanced Chart widget. Self-updating via JS -- never re-rendered by Streamlit."""
    tv_sym = TV_SYMBOLS.get(asset, "BINANCE:BTCUSDT.P")
    html = f"""
    <div class="tradingview-widget-container" style="height:600px;width:100%">
      <div class="tradingview-widget-container__widget" style="height:600px;width:100%"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
      {{
        "width": "100%",
        "height": "600",
        "symbol": "{tv_sym}",
        "interval": "240",
        "timezone": "Etc/UTC",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "backgroundColor": "rgba(0, 0, 0, 1)",
        "gridColor": "rgba(26, 26, 26, 0.5)",
        "hide_top_toolbar": false,
        "hide_legend": false,
        "allow_symbol_change": false,
        "save_image": false,
        "calendar": false,
        "hide_volume": false,
        "studies": ["MAExp@tv-basicstudies"],
        "support_host": "https://www.tradingview.com"
      }}
      </script>
    </div>
    """
    components.html(html, height=620)


# ---------------------------------------------------------------------------
# FRAGMENT: Live data (text/HTML only -- no Plotly, no flicker)
# ---------------------------------------------------------------------------
@st.fragment(run_every=timedelta(seconds=REFRESH_SECONDS))
def render_live_data():
    data = _load_live_data()

    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    st.markdown(
        f'<div style="text-align:right;color:#4A4D57;font-size:0.68rem;margin-bottom:8px;">'
        f'Updated: {now}</div>',
        unsafe_allow_html=True,
    )

    if data["state"] is None and not data["api_ok"]:
        st.markdown('''
        <div style="text-align:center;padding:40px 20px;">
            <div style="font-size:1rem;color:#787B86;font-weight:500;">
                Waiting for trading system to start...</div>
            <div style="color:#4A4D57;font-size:0.8rem;margin-top:8px;">
                state.json not found. Start main_loop to begin.</div>
        </div>''', unsafe_allow_html=True)
        return

    _render_kill_banner(data)
    _render_metrics(data)
    st.markdown("")
    _render_status_strip(data)
    _render_tickers(data)
    st.markdown("")
    _render_positions(data)
    st.markdown("")
    _render_strategy_grid(data)
    st.markdown("")
    _render_performance(data)
    st.markdown("")
    _render_recent_trades()
    _render_footer(data)


# ---------------------------------------------------------------------------
# Metrics Strip (4 cards)
# ---------------------------------------------------------------------------
def _render_metrics(data):
    state = data["state"]
    wallet = data["wallet"]
    equity = data["equity"]

    starting = session_start = None
    if state and "risk" in state:
        starting = state["risk"].get("starting_equity")
        session_start = state["risk"].get("session_start_equity")

    eq_val = wallet["equity"] if wallet else equity

    pnl = pnl_pct = None
    if eq_val is not None and starting:
        pnl = eq_val - starting
        pnl_pct = (pnl / starting) * 100

    daily_dd = None
    if eq_val is not None and session_start and session_start > 0:
        daily_dd = max(((session_start - eq_val) / session_start) * 100, 0)

    total_dd = None
    if eq_val is not None and starting and starting > 0:
        total_dd = max(((starting - eq_val) / starting) * 100, 0)

    phase = _determine_phase(eq_val, starting)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        delta_html = ""
        if pnl is not None:
            delta_html = f'<div class="metric-delta {_pnl_class(pnl)}">{_fmt_money(pnl, sign=True)} ({_fmt_pct(pnl_pct, sign=True)})</div>'
        st.markdown(f'<div class="metric-card"><div class="metric-label">Equity</div>'
                    f'<div class="metric-value">{_fmt_money(eq_val)}</div>{delta_html}</div>',
                    unsafe_allow_html=True)

    with c2:
        dd_val = daily_dd or 0
        fill = min(dd_val / (DAILY_DD_LIMIT_PERSONAL * 100), 1.0) * 100
        bar_c = TV_GREEN if dd_val < 1.5 else (TV_AMBER if dd_val < 2.5 else TV_RED)
        st.markdown(f'<div class="metric-card"><div class="metric-label">Daily DD</div>'
                    f'<div class="metric-value {_pnl_class(-(daily_dd or 0))}">-{_fmt_pct(dd_val)}</div>'
                    f'<div class="progress-bar-track"><div class="progress-bar-fill" style="width:{fill:.0f}%;background:{bar_c};"></div></div>'
                    f'<div style="color:#4A4D57;font-size:0.65rem;margin-top:4px;">Limit: -{_fmt_pct(DAILY_DD_LIMIT_PERSONAL*100)}</div></div>',
                    unsafe_allow_html=True)

    with c3:
        td_val = total_dd or 0
        fill_t = min(td_val / (TOTAL_DD_LIMIT_PERSONAL * 100), 1.0) * 100
        bar_t = TV_GREEN if td_val < 3 else (TV_AMBER if td_val < 5 else TV_RED)
        st.markdown(f'<div class="metric-card"><div class="metric-label">Total DD</div>'
                    f'<div class="metric-value {_pnl_class(-(total_dd or 0))}">-{_fmt_pct(td_val)}</div>'
                    f'<div class="progress-bar-track"><div class="progress-bar-fill" style="width:{fill_t:.0f}%;background:{bar_t};"></div></div>'
                    f'<div style="color:#4A4D57;font-size:0.65rem;margin-top:4px;">Limit: -{_fmt_pct(TOTAL_DD_LIMIT_PERSONAL*100)}</div></div>',
                    unsafe_allow_html=True)

    with c4:
        st.markdown(
            '<div class="metric-card" style="padding:10px 10px 10px 10px;">'
            '<div class="metric-label" style="margin-bottom:6px;">Now Playing</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        components.html(
            '<iframe style="border-radius:12px;background:#000;" width="100%" height="80"'
            ' title="Spotify Embed: Quant" frameborder="0" allowfullscreen'
            ' allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"'
            ' loading="lazy"'
            ' src="https://open.spotify.com/embed/playlist/2x8w8n7ZXrLnaM3hUHw24H?utm_source=oembed&theme=0"></iframe>',
            height=85,
        )


# ---------------------------------------------------------------------------
# Status Strip (DD action, losing days, positions, kill switch)
# ---------------------------------------------------------------------------
def _render_status_strip(data):
    state = data["state"]
    equity = data["equity"]

    session_start = None
    if state and "risk" in state:
        session_start = state["risk"].get("session_start_equity")
    daily_dd_pct = 0
    if equity and session_start and session_start > 0:
        daily_dd_pct = max((session_start - equity) / session_start, 0)
    action = _dd_action(daily_dd_pct)
    action_cls = {"NORMAL": "badge-normal", "REVIEW": "badge-review", "REDUCE": "badge-reduce",
                  "STOP_DAY": "badge-stop-day", "CLOSE_ALL": "badge-close-all"}

    losing_days = 0
    if state and "risk" in state:
        losing_days = state["risk"].get("consecutive_losing_days", 0)

    positions = state.get("positions", []) if state else []
    n_pos = len(positions)
    n_bull = sum(1 for p in positions if STRATEGY_REGIME.get(p.get("strategy"), "") == "bull")
    n_side = sum(1 for p in positions if STRATEGY_REGIME.get(p.get("strategy"), "") == "sideways")
    n_bear = sum(1 for p in positions if STRATEGY_REGIME.get(p.get("strategy"), "") == "bear")

    # Kill switch
    kill_armed = True
    rolling_sharpe_val = "---"
    worst_strat_dd = "---"
    if state and "risk" in state:
        trade_returns = state["risk"].get("trade_returns", [])
        min_trades = KILL_SWITCH.get("min_trades_for_sharpe", 20)
        if len(trade_returns) >= min_trades:
            returns = np.array(trade_returns, dtype=float)
            m, s = np.mean(returns), np.std(returns)
            if s > 0:
                rolling_sharpe_val = f"{(m / s) * np.sqrt(252):.2f}"
        peaks = state["risk"].get("strategy_peak_equity", {})
        currents = state["risk"].get("strategy_current_equity", {})
        worst_ratio = 0
        for strat in ALL_STRATEGIES:
            pk, cr, bt = peaks.get(strat), currents.get(strat), BACKTEST_MAX_DD.get(strat, 0)
            if pk and cr and pk > 0 and bt > 0:
                worst_ratio = max(worst_ratio, (pk - cr) / pk / bt)
        if worst_ratio > 0:
            worst_strat_dd = f"{worst_ratio:.1f}x"
            if worst_ratio > KILL_SWITCH.get("max_dd_vs_backtest_ratio", 1.5):
                kill_armed = False

    ks_color = TV_GREEN if kill_armed else TV_RED
    ks_label = "ARMED" if kill_armed else "TRIGGERED"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="card"><div class="metric-label">DD Action</div>'
                    f'<div style="margin-top:6px;"><span class="badge {action_cls.get(action, "badge-normal")}">'
                    f'{action.replace("_", " ")}</span></div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="card"><div class="metric-label">Losing Days</div>'
                    f'<div class="metric-value" style="font-size:1.2rem;">{losing_days}</div></div>',
                    unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="card"><div class="metric-label">Positions</div>'
                    f'<div class="metric-value" style="font-size:1.2rem;">{n_pos}/{MAX_TOTAL_POSITIONS}</div>'
                    f'<div style="color:#787B86;font-size:0.65rem;margin-top:4px;">'
                    f'<span style="color:{TV_GREEN};">Bull {n_bull}/{MAX_POSITIONS_PER_REGIME["bull"]}</span>'
                    f' | <span style="color:{TV_CYAN};">Side {n_side}/{MAX_POSITIONS_PER_REGIME["sideways"]}</span>'
                    f' | <span style="color:{TV_RED};">Bear {n_bear}/{MAX_POSITIONS_PER_REGIME["bear"]}</span></div></div>',
                    unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="card"><div class="metric-label">Kill Switch</div>'
                    f'<div style="margin-top:4px;"><span class="badge" style="background:rgba({"8,153,129" if kill_armed else "242,54,69"},0.15);color:{ks_color};">'
                    f'{ks_label}</span></div>'
                    f'<div style="color:#787B86;font-size:0.65rem;margin-top:4px;">S: {rolling_sharpe_val} | DD: {worst_strat_dd}</div></div>',
                    unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Ticker Bar (text-only -- no Plotly sparklines)
# ---------------------------------------------------------------------------
def _render_tickers(data):
    tickers = data["tickers"]
    symbols = [("BTC", "BTCUSDT", "#F7931A"), ("ETH", "ETHUSDT", "#627EEA"), ("SOL", "SOLUSDT", "#9945FF")]
    cols = st.columns(3)
    for i, (name, sym, color) in enumerate(symbols):
        with cols[i]:
            t = tickers.get(sym)
            price = f"${t['price']:,.2f}" if t else "---"
            change = t["change_24h_pct"] if t else None
            change_str = _fmt_pct(change, sign=True) if change is not None else "---"
            st.markdown(f'''<div class="ticker-card">
                <div style="display:flex;align-items:center;gap:8px;">
                    <div style="width:8px;height:8px;border-radius:50%;background:{color};"></div>
                    <span style="color:#F8F9FD;font-weight:600;font-size:0.85rem;">{name}</span></div>
                <div style="font-size:1.3rem;font-weight:600;color:#F8F9FD;margin-top:4px;">{price}</div>
                <div class="{_pnl_class(change)}" style="font-size:0.8rem;">{change_str}</div>
            </div>''', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Open Positions Table
# ---------------------------------------------------------------------------
def _render_positions(data):
    st.markdown("### Open Positions")
    state = data["state"]
    positions = state.get("positions", []) if state else []
    tickers = data["tickers"]

    if not positions:
        st.markdown('<div class="empty-state">No open positions -- waiting for signals</div>',
                    unsafe_allow_html=True)
        return

    rows = ""
    for pos in positions:
        strategy = pos.get("strategy", "?")
        asset = pos.get("asset", "?")
        tf_map = {"60": "1h", "240": "4h", "D": "D"}
        tf = tf_map.get(STRATEGY_TIMEFRAMES.get(strategy, "?"), "?")
        direction = pos.get("direction", "?")
        entry_price = pos.get("entry_price", 0)
        stop = pos.get("stop_price", 0)
        bars = pos.get("bars_held", 0)
        ticker = tickers.get(asset, {})
        current = ticker.get("price", entry_price) if ticker else entry_price
        ds = 1.0 if direction == "LONG" else -1.0
        upnl = (current - entry_price) * ds if entry_price else 0
        qty = pos.get("qty", 0)
        upnl_dollar = upnl * qty if qty else 0
        upnl_pct = (upnl / entry_price * 100) if entry_price else 0
        risk_pu = abs(entry_price - stop) if stop else 0
        r_mult = upnl / risk_pu if risk_pu > 0 else 0
        r_color = TV_GREEN if r_mult >= 1 else (TV_AMBER if r_mult >= 0 else TV_RED)
        regime = STRATEGY_REGIME.get(strategy, "?")
        regime_c = _regime_color(regime)
        d_dot = f'<span style="color:{TV_GREEN if direction=="LONG" else TV_RED};">{"^" if direction=="LONG" else "v"}</span>'
        regime_dot = f'<span style="color:{regime_c};font-size:0.65rem;">{regime[0].upper()}</span>'
        rows += (f'<tr><td>{d_dot}{regime_dot}</td><td style="font-weight:500;">{strategy}</td>'
                 f'<td>{asset.replace("USDT","")}({tf})</td><td>${entry_price:,.2f}</td>'
                 f'<td>${current:,.2f}</td><td class="{_pnl_class(upnl)}">{_fmt_money(upnl_dollar, sign=True)} ({_fmt_pct(upnl_pct, sign=True)})</td>'
                 f'<td>${stop:,.2f}</td><td style="color:{r_color};font-weight:500;">{r_mult:.1f}R</td><td>{bars}</td></tr>')

    st.markdown(f'<table class="pos-table"><thead><tr>'
                '<th></th><th>Strategy</th><th>Asset(TF)</th><th>Entry</th><th>Current</th>'
                '<th>Unrealized P&L</th><th>Stop</th><th>R-Mult</th><th>Bars</th>'
                f'</tr></thead><tbody>{rows}</tbody></table>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Strategy Grid
# ---------------------------------------------------------------------------
def _render_strategy_grid(data):
    st.markdown("### Strategy Grid")
    state = data["state"]
    positions = state.get("positions", []) if state else []
    tickers = data["tickers"]
    pos_map = {p.get("strategy"): p for p in positions}

    # Group by regime for section headers
    regime_groups = [
        ("Bull", BULL_STRATEGIES, TV_GREEN),
        ("Sideways", SIDEWAYS_STRATEGIES, TV_CYAN),
        ("Bear", BEAR_STRATEGIES, TV_RED),
    ]

    cards = []
    for strat in ALL_STRATEGIES:
        regime = STRATEGY_REGIME[strat]
        asset = STRATEGY_ASSETS.get(strat, ["?"])[0]
        asset_short = asset.replace("USDT", "")
        tf_map = {"60": "1h", "240": "4h", "D": "D"}
        tf = tf_map.get(STRATEGY_TIMEFRAMES.get(strat, "240"), "4h")
        sharpe = BACKTEST_SHARPE.get(strat, 0)
        bt_dd = BACKTEST_MAX_DD.get(strat, 0) * 100
        bt_ret = BACKTEST_RETURN.get(strat, 0)
        risk = STRATEGY_RISK_OVERRIDES.get(strat, 0.005) * 100
        risk_scale = STRATEGY_RISK_SCALE.get(strat, 1.0)
        eff_risk = risk * GLOBAL_RISK_SCALE * risk_scale
        pos = pos_map.get(strat)
        is_active = pos is not None
        status = '<span class="badge badge-active">ACTIVE</span>' if is_active else '<span class="badge badge-watching">WATCHING</span>'
        regime_b = f'<span class="badge badge-{regime}">{regime.upper()}</span>'
        pos_info = ""
        if is_active:
            entry = pos.get("entry_price", 0)
            stop = pos.get("stop_price", 0)
            bars = pos.get("bars_held", 0)
            ticker = tickers.get(asset, {})
            curr = ticker.get("price", entry) if ticker else entry
            ds = 1.0 if pos.get("direction") == "LONG" else -1.0
            up = ((curr - entry) * ds / entry * 100) if entry else 0
            pos_info = (f'<div style="margin-top:6px;font-size:0.7rem;color:#787B86;">'
                        f'Entry ${entry:,.2f} | Stop ${stop:,.2f} | {bars} bars<br>'
                        f'<span class="{_pnl_class(up)}" style="font-size:0.75rem;">{_fmt_pct(up, sign=True)}</span></div>')

        cards.append(f'<div class="strat-card strat-card-{regime}">'
                     f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                     f'<span style="color:#F8F9FD;font-weight:500;font-size:0.82rem;">{strat}</span>{status}</div>'
                     f'<div style="margin-top:4px;display:flex;gap:6px;align-items:center;">{regime_b}'
                     f'<span style="color:#787B86;font-size:0.7rem;">{asset_short}-{tf}</span></div>'
                     f'<div style="margin-top:6px;font-size:0.68rem;color:#4A4D57;">'
                     f'S={sharpe:.2f} | +{bt_ret:.0f}% | DD=-{bt_dd:.1f}% | Risk={eff_risk:.2f}%</div>'
                     f'{pos_info}</div>')

    for i in range(0, len(cards), 3):
        cols = st.columns(3)
        for j, card in enumerate(cards[i:i + 3]):
            with cols[j]:
                st.markdown(card, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Performance Stats
# ---------------------------------------------------------------------------
def _render_performance(data):
    st.markdown("### Performance")
    state = data["state"]
    # Load trades inline (lightweight)
    _, closed = _load_trades()

    total = wins = 0
    avg_win = avg_loss = expectancy = wr = None
    if closed is not None and not closed.empty:
        total = len(closed)
        winners = closed[closed["pnl"] > 0]
        losers = closed[closed["pnl"] < 0]
        wins = len(winners)
        wr = (wins / total * 100) if total > 0 else 0
        avg_win = winners["pnl"].mean() if not winners.empty else 0
        avg_loss = losers["pnl"].mean() if not losers.empty else 0
        if total > 0:
            wr_dec = wins / total
            expectancy = (wr_dec * (avg_win or 0)) + ((1 - wr_dec) * (avg_loss or 0))

    rolling_sharpe = "---"
    if state and "risk" in state:
        tr = state["risk"].get("trade_returns", [])
        min_n = KILL_SWITCH.get("min_trades_for_sharpe", 20)
        if len(tr) >= min_n:
            arr = np.array(tr, dtype=float)
            m, s = np.mean(arr), np.std(arr)
            if s > 0:
                rolling_sharpe = f"{(m / s) * np.sqrt(252):.2f}"
        else:
            rolling_sharpe = f"{min_n - len(tr)} more trades needed"

    cols = st.columns(6)
    items = [
        ("Total Trades", str(total), ""),
        ("Win Rate", _fmt_pct(wr) if wr is not None else "--", "positive" if wr and wr >= 50 else "negative"),
        ("Avg Win", _fmt_money(avg_win) if avg_win else "--", "positive"),
        ("Avg Loss", _fmt_money(avg_loss) if avg_loss else "--", "negative"),
        ("Expectancy", _fmt_money(expectancy, sign=True) if expectancy is not None else "--", _pnl_class(expectancy)),
        ("Rolling Sharpe", rolling_sharpe, ""),
    ]
    for i, (label, value, cls) in enumerate(items):
        with cols[i]:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div>'
                        f'<div class="metric-value {cls}" style="font-size:1.1rem;">{value}</div></div>',
                        unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
def _render_footer(data):
    state = data["state"]
    saved_at = "---"
    if state:
        saved_at = state.get("saved_at") or "---"
        if saved_at != "---":
            saved_at = saved_at[:19].replace("T", " ") + " UTC"
    st.markdown("---")
    st.markdown(f'<div style="text-align:center;padding:10px 0 20px;">'
                f'<div style="color:#4A4D57;font-size:0.75rem;font-weight:500;">'
                f'DevAntsa Lab -- Precision trading, systematic execution</div>'
                f'<div style="color:#2A2E39;font-size:0.65rem;margin-top:4px;">'
                f'Portfolio v11 | 8 strategies | 3 regimes | Binance Futures Demo | '
                f'Live refresh: {REFRESH_SECONDS}s | State saved: {saved_at}</div></div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Kill Banner
# ---------------------------------------------------------------------------
def _render_kill_banner(data):
    state = data["state"]
    if not state or "risk" not in state:
        return
    equity = data["equity"]
    risk = state["risk"]
    starting = risk.get("starting_equity", 0)
    if not equity or not starting or starting <= 0:
        return
    total_dd = (starting - equity) / starting
    if total_dd >= TOTAL_DD_LIMIT_PERSONAL:
        st.markdown(f'<div class="kill-banner">KILL SWITCH -- Total drawdown exceeded '
                    f'{TOTAL_DD_LIMIT_PERSONAL*100:.0f}% limit. All strategies HALTED.</div>',
                    unsafe_allow_html=True)
        return
    session_start = risk.get("session_start_equity", starting)
    if session_start and session_start > 0:
        if (session_start - equity) / session_start >= DAILY_DD_LIMIT_PERSONAL:
            st.markdown(f'<div class="kill-banner">DAILY STOP -- Daily drawdown exceeded '
                        f'{DAILY_DD_LIMIT_PERSONAL*100:.0f}% limit. Trading halted for the day.</div>',
                        unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Recent Trades (inside fragment -- auto-refreshes every 30s)
# ---------------------------------------------------------------------------
def _render_recent_trades():
    """Render recent trades table. Called from fragment for auto-refresh."""
    raw, closed = _load_trades()
    st.markdown("### Recent Trades")
    if raw is not None and not raw.empty:
        recent = raw.sort_values("timestamp", ascending=False).head(20)
        rows = ""
        for _, row in recent.iterrows():
            ts = str(row["timestamp"])[:16] if pd.notna(row["timestamp"]) else "?"
            strat = row.get("strategy", "?")
            asset = str(row.get("asset", "?")).replace("USDT", "")
            direction = row.get("direction", "?")
            action = row.get("action", "?")
            price = float(row["price"]) if pd.notna(row.get("price")) else 0
            reason = row.get("reason", "") if pd.notna(row.get("reason")) else ""
            regime = STRATEGY_REGIME.get(strat, "?")
            regime_c = _regime_color(regime)
            d_cls = "positive" if direction == "LONG" else "negative"
            rows += (f'<tr><td style="font-size:0.72rem;color:#4A4D57;">{ts}</td>'
                     f'<td style="font-weight:500;">{strat}</td><td>{asset}</td>'
                     f'<td class="{d_cls}">{action}</td>'
                     f'<td>${price:,.2f}</td>'
                     f'<td><span style="color:{regime_c};font-size:0.65rem;">{regime}</span></td>'
                     f'<td style="color:#4A4D57;font-size:0.72rem;">{reason}</td></tr>')
        st.markdown(f'<table class="pos-table"><thead><tr><th>Time</th><th>Strategy</th><th>Asset</th>'
                    f'<th>Action</th><th>Price</th><th>Regime</th><th>Reason</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table>', unsafe_allow_html=True)

        # Show matched P&L summary if available
        if closed is not None and not closed.empty:
            total_pnl = closed["pnl"].sum()
            pnl_cls = "positive" if total_pnl >= 0 else "negative"
            wins = (closed["pnl"] > 0).sum()
            losses = (closed["pnl"] < 0).sum()
            st.markdown(
                f'<div style="margin-top:8px;font-size:0.78rem;color:#787B86;">'
                f'Closed: {len(closed)} trades | '
                f'P&L: <span class="{pnl_cls}">${total_pnl:+,.2f}</span> | '
                f'W/L: {wins}/{losses}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown('<div class="empty-state">No trades recorded yet</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# STATIC: Equity Curve (outside fragment -- Plotly, no flicker)
# ---------------------------------------------------------------------------
def render_equity_section():
    _, closed = _load_trades()

    # -- Build Plotly chart HTML --
    starting = 5000.0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                s = json.load(f)
            starting = s.get("risk", {}).get("starting_equity", 5000.0)
        except Exception:
            pass

    if closed is not None and not closed.empty:
        cs = closed.sort_values("date")
        equity_line = starting + cs["pnl"].cumsum()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=cs["date"].astype(str), y=equity_line, mode="lines",
                                 fill="tozeroy", line=dict(color="#F7931A", width=2),
                                 fillcolor="rgba(247,147,26,0.08)"))
        fig.add_hline(y=starting, line_dash="dash", line_color="rgba(120,123,134,0.3)",
                      annotation_text=f"Start ${starting:,.0f}", annotation_font_color="#787B86", annotation_font_size=10)
        fig.add_hline(y=starting * 1.10, line_dash="dash", line_color="rgba(8,153,129,0.3)",
                      annotation_text=f"Target ${starting*1.10:,.0f}", annotation_font_color=TV_GREEN, annotation_font_size=10)
        fig.add_hrect(y0=0, y1=starting * 0.93, fillcolor="rgba(242,54,69,0.06)", line_width=0)
        fig.add_hline(y=starting * 0.93, line_dash="dash", line_color="rgba(242,54,69,0.3)",
                      annotation_text=f"Kill ${starting*0.93:,.0f}", annotation_font_color=TV_RED, annotation_font_size=10)
        fig.update_layout(**{**CHART_LAYOUT, "height": 280})
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=["Start", "Now"], y=[starting, starting], mode="lines",
                                 line=dict(color="#F7931A", width=2)))
        fig.update_layout(**{**CHART_LAYOUT, "height": 280})

    chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn",
                             config={"displayModeBar": False})

    # -- Equity curve in styled container (full width) --
    eq_html = f"""<!DOCTYPE html><html><head>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ background:transparent; font-family:'Inter',sans-serif; color:#D1D4DC; }}
        .wrap {{
            background: rgba(10,10,10,0.5);
            backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.03);
            border-radius: 10px; padding: 20px 24px; position: relative; overflow: hidden;
            box-shadow: 0 4px 24px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.02);
        }}
        .wrap::before {{
            content:''; position:absolute; top:0; left:0; right:0; height:45%;
            background: linear-gradient(180deg, rgba(8,153,129,0.045) 0%, transparent 100%);
            pointer-events:none; z-index:0; border-radius:10px 10px 0 0;
        }}
        .wrap::after {{
            content:''; position:absolute; bottom:0; left:0; right:0; height:45%;
            background: linear-gradient(0deg, rgba(242,54,69,0.045) 0%, transparent 100%);
            pointer-events:none; z-index:0; border-radius:0 0 10px 10px;
        }}
        .content {{ position:relative; z-index:1; }}
        h3 {{ color:#D1D4DC; font-size:0.95rem; font-weight:500; margin-bottom:12px; }}
        .empty {{ text-align:center; padding:20px; color:#4A4D57; font-size:0.82rem; }}
        .plotly-graph-div {{ width:100% !important; }}
    </style></head><body>
    <div class="wrap"><div class="content">
        <h3>Equity Curve</h3>
        {chart_html}
    </div></div>
    </body></html>"""

    components.html(eq_html, height=400)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Static: header
    render_header()

    # Static: asset selector (outside fragment -- change triggers full rerun)
    if "chart_asset" not in st.session_state:
        st.session_state.chart_asset = "BTC"
    chart_asset = st.radio("Asset", ["BTC", "ETH", "SOL"], horizontal=True,
                           index=["BTC", "ETH", "SOL"].index(st.session_state.chart_asset),
                           key="chart_asset_main")
    if chart_asset != st.session_state.chart_asset:
        st.session_state.chart_asset = chart_asset

    # Static: TradingView chart (live via JS websocket -- zero flicker)
    render_tradingview_chart(st.session_state.chart_asset)

    # Fragment: all data-dependent text/HTML (refreshes every 30s, no Plotly)
    render_live_data()

    st.markdown("")

    # Static: equity curve (Plotly, rendered once on page load -- trades in fragment)
    render_equity_section()


if __name__ == "__main__":
    main()
