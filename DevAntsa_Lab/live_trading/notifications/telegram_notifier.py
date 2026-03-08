"""
Telegram Notifier — DevAntsa Lab
=================================
Fire-and-forget notifications + command handler for Telegram Bot API.
Uses raw HTTP requests — no heavyweight async library needed.

Env vars required:
    TELEGRAM_BOT_TOKEN  — from @BotFather
    TELEGRAM_CHAT_ID    — your chat/group ID

Supported commands (send via Telegram chat):
    /positions  — list all active positions with unrealized P&L
    /status     — show equity, phase, regime gate, drawdown, target progress
    /journal    — trade journal with daily P&L and strategy breakdown
    /stats      — lifetime performance stats (win rate, expectancy, Sharpe)
    /help       — list all available commands
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import requests

from DevAntsa_Lab.live_trading.config import STRATEGY_TIMEFRAMES

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
API_URL = f"{BASE_API}/sendMessage"

# ---------------------------------------------------------------------------
# DevAntsa Lab Branding
# ---------------------------------------------------------------------------
BRAND_HEADER = "\U0001f41c\U0001f9ea *DevAntsa Lab*"  # 🐜🧪
BRAND_FOOTER = "_Precision trading, systematic execution_"
BRAND_EMOJI = "\U0001f41c"  # 🐜

# "240" -> "4H", "60" -> "1H"
_TF_LABELS = {"240": "4H", "60": "1H", "1440": "1D", "15": "15m"}

# Track last processed update to avoid replaying old commands
_last_update_id = 0

# Track previous regime for change detection
_previous_regime: Optional[str] = None

# Track last daily summary date to avoid duplicates
_last_summary_date: Optional[str] = None


def _tf_label(strategy_name: str) -> str:
    raw = STRATEGY_TIMEFRAMES.get(strategy_name, "")
    return _TF_LABELS.get(raw, raw)


def send_telegram(text: str) -> None:
    """Fire-and-forget Telegram message. Never raises — logs errors only."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(API_URL, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        }, timeout=5)
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)


def notify_entry(signal, fill_price, stop_price, position_size_usd, effective_leverage, risk_pct):
    """Send Telegram notification for a new entry."""
    direction_emoji = "\U0001f7e2" if signal.direction == "LONG" else "\U0001f534"
    tf = _tf_label(signal.strategy_name)
    asset_tf = f"{signal.asset}({tf})" if tf else signal.asset

    # Build TP lines if available
    tp_lines = ""
    if signal.metadata:
        tp1 = signal.metadata.get("tp1_price")
        tp2 = signal.metadata.get("tp2_price")
        if tp1:
            tp_lines += f"\U0001f3af *TP1:* `${tp1:.2f}`\n"
        if tp2:
            tp_lines += f"\U0001f3af *TP2:* `${tp2:.2f}`\n"

    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"{direction_emoji} *NEW ENTRY*\n"
        f"\n"
        f"\U0001f4cb *Strategy:* `{signal.strategy_name}`\n"
        f"\U0001f4c8 *Direction:* {signal.direction} {asset_tf}\n"
        f"\n"
        f"\U0001f4b0 *Entry:* `${fill_price:.2f}`\n"
        f"\U0001f6d1 *Stop:* `${stop_price:.2f}`\n"
        f"{tp_lines}"
        f"\U0001f4b5 *Size:* `${position_size_usd:.2f}` | *Lev:* `{effective_leverage:.1f}x` | *Risk:* `{risk_pct * 100:.2f}%`"
    )
    send_telegram(text)


def notify_exit(exit_sig, position, fill_price):
    """Send Telegram notification for a full position close."""
    entry_p = position.entry_price
    direction_sign = 1.0 if position.direction == "LONG" else -1.0
    pnl = (fill_price - entry_p) * position.remaining_qty * direction_sign
    pnl_emoji = "\u2705" if pnl >= 0 else "\u274c"
    pnl_sign = "+" if pnl >= 0 else ""
    tf = _tf_label(exit_sig.strategy_name)
    asset_tf = f"{position.asset}({tf})" if tf else position.asset

    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f3c1 *TRADE CLOSED*\n"
        f"\n"
        f"\U0001f4cb *Strategy:* `{exit_sig.strategy_name}`\n"
        f"\U0001f4c8 *Direction:* {position.direction} {asset_tf}\n"
        f"\n"
        f"*Entry:* `${entry_p:.2f}` \u2192 *Exit:* `${fill_price:.2f}`\n"
        f"*Bars held:* `{position.bars_held}` | *Reason:* `{exit_sig.reason}`\n"
        f"\n"
        f"{pnl_emoji} *P&L:* `{pnl_sign}${pnl:.2f}`"
    )
    send_telegram(text)


def notify_partial_exit(exit_sig, position, close_qty, fill_price):
    """Send Telegram notification for a partial close (TP1 hit)."""
    tf = _tf_label(exit_sig.strategy_name)
    asset_tf = f"{position.asset}({tf})" if tf else position.asset

    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f3af *TAKE PROFIT HIT*\n"
        f"\n"
        f"\U0001f4cb *Strategy:* `{exit_sig.strategy_name}`\n"
        f"\U0001f4c8 *Direction:* {position.direction} {asset_tf}\n"
        f"\n"
        f"*Closed:* `{close_qty:.4f}` | *Remaining:* `{position.remaining_qty:.4f}`\n"
        f"*Fill:* `${fill_price:.2f}` | *Reason:* `{exit_sig.reason}`"
    )
    send_telegram(text)


def notify_emergency(signal):
    """Send Telegram notification for an emergency position close."""
    tf = _tf_label(signal.strategy_name)
    asset_tf = f"{signal.asset}({tf})" if tf else signal.asset

    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f6a8 *EMERGENCY CLOSE*\n"
        f"\n"
        f"*Strategy:* `{signal.strategy_name}` | *Asset:* {asset_tf}\n"
        f"Stop placement failed \u2014 position closed immediately"
    )
    send_telegram(text)


def notify_kill_switch(reason: str) -> None:
    """Send critical alert when kill switch fires."""
    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f6a8\U0001f6a8\U0001f6a8 *KILL SWITCH TRIGGERED*\n"
        f"\n"
        f"*Reason:* `{reason}`\n"
        f"\n"
        f"All positions closed. Trading halted.\n"
        f"Manual restart required to resume."
    )
    send_telegram(text)


def notify_regime_change(old_regime: str, new_regime: str) -> None:
    """Send notification when market regime changes."""
    regime_emojis = {
        "BULLISH": "\U0001f7e2",   # green circle
        "BEARISH": "\U0001f534",   # red circle
        "NEUTRAL": "\U0001f7e1",   # yellow circle
    }
    old_emoji = regime_emojis.get(old_regime, "\u2753")
    new_emoji = regime_emojis.get(new_regime, "\u2753")

    # Explain impact
    if new_regime == "BEARISH":
        impact = "Loose LONG strategies now *blocked*"
    elif new_regime == "BULLISH":
        impact = "All LONG strategies now *eligible*"
    else:
        impact = "Strategies operating in *neutral* mode"

    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f504 *REGIME SHIFT DETECTED*\n"
        f"\n"
        f"{old_emoji} `{old_regime}` \u2192 {new_emoji} `{new_regime}`\n"
        f"\n"
        f"{impact}"
    )
    send_telegram(text)


def notify_daily_summary(
    date_str: str,
    entries: int,
    exits: int,
    realized_pnl: float,
    equity: float,
    starting_equity: float,
) -> None:
    """Send daily performance summary."""
    total_pnl = equity - starting_equity
    total_pnl_pct = (total_pnl / starting_equity * 100) if starting_equity > 0 else 0
    pnl_sign = "+" if realized_pnl >= 0 else ""
    total_sign = "+" if total_pnl >= 0 else ""
    pnl_emoji = "\U0001f4c8" if realized_pnl >= 0 else "\U0001f4c9"

    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4ca *DAILY SUMMARY*\n"
        f"*Date:* `{date_str}`\n"
        f"\n"
        f"\U0001f4cb *Trades:* `{entries}` entries, `{exits}` exits\n"
        f"{pnl_emoji} *Today's P&L:* `{pnl_sign}${realized_pnl:.2f}`\n"
        f"\n"
        f"\U0001f4b0 *Equity:* `${equity:.2f}`\n"
        f"\U0001f4c8 *Total P&L:* `{total_sign}${total_pnl:.2f}` (`{total_sign}{total_pnl_pct:.2f}%`)\n"
        f"\n"
        f"{BRAND_FOOTER}"
    )
    send_telegram(text)


# ---------------------------------------------------------------------------
# Command handler — poll for /positions, /status, /stats, /help commands
# ---------------------------------------------------------------------------

def poll_commands(position_manager, risk_manager=None, equity=None, regime=None, executor=None):
    """
    Check for new Telegram messages and respond to known commands.
    Called every tick + during sleep. Never raises.

    Supported:
        /positions  — list active positions with unrealized P&L
        /status     — equity, phase, DD, regime gate
        /stats      — lifetime performance stats
        /journal    — trade journal with daily P&L
        /help       — list all commands
    """
    global _last_update_id
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        resp = requests.get(
            f"{BASE_API}/getUpdates",
            params={"offset": _last_update_id + 1, "timeout": 0},
            timeout=5,
        )
        data = resp.json()
        if not data.get("ok"):
            return

        for update in data.get("result", []):
            _last_update_id = update["update_id"]
            msg = update.get("message", {})
            text = msg.get("text", "").strip().lower()
            chat_id = str(msg.get("chat", {}).get("id", ""))

            # Only respond to our chat
            if chat_id != TELEGRAM_CHAT_ID:
                continue

            if text in ("/positions", "/active", "/pos"):
                _handle_positions(position_manager, executor)
            elif text in ("/status", "/stat"):
                _handle_status(position_manager, risk_manager, equity, regime)
            elif text in ("/journal", "/trades", "/pnl"):
                _handle_journal()
            elif text in ("/stats", "/performance", "/perf"):
                _handle_stats(risk_manager)
            elif text in ("/help", "/h", "/?"):
                _handle_help()

    except Exception as e:
        logger.debug("Telegram poll failed: %s", e)


def _handle_positions(position_manager, executor=None):
    """Respond with list of active positions including unrealized P&L."""
    positions = position_manager.positions
    if not positions:
        send_telegram(
            f"{BRAND_HEADER}\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"\U0001f4ad *No open positions*"
        )
        return

    # Fetch current prices if executor available
    current_prices = {}
    if executor:
        for pos in positions:
            try:
                ticker = executor.get_ticker(pos.asset)
                if ticker and "price" in ticker:
                    current_prices[pos.asset] = float(ticker["price"])
            except Exception:
                pass

    lines = [
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4ca *OPEN POSITIONS ({len(positions)})*\n"
    ]

    for pos in positions:
        tf = _tf_label(pos.strategy_name)
        asset_tf = f"{pos.asset}({tf})" if tf else pos.asset
        direction_emoji = "\U0001f7e2" if pos.direction == "LONG" else "\U0001f534"
        tp1_tag = " (TP1\u2713)" if pos.tp1_hit else ""
        size_usd = pos.remaining_qty * pos.entry_price

        # Calculate unrealized P&L if we have current price
        unrealized_line = ""
        current_price = current_prices.get(pos.asset)
        if current_price:
            direction_sign = 1.0 if pos.direction == "LONG" else -1.0
            unrealized = (current_price - pos.entry_price) * pos.remaining_qty * direction_sign
            unrealized_pct = ((current_price / pos.entry_price) - 1) * 100 * direction_sign
            u_sign = "+" if unrealized >= 0 else ""
            u_emoji = "\U0001f4c8" if unrealized >= 0 else "\U0001f4c9"
            unrealized_line = (
                f"\n   {u_emoji} *Now:* `${current_price:.2f}` | "
                f"*Unrealized:* `{u_sign}${unrealized:.2f}` (`{u_sign}{unrealized_pct:.1f}%`)"
            )

        # Build TP line if available
        tp_line = ""
        tp1 = pos.metadata.get("tp1_price") if pos.metadata else None
        tp2 = pos.metadata.get("tp2_price") if pos.metadata else None
        if tp1 and tp2:
            tp_line = f"\n   \U0001f3af *TP1:* `${tp1:.2f}` | *TP2:* `${tp2:.2f}`"
        elif tp1:
            tp_line = f"\n   \U0001f3af *TP1:* `${tp1:.2f}`"

        lines.append(
            f"{direction_emoji} `{pos.strategy_name}`{tp1_tag}\n"
            f"   {pos.direction} {asset_tf}\n"
            f"   *Entry:* `${pos.entry_price:.2f}` | *Stop:* `${pos.current_stop:.2f}`"
            f"{unrealized_line}"
            f"{tp_line}\n"
            f"   *Size:* `${size_usd:.2f}` | *Bars:* `{pos.bars_held}`"
        )

    send_telegram("\n\n".join(lines))


def _handle_status(position_manager, risk_manager, equity, regime):
    """Respond with system status summary."""
    lines = [
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4ca *SYSTEM STATUS*\n"
    ]

    if equity is not None and risk_manager is not None:
        starting = risk_manager.starting_equity or equity
        pnl = equity - starting
        pnl_pct = (pnl / starting * 100) if starting > 0 else 0
        pnl_sign = "+" if pnl >= 0 else ""
        target = starting * 1.10
        remaining = max(target - equity, 0)

        phase = risk_manager.determine_phase(equity)
        daily_dd = risk_manager.get_daily_dd(equity) * 100
        total_dd = risk_manager.get_total_dd(equity) * 100
        dd_action = risk_manager.get_dd_action(equity)

        lines.append(f"\U0001f4b0 *Equity:* `${equity:.2f}`")
        lines.append(f"*Starting:* `${starting:.2f}` | *P&L:* `{pnl_sign}${pnl:.2f}` (`{pnl_sign}{pnl_pct:.2f}%`)")
        lines.append(f"\U0001f3af *Target (10%):* `${target:.2f}` | *Remaining:* `${remaining:.2f}`")
        lines.append("")
        lines.append(f"\U0001f6e1 *Phase:* `{phase}` | *DD action:* `{dd_action}`")
        lines.append(f"*Daily DD:* `{daily_dd:.2f}%` | *Total DD:* `{total_dd:.2f}%`")
        lines.append(f"*Losing days:* `{risk_manager.consecutive_losing_days}/5`")
    else:
        lines.append("_Awaiting first data sample..._")

    if regime:
        regime_emoji = {
            "BULLISH": "\U0001f7e2",
            "BEARISH": "\U0001f534",
            "NEUTRAL": "\U0001f7e1",
        }.get(regime, "\u2753")
        lines.append(f"\n{regime_emoji} *Regime gate:* `{regime}`")

    pos_count = len(position_manager.positions)
    regime_counts = position_manager.regime_counts()
    lines.append(f"\U0001f4cb *Positions:* `{pos_count}/8` (bull:{regime_counts.get('bull',0)}/2 side:{regime_counts.get('sideways',0)}/3 bear:{regime_counts.get('bear',0)}/3)")

    send_telegram("\n".join(lines))


def _handle_journal():
    """Respond with trade journal summary from trades.csv."""
    try:
        from DevAntsa_Lab.live_trading.trade_journal import generate_report
        report = generate_report()
        # Telegram 4096 char limit — send as monospace block
        tg_text = report[:3800]
        send_telegram(
            f"{BRAND_HEADER}\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"```\n{tg_text}\n```"
        )
    except FileNotFoundError:
        send_telegram(
            f"{BRAND_HEADER}\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"\U0001f4ad *No trades recorded yet*"
        )
    except Exception as e:
        send_telegram(f"\U0001f6a8 *Journal error:* `{e}`")


def _handle_stats(risk_manager):
    """Respond with lifetime performance statistics."""
    try:
        import csv
        from pathlib import Path

        trades_path = Path(__file__).parent.parent / "data" / "trades.csv"
        if not trades_path.exists():
            send_telegram(
                f"{BRAND_HEADER}\n"
                f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
                f"\U0001f4ad *No trades completed yet*\n"
                f"_Stats available after first closed trade_"
            )
            return

        # Parse trades.csv to calculate stats
        entries = {}  # order_id -> entry row
        completed_trades = []

        with open(trades_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                action = row.get("action", "")
                order_id = row.get("order_id", "")
                strategy = row.get("strategy", "")

                if action == "ENTRY" and order_id:
                    entries[f"{strategy}_{row.get('asset')}"] = row
                elif action in ("EXIT", "PARTIAL_EXIT"):
                    key = f"{strategy}_{row.get('asset')}"
                    entry_row = entries.get(key)
                    if entry_row:
                        entry_price = float(entry_row.get("price", 0) or 0)
                        exit_price = float(row.get("price", 0) or 0)
                        qty = float(row.get("qty", 0) or 0)
                        direction = entry_row.get("direction", "LONG")

                        if entry_price > 0 and exit_price > 0 and qty > 0:
                            direction_sign = 1.0 if direction == "LONG" else -1.0
                            pnl = (exit_price - entry_price) * qty * direction_sign
                            completed_trades.append({
                                "strategy": strategy,
                                "pnl": pnl,
                                "direction": direction,
                            })

                        if action == "EXIT":
                            entries.pop(key, None)

        if not completed_trades:
            send_telegram(
                f"{BRAND_HEADER}\n"
                f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
                f"\U0001f4ad *No completed trades yet*"
            )
            return

        # Calculate statistics
        total_trades = len(completed_trades)
        wins = [t for t in completed_trades if t["pnl"] > 0]
        losses = [t for t in completed_trades if t["pnl"] <= 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

        total_pnl = sum(t["pnl"] for t in completed_trades)
        avg_win = sum(t["pnl"] for t in wins) / win_count if wins else 0
        avg_loss = sum(t["pnl"] for t in losses) / loss_count if losses else 0

        # Expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
        expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss) if total_trades > 0 else 0

        # Sharpe from risk_manager if available
        sharpe_line = ""
        if risk_manager and hasattr(risk_manager, "get_rolling_sharpe"):
            sharpe = risk_manager.get_rolling_sharpe()
            if sharpe is not None:
                sharpe_line = f"\U0001f4c8 *Rolling Sharpe:* `{sharpe:.2f}`\n"
            else:
                trades_needed = 20 - len(risk_manager.trade_returns)
                sharpe_line = f"\U0001f4c8 *Sharpe:* _{trades_needed} more trades needed_\n"

        pnl_sign = "+" if total_pnl >= 0 else ""
        pnl_emoji = "\U0001f4c8" if total_pnl >= 0 else "\U0001f4c9"

        text = (
            f"{BRAND_HEADER}\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"\U0001f4c8 *PERFORMANCE STATS*\n"
            f"\n"
            f"\U0001f4cb *Total Trades:* `{total_trades}`\n"
            f"\u2705 *Wins:* `{win_count}` | \u274c *Losses:* `{loss_count}`\n"
            f"\U0001f3af *Win Rate:* `{win_rate:.1f}%`\n"
            f"\n"
            f"*Avg Win:* `+${avg_win:.2f}`\n"
            f"*Avg Loss:* `${avg_loss:.2f}`\n"
            f"*Expectancy:* `${expectancy:.2f}` per trade\n"
            f"\n"
            f"{sharpe_line}"
            f"{pnl_emoji} *Total P&L:* `{pnl_sign}${total_pnl:.2f}`"
        )
        send_telegram(text)

    except Exception as e:
        logger.warning("Stats calculation failed: %s", e)
        send_telegram(f"\U0001f6a8 *Stats error:* `{e}`")


def _handle_help():
    """Respond with list of available commands."""
    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4d6 *COMMANDS*\n"
        f"\n"
        f"\U0001f4ca `/positions` — Open positions with unrealized P&L\n"
        f"\U0001f4cb `/status` — System status, equity, DD, regime\n"
        f"\U0001f4c8 `/stats` — Performance statistics\n"
        f"\U0001f4d3 `/journal` — Trade history and daily P&L\n"
        f"\U0001f4d6 `/help` — This command list\n"
        f"\n"
        f"_Aliases: /pos, /stat, /perf, /trades, /pnl, /h_\n"
        f"\n"
        f"{BRAND_FOOTER}"
    )
    send_telegram(text)


# ---------------------------------------------------------------------------
# Regime change detection — call from main_loop
# ---------------------------------------------------------------------------

def check_regime_change(new_regime: str) -> None:
    """
    Check if regime has changed and send notification if so.
    Call this from main_loop after getting regime from regime_gate.
    """
    global _previous_regime
    if _previous_regime is None:
        # First run — just store, don't notify
        _previous_regime = new_regime
        return

    if new_regime != _previous_regime:
        notify_regime_change(_previous_regime, new_regime)
        _previous_regime = new_regime


# ---------------------------------------------------------------------------
# Daily summary — call from main_loop at UTC midnight
# ---------------------------------------------------------------------------

def check_daily_summary(
    current_date: str,
    equity: float,
    starting_equity: float,
    trades_csv_path: str = None,
) -> None:
    """
    Check if we've crossed into a new day and send daily summary.
    Call this from main_loop's daily reset check.

    Args:
        current_date: Today's date as "YYYY-MM-DD"
        equity: Current account equity
        starting_equity: Original starting equity (for total P&L)
        trades_csv_path: Optional path to trades.csv
    """
    global _last_summary_date
    import csv
    from pathlib import Path

    if _last_summary_date == current_date:
        return  # Already sent today

    if _last_summary_date is None:
        # First run — don't send summary, just record date
        _last_summary_date = current_date
        return

    # New day! Send summary for previous day
    previous_date = _last_summary_date
    _last_summary_date = current_date

    # Count trades from previous day
    entries = 0
    exits = 0
    realized_pnl = 0.0

    try:
        if trades_csv_path is None:
            trades_csv_path = Path(__file__).parent.parent / "data" / "trades.csv"

        if Path(trades_csv_path).exists():
            entry_prices = {}  # strategy_asset -> entry_price

            with open(trades_csv_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = row.get("timestamp", "")
                    if not ts.startswith(previous_date):
                        continue

                    action = row.get("action", "")
                    strategy = row.get("strategy", "")
                    asset = row.get("asset", "")
                    key = f"{strategy}_{asset}"

                    if action == "ENTRY":
                        entries += 1
                        price = float(row.get("price", 0) or 0)
                        if price > 0:
                            entry_prices[key] = {
                                "price": price,
                                "direction": row.get("direction", "LONG"),
                            }
                    elif action in ("EXIT", "PARTIAL_EXIT"):
                        exits += 1
                        exit_price = float(row.get("price", 0) or 0)
                        qty = float(row.get("qty", 0) or 0)
                        entry_info = entry_prices.get(key)
                        if entry_info and exit_price > 0 and qty > 0:
                            direction_sign = 1.0 if entry_info["direction"] == "LONG" else -1.0
                            pnl = (exit_price - entry_info["price"]) * qty * direction_sign
                            realized_pnl += pnl

    except Exception as e:
        logger.warning("Daily summary trade parsing failed: %s", e)

    # Send summary
    notify_daily_summary(
        date_str=previous_date,
        entries=entries,
        exits=exits,
        realized_pnl=realized_pnl,
        equity=equity,
        starting_equity=starting_equity,
    )


# ---------------------------------------------------------------------------
# Test function — send sample notifications
# ---------------------------------------------------------------------------

def send_test_notifications():
    """Send test notifications to verify Telegram setup and branding."""
    print("Sending test notifications to Telegram...")

    # Test 1: Help command
    _handle_help()
    print("  Sent: /help")

    # Test 2: Sample status
    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4ca *SYSTEM STATUS*\n"
        f"\n"
        f"\U0001f4b0 *Equity:* `$5,030.00`\n"
        f"*Starting:* `$5,000.00` | *P&L:* `+$30.00` (`+0.60%`)\n"
        f"\U0001f3af *Target (10%):* `$5,500.00` | *Remaining:* `$470.00`\n"
        f"\n"
        f"\U0001f6e1 *Phase:* `BUILDING` | *DD action:* `NORMAL`\n"
        f"*Daily DD:* `0.15%` | *Total DD:* `0.00%`\n"
        f"*Losing days:* `0/5`\n"
        f"\n"
        f"\U0001f7e2 *Regime gate:* `NEUTRAL`\n"
        f"\U0001f4cb *Positions:* `1/8` (bull:0/2 side:0/3 bear:1/3)"
    )
    send_telegram(text)
    print("  Sent: Sample /status")

    # Test 3: Sample position with unrealized P&L
    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4ca *OPEN POSITIONS (1)*\n"
        f"\n"
        f"\U0001f534 `StructuralFade`\n"
        f"   SHORT ETHUSDT(4H)\n"
        f"   *Entry:* `$2388.50` | *Stop:* `$2472.84`\n"
        f"   \U0001f4c8 *Now:* `$2310.00` | *Unrealized:* `+$2.35` (`+3.3%`)\n"
        f"   *Size:* `$71.82` | *Bars:* `12`"
    )
    send_telegram(text)
    print("  Sent: Sample /positions")

    # Test 4: Sample stats
    text = (
        f"{BRAND_HEADER}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4c8 *PERFORMANCE STATS*\n"
        f"\n"
        f"\U0001f4cb *Total Trades:* `4`\n"
        f"\u2705 *Wins:* `3` | \u274c *Losses:* `1`\n"
        f"\U0001f3af *Win Rate:* `75.0%`\n"
        f"\n"
        f"*Avg Win:* `+$17.72`\n"
        f"*Avg Loss:* `-$10.30`\n"
        f"*Expectancy:* `$10.64` per trade\n"
        f"\n"
        f"\U0001f4c8 *Sharpe:* _16 more trades needed_\n"
        f"\U0001f4c8 *Total P&L:* `+$42.86`"
    )
    send_telegram(text)
    print("  Sent: Sample /stats")

    print("\nAll test notifications sent!")


if __name__ == "__main__":
    # Run test notifications when executed directly
    send_test_notifications()
