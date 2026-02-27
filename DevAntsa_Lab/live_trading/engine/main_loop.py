"""
Main Trading Loop
=================
Plan Part 7: Execution Architecture - main_trading_loop()

This is the top-level orchestrator that ties together:
    1. Account status check -> adaptive leverage phase
    2. Current positions -> from PositionManager
    3. Signal collection -> SignalEngine
    4. Conflict resolution -> ConflictResolver
    5. Position sizing -> RiskManager
    6. Trade execution -> BinanceExecutor
    7. Open position management -> trailing stops, targets, max hold
    8. Sleep until next bar

Bootstrap Plan: Stages 1-3 run on Binance Futures Demo.  Stage 4+ switches to live.

Stage 0 update: Added timeframe gating (Decision 1) so 4h strategies are
only evaluated on 4h boundary ticks, while 1h strategies are evaluated every tick.

Stage 1 update: Full execution wiring with state persistence, reconciliation,
and proper entry/exit order flow.
"""

from __future__ import annotations
import time
import logging
import csv
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from DevAntsa_Lab.live_trading.engine.signal_engine import SignalEngine
from DevAntsa_Lab.live_trading.engine.conflict_resolver import ConflictResolver
from DevAntsa_Lab.live_trading.engine.regime_gate import RegimeGate
from DevAntsa_Lab.live_trading.engine.position_manager import PositionManager, Position
from DevAntsa_Lab.live_trading.risk.position_sizing import calculate_position_size, position_size_to_quantity
from DevAntsa_Lab.live_trading.risk.risk_manager import RiskManager
from DevAntsa_Lab.live_trading.execution.binance_executor import BinanceExecutor
from DevAntsa_Lab.live_trading.strategies.base import ExitSignal
from DevAntsa_Lab.live_trading.data.state_manager import (
    save_state, load_state,
    serialize_candle_times, deserialize_candle_times,
)
from DevAntsa_Lab.live_trading.config import (
    RISK_PER_TRADE,
    ACCOUNT_MODE,
    STRATEGY_TIMEFRAMES,
    STRATEGY_RISK_OVERRIDES,
    STRATEGY_ASSETS,
    BEAR_PHASE_RISK_MULTIPLIER,
    BINANCE_MARGIN_TYPE,
    TRADE_LOG_FILE,
)
from DevAntsa_Lab.live_trading.notifications.telegram_notifier import (
    notify_entry, notify_exit, notify_partial_exit, notify_emergency,
    notify_kill_switch, poll_commands, check_regime_change, check_daily_summary,
)
from DevAntsa_Lab.live_trading.utils.console import (
    console, print_banner, print_status_table, log_entry, log_exit,
    log_partial_exit, log_stop_placed, log_stop_updated, log_signal_skip,
    log_regime_change, log_tick_start, log_sleep, log_emergency,
    log_kill_switch, log_info, log_warning, log_error, setup_rich_logging,
)

logger = logging.getLogger(__name__)

# Map interval strings to seconds
INTERVAL_SECONDS = {
    "1": 60,
    "3": 180,
    "5": 300,
    "15": 900,
    "30": 1800,
    "60": 3600,
    "120": 7200,
    "240": 14400,
    "360": 21600,
    "720": 43200,
    "D": 86400,
}


def get_eligible_strategies(now: datetime, last_candle_times: Dict[str, datetime]) -> Set[str]:
    """
    Determine which strategies have a NEW closed candle at time `now`.

    A strategy is eligible if the current time is on or past the next
    candle boundary for that strategy's timeframe, and we haven't already
    evaluated that boundary.

    Args:
        now: Current UTC time.
        last_candle_times: Dict mapping strategy_name -> last evaluated candle close time.

    Returns:
        Set of eligible strategy names.
    """
    eligible = set()
    for strategy_name, interval_str in STRATEGY_TIMEFRAMES.items():
        interval_sec = INTERVAL_SECONDS.get(interval_str, 3600)
        # Compute the most recent candle close time aligned to the interval
        epoch = int(now.timestamp())
        current_boundary = (epoch // interval_sec) * interval_sec
        boundary_dt = datetime.fromtimestamp(current_boundary, tz=timezone.utc)

        last_eval = last_candle_times.get(strategy_name)
        if last_eval is None or boundary_dt > last_eval:
            eligible.add(strategy_name)
            last_candle_times[strategy_name] = boundary_dt

    return eligible


def _log_trade(
    action: str,
    strategy_name: str,
    asset: str,
    direction: str,
    qty: float,
    price: float,
    reason: str = "",
    order_id: str = "",
) -> None:
    """Append a trade record to the CSV trade log."""
    os.makedirs(os.path.dirname(TRADE_LOG_FILE), exist_ok=True)
    file_exists = os.path.exists(TRADE_LOG_FILE)
    with open(TRADE_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "action", "strategy", "asset", "direction",
                "qty", "price", "reason", "order_id",
            ])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            action, strategy_name, asset, direction,
            qty, price, reason, order_id,
        ])


class TradingLoop:
    """
    Plan Part 7 pseudo-code implemented as a class.

    Lifecycle:
        loop = TradingLoop()
        loop.run()   # blocks forever, sleeping between bars
    """

    def __init__(self) -> None:
        self.executor = BinanceExecutor()
        self.signal_engine = SignalEngine(data_fetcher=self.executor)
        self.conflict_resolver = ConflictResolver()
        self.regime_gate = RegimeGate(data_fetcher=self.executor)
        self.position_manager = PositionManager()
        self.risk_manager = RiskManager(account_mode=ACCOUNT_MODE)
        self.last_candle_times: Dict[str, datetime] = {}
        self._last_equity: Optional[float] = None
        self._last_regime: Optional[str] = None
        self._killed: bool = False  # Set True by kill switch to halt the loop
        self._tick_count: int = 0  # Tick counter for console logging
        self._restore_state()
        self._setup_exchange()

    def _restore_state(self) -> None:
        """Load persisted state from disk on startup."""
        state = load_state()
        if state is None:
            return

        # Restore positions
        positions_data = state.get("positions", [])
        if positions_data:
            self.position_manager.from_dict_list(positions_data)
            log_info(f"Restored {len(positions_data)} positions from state")

        # Restore risk manager scalars
        risk = state.get("risk", {})
        if risk.get("starting_equity") is not None:
            self.risk_manager.starting_equity = risk["starting_equity"]
        if risk.get("session_start_equity") is not None:
            self.risk_manager.session_start_equity = risk["session_start_equity"]
        if risk.get("consecutive_losing_days") is not None:
            self.risk_manager.consecutive_losing_days = risk["consecutive_losing_days"]
        if risk.get("last_session_date") is not None:
            self.risk_manager.last_session_date = risk["last_session_date"]

        # Restore kill switch tracking (T2-2, T2-3)
        if risk.get("trade_returns") is not None:
            self.risk_manager.trade_returns = risk["trade_returns"]
            log_info(f"Restored {len(self.risk_manager.trade_returns)} trade returns from state")
        if risk.get("strategy_peak_equity") is not None:
            self.risk_manager.strategy_peak_equity = risk["strategy_peak_equity"]
        if risk.get("strategy_current_equity") is not None:
            self.risk_manager.strategy_current_equity = risk["strategy_current_equity"]

        # Restore last candle times
        candle_data = state.get("last_candle_times", {})
        if candle_data:
            self.last_candle_times = deserialize_candle_times(candle_data)

    def _save_state(self) -> None:
        """Persist current state to disk."""
        risk_state = {
            "starting_equity": self.risk_manager.starting_equity,
            "session_start_equity": self.risk_manager.session_start_equity,
            "consecutive_losing_days": self.risk_manager.consecutive_losing_days,
            "last_session_date": self.risk_manager.last_session_date,
            # Kill switch tracking (T2-2, T2-3)
            "trade_returns": self.risk_manager.trade_returns,
            "strategy_peak_equity": self.risk_manager.strategy_peak_equity,
            "strategy_current_equity": self.risk_manager.strategy_current_equity,
        }
        save_state(
            positions_data=self.position_manager.to_dict_list(),
            risk_state=risk_state,
            last_candle_times=serialize_candle_times(self.last_candle_times),
        )

    def _reconcile_positions(self) -> None:
        """
        Compare internal position tracking with actual exchange positions.

        Detects two failure modes:
          - Ghost positions: tracked internally but not on exchange
            (exchange stop fired mid-candle, or close order filled late)
          - Orphan positions: on exchange but not tracked internally
            (entry filled but tracking failed, or manual intervention)

        Called at the start of every tick, before exit/entry management.
        """
        internal = self.position_manager.positions
        if not internal and not self.position_manager.positions:
            # Quick path: nothing tracked, check exchange for orphans
            try:
                exchange_positions = self.executor.get_positions()
            except Exception as e:
                logger.warning("Reconciliation: cannot fetch exchange positions: %s", e)
                return
            if exchange_positions:
                for ep in exchange_positions:
                    sym = ep.get("symbol", "?")
                    amt = ep.get("positionAmt", "0")
                    log_warning(f"Reconciliation: ORPHAN position on exchange: {sym} amt={amt}")
                    try:
                        self.executor.close_position(sym)
                        log_warning(f"Reconciliation: closed orphan {sym}")
                        notify_emergency(None)
                    except Exception as e2:
                        log_error(f"Reconciliation: failed to close orphan {sym}: {e2}")
            return

        # Fetch exchange state
        try:
            exchange_positions = self.executor.get_positions()
        except Exception as e:
            logger.warning("Reconciliation: cannot fetch exchange positions: %s", e)
            return

        # Build exchange map: symbol -> {positionAmt, entryPrice, ...}
        exchange_map = {}
        for ep in exchange_positions:
            sym = ep.get("symbol", "")
            amt = float(ep.get("positionAmt", 0))
            if amt != 0:
                exchange_map[sym] = ep

        # Check for ghost positions (tracked internally, not on exchange)
        ghosts = []
        for position in list(internal):
            exchange_pos = exchange_map.get(position.asset)
            if exchange_pos is None:
                # Position not on exchange at all
                ghosts.append(position)
            else:
                # Position exists but check direction matches
                ex_amt = float(exchange_pos.get("positionAmt", 0))
                is_long = position.direction == "LONG"
                if (is_long and ex_amt <= 0) or (not is_long and ex_amt >= 0):
                    ghosts.append(position)

        for ghost in ghosts:
            log_warning(
                f"Reconciliation: GHOST position detected — {ghost.strategy_name} "
                f"{ghost.direction} {ghost.asset} (not on exchange). Removing from tracking."
            )
            # Get current price for P&L logging
            try:
                ticker = self.executor.get_ticker(ghost.asset)
                fill_price = ticker["price"]
            except Exception:
                fill_price = ghost.entry_price  # Fallback

            # Record P&L
            direction_sign = 1.0 if ghost.direction == "LONG" else -1.0
            pnl = (fill_price - ghost.entry_price) * ghost.remaining_qty * direction_sign
            log_exit(
                strategy=ghost.strategy_name,
                direction=ghost.direction,
                asset=ghost.asset,
                entry_price=ghost.entry_price,
                exit_price=fill_price,
                pnl=pnl,
                reason="EXCHANGE_RECONCILE",
            )
            self.position_manager.remove_position(ghost.asset, ghost.strategy_name)
            _log_trade("EXIT", ghost.strategy_name, ghost.asset,
                        ghost.direction, ghost.remaining_qty, fill_price,
                        "EXCHANGE_RECONCILE", "")

            # Record for kill switch
            size_usd = ghost.entry_price * ghost.remaining_qty
            if size_usd > 0:
                pnl_pct = pnl / size_usd
                self.risk_manager.record_trade(ghost.strategy_name, pnl_pct)
                self.risk_manager.update_strategy_equity(ghost.strategy_name, pnl)

            from DevAntsa_Lab.live_trading.notifications.telegram_notifier import send_telegram
            send_telegram(
                f"*RECONCILE* Ghost position removed: {ghost.strategy_name} "
                f"{ghost.direction} {ghost.asset} | PnL: ${pnl:+.2f}"
            )

        # Check for orphan positions (on exchange, not tracked internally)
        tracked_assets = set()
        for p in internal:
            if p not in ghosts:
                tracked_assets.add(p.asset)

        for sym, ep in exchange_map.items():
            if sym not in tracked_assets:
                amt = float(ep.get("positionAmt", 0))
                log_warning(f"Reconciliation: ORPHAN position on exchange: {sym} amt={amt}")
                try:
                    self.executor.close_position(sym)
                    log_warning(f"Reconciliation: closed orphan {sym}")
                    from DevAntsa_Lab.live_trading.notifications.telegram_notifier import send_telegram
                    send_telegram(f"*RECONCILE* Closed orphan position: {sym} amt={amt}")
                except Exception as e2:
                    log_error(f"Reconciliation: failed to close orphan {sym}: {e2}")

        if ghosts or any(sym not in tracked_assets for sym in exchange_map):
            log_info(f"Reconciliation complete: {len(ghosts)} ghosts removed")

    def _setup_exchange(self) -> None:
        """Set leverage and margin type for all strategy assets on startup."""
        from DevAntsa_Lab.live_trading.config import STRATEGY_LEVERAGE_CAPS

        configured: set = set()
        for strategy_name, assets in STRATEGY_ASSETS.items():
            for asset in assets:
                if asset in configured:
                    continue
                configured.add(asset)

                # Set margin type
                try:
                    self.executor.set_margin_type(asset, BINANCE_MARGIN_TYPE)
                except Exception as e:
                    logger.warning("Failed to set margin type for %s: %s", asset, e)

                # Set leverage to the max cap for this asset across strategies
                max_lev = 1
                for sname, assets_list in STRATEGY_ASSETS.items():
                    if asset in assets_list:
                        caps = STRATEGY_LEVERAGE_CAPS.get(sname, {})
                        cap = caps.get(ACCOUNT_MODE, 1)
                        if cap and cap > max_lev:
                            max_lev = int(cap)
                try:
                    self.executor.set_leverage(asset, max(max_lev, 1))
                except Exception as e:
                    logger.warning("Failed to set leverage for %s: %s", asset, e)

    def run(self) -> None:
        """
        Plan Part 7 step 7: "while True ... sleep_until_next_bar(timeframe='4h')"
        """
        log_info(f"TradingLoop starting -- mode={ACCOUNT_MODE}")

        while True:
            # Check if kill switch was triggered
            if self._killed:
                log_error("Kill switch active — loop halted. Manual restart required.")
                break

            try:
                self._tick()
            except KeyboardInterrupt:
                log_info("Graceful shutdown requested.")
                self._save_state()
                break
            except Exception:
                logger.exception("Unhandled error in main loop tick")

            # Plan Part 7 step 7: sleep until next bar
            self._sleep_until_next_bar()

    def _tick(self) -> None:
        """
        Single iteration of the trading loop.

        Execution order (critical for safety):
            1. Equity + daily reset + phase detection
            2. KILL SWITCH (permanent halt) — fires first, closes all
            3. CLOSE_ALL (-4% daily DD) — closes all, but loop resumes next day
            4. Determine halt_entries flag (-3% daily DD halts new entries)
            5. bars_held increment + regime classification + status display
            6. EXIT MANAGEMENT (ALWAYS runs — trailing stops, TPs, max_hold)
            7. Trailing stop sync to exchange
            8. ENTRY MANAGEMENT (only when not halted)
            9. Save state

        The key invariant: exit management ALWAYS runs, even when DD limits
        halt new entries. Positions must never sit unmanaged.
        """
        self._tick_count += 1
        now = datetime.now(timezone.utc)

        # -- Timeframe gating (Decision 1) -----------------------------------
        eligible = get_eligible_strategies(now, self.last_candle_times)
        if not eligible:
            logger.debug("No strategies eligible at %s", now.isoformat())
            return

        # -- Step 1: Check account status (Plan Part 7 step 1) ---------------
        try:
            equity = self.executor.get_equity()
        except Exception as e:
            log_error(f"Failed to get equity: {e} — skipping tick")
            return

        # -- Daily session boundary check (T1-1, T1-2, T1-3) ----------------
        self.risk_manager.check_daily_reset(equity)

        # -- Daily summary check (sends Telegram report at UTC midnight) ----
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        check_daily_summary(
            current_date=today_str,
            equity=equity,
            starting_equity=self.risk_manager.starting_equity or equity,
        )

        if self.risk_manager.starting_equity is None:
            self.risk_manager.set_session_start(equity)
            log_info(f"Initial equity set: ${equity:,.2f}")

        # -- Position reconciliation (H-1) — detect ghost/orphan positions ----
        self._reconcile_positions()

        phase = self.risk_manager.determine_phase(equity)
        phase_leverage = self.risk_manager.get_leverage_for_phase(phase)

        # ================================================================
        # SAFETY NETS — must run BEFORE entry/exit management
        # ================================================================

        # -- Kill switch (permanent halt: total DD, Sharpe, strategy DD, losing days)
        should_kill, kill_reason = self.risk_manager.evaluate_kill_switch(equity)
        if should_kill:
            log_kill_switch(kill_reason)
            self._close_all_positions(f"KILL_SWITCH_{kill_reason}")
            notify_kill_switch(kill_reason)
            self._save_state()
            self._killed = True
            return

        # -- DD action: CLOSE_ALL (-4% daily DD) — close all, loop continues tomorrow
        dd_action = self.risk_manager.get_dd_action(equity)
        if dd_action == "CLOSE_ALL":
            log_error("DD action CLOSE_ALL (-4%) — closing all positions")
            self._close_all_positions("DD_CLOSE_ALL")
            self._save_state()
            return

        # -- Determine if new entries should be halted (-3% daily DD) --------
        # NOTE: This only halts entries. Exit management ALWAYS runs below.
        halt_entries = self.risk_manager.should_halt_trading(equity)
        if halt_entries:
            log_warning("Daily DD limit reached — new entries halted, exits still active")
        if dd_action == "REDUCE":
            log_warning("DD action REDUCE (-2%) — limiting to 1 position per regime")

        # ================================================================
        # POSITION MANAGEMENT — always runs regardless of DD level
        # ================================================================

        # -- Step 2: bars_held increment (Plan Part 7 step 2) ----------------
        self.position_manager.increment_bars_held(eligible)

        # -- Regime classification (needed for display + entry filtering) -----
        open_positions = self.position_manager.positions
        market_regime = self.regime_gate.classify()

        # -- Status display --------------------------------------------------
        daily_dd = self.risk_manager.get_daily_dd(equity) * 100
        total_dd = self.risk_manager.get_total_dd(equity) * 100
        print_status_table(
            equity=equity,
            starting_equity=self.risk_manager.starting_equity or equity,
            phase=phase,
            regime=market_regime,
            positions=len(open_positions),
            daily_dd=daily_dd,
            total_dd=total_dd,
            losing_days=self.risk_manager.consecutive_losing_days,
        )

        log_tick_start(self._tick_count, list(eligible))

        # -- Regime change detection (display only — gate DISABLED in v10) -----
        # No Telegram alert or console log — regime is informational only,
        # all 15 strategies self-gate via SMA200. Removed to avoid confusion.
        # check_regime_change(market_regime)
        # if self._last_regime is not None and market_regime != self._last_regime:
        #     log_regime_change(self._last_regime, market_regime)

        # Cache for sleep-time command polling
        self._last_equity = equity
        self._last_regime = market_regime

        # -- Telegram commands -----------------------------------------------
        poll_commands(self.position_manager, self.risk_manager, equity, market_regime, self.executor)

        # ================================================================
        # EXIT MANAGEMENT — ALWAYS runs (trailing stops, TPs, max_hold)
        # ================================================================

        exit_signals = self.signal_engine.check_exits(open_positions, eligible)
        for exit_sig in exit_signals:
            self._execute_exit(exit_sig)

        # -- Sync trailing stops to exchange (Priority 3) --------------------
        self._sync_trailing_stops(open_positions, eligible)

        # ================================================================
        # ENTRY MANAGEMENT — halted when DD limit reached
        # ================================================================

        if not halt_entries:
            pending_signals = self.signal_engine.collect_signals(eligible)
            resolved = self.conflict_resolver.resolve(pending_signals, open_positions)
            # Regime gate disabled (v10): all 15 strategies are self-gating via SMA200
            # resolved = self.regime_gate.filter_signals(resolved, market_regime)

            for signal in resolved:
                if dd_action == "REDUCE":
                    regime_counts = self.position_manager.regime_counts()
                    if regime_counts.get(signal.regime, 0) >= 1:
                        log_signal_skip(signal.strategy_name, f"REDUCE mode — already 1 {signal.regime} position")
                        continue
                self._execute_entry(signal, equity, phase, phase_leverage)
        else:
            log_info("Entries halted — managing existing positions only")

        # -- Persist state after every tick ----------------------------------
        self._save_state()

    def _execute_entry(
        self,
        signal,
        equity: float,
        phase: str,
        phase_leverage: float,
    ) -> None:
        """Execute a single entry signal: size, place order, place stop, track position."""
        # Regime limit check
        if not self.position_manager.within_regime_limits(signal.regime):
            log_signal_skip(signal.strategy_name, f"Regime limit reached for {signal.regime}")
            return
        if not self.position_manager.within_total_limit():
            log_signal_skip(signal.strategy_name, "Total position limit reached")
            return
        # Already have position for this strategy
        if self.position_manager.has_position_for_strategy(signal.strategy_name):
            log_signal_skip(signal.strategy_name, "Already have position")
            return
        # Opposite direction on same asset (Binance one-way mode protection)
        if self.position_manager.has_opposite_direction_on_asset(signal.asset, signal.direction):
            log_signal_skip(
                signal.strategy_name,
                f"Opposite-direction position already open on {signal.asset}"
            )
            return

        # Effective leverage: min(phase, strategy_cap) — Decision 3
        strategy_cap = self.risk_manager.get_strategy_leverage_cap(signal.strategy_name)
        if strategy_cap is None:
            log_signal_skip(signal.strategy_name, f"Not safe for {ACCOUNT_MODE} mode")
            return

        # Leverage: bears use strategy cap directly, bulls use min(phase, cap)
        is_bear = signal.regime == "bear"
        if is_bear:
            effective_leverage = strategy_cap
        else:
            effective_leverage = min(phase_leverage, strategy_cap)

        # Risk: per-strategy override (both regimes). Bears scale by phase multiplier.
        base_risk = STRATEGY_RISK_OVERRIDES.get(signal.strategy_name, RISK_PER_TRADE)
        if is_bear:
            phase_mult = BEAR_PHASE_RISK_MULTIPLIER.get(phase, 1.0)
            risk_pct = base_risk * phase_mult
        else:
            risk_pct = base_risk

        # Stop distance from signal
        stop_distance_pct = signal.stop_distance_pct
        if stop_distance_pct is None or stop_distance_pct <= 0:
            logger.error("No valid stop distance for %s — skipping", signal.strategy_name)
            return

        # Position sizing
        position_size_usd = calculate_position_size(
            account_equity=equity,
            risk_pct=risk_pct,
            stop_distance_pct=stop_distance_pct,
            leverage=effective_leverage,
        )

        entry_price = signal.entry_price
        if entry_price is None or entry_price <= 0:
            logger.error("No entry price for %s — skipping", signal.strategy_name)
            return

        qty = position_size_to_quantity(position_size_usd, entry_price)

        # Check minimum notional
        filters = self.executor.get_symbol_filters(signal.asset)
        min_notional = filters.get("minNotional", 5.0)
        if position_size_usd < min_notional:
            logger.warning(
                "Position $%.2f < minNotional $%.2f for %s — skipping",
                position_size_usd, min_notional, signal.asset,
            )
            return

        # Place market order
        order_side = "BUY" if signal.direction == "LONG" else "SELL"
        try:
            order = self.executor.place_market_order(signal.asset, order_side, qty)
        except Exception as e:
            logger.error("Entry order failed for %s: %s", signal.strategy_name, e)
            return

        order_id = str(order.get("orderId", ""))
        order_status = order.get("status", "")

        # C-1: Verify entry order actually filled
        if order_status != "FILLED":
            logger.error(
                "Entry order for %s status=%s (not FILLED) — aborting entry",
                signal.strategy_name, order_status,
            )
            # Try to close any position that may have partially opened
            try:
                self.executor.close_position(signal.asset)
            except Exception:
                pass
            return

        raw_fill = float(order.get("avgPrice", 0))
        if raw_fill <= 0:
            logger.error(
                "Entry order for %s FILLED but avgPrice=%s — using signal price as fallback",
                signal.strategy_name, raw_fill,
            )
        fill_price = raw_fill if raw_fill > 0 else entry_price

        # Place stop-loss order
        stop_side = "SELL" if signal.direction == "LONG" else "BUY"
        stop_price = signal.stop_price
        stop_order_id = None
        if stop_price is not None and stop_price > 0:
            try:
                rounded_qty = self.executor._round_qty(signal.asset, qty)
                stop_result = self.executor.place_stop_loss(signal.asset, stop_side, stop_price, rounded_qty)
                stop_order_id = str(stop_result.get("algoId", stop_result.get("orderId", "")))

                # H-4: Verify stop is actually ACTIVE on exchange
                if stop_order_id:
                    time.sleep(1)  # Brief delay for async algo order acceptance
                    try:
                        open_algos = self.executor.get_open_algo_orders(signal.asset)
                        found = any(str(ao.get("algoId")) == stop_order_id for ao in open_algos)
                        if not found:
                            raise RuntimeError(f"Stop {stop_order_id} not found in open algo orders after placement")
                        logger.info("Stop %s verified ACTIVE for %s", stop_order_id, signal.strategy_name)
                    except RuntimeError:
                        raise  # Re-raise so the outer except catches it
                    except Exception as e:
                        logger.warning("Stop verification check failed for %s: %s — proceeding with caution", signal.strategy_name, e)

            except Exception as e:
                logger.error(
                    "CRITICAL: Stop loss placement/verification failed for %s after entry! Error: %s",
                    signal.strategy_name, e,
                )
                # Entry succeeded but stop failed — position is unprotected
                # Close position immediately for safety
                try:
                    self.executor.close_position(signal.asset)
                    log_emergency(signal.strategy_name, signal.asset, "Stop placement failed")
                    _log_trade("EMERGENCY_CLOSE", signal.strategy_name, signal.asset,
                               signal.direction, qty, fill_price, "stop_placement_failed", order_id)
                    notify_emergency(signal)
                except Exception as e2:
                    log_error(f"Emergency close also failed for {signal.strategy_name}: {e2}")
                return

        # Track position internally
        rounded_qty = self.executor._round_qty(signal.asset, qty)
        position = Position(
            asset=signal.asset,
            direction=signal.direction,
            strategy_name=signal.strategy_name,
            regime=signal.regime,
            entry_price=fill_price,
            current_stop=stop_price if stop_price else 0.0,
            quantity=rounded_qty,
            remaining_qty=rounded_qty,
            bars_held=0,
            entry_time=datetime.now(timezone.utc),
            order_id=order_id,
            tp1_price=signal.metadata.get("tp1_price") if signal.metadata else None,
            tp2_price=signal.metadata.get("tp2_price") if signal.metadata else None,
            metadata={
                "stop_order_id": stop_order_id,
                "fill_price": fill_price,
                "position_size_usd": position_size_usd,
                "effective_leverage": effective_leverage,
                "risk_pct": risk_pct,
            },
        )
        self.position_manager.add_position(position)

        # Rich console logging
        log_entry(
            strategy=signal.strategy_name,
            direction=signal.direction,
            asset=signal.asset,
            price=fill_price,
            stop=stop_price or 0,
            size_usd=position_size_usd,
            leverage=effective_leverage,
        )
        log_stop_placed(signal.asset, stop_price or 0)
        _log_trade("ENTRY", signal.strategy_name, signal.asset,
                    signal.direction, rounded_qty, fill_price, "", order_id)
        notify_entry(signal, fill_price, stop_price or 0, position_size_usd, effective_leverage, risk_pct)

    def _execute_exit(self, exit_sig: ExitSignal) -> None:
        """Execute a single exit signal: close position (full or partial), update tracking."""
        position = self.position_manager.get_position_for_strategy(exit_sig.strategy_name)
        if position is None:
            logger.warning("Exit signal for %s but no tracked position", exit_sig.strategy_name)
            return

        is_partial = exit_sig.metadata and exit_sig.metadata.get("partial", False)
        close_pct = exit_sig.metadata.get("close_pct", 0.5) if exit_sig.metadata else 0.5

        if is_partial:
            # Partial close (bear TP1) — Decision 4
            close_qty = position.remaining_qty * close_pct
            try:
                order = self.executor.partial_close_position(position.asset, close_qty)
            except Exception as e:
                logger.error("Partial close failed for %s: %s", exit_sig.strategy_name, e)
                return

            # C-2: Verify partial close actually filled
            order_status = order.get("status", "") if order else ""
            if order_status not in ("FILLED", ""):
                logger.warning(
                    "Partial close for %s status=%s (not FILLED) — keeping position unchanged, retry next tick",
                    exit_sig.strategy_name, order_status,
                )
                return  # Don't reduce qty, don't set tp1_hit

            position.remaining_qty -= self.executor._round_qty(position.asset, close_qty)
            position.tp1_hit = True
            fill_price = float(order.get("avgPrice", 0))
            if fill_price == 0:
                fill_price = self.executor.get_ticker(position.asset)["price"]

            # Rich console logging for partial exit
            direction_sign = 1.0 if position.direction == "LONG" else -1.0
            partial_pnl_display = (fill_price - position.entry_price) * close_qty * direction_sign
            log_partial_exit(exit_sig.strategy_name, position.asset, fill_price, partial_pnl_display, exit_sig.reason)
            _log_trade("PARTIAL_EXIT", exit_sig.strategy_name, position.asset,
                        position.direction, close_qty, fill_price, exit_sig.reason, "")
            notify_partial_exit(exit_sig, position, close_qty, fill_price)

            # Record trade for kill switch tracking (T2-2, T2-3)
            direction_sign = 1.0 if position.direction == "LONG" else -1.0
            partial_pnl = (fill_price - position.entry_price) * close_qty * direction_sign
            partial_size_usd = position.entry_price * close_qty
            if partial_size_usd > 0:
                pnl_pct = partial_pnl / partial_size_usd
                self.risk_manager.record_trade(position.strategy_name, pnl_pct)
                self.risk_manager.update_strategy_equity(position.strategy_name, partial_pnl)

            # Update stop order to reflect reduced quantity
            stop_order_id = position.metadata.get("stop_order_id")
            if position.current_stop > 0:
                stop_side = "BUY" if position.direction == "SHORT" else "SELL"
                placed = False

                # Try modifying existing stop first
                if stop_order_id:
                    try:
                        new_stop = self.executor.modify_stop_loss(
                            position.asset, stop_order_id,
                            position.current_stop, position.remaining_qty,
                        )
                        position.metadata["stop_order_id"] = str(new_stop.get("algoId", new_stop.get("orderId", "")))
                        placed = True
                    except Exception as e:
                        logger.warning("Modify stop failed after partial close: %s — placing fresh stop", e)

                # Fallback: place a brand new stop if modify failed or no ID
                if not placed:
                    try:
                        new_stop = self.executor.place_stop_loss(
                            position.asset, stop_side,
                            position.current_stop, position.remaining_qty,
                        )
                        position.metadata["stop_order_id"] = str(new_stop.get("algoId", ""))
                        logger.info(
                            "Fresh stop placed for %s %s @ $%.2f qty=%.4f",
                            position.strategy_name, position.asset,
                            position.current_stop, position.remaining_qty,
                        )
                    except Exception as e:
                        logger.error("CRITICAL: Could not place stop after partial close: %s", e)

        else:
            # Full close — C-3: pass specific stop ID to avoid killing other strategies' stops
            stop_id = position.metadata.get("stop_order_id")
            try:
                order = self.executor.close_position(position.asset, algo_id_to_cancel=stop_id)
            except Exception as e:
                logger.error("Full close failed for %s: %s", exit_sig.strategy_name, e)
                return

            # Verify close actually filled (Binance Demo may return status=NEW)
            order_status = order.get("status", "") if order else ""
            if order and order_status not in ("FILLED", ""):
                # close_position returned {} (no position) is fine, but NEW/PARTIAL = not closed
                logger.warning(
                    "Close order for %s status=%s (not FILLED) — keeping position tracked",
                    exit_sig.strategy_name, order_status,
                )
                # Verify via exchange: is position actually gone?
                try:
                    exchange_pos = self.executor.get_position(position.asset)
                    if exchange_pos is not None:
                        logger.warning(
                            "Exchange still has %s position (amt=%s) — will retry next tick",
                            position.asset, exchange_pos.get("positionAmt"),
                        )
                        return  # Don't log exit, don't remove — retry next eligible tick
                except Exception:
                    pass  # If we can't check, proceed cautiously below

            fill_price = float(order.get("avgPrice", 0)) if order else 0
            if fill_price == 0:
                fill_price = self.executor.get_ticker(position.asset)["price"]
            removed = self.position_manager.remove_position(position.asset, position.strategy_name)

            # Rich console logging for full exit
            direction_sign = 1.0 if position.direction == "LONG" else -1.0
            exit_pnl_display = (fill_price - position.entry_price) * position.remaining_qty * direction_sign
            log_exit(
                strategy=exit_sig.strategy_name,
                direction=position.direction,
                asset=position.asset,
                entry_price=position.entry_price,
                exit_price=fill_price,
                pnl=exit_pnl_display,
                reason=exit_sig.reason,
            )
            _log_trade("EXIT", exit_sig.strategy_name, position.asset,
                        position.direction, position.remaining_qty, fill_price,
                        exit_sig.reason, "")
            notify_exit(exit_sig, position, fill_price)

            # Record trade for kill switch tracking (T2-2, T2-3)
            direction_sign = 1.0 if position.direction == "LONG" else -1.0
            exit_pnl = (fill_price - position.entry_price) * position.remaining_qty * direction_sign
            exit_size_usd = position.entry_price * position.remaining_qty
            if exit_size_usd > 0:
                pnl_pct = exit_pnl / exit_size_usd
                self.risk_manager.record_trade(position.strategy_name, pnl_pct)
                self.risk_manager.update_strategy_equity(position.strategy_name, exit_pnl)

    def _sync_trailing_stops(self, open_positions: list, eligible: set) -> None:
        """
        Sync internal trailing stop updates to the exchange.

        After check_exits() updates position.current_stop via calculate_trail(),
        this method pushes the new stop to Binance so the exchange-side stop
        reflects the trailed level. If the bot crashes, the exchange stop is
        up to date rather than stuck at the original level.
        """
        for position in open_positions:
            if position.strategy_name not in eligible:
                continue
            if position.current_stop <= 0:
                continue

            stop_order_id = position.metadata.get("stop_order_id")
            if not stop_order_id:
                continue

            # Check if stop has moved from what exchange has
            last_synced = position.metadata.get("last_synced_stop", 0.0)
            if abs(position.current_stop - last_synced) < 0.001:
                continue  # No change, skip

            stop_side = "SELL" if position.direction == "LONG" else "BUY"
            try:
                new_stop = self.executor.modify_stop_loss(
                    position.asset, stop_order_id,
                    position.current_stop, position.remaining_qty,
                )
                position.metadata["stop_order_id"] = str(new_stop.get("algoId", new_stop.get("orderId", "")))
                position.metadata["last_synced_stop"] = position.current_stop
                log_stop_updated(position.asset, last_synced, position.current_stop)
            except Exception as e:
                # Modify failed — try placing a fresh stop
                logger.warning("Trail sync modify failed for %s: %s — placing fresh stop", position.strategy_name, e)
                try:
                    fresh = self.executor.place_stop_loss(
                        position.asset, stop_side,
                        position.current_stop, position.remaining_qty,
                    )
                    position.metadata["stop_order_id"] = str(fresh.get("algoId", fresh.get("orderId", "")))
                    position.metadata["last_synced_stop"] = position.current_stop
                    log_stop_updated(position.asset, last_synced, position.current_stop)
                except Exception as e2:
                    log_error(f"CRITICAL: Trail sync failed for {position.strategy_name}: {e2}")

    def _close_all_positions(self, reason: str) -> None:
        """
        Close all open positions. Used by CLOSE_ALL DD action and kill switch.

        C-4: Verifies each close is actually filled before removing from tracking.
        Positions that fail to close are kept tracked for reconciliation to catch.
        """
        from DevAntsa_Lab.live_trading.notifications.telegram_notifier import send_telegram

        positions = list(self.position_manager.positions)
        if not positions:
            return

        log_error(f"Closing all {len(positions)} positions — reason: {reason}")
        send_telegram(f"\U0001f6a8 *{reason}*\nClosing all {len(positions)} positions")

        for position in positions:
            # C-3: Pass specific stop ID to avoid killing other strategies' stops
            stop_id = position.metadata.get("stop_order_id")
            try:
                order = self.executor.close_position(position.asset, algo_id_to_cancel=stop_id)
            except Exception as e:
                log_error(f"Failed to close {position.strategy_name} {position.asset}: {e}")
                continue  # C-4: Keep position tracked — don't remove on failure

            # C-4: Verify close actually filled
            order_status = order.get("status", "") if order else ""
            if order_status not in ("FILLED", ""):
                # Verify via exchange
                try:
                    exchange_pos = self.executor.get_position(position.asset)
                    if exchange_pos is not None:
                        log_error(f"Close FAILED for {position.strategy_name} status={order_status} — keeping tracked")
                        continue  # Don't remove — reconciliation will catch it
                except Exception:
                    pass  # If can't verify, proceed cautiously

            fill_price = float(order.get("avgPrice", 0)) if order else 0
            if fill_price == 0:
                try:
                    fill_price = self.executor.get_ticker(position.asset)["price"]
                except Exception:
                    fill_price = 0

            # Only remove + log if close confirmed
            direction_sign = 1.0 if position.direction == "LONG" else -1.0
            pnl = (fill_price - position.entry_price) * position.remaining_qty * direction_sign if fill_price > 0 else 0
            log_exit(
                strategy=position.strategy_name,
                direction=position.direction,
                asset=position.asset,
                entry_price=position.entry_price,
                exit_price=fill_price,
                pnl=pnl,
                reason=reason,
            )
            self.position_manager.remove_position(position.asset, position.strategy_name)
            _log_trade("EXIT", position.strategy_name, position.asset,
                        position.direction, position.remaining_qty, fill_price, reason, "")

    def _sleep_until_next_bar(self) -> None:
        """
        Sleep until the next candle close for the shortest registered timeframe.
        Longer timeframes are gated via get_eligible_strategies().
        Polls for Telegram commands every 30 seconds during sleep.
        """
        # Compute tick interval from the smallest timeframe in STRATEGY_TIMEFRAMES
        min_interval = min(
            INTERVAL_SECONDS.get(tf, 3600)
            for tf in STRATEGY_TIMEFRAMES.values()
        )
        now = datetime.now(timezone.utc)
        epoch = int(now.timestamp())
        next_boundary = ((epoch // min_interval) + 1) * min_interval
        sleep_sec = max(next_boundary - epoch, 1)
        log_sleep(sleep_sec)

        poll_interval = 30
        remaining = sleep_sec
        while remaining > 0:
            chunk = min(poll_interval, remaining)
            time.sleep(chunk)
            remaining -= chunk
            if remaining > 0:
                poll_commands(
                    self.position_manager, self.risk_manager,
                    self._last_equity, self._last_regime, self.executor,
                )


# -- Entry point -------------------------------------------------------------

def main():
    """Standalone entry point for the live trading system."""
    # Use rich for beautiful console output
    setup_rich_logging()

    # Print startup banner
    print_banner()

    loop = TradingLoop()
    loop.run()


if __name__ == "__main__":
    main()
