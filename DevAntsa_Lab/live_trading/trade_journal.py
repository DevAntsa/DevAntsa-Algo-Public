"""
Trade Journal
=============
Parses trades.csv and generates daily P&L summaries + strategy breakdowns.

Usage:
    python -m src.live_trading.trade_journal
    python -m src.live_trading.trade_journal --telegram
"""

from __future__ import annotations
import argparse
import sys
from datetime import datetime

import pandas as pd

from DevAntsa_Lab.live_trading.config import TRADE_LOG_FILE


def load_trades() -> pd.DataFrame:
    """Load trades.csv into a DataFrame."""
    df = pd.read_csv(TRADE_LOG_FILE, parse_dates=["timestamp"])
    df["date"] = df["timestamp"].dt.date
    return df


def match_trades(df: pd.DataFrame) -> pd.DataFrame:
    """
    Match ENTRY rows with their EXIT/PARTIAL_EXIT rows by strategy+asset.
    Returns a DataFrame of closed trades with realized P&L.
    """
    entries = {}  # (strategy, asset) -> entry row
    closed = []

    for _, row in df.iterrows():
        key = (row["strategy"], row["asset"])

        if row["action"] == "ENTRY":
            entries[key] = row
        elif row["action"] in ("EXIT", "PARTIAL_EXIT", "EMERGENCY_CLOSE"):
            entry = entries.get(key)
            if entry is None:
                continue

            direction_sign = 1.0 if entry["direction"] == "LONG" else -1.0
            exit_price = float(row["price"]) if row["price"] else 0.0
            entry_price = float(entry["price"]) if entry["price"] else 0.0
            qty = float(row["qty"]) if row["qty"] else 0.0

            pnl = (exit_price - entry_price) * qty * direction_sign

            closed.append({
                "date": row["date"],
                "strategy": row["strategy"],
                "asset": row["asset"],
                "direction": entry["direction"],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "qty": qty,
                "pnl": pnl,
                "reason": row.get("reason", ""),
                "bars_held": None,
            })

            # Remove entry on full close; keep on partial
            if row["action"] == "EXIT" or row["action"] == "EMERGENCY_CLOSE":
                entries.pop(key, None)

    closed_df = pd.DataFrame(closed) if closed else pd.DataFrame(
        columns=["date", "strategy", "asset", "direction", "entry_price",
                 "exit_price", "qty", "pnl", "reason", "bars_held"]
    )
    open_entries = entries
    return closed_df, open_entries


def daily_summary(df: pd.DataFrame, closed: pd.DataFrame) -> str:
    """Generate daily summary table."""
    entries_by_date = df[df["action"] == "ENTRY"].groupby("date").size()
    exits_by_date = df[df["action"].isin(["EXIT", "PARTIAL_EXIT", "EMERGENCY_CLOSE"])].groupby("date").size()

    if closed.empty:
        pnl_by_date = pd.Series(dtype=float)
    else:
        pnl_by_date = closed.groupby("date")["pnl"].sum()

    all_dates = sorted(set(entries_by_date.index) | set(exits_by_date.index) | set(pnl_by_date.index))

    lines = ["Daily Summary:"]
    lines.append(f"  {'Date':<14}{'Entries':>8}{'Exits':>8}{'Realized P&L':>14}")
    for d in all_dates:
        e = entries_by_date.get(d, 0)
        x = exits_by_date.get(d, 0)
        p = pnl_by_date.get(d, 0.0)
        lines.append(f"  {str(d):<14}{e:>8}{x:>8}{'${:.2f}'.format(p):>14}")

    return "\n".join(lines)


def strategy_breakdown(closed: pd.DataFrame, open_entries: dict) -> str:
    """Generate per-strategy breakdown."""
    lines = ["Strategy Breakdown:"]
    lines.append(f"  {'Strategy':<28}{'Trades':>7}{'Wins':>6}{'Losses':>8}{'Total P&L':>12}")

    all_strategies = set()
    if not closed.empty:
        all_strategies |= set(closed["strategy"].unique())
    all_strategies |= {key[0] for key in open_entries}

    for strat in sorted(all_strategies):
        strat_trades = closed[closed["strategy"] == strat] if not closed.empty else pd.DataFrame()

        if strat_trades.empty and (strat, ) not in {(k[0],) for k in open_entries}:
            continue

        n = len(strat_trades)
        wins = (strat_trades["pnl"] > 0).sum() if n > 0 else 0
        losses = (strat_trades["pnl"] < 0).sum() if n > 0 else 0
        total_pnl = strat_trades["pnl"].sum() if n > 0 else 0.0

        # Check if strategy has open position
        has_open = any(k[0] == strat for k in open_entries)

        if n == 0 and has_open:
            lines.append(f"  {strat:<28}{n:>7}{wins:>6}{losses:>8}{'(open)':>12}")
        else:
            lines.append(f"  {strat:<28}{n:>7}{wins:>6}{losses:>8}{'${:.2f}'.format(total_pnl):>12}")

    return "\n".join(lines)


def open_positions_section(df: pd.DataFrame, open_entries: dict) -> str:
    """List currently open positions."""
    if not open_entries:
        return "Open Positions: 0"

    lines = [f"Open Positions: {len(open_entries)}"]
    for (strat, asset), entry in open_entries.items():
        price = float(entry["price"]) if entry["price"] else 0.0
        direction = entry["direction"]
        lines.append(f"  {strat} {direction} {asset} @ ${price:.2f}")

    return "\n".join(lines)


def account_summary(closed: pd.DataFrame) -> str:
    """Fetch live equity from Binance and show alongside realized P&L."""
    total_realized = closed["pnl"].sum() if not closed.empty else 0.0

    lines = ["Account:"]
    try:
        from DevAntsa_Lab.live_trading.execution.binance_executor import BinanceExecutor
        executor = BinanceExecutor()
        equity = executor.get_equity()
        starting = 5000.0  # demo starting balance
        total_pnl = equity - starting
        pnl_sign = "+" if total_pnl >= 0 else ""
        pnl_pct = (total_pnl / starting * 100) if starting > 0 else 0

        lines.append(f"  Equity:       ${equity:.2f}")
        lines.append(f"  Starting:     ${starting:.2f}")
        lines.append(f"  Total P&L:    {pnl_sign}${total_pnl:.2f} ({pnl_sign}{pnl_pct:.2f}%)")
        lines.append(f"  Realized:     ${total_realized:.2f}")
        lines.append(f"  Unrealized:   ${total_pnl - total_realized:.2f}")
    except Exception:
        lines.append(f"  Realized P&L: ${total_realized:.2f}")
        lines.append(f"  (Could not fetch live equity)")

    return "\n".join(lines)


def generate_report(send_tg: bool = False) -> str:
    """Generate the full trade journal report."""
    df = load_trades()

    if df.empty:
        return "No trades found in trades.csv"

    min_date = df["date"].min()
    max_date = df["date"].max()

    closed, open_entries = match_trades(df)

    sections = [
        f"=== Trade Journal: {min_date} to {max_date} ===",
        "",
        account_summary(closed),
        "",
        daily_summary(df, closed),
        "",
        strategy_breakdown(closed, open_entries),
        "",
        open_positions_section(df, open_entries),
    ]

    report = "\n".join(sections)

    if send_tg:
        from DevAntsa_Lab.live_trading.notifications.telegram_notifier import send_telegram
        # Telegram has 4096 char limit; truncate if needed
        tg_text = report[:3900]
        send_telegram(f"```\n{tg_text}\n```")

    return report


def main():
    parser = argparse.ArgumentParser(description="Trade Journal - daily P&L summary")
    parser.add_argument("--telegram", action="store_true", help="Send summary via Telegram")
    args = parser.parse_args()

    report = generate_report(send_tg=args.telegram)
    print(report)


if __name__ == "__main__":
    main()
