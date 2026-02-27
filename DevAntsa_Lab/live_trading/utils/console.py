"""
Rich Console Logger — DevAntsa Lab
===================================
Beautiful terminal output for the live trading system.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme
from rich.logging import RichHandler
from rich.live import Live
from rich.layout import Layout
from datetime import datetime
import logging

# Custom theme for trading
TRADING_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
    "success": "green",
    "entry_long": "green bold",
    "entry_short": "red bold",
    "exit_win": "green",
    "exit_loss": "red",
    "tp_hit": "cyan bold",
    "stop_loss": "red",
    "strategy": "magenta",
    "asset": "yellow",
    "price": "white",
    "equity": "cyan",
    "regime_bull": "green",
    "regime_bear": "red",
    "regime_neutral": "yellow",
})

console = Console(theme=TRADING_THEME)

# Brand
BRAND = "[bold cyan]🐜🧪 DevAntsa Lab[/bold cyan]"


def setup_rich_logging():
    """Configure logging to use Rich handler."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(
            console=console,
            rich_tracebacks=True,
            show_path=False,
            markup=True,
        )]
    )


def print_banner():
    """Print startup banner."""
    banner = Panel(
        Text.from_markup(
            f"{BRAND}\n"
            "[dim]Precision trading, systematic execution[/dim]\n\n"
            "[cyan]15 Strategies[/cyan] • [green]6 Bull[/green] • [red]9 Bear[/red] • [dim]Portfolio v10[/dim]"
        ),
        title="[bold white]Live Trading System[/bold white]",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(banner)
    console.print()


def print_status_table(
    equity: float,
    starting_equity: float,
    phase: str,
    regime: str,
    positions: int,
    daily_dd: float,
    total_dd: float,
    losing_days: int,
):
    """Print a status table at the start of each tick."""
    pnl = equity - starting_equity
    pnl_pct = (pnl / starting_equity * 100) if starting_equity > 0 else 0
    pnl_sign = "+" if pnl >= 0 else ""
    pnl_color = "green" if pnl >= 0 else "red"

    regime_color = {
        "BULLISH": "regime_bull",
        "BEARISH": "regime_bear",
        "NEUTRAL": "regime_neutral",
    }.get(regime, "white")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value")
    table.add_column("Label", style="dim")
    table.add_column("Value")

    table.add_row(
        "Equity", f"[equity]${equity:,.2f}[/equity]",
        "P&L", f"[{pnl_color}]{pnl_sign}${pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%)[/{pnl_color}]",
    )
    table.add_row(
        "Phase", f"[white]{phase}[/white]",
        "Regime", f"[{regime_color}]{regime}[/{regime_color}]",
    )
    table.add_row(
        "Positions", f"[white]{positions}/15[/white]",
        "DD", f"[yellow]Daily: {daily_dd:.2f}% | Total: {total_dd:.2f}%[/yellow]",
    )

    panel = Panel(
        table,
        title=f"[bold]{BRAND}[/bold]",
        subtitle=f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
        border_style="cyan",
    )
    console.print(panel)


def log_entry(strategy: str, direction: str, asset: str, price: float, stop: float, size_usd: float, leverage: float):
    """Log a new entry."""
    dir_style = "entry_long" if direction == "LONG" else "entry_short"
    dir_emoji = "🟢" if direction == "LONG" else "🔴"

    console.print(
        f"  {dir_emoji} [{dir_style}]ENTRY[/{dir_style}]  "
        f"[strategy]{strategy}[/strategy]  "
        f"[{dir_style}]{direction}[/{dir_style}] [asset]{asset}[/asset]  "
        f"@ [price]${price:,.2f}[/price]  "
        f"Stop: [price]${stop:,.2f}[/price]  "
        f"Size: [price]${size_usd:,.2f}[/price]  "
        f"Lev: [dim]{leverage:.1f}x[/dim]"
    )


def log_exit(strategy: str, direction: str, asset: str, entry_price: float, exit_price: float, pnl: float, reason: str):
    """Log a position close."""
    pnl_color = "exit_win" if pnl >= 0 else "exit_loss"
    pnl_emoji = "✅" if pnl >= 0 else "❌"
    pnl_sign = "+" if pnl >= 0 else ""

    console.print(
        f"  {pnl_emoji} [{pnl_color}]EXIT[/{pnl_color}]   "
        f"[strategy]{strategy}[/strategy]  "
        f"[asset]{asset}[/asset]  "
        f"[price]${entry_price:,.2f}[/price] → [price]${exit_price:,.2f}[/price]  "
        f"[{pnl_color}]{pnl_sign}${pnl:,.2f}[/{pnl_color}]  "
        f"[dim]({reason})[/dim]"
    )


def log_partial_exit(strategy: str, asset: str, price: float, pnl: float, reason: str):
    """Log a partial close (TP1)."""
    console.print(
        f"  🎯 [tp_hit]TP HIT[/tp_hit]  "
        f"[strategy]{strategy}[/strategy]  "
        f"[asset]{asset}[/asset]  "
        f"@ [price]${price:,.2f}[/price]  "
        f"[green]+${pnl:,.2f}[/green]  "
        f"[dim]({reason})[/dim]"
    )


def log_stop_placed(asset: str, stop_price: float):
    """Log stop loss placement."""
    console.print(
        f"  🛑 [dim]STOP[/dim]    "
        f"[asset]{asset}[/asset] @ [price]${stop_price:,.2f}[/price]"
    )


def log_stop_updated(asset: str, old_stop: float, new_stop: float):
    """Log trailing stop update."""
    console.print(
        f"  📈 [dim]TRAIL[/dim]   "
        f"[asset]{asset}[/asset]  "
        f"[dim]${old_stop:,.2f}[/dim] → [price]${new_stop:,.2f}[/price]"
    )


def log_signal_skip(strategy: str, reason: str):
    """Log a skipped signal."""
    console.print(
        f"  ⏭️  [dim]SKIP[/dim]    "
        f"[strategy]{strategy}[/strategy]  "
        f"[dim]{reason}[/dim]"
    )


def log_regime_change(old_regime: str, new_regime: str):
    """Log regime change."""
    old_color = {"BULLISH": "green", "BEARISH": "red", "NEUTRAL": "yellow"}.get(old_regime, "white")
    new_color = {"BULLISH": "green", "BEARISH": "red", "NEUTRAL": "yellow"}.get(new_regime, "white")

    console.print(
        f"\n  🔄 [bold]REGIME CHANGE[/bold]  "
        f"[{old_color}]{old_regime}[/{old_color}] → [{new_color}]{new_regime}[/{new_color}]\n"
    )


def log_tick_start(tick_num: int, eligible_strategies: list):
    """Log start of a tick."""
    strats = ", ".join(eligible_strategies) if eligible_strategies else "none"
    console.print(
        f"\n[dim]{'─' * 60}[/dim]\n"
        f"[bold cyan]TICK {tick_num}[/bold cyan]  "
        f"[dim]Eligible: {strats}[/dim]"
    )


def log_sleep(seconds: int):
    """Log sleep message."""
    console.print(f"\n[dim]💤 Sleeping {seconds}s until next bar...[/dim]\n")


def log_emergency(strategy: str, asset: str, reason: str):
    """Log emergency close."""
    console.print(
        f"  🚨 [error]EMERGENCY[/error]  "
        f"[strategy]{strategy}[/strategy]  "
        f"[asset]{asset}[/asset]  "
        f"[error]{reason}[/error]"
    )


def log_kill_switch(reason: str):
    """Log kill switch trigger."""
    console.print(
        Panel(
            f"[bold red]KILL SWITCH TRIGGERED[/bold red]\n\n"
            f"Reason: [white]{reason}[/white]\n\n"
            f"[dim]All positions closed. Manual restart required.[/dim]",
            title="🚨 SYSTEM HALT 🚨",
            border_style="red",
        )
    )


def log_info(message: str):
    """Log an info message."""
    console.print(f"  [dim]ℹ️  {message}[/dim]")


def log_warning(message: str):
    """Log a warning message."""
    console.print(f"  [warning]⚠️  {message}[/warning]")


def log_error(message: str):
    """Log an error message."""
    console.print(f"  [error]❌ {message}[/error]")


def print_positions_table(positions: list):
    """Print a table of open positions."""
    if not positions:
        console.print("[dim]No open positions[/dim]")
        return

    table = Table(title="Open Positions", border_style="cyan")
    table.add_column("Strategy", style="strategy")
    table.add_column("Dir", justify="center")
    table.add_column("Asset", style="asset")
    table.add_column("Entry", justify="right", style="price")
    table.add_column("Stop", justify="right")
    table.add_column("Bars", justify="center")
    table.add_column("Size", justify="right")

    for pos in positions:
        dir_style = "green" if pos.direction == "LONG" else "red"
        table.add_row(
            pos.strategy_name,
            f"[{dir_style}]{pos.direction}[/{dir_style}]",
            pos.asset,
            f"${pos.entry_price:,.2f}",
            f"${pos.current_stop:,.2f}",
            str(pos.bars_held),
            f"${pos.remaining_qty * pos.entry_price:,.2f}",
        )

    console.print(table)
