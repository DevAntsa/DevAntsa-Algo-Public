"""
Regime Gate — Portfolio v10
===========================
Lightweight BTC EMA slope gate that blocks LONG entries from loose strategies
when the market is clearly bearish.

BEARISH requires BOTH conditions (loosened to avoid blocking during V-reversals):
    1. EMA-50 slope over 5 bars < -0.5%  (trend is declining)
    2. Current close < EMA-50             (price hasn't reclaimed yet)

If price reclaims above EMA while slope is still negative, gate lifts to NEUTRAL
so LONG strategies can catch the reversal.

Portfolio v10: All 15 strategies are self-gating (Close > SMA200 for bull,
Close < SMA200 for bear). The regime gate provides an additional safety layer
for bull LONGs during sharp bear turns where SMA200 hasn't caught up yet.
"""

from __future__ import annotations
from typing import List
import logging

logger = logging.getLogger(__name__)

# Strategies whose LONG entries get blocked in BEARISH regime
GATED_STRATEGIES = {"DualROCAlignment", "VolSpikeBreakout"}

# EMA parameters
EMA_PERIOD = 50        # ~8.3 days on 4H
SLOPE_BARS = 5         # slope measured over 5 bars (20 hours)
BEARISH_THRESHOLD = -0.005   # -0.5% slope -> bearish


class RegimeGate:
    """
    Checks BTC 4H EMA-50 slope to classify market as BULLISH / BEARISH / NEUTRAL.
    Blocks gated LONG strategies when BEARISH.
    """

    def __init__(self, data_fetcher) -> None:
        self.data_fetcher = data_fetcher

    def classify(self) -> str:
        """
        Fetch BTC 4H, compute EMA-50 slope over last SLOPE_BARS bars.

        BEARISH requires BOTH:
            - slope < -0.5%
            - price < EMA-50  (price hasn't reclaimed)

        Returns:
            'BULLISH'  -- slope > +0.5%
            'BEARISH'  -- slope < -0.5% AND price below EMA
            'NEUTRAL'  -- in between, or slope bearish but price reclaimed EMA
        """
        try:
            df = self.data_fetcher.get_ohlcv("BTCUSDT", "240")
        except Exception as exc:
            logger.warning("Regime gate data fetch failed (%s) -- defaulting to NEUTRAL", exc)
            return "NEUTRAL"
        if df is None or len(df) < EMA_PERIOD + SLOPE_BARS:
            return "NEUTRAL"

        ema = df["Close"].ewm(span=EMA_PERIOD, adjust=False).mean()
        current_ema = ema.iloc[-1]
        prior_ema = ema.iloc[-1 - SLOPE_BARS]
        close_price = df["Close"].iloc[-1]

        if prior_ema <= 0:
            return "NEUTRAL"

        slope = (current_ema - prior_ema) / prior_ema

        if slope < BEARISH_THRESHOLD and close_price < current_ema:
            return "BEARISH"
        elif slope > abs(BEARISH_THRESHOLD):
            return "BULLISH"
        return "NEUTRAL"

    def filter_signals(self, signals: List, regime: str) -> List:
        """
        Remove gated LONG signals when regime is BEARISH.
        All other signals pass through unchanged.
        """
        if regime != "BEARISH":
            return signals

        filtered = []
        for sig in signals:
            if sig.strategy_name in GATED_STRATEGIES:
                logger.info(
                    "REGIME GATE: blocking %s %s %s -- market BEARISH (EMA50 slope < %.1f%%)",
                    sig.strategy_name, sig.direction, sig.asset,
                    BEARISH_THRESHOLD * 100,
                )
                continue
            filtered.append(sig)
        return filtered
