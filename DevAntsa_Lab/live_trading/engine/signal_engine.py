"""
Signal Engine -- Portfolio v11 (8 strategies, 3 regimes)
========================================================
Iterates all active strategies x assets and collects entry/exit signals.
Supports eligible_strategies filter for timeframe gating.

This is the public framework version. Import your own strategies below.
See strategies/example_sma_crossover.py for a working template.
"""

from __future__ import annotations
from typing import List, Optional, Set
import logging
import pandas as pd

from DevAntsa_Lab.live_trading.strategies.base import StrategyBase, Signal, ExitSignal
# Import your strategies here:
from DevAntsa_Lab.live_trading.strategies.example_sma_crossover import SmaCrossoverStrategy
from DevAntsa_Lab.live_trading.config import STRATEGY_ASSETS

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Iterates all active strategies x assets and collects entry signals.
    """

    def __init__(self, data_fetcher) -> None:
        """
        Args:
            data_fetcher: Object with .get_ohlcv(symbol, interval, limit) -> pd.DataFrame
        """
        self.data_fetcher = data_fetcher

        # Register your strategies here:
        self.strategies: List[StrategyBase] = [
            SmaCrossoverStrategy(),    # Example -- replace with your own
        ]

    def collect_signals(
        self,
        eligible_strategies: Optional[Set[str]] = None,
    ) -> List[Signal]:
        """
        Scan strategies x assets for entry signals.
        Only evaluates strategies in eligible_strategies (if provided).
        Returns list of Signal objects (unresolved -- may contain conflicts).
        """
        pending: List[Signal] = []

        for strategy in self.strategies:
            if eligible_strategies is not None and strategy.name not in eligible_strategies:
                continue

            for asset in strategy.assets:
                try:
                    df = self.data_fetcher.get_ohlcv(asset, strategy.timeframe, limit=strategy.min_bars)
                    if df is None or len(df) < strategy.min_bars:
                        logger.debug("Insufficient data for %s on %s", strategy.name, asset)
                        continue

                    df = strategy.compute_indicators(df)
                    signal = strategy.check_entry(df)
                    if signal is not None:
                        signal.asset = asset
                        pending.append(signal)

                except Exception as e:
                    logger.error("Signal check failed for %s on %s: %s", strategy.name, asset, e)

        return pending

    def check_exits(
        self,
        open_positions: list,
        eligible_strategies: Optional[Set[str]] = None,
    ) -> List[ExitSignal]:
        """
        Check all open positions for exit signals (full close, partial close, trail update).
        """
        exit_signals: List[ExitSignal] = []

        strategy_map = {s.name: s for s in self.strategies}

        for position in open_positions:
            strategy = strategy_map.get(position.strategy_name)
            if strategy is None:
                continue
            if eligible_strategies is not None and strategy.name not in eligible_strategies:
                continue

            try:
                df = self.data_fetcher.get_ohlcv(position.asset, strategy.timeframe, limit=strategy.min_bars)
                if df is None or len(df) < strategy.min_bars:
                    continue

                df = strategy.compute_indicators(df)

                # Check for exit signal
                exit_sig = strategy.check_exit(df, position)
                if exit_sig is not None:
                    exit_signals.append(exit_sig)
                    continue  # Don't trail if exiting

                # Update trailing stop
                new_stop = strategy.calculate_trail(df, position)
                if new_stop is not None and new_stop > 0:
                    if position.direction == "LONG" and new_stop > position.current_stop:
                        position.current_stop = new_stop
                    elif position.direction == "SHORT" and (position.current_stop == 0 or new_stop < position.current_stop):
                        position.current_stop = new_stop

            except Exception as e:
                logger.error("Exit check failed for %s on %s: %s", position.strategy_name, position.asset, e)

        return exit_signals
