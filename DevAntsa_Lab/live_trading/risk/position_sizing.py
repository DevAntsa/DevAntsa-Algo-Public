"""
Position Sizing
===============
Plan Part 4 - MASTER POSITION SIZING FORMULA (Same for all regimes):

    risk_based_position     = (account_equity * risk_pct) / stop_distance_pct
    leverage_based_position = account_equity * leverage
    position_size           = min(risk_based_position, leverage_based_position)

Example from plan:
    $100K account, 0.5% risk, 2.5% stop, 2x leverage
    Risk-based:     ($100,000 * 0.005) / 0.025 = $20,000
    Leverage-based: $100,000 * 2 = $200,000
    Use: $20,000 (safer option)
"""


def calculate_position_size(
    account_equity: float,
    risk_pct: float,
    stop_distance_pct: float,
    leverage: float,
) -> float:
    """
    Calculate position size based on risk and leverage constraints.
    IDENTICAL for bull, bear, and sideways strategies.

    Copied verbatim from Plan Part 4.

    Args:
        account_equity:    Total account value in USD.
        risk_pct:          Risk per trade as decimal (0.005 = 0.5%).
        stop_distance_pct: Stop loss distance as decimal (0.025 = 2.5%).
        leverage:          Target leverage (e.g., 2.0).

    Returns:
        Dollar value of the position (notional).
    """
    if stop_distance_pct <= 0:
        raise ValueError("stop_distance_pct must be > 0")

    # Risk-based position (primary)
    risk_based_position = (account_equity * risk_pct) / stop_distance_pct

    # Leverage-based position (secondary)
    leverage_based_position = account_equity * leverage

    # Take the SMALLER of the two (safety first)
    position_size = min(risk_based_position, leverage_based_position)

    # TODO [REGIME SELECTION]: this function receives a single `leverage` value but
    #   the plan has TWO leverage constraints: phase-based leverage (from RiskManager)
    #   and per-strategy leverage cap (from STRATEGY_LEVERAGE_CAPS). The caller must
    #   pass min(phase_leverage, strategy_cap) — this is not enforced here.
    # TODO [EXECUTION]: position_size is notional USD, but Binance enforces per-symbol
    #   minimum order size and step size. The returned value may be below the minimum
    #   or need rounding. This must be handled before order placement.

    return position_size


def position_size_to_quantity(
    position_size_usd: float,
    entry_price: float,
) -> float:
    """
    Convert USD position size to asset quantity (for exchange order).

    Args:
        position_size_usd: Dollar value from calculate_position_size()
        entry_price:       Current price of the asset

    Returns:
        Quantity of the asset to trade.
    """
    if entry_price <= 0:
        raise ValueError("entry_price must be > 0")
    return position_size_usd / entry_price
