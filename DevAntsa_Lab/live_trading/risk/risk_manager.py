"""
Risk Manager
============
Plan Part 4: Risk Control Architecture.

Responsibilities:
    - Track daily P&L and drawdown (Plan Part 4 - Daily Risk Limits)
    - Determine adaptive leverage phase (Plan Part 4 - Adaptive Leverage System)
    - Kill switch evaluation (Plan Part 10 - Kill Switch Rules)
    - Per-regime exposure limit enforcement (Plan Part 4 - Regime-Specific Risk Limits)
"""

from __future__ import annotations
from typing import Optional, Tuple, Dict, List
import logging

from DevAntsa_Lab.live_trading.config import (
    LEVERAGE_PHASES,
    DEFAULT_LEVERAGE,
    DD_ACTION_REVIEW,
    DD_ACTION_REDUCE,
    DD_ACTION_STOP_DAY,
    DD_ACTION_CLOSE_ALL,
    DAILY_DD_LIMIT_PERSONAL,
    TOTAL_DD_LIMIT_PERSONAL,
    KILL_SWITCH,
    BACKTEST_MAX_DD,
    ACCOUNT_MODE,
    STRATEGY_LEVERAGE_CAPS,
)

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Central risk controller.

    Plan Part 4: Equity-based leverage phases + daily/total DD limits.
    Plan Part 10: Kill switch conditions.
    """

    def __init__(self, account_mode: str = "prop") -> None:
        """
        Args:
            account_mode: "prop" | "funded" | "personal"
                          Determines which leverage caps and DD limits apply.
        """
        self.account_mode = account_mode
        self.starting_equity: Optional[float] = None
        self.session_start_equity: Optional[float] = None  # for daily DD tracking
        self.consecutive_losing_days: int = 0
        self.last_session_date: Optional[str] = None  # ISO date string "YYYY-MM-DD"

        # Kill switch tracking (T2-2 and T2-3)
        self.trade_returns: List[float] = []  # P&L as % of position size for Sharpe calc
        self.strategy_peak_equity: Dict[str, float] = {}  # peak cumulative P&L per strategy
        self.strategy_current_equity: Dict[str, float] = {}  # current cumulative P&L per strategy

    # ── Adaptive Leverage (Plan Part 4) ─────────────────────────────────

    def determine_phase(self, current_equity: float) -> str:
        """
        Plan Part 4 - Adaptive Leverage System:
            Phase 1: BUILDING     (100-105% equity)
            Phase 2: ACCELERATING (105-110% equity)
            Phase 3: PROTECTING   (>110% equity)
            Phase 4: RECOVERY     (95-100% equity)
            Phase 5: SURVIVAL     (<95% equity)
        """
        if self.starting_equity is None or self.starting_equity <= 0:
            return "BUILDING"

        ratio = current_equity / self.starting_equity

        if ratio < 0.95:
            return "SURVIVAL"
        elif ratio < 1.00:
            return "RECOVERY"
        elif ratio < 1.05:
            return "BUILDING"
        elif ratio < 1.10:
            return "ACCELERATING"
        else:
            return "PROTECTING"

    def get_leverage_for_phase(self, phase: str) -> float:
        """
        Return target leverage for the current phase.
        Plan Part 4 - Adaptive Leverage System table.
        """
        phase_map = {
            "SURVIVAL":     1.0,
            "RECOVERY":     1.5,
            "BUILDING":     2.0,
            "ACCELERATING": 2.5,
            "PROTECTING":   1.5,
        }
        return phase_map.get(phase, DEFAULT_LEVERAGE)

    def get_risk_per_trade_for_phase(self, phase: str) -> float:
        """
        Return risk-per-trade for the current phase.
        Plan Part 4 - Adaptive Leverage System table.
        """
        phase_map = {
            "SURVIVAL":     0.0025,
            "RECOVERY":     0.004,
            "BUILDING":     0.005,
            "ACCELERATING": 0.0065,
            "PROTECTING":   0.004,
        }
        return phase_map.get(phase, 0.005)

    def get_strategy_leverage_cap(self, strategy_name: str) -> Optional[float]:
        """
        Plan Part 5: Per-strategy leverage caps by account mode.
        Returns None if strategy is not safe for this account mode.
        """
        caps = STRATEGY_LEVERAGE_CAPS.get(strategy_name)
        if caps is None:
            return DEFAULT_LEVERAGE
        return caps.get(self.account_mode)

    # ── Daily DD Tracking (Plan Part 4) ─────────────────────────────────

    def set_session_start(self, equity: float) -> None:
        """Call at start of each trading day (UTC midnight boundary)."""
        self.session_start_equity = equity
        if self.starting_equity is None:
            self.starting_equity = equity

    def check_daily_reset(self, current_equity: float) -> None:
        """
        Detect UTC date change and reset daily session.

        Called every tick. On the first tick of a new UTC day:
        1. Evaluate whether the previous day was a losing day
        2. Update consecutive_losing_days counter
        3. Reset session_start_equity for the new day

        "Losing day" definition: session ended with equity below session start.
        """
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if self.last_session_date is None:
            # First ever tick — initialise
            self.last_session_date = today
            self.set_session_start(current_equity)
            return

        if today == self.last_session_date:
            return  # Same day, nothing to do

        # === New UTC day detected ===
        # Evaluate the day that just ended
        if self.session_start_equity is not None and self.session_start_equity > 0:
            if current_equity < self.session_start_equity:
                self.consecutive_losing_days += 1
                logger.warning(
                    "LOSING DAY #%d: started=$%.2f ended=$%.2f (%.2f%%)",
                    self.consecutive_losing_days,
                    self.session_start_equity,
                    current_equity,
                    ((current_equity - self.session_start_equity) / self.session_start_equity) * 100,
                )
            else:
                if self.consecutive_losing_days > 0:
                    logger.info(
                        "Winning day — resetting consecutive losing days (was %d)",
                        self.consecutive_losing_days,
                    )
                self.consecutive_losing_days = 0

        # Reset for the new day
        self.last_session_date = today
        self.set_session_start(current_equity)
        logger.info("Daily session reset: date=%s equity=$%.2f", today, current_equity)

    def get_daily_dd(self, current_equity: float) -> float:
        """Return daily drawdown as positive decimal (e.g. 0.02 = -2%)."""
        if self.session_start_equity is None or self.session_start_equity <= 0:
            return 0.0
        dd = (self.session_start_equity - current_equity) / self.session_start_equity
        return max(dd, 0.0)

    def get_total_dd(self, current_equity: float) -> float:
        """Return total drawdown from starting equity."""
        if self.starting_equity is None or self.starting_equity <= 0:
            return 0.0
        dd = (self.starting_equity - current_equity) / self.starting_equity
        return max(dd, 0.0)

    # ── Halt / Kill Switch (Plan Parts 4 & 10) ─────────────────────────

    def should_halt_trading(self, current_equity: float) -> bool:
        """
        Plan Part 4 - Daily Risk Limits:
            Action at -3%: STOP trading for the day
        Plan Part 10 - Kill Switch:
            daily_dd_pct: 0.03
            total_dd_pct: 0.07
        """
        daily_dd = self.get_daily_dd(current_equity)
        total_dd = self.get_total_dd(current_equity)

        if daily_dd >= DAILY_DD_LIMIT_PERSONAL:
            logger.critical(
                "HALT: Daily DD %.2f%% exceeds limit %.2f%%",
                daily_dd * 100, DAILY_DD_LIMIT_PERSONAL * 100,
            )
            return True

        if total_dd >= TOTAL_DD_LIMIT_PERSONAL:
            logger.critical(
                "HALT: Total DD %.2f%% exceeds limit %.2f%%",
                total_dd * 100, TOTAL_DD_LIMIT_PERSONAL * 100,
            )
            return True

        return False

    def get_dd_action(self, current_equity: float) -> str:
        """
        Plan Part 4 - Action at drawdown thresholds:
            -1.5% → REVIEW
            -2.0% → REDUCE
            -3.0% → STOP_DAY
            -4.0% → CLOSE_ALL
        """
        daily_dd = self.get_daily_dd(current_equity)

        if daily_dd >= DD_ACTION_CLOSE_ALL:
            return "CLOSE_ALL"
        elif daily_dd >= DD_ACTION_STOP_DAY:
            return "STOP_DAY"
        elif daily_dd >= DD_ACTION_REDUCE:
            return "REDUCE"
        elif daily_dd >= DD_ACTION_REVIEW:
            return "REVIEW"
        else:
            return "NORMAL"

    # ── Trade Tracking for Kill Switch (T2-2, T2-3) ─────────────────────

    def record_trade(self, strategy_name: str, pnl_pct: float) -> None:
        """
        Record a completed trade's return for Sharpe calculation.

        Args:
            strategy_name: Name of the strategy that completed the trade
            pnl_pct: P&L as a decimal (e.g., 0.02 = +2% return on position)
        """
        self.trade_returns.append(pnl_pct)
        logger.debug(
            "Recorded trade: %s return=%.2f%% (total trades: %d)",
            strategy_name, pnl_pct * 100, len(self.trade_returns)
        )

    def update_strategy_equity(self, strategy_name: str, pnl: float) -> None:
        """
        Update running equity and peak for a strategy (for per-strategy DD tracking).

        Args:
            strategy_name: Name of the strategy
            pnl: Dollar P&L of the trade (positive or negative)
        """
        current = self.strategy_current_equity.get(strategy_name, 0.0)
        current += pnl
        self.strategy_current_equity[strategy_name] = current

        peak = self.strategy_peak_equity.get(strategy_name, 0.0)
        if current > peak:
            self.strategy_peak_equity[strategy_name] = current
            logger.debug("New peak for %s: $%.2f", strategy_name, current)

    def get_rolling_sharpe(self) -> Optional[float]:
        """
        Calculate Sharpe ratio from trade returns.

        Returns None if fewer than min_trades_for_sharpe trades completed.
        Uses trade-by-trade returns (not time-based).

        Sharpe = mean(returns) / std(returns)
        """
        min_trades = KILL_SWITCH["min_trades_for_sharpe"]
        if len(self.trade_returns) < min_trades:
            return None

        # Use last N trades for rolling calculation
        returns = self.trade_returns[-min_trades:]
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_return = variance ** 0.5

        if std_return == 0:
            return float('inf') if mean_return > 0 else 0.0

        return mean_return / std_return

    def get_strategy_live_dd(self, strategy_name: str) -> float:
        """
        Return current drawdown from peak for a strategy, as % of account equity.

        DD = (peak_pnl - current_pnl) / starting_equity

        This makes the value directly comparable to BACKTEST_MAX_DD percentages.
        Works even if strategy has never been profitable (peak stays at 0,
        current goes negative → DD = abs(current) / starting_equity).
        """
        peak = self.strategy_peak_equity.get(strategy_name, 0.0)
        current = self.strategy_current_equity.get(strategy_name, 0.0)
        if self.starting_equity is None or self.starting_equity <= 0:
            return 0.0
        dd = (peak - current) / self.starting_equity
        return max(dd, 0.0)

    def evaluate_kill_switch(self, current_equity: float) -> Tuple[bool, Optional[str]]:
        """
        Plan Part 10 - Kill Switch Rules (permanent halt, requires manual restart):
            1. Total DD hits -7% (prop firm total limit)
            2. (DISABLED v10) Consecutive losing days — 4h strategies show 10+ day streaks normally
            3. Strategy live Sharpe < 0.5 after 20 trades
            4. Live DD > backtest DD * 1.5 (per strategy)

        NOTE: Daily DD is NOT a kill switch. Daily DD is handled by dd_action
        levels in main_loop (STOP_DAY at -3%, CLOSE_ALL at -4%). The kill switch
        is reserved for conditions that require permanent halt + manual review.

        Returns:
            (should_kill, reason) tuple. reason is None if should_kill is False.
        """
        # Condition 1: Total DD >= 7% (prop firm total limit)
        total_dd = self.get_total_dd(current_equity)
        if total_dd >= TOTAL_DD_LIMIT_PERSONAL:
            logger.critical(
                "KILL SWITCH: Total DD %.2f%% exceeds limit %.2f%%",
                total_dd * 100, TOTAL_DD_LIMIT_PERSONAL * 100,
            )
            return True, f"TOTAL_DD_{total_dd*100:.1f}%"

        # Condition 2: Consecutive losing days — DISABLED (v10)
        # 4h strategies can naturally show 10+ consecutive losing days.
        # Keeping the counter for monitoring, but not triggering kill switch.
        # if self.consecutive_losing_days >= KILL_SWITCH["max_consecutive_losing_days"]:
        #     logger.critical(...)
        #     return True, f"LOSING_DAYS_{self.consecutive_losing_days}"

        # Condition 3: Sharpe < 0.5 after 20 trades (T2-2)
        sharpe = self.get_rolling_sharpe()
        if sharpe is not None and sharpe < KILL_SWITCH["min_sharpe_after_n_trades"]:
            logger.critical(
                "KILL SWITCH: Rolling Sharpe %.2f < %.2f after %d trades",
                sharpe, KILL_SWITCH["min_sharpe_after_n_trades"], len(self.trade_returns)
            )
            return True, f"LOW_SHARPE_{sharpe:.2f}"

        # Condition 4: Live DD > backtest DD * 1.5 (T2-3)
        ratio = KILL_SWITCH["max_dd_vs_backtest_ratio"]
        for strategy_name, backtest_dd in BACKTEST_MAX_DD.items():
            live_dd = self.get_strategy_live_dd(strategy_name)
            threshold = backtest_dd * ratio
            if live_dd > threshold:
                logger.critical(
                    "KILL SWITCH: %s live DD %.1f%% > backtest DD %.1f%% * %.1f = %.1f%%",
                    strategy_name, live_dd * 100, backtest_dd * 100, ratio, threshold * 100
                )
                return True, f"STRATEGY_DD_{strategy_name}_{live_dd*100:.1f}%"

        return False, None
