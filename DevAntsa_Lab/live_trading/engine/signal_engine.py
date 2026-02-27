"""
Signal Engine -- Trading Framework
====================================
Iterates all active strategies x assets and collects entry/exit signals.
Supports eligible_strategies filter for timeframe gating (Decision 1).

Replace the example strategy with your own strategies.
"""

from __future__ import annotations
from typing import List, Optional, Set
import logging
import pandas as pd

from DevAntsa_Lab.live_trading.strategies.base import StrategyBase, Signal, ExitSignal
# Replace with your own strategy imports
from DevAntsa_Lab.live_trading.strategies.example_sma_crossover import ExampleSMACrossover
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

        # Replace with your own strategy instances
        self.strategies: List[StrategyBase] = [
            ExampleSMACrossover(),       # SOL-4h  (textbook SMA crossover, zero alpha)
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
                except Exception as exc:
                    logger.warning("Data fetch failed for %s %s (%s) — skipping", strategy.name, asset, exc)
                    continue
                if df is None or len(df) == 0:
                    continue

                strategy.compute_indicators(df)
                signal = strategy.check_entry(df)
                if signal is not None:
                    signal.asset = asset
                    pending.append(signal)

        return pending

    def check_exits(
        self,
        open_positions: list,
        eligible_strategies: Optional[Set[str]] = None,
    ) -> List[ExitSignal]:
        """
        For each open position (whose strategy is eligible), check exit conditions.
        Also updates trailing stops in-place on positions.
        """
        exit_signals: List[ExitSignal] = []

        for position in open_positions:
            if eligible_strategies is not None and position.strategy_name not in eligible_strategies:
                continue

            strategy = self._get_strategy(position.strategy_name)
            if strategy is None:
                continue

            try:
                df = self.data_fetcher.get_ohlcv(position.asset, strategy.timeframe, limit=strategy.min_bars)
            except Exception as exc:
                logger.warning("Data fetch failed for exit check %s %s (%s) — skipping", position.strategy_name, position.asset, exc)
                continue
            if df is None or len(df) == 0:
                continue

            strategy.compute_indicators(df)

            # Trailing stop update (before exit check)
            if strategy.has_trailing_stop:
                new_stop = strategy.calculate_trail(df, position)
                if new_stop is not None:
                    position.current_stop = new_stop

            # Exit check
            exit_sig = strategy.check_exit(df, position)
            if exit_sig is not None:
                exit_signals.append(exit_sig)

        return exit_signals

    def _get_strategy(self, name: str) -> Optional[StrategyBase]:
        for s in self.strategies:
            if s.name == name:
                return s
        return None
