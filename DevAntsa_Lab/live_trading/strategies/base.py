"""
Base Strategy Class + Indicator Helpers
=======================================
All regime strategies inherit from StrategyBase.
Indicator functions use raw pandas/numpy (NOT pandas_ta) for exact backtest equivalence.

Provides: ATR, EMA, RSI, ADX, ADX+DI, BB, momentum, ROC, TRIX, TSI, MFI,
          percentile rank, and Wilder's smoothing variants.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd
import numpy as np


# == Data objects ===========================================================

@dataclass
class Signal:
    """Emitted by a strategy when entry conditions are met."""
    strategy_name: str
    regime: str            # "bull" | "bear" | "sideways"
    direction: str         # "LONG" | "SHORT"
    asset: str             # e.g. "SOLUSDT"
    entry_price: float
    stop_price: float
    stop_distance_pct: float
    metadata: dict = field(default_factory=dict)


@dataclass
class ExitSignal:
    """Emitted by a strategy when an open position should be closed."""
    strategy_name: str
    asset: str
    reason: str            # "TRAILING_STOP" | "TARGET_HIT" | "MAX_HOLD" | ...
    metadata: dict = field(default_factory=dict)


# == Indicator functions (raw pandas/numpy) =================================
# These match the backtest source files exactly.

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ATR(period) using simple rolling mean of true range.
    Formula from all 6 backtest files (identical implementation).
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calculate_ema(series: pd.Series, span: int) -> pd.Series:
    """EMA using pandas ewm. From T16_ElasticReclaim."""
    return series.ewm(span=span).mean()


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI using simple rolling mean of gains/losses.
    From T00_PercentileRSIReversion_BEST_3.99pct.py (RSI function).
    """
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ADX from T00_PercentileRSIReversion_BEST_3.99pct.py (adx_func).
    Uses ATR as the smoothed true range denominator.
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    atr = calculate_atr(df, period)
    up = high - high.shift(1)
    down = low.shift(1) - low
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    plus_dm_smooth = plus_dm.rolling(period).mean()
    minus_dm_smooth = minus_dm.rolling(period).mean()
    plus_di = 100 * (plus_dm_smooth / atr)
    minus_di = 100 * (minus_dm_smooth / atr)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di)) * 100
    adx = dx.rolling(period).mean()
    return adx


def calculate_percentile_rank(series: pd.Series, period: int = 60) -> pd.Series:
    """
    Rolling percentile rank (0-1 scale).
    From T00_PercentileRSIReversion_BEST_3.99pct.py (calculate_percentile_rank).
    """
    def rank_window(window):
        if len(window) < period:
            return np.nan
        return pd.Series(window).rank(pct=True).iloc[-1]
    return series.rolling(period).apply(rank_window, raw=False)


def calculate_bb_mid(close: pd.Series, period: int = 20) -> pd.Series:
    """BB midline = SMA(period). From T00_PercentileRSIReversion."""
    return close.rolling(period).mean()


def calculate_bb_width(close: pd.Series, period: int = 20) -> pd.Series:
    """
    Relative BB width = 4 * std / mid (for 2-std bands).
    From T00_PercentileRSIReversion_BEST_3.99pct.py (bb_width_func).
    """
    return 4 * close.rolling(period).std() / close.rolling(period).mean()


def calculate_momentum(close: pd.Series, bars: int) -> pd.Series:
    """Momentum = close / close.shift(bars) - 1. From multiple backtests."""
    return close / close.shift(bars) - 1


def calculate_pct_change(close: pd.Series, bars: int) -> pd.Series:
    """pct_change(bars). Used by ConfluentMomentum (mom8, mom10)."""
    return close.pct_change(bars)


def calculate_roc_pct(close: pd.Series, period: int) -> pd.Series:
    """ROC as percentage: (close - close[n]) / close[n] * 100. From AccelBreakdown."""
    return (close - close.shift(period)) / close.shift(period) * 100


def calculate_trix(close: pd.Series, period: int = 12) -> pd.Series:
    """
    TRIX: Triple-smoothed EMA rate of change.
    From B17_TripleMomentum_SOL4h_Sharpe1.14.py.
    """
    ema1 = close.ewm(span=period).mean()
    ema2 = ema1.ewm(span=period).mean()
    ema3 = ema2.ewm(span=period).mean()
    return 100 * (ema3 - ema3.shift(1)) / ema3.shift(1)


def calculate_tsi(close: pd.Series, r: int = 25, s: int = 13) -> pd.Series:
    """
    TSI (True Strength Index): Double-smoothed price change ratio.
    From bear_worsening_momentum.py (TSI function).
    """
    pc = close.diff()
    smoothed_pc = pc.ewm(span=r).mean().ewm(span=s).mean()
    smoothed_abs_pc = pc.abs().ewm(span=r).mean().ewm(span=s).mean()
    return 100 * (smoothed_pc / smoothed_abs_pc)


def calculate_mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    MFI (Money Flow Index).
    From bear_mfi_distribution.py (MFI function).
    """
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    mf = tp * df["Volume"]
    pos_mf = mf.where(tp > tp.shift(1), 0).rolling(period).sum()
    neg_mf = mf.where(tp < tp.shift(1), 0).rolling(period).sum()
    return 100 - (100 / (1 + pos_mf / neg_mf.replace(0, 1)))


def calculate_adx_di(df: pd.DataFrame, period: int = 14):
    """
    ADX + DI+/DI- using simple rolling mean smoothing.
    From bear_bearish_lower_high.py and bear_ema_rejection_adx.py (ADX_DI function).
    Returns (adx, plus_di, minus_di) as pd.Series.
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    plus_dm = high.diff().copy()
    minus_dm = (-low.diff()).copy()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0
    tr = pd.concat([high - low, (high - close.shift(1)).abs(),
                     (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(period).mean()
    return adx, plus_di, minus_di


def calculate_adx_di_wilder(df: pd.DataFrame, period: int = 14):
    """
    ADX + DI+/DI- using Wilder's smoothing (ewm alpha=1/n).
    From B14_DIBreakoutPyramid (directional_indicator) and
    T09_DirectionalIgnition (calculate_dmi).
    Returns (adx, plus_di, minus_di) as pd.Series.
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(0.0, index=high.index)
    minus_dm = pd.Series(0.0, index=high.index)
    mask_plus = (up_move > down_move) & (up_move > 0)
    mask_minus = (down_move > up_move) & (down_move > 0)
    plus_dm[mask_plus] = up_move[mask_plus]
    minus_dm[mask_minus] = down_move[mask_minus]
    tr = pd.concat([high - low, (high - close.shift(1)).abs(),
                     (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / period).mean()
    return adx, plus_di, minus_di


def calculate_atr_wilder(df: pd.DataFrame, period: int = 17) -> pd.Series:
    """
    ATR using Wilder's smoothing (ewm alpha=1/n).
    From T09_DirectionalIgnition (calculate_atr with wilders_smoothing).
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr = pd.concat([high - low, (high - close.shift(1)).abs(),
                     (low - close.shift(1)).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period).mean()


# == Abstract base ==========================================================

class StrategyBase:
    """
    Abstract base for all regime strategies.

    Subclasses MUST implement:
        compute_indicators(df) -> pd.DataFrame
        check_entry(df) -> Optional[Signal]
        check_exit(df, position) -> Optional[ExitSignal]

    Subclasses with trailing stops MUST also implement:
        calculate_trail(df, position) -> Optional[float]
    """

    name: str = "BaseStrategy"
    regime: str = "unknown"       # "bull" | "bear" | "sideways"
    direction: str = "LONG"       # "LONG" | "SHORT"
    assets: List[str] = []
    timeframe: str = "240"        # kline interval string (minutes)

    # How many bars the strategy needs (for get_ohlcv limit param).
    # Strategies with long indicators (e.g. SMA200) override this.
    min_bars: int = 200

    # Stop / trail ATR multipliers (overridden per strategy)
    stop_atr_mult: float = 2.5
    trail_atr_mult: float = 2.0
    has_trailing_stop: bool = True
    has_target_exit: bool = False

    def __init__(self) -> None:
        pass

    # -- Indicators ---------------------------------------------------------

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add all indicators needed by this strategy to df (in-place).
        Subclasses override to add strategy-specific columns.
        Always call compute_common_indicators first.
        """
        raise NotImplementedError

    @staticmethod
    def compute_common_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add ATR(14) common to all strategies.
        Individual strategies add their own specific indicators on top.
        """
        if "ATR_14" not in df.columns:
            df["ATR_14"] = calculate_atr(df, 14)
        return df

    # -- Entry --------------------------------------------------------------

    def check_entry(self, df: pd.DataFrame) -> Optional[Signal]:
        """
        Evaluate the latest bar(s) of df for an entry signal.
        Return a Signal if conditions met, else None.
        """
        raise NotImplementedError

    # -- Exit / Trail -------------------------------------------------------

    def check_exit(self, df: pd.DataFrame, position) -> Optional[ExitSignal]:
        """
        Evaluate whether position should be closed.
        """
        raise NotImplementedError

    def calculate_trail(self, df: pd.DataFrame, position) -> Optional[float]:
        """
        Return updated trailing-stop price, or None if no update needed.
        """
        return None
