"""
Example Strategy: SMA Crossover
================================
A simple SMA(50)/SMA(200) golden cross strategy to demonstrate how to build
strategies using the StrategyBase framework.

THIS IS A DUMMY EXAMPLE with zero alpha -- it exists only to show the
strategy interface pattern. Replace it with your own proprietary logic.

To create your own strategy:
    1. Copy this file and rename it (e.g., my_strategy.py)
    2. Subclass StrategyBase
    3. Implement: compute_indicators(), check_entry(), check_exit()
    4. Optionally implement: calculate_trail() for trailing stops
    5. Register in signal_engine.py and config.py
"""

from __future__ import annotations
from typing import Optional
import pandas as pd

from DevAntsa_Lab.live_trading.strategies.base import (
    StrategyBase,
    Signal,
    ExitSignal,
    calculate_atr,
    calculate_ema,
)


class ExampleSMACrossover(StrategyBase):
    """
    DUMMY EXAMPLE -- SMA(50)/SMA(200) golden cross with volume confirmation.

    Entry (LONG):
        - SMA(50) crosses above SMA(200)  (golden cross)
        - Close > SMA(200)                 (trend filter)
        - Volume > 1.5x 20-bar average    (confirmation)

    Exit:
        - Trailing stop: adaptive ATR-based (tightens as profit grows)
        - Signal exit: SMA(50) crosses below SMA(200) (death cross)
        - Max hold: 150 bars

    This strategy is intentionally simple. Real deployed strategies use
    more sophisticated entry conditions, signal exits, and risk management.
    """

    name = "ExampleSMACrossover"
    regime = "bull"
    direction = "LONG"
    assets = ["SOLUSDT"]
    timeframe = "240"         # 4h candles
    min_bars = 250            # need 200+ bars for SMA(200)

    stop_atr_mult = 2.5
    trail_atr_mult = 2.0
    has_trailing_stop = True
    has_target_exit = False

    def __init__(self) -> None:
        super().__init__()
        self._entry_price: Optional[float] = None
        self._trailing_stop: Optional[float] = None
        self._highest_since_entry: Optional[float] = None
        self._bars_held: int = 0

    # -- Indicators ---------------------------------------------------------

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add SMA(50), SMA(200), ATR(14), volume average to the dataframe."""
        self.compute_common_indicators(df)  # ATR_14

        if "SMA_50" not in df.columns:
            df["SMA_50"] = df["Close"].rolling(50).mean()
        if "SMA_200" not in df.columns:
            df["SMA_200"] = df["Close"].rolling(200).mean()
        if "VOL_AVG_20" not in df.columns:
            df["VOL_AVG_20"] = df["Volume"].rolling(20).mean()

        return df

    # -- Entry --------------------------------------------------------------

    def check_entry(self, df: pd.DataFrame) -> Optional[Signal]:
        """
        Check for SMA golden cross + volume confirmation.
        Returns a Signal if entry conditions are met, else None.
        """
        if len(df) < 202:
            return None

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # Skip if indicators are NaN
        if pd.isna(curr["SMA_50"]) or pd.isna(curr["SMA_200"]) or pd.isna(curr["ATR_14"]):
            return None

        atr = curr["ATR_14"]
        if atr <= 0:
            return None

        # Already in a position? Skip entry.
        if self._entry_price is not None:
            return None

        # --- Entry conditions ---
        # 1. Golden cross: SMA50 was below SMA200, now above
        golden_cross = prev["SMA_50"] < prev["SMA_200"] and curr["SMA_50"] > curr["SMA_200"]
        # OR: already in uptrend (SMA50 > SMA200) and close pulls back to SMA50
        uptrend_pullback = (
            curr["SMA_50"] > curr["SMA_200"]
            and prev["Close"] < prev["SMA_50"]
            and curr["Close"] > curr["SMA_50"]
        )

        # 2. Trend filter: close above SMA200
        above_sma200 = curr["Close"] > curr["SMA_200"]

        # 3. Volume confirmation
        vol_ok = curr["Volume"] > 1.5 * curr["VOL_AVG_20"] if curr["VOL_AVG_20"] > 0 else False

        if (golden_cross or uptrend_pullback) and above_sma200 and vol_ok:
            entry_price = curr["Close"]
            stop_distance = self.stop_atr_mult * atr
            stop_price = entry_price - stop_distance

            self._entry_price = entry_price
            self._trailing_stop = stop_price
            self._highest_since_entry = curr["High"]
            self._bars_held = 0

            return Signal(
                strategy_name=self.name,
                regime=self.regime,
                direction=self.direction,
                asset="",          # filled by signal_engine
                entry_price=entry_price,
                stop_price=stop_price,
                stop_distance_pct=stop_distance / entry_price,
                metadata={
                    "trigger": "golden_cross" if golden_cross else "pullback",
                    "sma50": round(curr["SMA_50"], 2),
                    "sma200": round(curr["SMA_200"], 2),
                    "atr": round(atr, 4),
                },
            )

        return None

    # -- Exit ---------------------------------------------------------------

    def check_exit(self, df: pd.DataFrame, position) -> Optional[ExitSignal]:
        """
        Check for death cross signal exit, trailing stop hit, or max hold.
        """
        if self._entry_price is None:
            return None

        curr = df.iloc[-1]
        self._bars_held += 1

        # 1. Signal exit: death cross (SMA50 < SMA200)
        if not pd.isna(curr["SMA_50"]) and not pd.isna(curr["SMA_200"]):
            if curr["SMA_50"] < curr["SMA_200"]:
                self._reset_position()
                return ExitSignal(
                    strategy_name=self.name,
                    asset=position.asset,
                    reason="SIGNAL_EXIT",
                    metadata={"trigger": "death_cross"},
                )

        # 2. Trailing stop hit
        if self._trailing_stop is not None and curr["Close"] <= self._trailing_stop:
            self._reset_position()
            return ExitSignal(
                strategy_name=self.name,
                asset=position.asset,
                reason="TRAILING_STOP",
            )

        # 3. Max hold (150 bars = 25 days on 4h)
        if self._bars_held >= 150:
            self._reset_position()
            return ExitSignal(
                strategy_name=self.name,
                asset=position.asset,
                reason="MAX_HOLD",
            )

        return None

    # -- Trail --------------------------------------------------------------

    def calculate_trail(self, df: pd.DataFrame, position) -> Optional[float]:
        """
        Adaptive trailing stop: tightens as profit grows.
            0-1.5R:  trail at 3.0x ATR below highest high
            1.5-3R:  trail at 2.5x ATR
            3R+:     trail at 2.0x ATR
        Only ratchets up (never moves down).
        """
        if self._entry_price is None or self._trailing_stop is None:
            return None

        curr = df.iloc[-1]
        atr = curr.get("ATR_14", 0)
        if pd.isna(atr) or atr <= 0:
            return None

        # Track highest high since entry
        if curr["High"] > (self._highest_since_entry or 0):
            self._highest_since_entry = curr["High"]

        # Calculate R-multiples
        initial_risk = self.stop_atr_mult * atr
        profit = curr["Close"] - self._entry_price
        risk_multiples = profit / max(initial_risk, 0.001)

        # Adaptive trail multiplier
        if risk_multiples >= 3.0:
            trail_mult = 2.0
        elif risk_multiples >= 1.5:
            trail_mult = 2.5
        else:
            trail_mult = 3.0

        new_stop = self._highest_since_entry - trail_mult * atr

        # Only ratchet up
        if new_stop > self._trailing_stop:
            self._trailing_stop = new_stop
            return new_stop

        return None

    # -- Internal -----------------------------------------------------------

    def _reset_position(self) -> None:
        """Clear position tracking state."""
        self._entry_price = None
        self._trailing_stop = None
        self._highest_since_entry = None
        self._bars_held = 0
