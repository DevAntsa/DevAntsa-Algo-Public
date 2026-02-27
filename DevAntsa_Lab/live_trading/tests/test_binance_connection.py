r"""
Stage 1 Connection Test -- Binance Futures Demo
===============================================
Tests each BinanceExecutor API operation to verify connectivity.

Usage:
    cd C:\Users\anton\MoneyGlich\moon-dev-ai-agents
    python -m src.live_trading.tests.test_binance_connection
"""

from __future__ import annotations
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_binance")


def main():
    logger.info("=" * 70)
    logger.info("Stage 1 Connection Test — Binance Futures Demo")
    logger.info("=" * 70)

    # ── 1. Instantiate executor (triggers _connect: ping + exchangeInfo + equity) ──
    logger.info("\n--- TEST 1: Instantiate BinanceExecutor ---")
    from DevAntsa_Lab.live_trading.execution.binance_executor import BinanceExecutor
    executor = BinanceExecutor()

    passed = 0
    failed = 0
    total = 0

    def check(name: str, fn):
        nonlocal passed, failed, total
        total += 1
        try:
            result = fn()
            logger.info("  PASS: %s → %s", name, result)
            passed += 1
            return result
        except Exception as e:
            logger.error("  FAIL: %s → %s", name, e)
            failed += 1
            return None

    # ── 2. Health check ──
    logger.info("\n--- TEST 2: Health check ---")
    check("check_health()", executor.check_health)

    # ── 3. Get equity ──
    logger.info("\n--- TEST 3: Account equity ---")
    equity = check("get_equity()", executor.get_equity)

    # ── 4. Get wallet balance ──
    logger.info("\n--- TEST 4: Wallet balance ---")
    check("get_wallet_balance()", executor.get_wallet_balance)

    # ── 5. Get margin ratio ──
    logger.info("\n--- TEST 5: Margin ratio ---")
    check("get_margin_ratio()", executor.get_margin_ratio)

    # ── 6. Get OHLCV (SOL 4h) ──
    logger.info("\n--- TEST 6: OHLCV data ---")
    def test_ohlcv_sol():
        df = executor.get_ohlcv("SOLUSDT", "240", limit=5)
        return f"{len(df)} candles, cols={list(df.columns)}, latest={df.iloc[-1]['Timestamp']}"
    check("get_ohlcv('SOLUSDT', '240', 5)", test_ohlcv_sol)

    def test_ohlcv_btc():
        df = executor.get_ohlcv("BTCUSDT", "60", limit=3)
        return f"{len(df)} candles, last close={df.iloc[-1]['Close']}"
    check("get_ohlcv('BTCUSDT', '60', 3)", test_ohlcv_btc)

    def test_ohlcv_eth():
        df = executor.get_ohlcv("ETHUSDT", "240", limit=3)
        return f"{len(df)} candles, last close={df.iloc[-1]['Close']}"
    check("get_ohlcv('ETHUSDT', '240', 3)", test_ohlcv_eth)

    # ── 7. Get ticker ──
    logger.info("\n--- TEST 7: Ticker ---")
    check("get_ticker('SOLUSDT')", lambda: executor.get_ticker("SOLUSDT"))
    check("get_ticker('BTCUSDT')", lambda: executor.get_ticker("BTCUSDT"))

    # ── 8. Get positions (should be empty on fresh demo account) ──
    logger.info("\n--- TEST 8: Positions ---")
    check("get_positions()", executor.get_positions)
    check("get_position('SOLUSDT')", lambda: executor.get_position("SOLUSDT"))

    # ── 9. Get open orders (should be empty) ──
    logger.info("\n--- TEST 9: Open orders ---")
    check("get_open_orders()", executor.get_open_orders)

    # ── 10. Symbol filters ──
    logger.info("\n--- TEST 10: Symbol filters ---")
    for sym in ["SOLUSDT", "BTCUSDT", "ETHUSDT"]:
        check(f"get_symbol_filters('{sym}')", lambda s=sym: executor.get_symbol_filters(s))

    # ── 11. Set leverage (read-only safe — just sets leverage, doesn't trade) ──
    logger.info("\n--- TEST 11: Set leverage ---")
    check("set_leverage('SOLUSDT', 2)", lambda: executor.set_leverage("SOLUSDT", 2))
    check("set_leverage('BTCUSDT', 2)", lambda: executor.set_leverage("BTCUSDT", 2))
    check("set_leverage('ETHUSDT', 2)", lambda: executor.set_leverage("ETHUSDT", 2))

    # ── 12. Set margin type ──
    logger.info("\n--- TEST 12: Set margin type ---")
    check("set_margin_type('SOLUSDT', 'CROSSED')", lambda: executor.set_margin_type("SOLUSDT", "CROSSED"))

    # ── 13. Unrealized PnL ──
    logger.info("\n--- TEST 13: Unrealized PnL ---")
    check("get_unrealized_pnl()", executor.get_unrealized_pnl)

    # ── 14. Round-trip trade test: market order → algo stop → cancel → close ──
    logger.info("\n--- TEST 14: Trade round-trip (SOL) ---")
    def test_trade_roundtrip():
        # Place a small market buy (1 SOL ≈ $112)
        order = executor.place_market_order("SOLUSDT", "BUY", 1.0)
        entry_id = order.get("orderId")
        # Demo market orders return avgPrice=0.00, so use ticker for stop calc
        ticker = executor.get_ticker("SOLUSDT")
        current_price = ticker["price"]
        # Place algo stop-loss 5% below current price
        stop_price = executor._round_price("SOLUSDT", current_price * 0.95)
        stop = executor.place_stop_loss("SOLUSDT", "SELL", stop_price, 1.0)
        algo_id = stop.get("algoId", "")
        # Cancel the stop
        executor.cancel_algo_order("SOLUSDT", str(algo_id))
        # Close position
        executor.close_position("SOLUSDT")
        return f"entry={entry_id} price={current_price} stop_algoId={algo_id} → closed"
    check("trade_roundtrip(SOL)", test_trade_roundtrip)

    # ── Summary ──
    print()
    print("=" * 70)
    print(f"RESULTS: {passed}/{total} passed, {failed}/{total} failed")
    print(f"VERDICT: {'ALL PASS' if failed == 0 else 'SOME FAILED'}")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
