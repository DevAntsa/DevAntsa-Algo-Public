"""
Signal Engine -- Portfolio v12 (11 strategies, 3 regimes)
=========================================================
Iterates all active strategies x assets and collects entry/exit signals.
Supports eligible_strategies filter for timeframe gating.

Portfolio v12 (upgraded 2026-03-11):
    3 Bull LONG + 3 Sideways LONG + 3 Bear SHORT = 9 strategies
    (ElasticMultiSignal kept temporarily until open trade closes, then removed)

v12 changes:
    - CrossAssetBTCSignal replaces MultiSignalCCI (sideways)
    - EhlersInstantTrend added as bull slot (replaces ElasticMultiSignal after trade closes)
    - VolumeWeightedTSMOM added as 3rd bull slot
"""

from __future__ import annotations
from typing import List, Optional, Set
import logging
import pandas as pd

from DevAntsa_Lab.live_trading.strategies.base import StrategyBase, Signal, ExitSignal
# v12 strategies (3 regimes)
from DevAntsa_Lab.live_trading.strategies_v11 import (
    # Bull (3 + ElasticMultiSignal kept temporarily)
    ElasticMultiSignal,
    DonchianModern,
    EhlersInstantTrend,
    VolumeWeightedTSMOM,
    # Sideways (3)
    CrossAssetBTCSignal,
    DailyCCI,
    EMABounce,
    # Bear (3)
    ExitMicroTune,
    BCDExitTune,
    PanicSweepOpt,
)
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

        # CrossAssetBTCSignal needs data_fetcher to fetch BTC OHLCV
        cross_asset = CrossAssetBTCSignal()
        cross_asset.set_data_fetcher(data_fetcher)

        self.strategies: List[StrategyBase] = [
            # Bull LONG (3 + ElasticMultiSignal kept for open trade management)
            ElasticMultiSignal(),     # SOL-4h (WF 85%, S=1.61, +201.0%) -- PENDING REMOVAL
            DonchianModern(),         # BTC-4h (WF 103%, S=1.35, +58.0%)
            EhlersInstantTrend(),     # SOL-4h (WF 71%, S=1.86, +203.9%) -- NEW v12
            VolumeWeightedTSMOM(),    # SOL-4h (WF 93%, S=1.84, +232.0%) -- NEW v12
            # Sideways LONG (3)
            cross_asset,              # SOL-4h (WF 90.5%, S=1.97, +138.2%) -- NEW v12
            DailyCCI(),               # SOL-D  (S=1.38, +41.3%)
            EMABounce(),              # ETH-4h (WF 168%, S=0.95, +24.8%)
            # Bear SHORT (3)
            ExitMicroTune(),          # ETH-4h (S=1.22, +75.4%)
            BCDExitTune(),            # SOL-4h (quality-stratified exits)
            PanicSweepOpt(),          # BTC-4h (S=1.17, +45.8%)
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
