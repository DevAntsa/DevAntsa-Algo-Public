"""
Position Manager
================
Tracks open positions, regime counts, allocation limits, and bars held.

Plan Part 3: Number of Concurrent Strategies
    Max positions: 6 (2 bull + 2 bear + 2 sideways)

Updated for Stage 0:
    - remaining_qty field for bear partial closes (Decision 4)
    - Timeframe-aware bars_held increment (Decision 1)
    - Serialization for test harness logging
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime

from DevAntsa_Lab.live_trading.config import MAX_POSITIONS_PER_REGIME, MAX_TOTAL_POSITIONS


@dataclass
class Position:
    """Internal representation of an open position."""
    asset: str                      # e.g. "SOLUSDT"
    direction: str                  # "LONG" | "SHORT"
    strategy_name: str              # e.g. "CascadeHighMomentum"
    regime: str                     # "bull" | "bear" | "sideways"
    entry_price: float = 0.0
    current_stop: float = 0.0
    quantity: float = 0.0
    remaining_qty: float = 0.0     # for partial closes; defaults to quantity
    bars_held: int = 0
    entry_time: Optional[datetime] = None
    order_id: Optional[str] = None  # Exchange order ID
    tp1_price: Optional[float] = None  # Bear strategy TP1
    tp2_price: Optional[float] = None  # Bear strategy TP2
    tp1_hit: bool = False
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.remaining_qty == 0.0 and self.quantity > 0:
            self.remaining_qty = self.quantity

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "direction": self.direction,
            "strategy_name": self.strategy_name,
            "regime": self.regime,
            "entry_price": self.entry_price,
            "current_stop": self.current_stop,
            "quantity": self.quantity,
            "remaining_qty": self.remaining_qty,
            "bars_held": self.bars_held,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "tp1_price": self.tp1_price,
            "tp2_price": self.tp2_price,
            "tp1_hit": self.tp1_hit,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Position:
        entry_time = None
        if d.get("entry_time"):
            entry_time = datetime.fromisoformat(d["entry_time"])
        return cls(
            asset=d["asset"],
            direction=d["direction"],
            strategy_name=d["strategy_name"],
            regime=d["regime"],
            entry_price=d.get("entry_price", 0.0),
            current_stop=d.get("current_stop", 0.0),
            quantity=d.get("quantity", 0.0),
            remaining_qty=d.get("remaining_qty", 0.0),
            bars_held=d.get("bars_held", 0),
            entry_time=entry_time,
            tp1_price=d.get("tp1_price"),
            tp2_price=d.get("tp2_price"),
            tp1_hit=d.get("tp1_hit", False),
            metadata=d.get("metadata", {}),
        )


class PositionManager:
    """
    Manages internal position tracking and regime allocation enforcement.
    """

    def __init__(self) -> None:
        self.positions: List[Position] = []

    # -- Regime limit checks ------------------------------------------------

    def within_regime_limits(self, regime: str) -> bool:
        count = sum(1 for p in self.positions if p.regime == regime)
        limit = MAX_POSITIONS_PER_REGIME.get(regime, 0)
        return count < limit

    def within_total_limit(self) -> bool:
        return len(self.positions) < MAX_TOTAL_POSITIONS

    # -- Overlap checks -----------------------------------------------------

    def has_position_on_asset(self, asset: str, direction: str) -> bool:
        return any(
            p.asset == asset and p.direction == direction
            for p in self.positions
        )

    def has_position_for_strategy(self, strategy_name: str) -> bool:
        """Check if a position already exists for this strategy."""
        return any(p.strategy_name == strategy_name for p in self.positions)

    def has_opposite_direction_on_asset(self, asset: str, direction: str) -> bool:
        """
        Check if any strategy has an open position on this asset in the
        OPPOSITE direction. Prevents desync with Binance one-way position mode
        where a BUY would close/reduce an existing SHORT (and vice versa).
        """
        opposite = "SHORT" if direction == "LONG" else "LONG"
        return any(p.asset == asset and p.direction == opposite for p in self.positions)

    # -- CRUD ---------------------------------------------------------------

    def add_position(self, position: Position) -> None:
        self.positions.append(position)

    def remove_position(self, asset: str, strategy_name: str) -> Optional[Position]:
        """Remove and return a position by asset + strategy_name."""
        for i, p in enumerate(self.positions):
            if p.asset == asset and p.strategy_name == strategy_name:
                return self.positions.pop(i)
        return None

    def remove_position_by_direction(self, asset: str, direction: str) -> Optional[Position]:
        """Remove and return a position by asset+direction (legacy compat)."""
        for i, p in enumerate(self.positions):
            if p.asset == asset and p.direction == direction:
                return self.positions.pop(i)
        return None

    def get_position(self, asset: str, direction: str) -> Optional[Position]:
        for p in self.positions:
            if p.asset == asset and p.direction == direction:
                return p
        return None

    def get_position_for_strategy(self, strategy_name: str) -> Optional[Position]:
        """Get position by strategy name (each strategy has at most 1 position)."""
        for p in self.positions:
            if p.strategy_name == strategy_name:
                return p
        return None

    def get_positions_by_regime(self, regime: str) -> List[Position]:
        return [p for p in self.positions if p.regime == regime]

    def regime_counts(self) -> Dict[str, int]:
        counts = {"bull": 0, "bear": 0, "sideways": 0}
        for p in self.positions:
            counts[p.regime] = counts.get(p.regime, 0) + 1
        return counts

    # -- Timeframe-aware bars_held (Decision 1) ----------------------------

    def increment_bars_held(self, eligible_strategies: Optional[Set[str]] = None) -> None:
        """
        Increment bars_held only for positions whose strategy is in the eligible set.
        If eligible_strategies is None, increment all (legacy behavior).
        """
        for p in self.positions:
            if eligible_strategies is None or p.strategy_name in eligible_strategies:
                p.bars_held += 1

    def update_stop(self, asset: str, direction: str, new_stop: float) -> None:
        pos = self.get_position(asset, direction)
        if pos is not None:
            pos.current_stop = new_stop

    # -- Serialization ------------------------------------------------------

    def to_dict_list(self) -> List[dict]:
        return [p.to_dict() for p in self.positions]

    def from_dict_list(self, data: List[dict]) -> None:
        self.positions = [Position.from_dict(d) for d in data]
