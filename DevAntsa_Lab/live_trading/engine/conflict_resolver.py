"""
Signal Conflict Resolver
========================
Plan Part 6 - Signal Priority When Multiple Fire:
    Bull + Bear on SAME asset, same bar -> Execute NEITHER
    Bull + Sideways on SAME asset, same bar -> Execute BULL
    Priority: Bull > Bear > Sideways on same asset.
"""

from __future__ import annotations
from typing import List, Set, Tuple

from DevAntsa_Lab.live_trading.strategies.base import Signal
from DevAntsa_Lab.live_trading.config import REGIME_PRIORITY


class ConflictResolver:
    """
    Resolves conflicts when multiple signals fire on the same bar.
    """

    def resolve(
        self,
        signals: List[Signal],
        open_positions: list,
    ) -> List[Signal]:
        """
        Filter and prioritize signals.

        Args:
            signals: Raw signals from SignalEngine.collect_signals()
            open_positions: Currently open Position objects

        Returns:
            List of non-conflicting signals safe to execute.
        """
        # Assets already claimed by open positions
        assets_claimed: Set[Tuple[str, str]] = set()
        for pos in open_positions:
            assets_claimed.add((pos.asset, pos.direction))

        # Detect bull+bear conflicts: same asset with both bull and bear signals
        bull_bear_conflicts: Set[str] = set()
        bull_assets = {s.asset for s in signals if s.regime == "bull"}
        bear_assets = {s.asset for s in signals if s.regime == "bear"}
        bull_bear_conflicts = bull_assets & bear_assets

        # Sort by priority: bull=0, bear=1, sideways=2
        sorted_signals = sorted(signals, key=lambda s: REGIME_PRIORITY.get(s.regime, 99))

        resolved: List[Signal] = []
        for signal in sorted_signals:
            # Skip if asset is in bull+bear conflict set
            if signal.asset in bull_bear_conflicts:
                continue

            asset_key = (signal.asset, signal.direction)

            # Skip if already claimed
            if asset_key not in assets_claimed:
                resolved.append(signal)
                assets_claimed.add(asset_key)

        return resolved
