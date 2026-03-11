"""
Binance Executor
================
Bootstrap Plan Stage 1: Binance Futures Demo API Execution.

Uses raw `requests` library — no extra dependencies (python-binance, ccxt).

Wraps the Binance USDS-M Futures API to provide:
    - Connection management (demo vs production)
    - Market orders, stop orders, modifications
    - Open positions, P&L, margin
    - Equity, daily P&L, health checks
    - OHLCV candles for indicator calculation

Config:
    BINANCE_FUTURES_DEMO = True   →  demo-fapi.binance.com  (Stages 1-3)
    BINANCE_FUTURES_DEMO = False  →  fapi.binance.com       (Stage 4+)

Environment variables (loaded from .env):
    BINANCE_FUTURES_API_KEY
    BINANCE_FUTURES_API_SECRET

Authentication: HMAC SHA256 signature, API key via X-MBX-APIKEY header.
"""

from __future__ import annotations
from typing import Dict, List, Optional
import os
import logging
import hashlib
import hmac
import time
import math
import requests
import pandas as pd
from dotenv import load_dotenv

from DevAntsa_Lab.live_trading.config import (
    BINANCE_FUTURES_DEMO,
    BINANCE_BASE_URL,
    BINANCE_MARGIN_TYPE,
)

load_dotenv()
logger = logging.getLogger(__name__)

# Map our internal interval strings (minutes) to Binance kline intervals
INTERVAL_MAP = {
    "1": "1m",
    "3": "3m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "120": "2h",
    "240": "4h",
    "360": "6h",
    "480": "8h",
    "720": "12h",
    "D": "1d",
    "W": "1w",
    # Also accept Binance-native strings directly
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h",
    "12h": "12h", "1d": "1d", "1w": "1w",
}

# Request timeout in seconds
REQUEST_TIMEOUT = 10


class BinanceExecutor:
    """
    Unified Binance USDS-M Futures API interface.
    All exchange interaction goes through this class.

    Uses requests library with HMAC SHA256 authentication.
    """

    def __init__(self) -> None:
        self.demo = BINANCE_FUTURES_DEMO
        self.base_url = BINANCE_BASE_URL
        self.api_key = os.getenv("BINANCE_FUTURES_API_KEY")
        self.api_secret = os.getenv("BINANCE_FUTURES_API_SECRET")
        self._symbol_filters: Dict[str, Dict] = {}
        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": self.api_key or ""})
        self._connect()

    # ── Internal Helpers ──────────────────────────────────────────────

    def _timestamp(self) -> int:
        """Current time in milliseconds (Binance requires ms timestamps)."""
        return int(time.time() * 1000)

    def _sign(self, params: Dict) -> str:
        """Create HMAC SHA256 signature for request parameters."""
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _signed_params(self, params: Optional[Dict] = None) -> Dict:
        """Add timestamp and signature to params dict."""
        p = params.copy() if params else {}
        p["timestamp"] = self._timestamp()
        p["signature"] = self._sign(p)
        return p

    def _get(self, path: str, params: Optional[Dict] = None, signed: bool = False) -> Dict:
        """
        Signed or unsigned GET request.
        Raises on HTTP errors or Binance API error codes.
        """
        url = f"{self.base_url}{path}"
        if signed:
            params = self._signed_params(params)
        resp = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        return self._handle_response(resp)

    def _post(self, path: str, params: Optional[Dict] = None) -> Dict:
        """Signed POST request."""
        url = f"{self.base_url}{path}"
        params = self._signed_params(params)
        resp = self._session.post(url, params=params, timeout=REQUEST_TIMEOUT)
        return self._handle_response(resp)

    def _delete(self, path: str, params: Optional[Dict] = None) -> Dict:
        """Signed DELETE request."""
        url = f"{self.base_url}{path}"
        params = self._signed_params(params)
        resp = self._session.delete(url, params=params, timeout=REQUEST_TIMEOUT)
        return self._handle_response(resp)

    def _handle_response(self, resp: requests.Response) -> Dict:
        """
        Parse JSON response. Raise on HTTP errors or Binance error codes.
        Binance returns {"code": -XXXX, "msg": "..."} on errors even with HTTP 200.
        """
        data = resp.json()
        # Binance error format: {"code": -1XXX, "msg": "..."}
        if isinstance(data, dict) and "code" in data and int(data["code"]) < 0:
            code = int(data["code"])
            msg = data.get("msg", "")
            # -4046 "No need to change margin type" is expected and handled by caller
            if code == -4046:
                logger.debug("Binance API: %s %s", code, msg)
            else:
                logger.error("Binance API error: %s %s", code, msg)
            raise RuntimeError(f"Binance API error {code}: {msg}")
        resp.raise_for_status()
        return data

    def _to_binance_interval(self, interval: str) -> str:
        """Convert our interval string (e.g. '240') to Binance format ('4h')."""
        result = INTERVAL_MAP.get(interval)
        if result is None:
            raise ValueError(f"Unknown interval '{interval}'. Valid: {list(INTERVAL_MAP.keys())}")
        return result

    def _round_qty(self, symbol: str, qty: float) -> float:
        """Round quantity to symbol's step size."""
        filt = self._symbol_filters.get(symbol)
        if filt is None:
            logger.warning("No filters cached for %s — using raw qty", symbol)
            return qty
        step = filt.get("stepSize", 0.001)
        if step <= 0:
            return qty
        precision = int(round(-math.log10(step)))
        return round(math.floor(qty / step) * step, precision)

    def _round_price(self, symbol: str, price: float) -> float:
        """Round price to symbol's tick size."""
        filt = self._symbol_filters.get(symbol)
        if filt is None:
            return round(price, 2)
        tick = filt.get("tickSize", 0.01)
        if tick <= 0:
            return round(price, 2)
        precision = int(round(-math.log10(tick)))
        return round(math.floor(price / tick) * tick, precision)

    # ── Connection ────────────────────────────────────────────────────

    def _connect(self) -> None:
        """Validate credentials, ping API, and cache exchange info."""
        if not self.api_key or not self.api_secret:
            logger.error("BINANCE_FUTURES_API_KEY or BINANCE_FUTURES_API_SECRET not set in .env")
            return

        # Ping
        try:
            self._get("/fapi/v1/ping")
            logger.info("Binance Futures API reachable (%s)", self.base_url)
        except Exception as e:
            logger.error("Binance ping failed: %s", e)
            return

        # Fetch exchange info and cache symbol filters
        try:
            info = self._get("/fapi/v1/exchangeInfo")
            for sym_info in info.get("symbols", []):
                symbol = sym_info["symbol"]
                filters = {}
                for f in sym_info.get("filters", []):
                    if f["filterType"] == "LOT_SIZE":
                        filters["stepSize"] = float(f["stepSize"])
                        filters["minQty"] = float(f["minQty"])
                        filters["maxQty"] = float(f["maxQty"])
                    elif f["filterType"] == "PRICE_FILTER":
                        filters["tickSize"] = float(f["tickSize"])
                        filters["minPrice"] = float(f["minPrice"])
                    elif f["filterType"] == "MIN_NOTIONAL":
                        filters["minNotional"] = float(f.get("notional", f.get("minNotional", 0)))
                self._symbol_filters[symbol] = filters

            cached = [s for s in ["SOLUSDT", "BTCUSDT", "ETHUSDT"] if s in self._symbol_filters]
            logger.info(
                "Cached filters for %d symbols (our assets: %s)",
                len(self._symbol_filters),
                cached,
            )
        except Exception as e:
            logger.error("Failed to fetch exchangeInfo: %s", e)

        # Verify account access with a signed request
        try:
            self.get_equity()
            logger.info(
                "BinanceExecutor connected (demo=%s, base_url=%s)",
                self.demo,
                self.base_url,
            )
        except Exception as e:
            logger.error("Account access check failed: %s", e)

    # ── DataFetcher ───────────────────────────────────────────────────

    def get_ohlcv(
        self,
        symbol: str,
        interval: str = "240",
        limit: int = 200,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candle data from Binance Futures.

        Args:
            symbol:   e.g. "SOLUSDT"
            interval: Internal interval string ("60", "240") or Binance ("1h", "4h")
            limit:    Number of candles (max 1500)

        Returns:
            DataFrame with columns: Timestamp, Open, High, Low, Close, Volume
            Sorted chronologically (oldest first).
        """
        binance_interval = self._to_binance_interval(interval)
        params = {
            "symbol": symbol,
            "interval": binance_interval,
            "limit": min(limit, 1500),
        }
        # klines endpoint is public — no signature needed
        data = self._get("/fapi/v1/klines", params=params, signed=False)

        if not data:
            raise RuntimeError(f"Empty klines response for {symbol} {interval}")

        # Response format: list of lists
        # [open_time, open, high, low, close, volume, close_time,
        #  quote_volume, trades, taker_buy_base, taker_buy_quote, ignore]
        rows = []
        for candle in data:
            rows.append({
                "Timestamp": pd.Timestamp(candle[0], unit="ms", tz="UTC"),
                "Open": float(candle[1]),
                "High": float(candle[2]),
                "Low": float(candle[3]),
                "Close": float(candle[4]),
                "Volume": float(candle[5]),
            })

        df = pd.DataFrame(rows)
        # Binance returns oldest-first — already chronological.
        # Drop the last row: it's the in-progress candle (not yet closed).
        # Strategies must evaluate on CLOSED bars only, matching backtests.
        if len(df) > 1:
            df = df.iloc[:-1].reset_index(drop=True)
        return df

    def get_ticker(self, symbol: str) -> Dict:
        """
        Get current price, 24h volume, 24h change for a symbol.

        Returns:
            {"price": float, "volume_24h": float, "change_24h_pct": float}
        """
        data = self._get("/fapi/v1/ticker/24hr", params={"symbol": symbol})
        return {
            "price": float(data["lastPrice"]),
            "volume_24h": float(data["quoteVolume"]),
            "change_24h_pct": float(data["priceChangePercent"]),
        }

    # ── OrderManager ──────────────────────────────────────────────────

    def _wait_for_fill(self, symbol: str, order_id: int, max_wait: float = 10.0) -> Dict:
        """
        Poll order status until filled or timeout.

        Binance Demo may return status=NEW for market orders that haven't
        matched yet. This method polls until FILLED or max_wait seconds.

        Returns:
            Updated order dict (with status, avgPrice, executedQty, etc.)
        """
        import time as _time
        poll_interval = 1.0
        waited = 0.0
        while waited < max_wait:
            _time.sleep(poll_interval)
            waited += poll_interval
            try:
                result = self._get(
                    "/fapi/v1/order",
                    params={"symbol": symbol, "orderId": order_id},
                    signed=True,
                )
                status = result.get("status", "")
                if status in ("FILLED", "CANCELED", "REJECTED", "EXPIRED"):
                    logger.info("Order %s %s final status: %s avgPrice=%s",
                                order_id, symbol, status, result.get("avgPrice"))
                    return result
            except Exception as e:
                logger.warning("Poll order %s failed: %s", order_id, e)
        logger.warning("Order %s %s still not filled after %.0fs", order_id, symbol, max_wait)
        # Return last known state
        try:
            return self._get(
                "/fapi/v1/order",
                params={"symbol": symbol, "orderId": order_id},
                signed=True,
            )
        except Exception:
            return {"status": "UNKNOWN", "avgPrice": "0"}

    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        reduce_only: bool = False,
    ) -> Dict:
        """
        Place a market order.

        Args:
            symbol:      e.g. "SOLUSDT"
            side:        "BUY" or "SELL"
            qty:         Quantity in base asset (will be rounded to step size)
            reduce_only: If True, order can only reduce an existing position.
                         Bypasses minimum notional requirement and prevents
                         accidentally opening a new position.

        Returns:
            Order response dict with orderId, status, avgPrice, etc.
            On Binance Demo, waits up to 10s for fill if status=NEW.
        """
        rounded_qty = self._round_qty(symbol, qty)
        if rounded_qty <= 0:
            raise ValueError(f"Qty rounds to 0 for {symbol}: raw={qty}")

        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": rounded_qty,
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        result = self._post("/fapi/v1/order", params)
        logger.info(
            "Market order: %s %s qty=%s orderId=%s status=%s avgPrice=%s",
            side, symbol, rounded_qty,
            result.get("orderId"), result.get("status"),
            result.get("avgPrice", "N/A"),
        )

        # Binance Demo: market orders may return status=NEW (not yet filled).
        # Poll until filled so callers get accurate avgPrice.
        order_id = result.get("orderId")
        if result.get("status") == "NEW" and order_id:
            logger.info("Order %s status=NEW, waiting for fill...", order_id)
            result = self._wait_for_fill(symbol, order_id, max_wait=10.0)

        return result

    def place_stop_loss(
        self,
        symbol: str,
        side: str,
        trigger_price: float,
        qty: float,
    ) -> Dict:
        """
        Place a stop-loss order (STOP_MARKET via Algo Order API).

        Since 2025-12-09, Binance requires STOP_MARKET orders to go through
        the /fapi/v1/algoOrder endpoint (returns -4120 on the old endpoint).

        Args:
            symbol:        e.g. "SOLUSDT"
            side:          "BUY" (to close short) or "SELL" (to close long)
            trigger_price: Price at which stop triggers
            qty:           Quantity to close

        Returns:
            Order response dict with algoId.
        """
        rounded_qty = self._round_qty(symbol, qty)
        rounded_price = self._round_price(symbol, trigger_price)

        params = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side.upper(),
            "type": "STOP_MARKET",
            "triggerPrice": rounded_price,
            "quantity": rounded_qty,
            "reduceOnly": "true",
            "workingType": "CONTRACT_PRICE",
        }
        result = self._post("/fapi/v1/algoOrder", params)
        algo_id = result.get("algoId", result.get("orderId", ""))
        logger.info(
            "Algo stop loss: %s %s @ %s qty=%s → algoId=%s",
            side, symbol, rounded_price, rounded_qty, algo_id,
        )
        return result

    def modify_stop_loss(
        self,
        symbol: str,
        stop_order_id: str,
        new_trigger_price: float,
        qty: float,
    ) -> Dict:
        """
        Modify an existing stop-loss trigger price (for trailing stops).
        Binance doesn't support modifying algo orders — place new FIRST, then cancel old.

        H-2: Atomic approach — new stop is placed before old is cancelled.
        If new placement fails, old stop stays active (position never unprotected).
        Worst case: both stops active briefly (both reduceOnly, safe).

        Returns:
            New order response dict (with algoId).
        """
        # Determine side from current position direction
        pos = self.get_position(symbol)
        if pos is None:
            raise RuntimeError(f"No position for {symbol}, cannot set stop loss")
        pos_amt = float(pos["positionAmt"])
        stop_side = "SELL" if pos_amt > 0 else "BUY"

        # Place new stop FIRST — old stop stays as safety net
        new_result = self.place_stop_loss(
            symbol, stop_side, new_trigger_price,
            abs(pos_amt) if qty == 0 else qty,
        )

        # Verify new stop accepted (check for algoId in response)
        new_algo_id = new_result.get("algoId")
        if not new_algo_id:
            raise RuntimeError(f"New stop placement returned no algoId: {new_result}")

        # New stop is live — now safe to cancel old one
        try:
            self.cancel_algo_order(symbol, stop_order_id)
        except Exception as e:
            # Old stop still active — two stops now (redundant but safe,
            # both are reduceOnly so whichever hits first closes position)
            logger.warning(
                "Failed to cancel old stop %s on %s: %s (new stop %s is active)",
                stop_order_id, symbol, e, new_algo_id,
            )

        return new_result

    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """Cancel an open regular order by orderId."""
        params = {
            "symbol": symbol,
            "orderId": order_id,
        }
        result = self._delete("/fapi/v1/order", params)
        logger.info("Cancelled order %s on %s", order_id, symbol)
        return result

    def cancel_algo_order(self, symbol: str, algo_id: str) -> Dict:
        """Cancel an open algo order (stop-loss) by algoId."""
        params = {
            "symbol": symbol,
            "algoId": algo_id,
        }
        result = self._delete("/fapi/v1/algoOrder", params)
        logger.info("Cancelled algo order %s on %s", algo_id, symbol)
        return result

    def cancel_all_orders(self, symbol: str) -> Dict:
        """Cancel all open orders on a symbol (regular + algo)."""
        # Cancel regular orders
        params = {"symbol": symbol}
        result = self._delete("/fapi/v1/allOpenOrders", params)
        # Also cancel any algo orders
        try:
            algo_orders = self.get_open_algo_orders(symbol)
            for ao in algo_orders:
                aid = ao.get("algoId")
                if aid:
                    self.cancel_algo_order(symbol, str(aid))
        except Exception as e:
            logger.debug("No algo orders to cancel for %s: %s", symbol, e)
        logger.info("Cancelled all orders on %s", symbol)
        return result

    def get_open_algo_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all open algo orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._get("/fapi/v1/openAlgoOrders", params=params, signed=True)

    def partial_close_position(self, symbol: str, qty: float) -> Dict:
        """
        Market-close a partial quantity of an open position.
        Used for bear TP1/TP2 partial closes (Decision 4).
        Uses reduceOnly to bypass minimum notional and prevent accidental new positions.

        Args:
            symbol: e.g. "SOLUSDT"
            qty:    Quantity to close (absolute value)
        """
        pos = self.get_position(symbol)
        if pos is None:
            logger.warning("No open position on %s to partially close", symbol)
            return {}
        pos_amt = float(pos["positionAmt"])
        if pos_amt == 0:
            return {}
        close_side = "SELL" if pos_amt > 0 else "BUY"
        close_qty = min(abs(qty), abs(pos_amt))
        return self.place_market_order(symbol, close_side, close_qty, reduce_only=True)

    def close_position(self, symbol: str, algo_id_to_cancel: Optional[str] = None) -> Dict:
        """
        Market-close an open position on *symbol*.
        Determines direction from current position and sends opposite market order.
        Uses reduceOnly to bypass minimum notional and prevent accidental new positions.

        Order of operations: close FIRST, cancel stop orders AFTER.
        This ensures the position stays protected by its exchange-side stop
        if the market close fails for any reason.

        Args:
            symbol:             e.g. "SOLUSDT"
            algo_id_to_cancel:  If provided, cancel only this specific algo stop order
                                instead of ALL orders on the symbol. Prevents killing
                                stops for other strategies sharing the same asset.
        """
        pos = self.get_position(symbol)
        if pos is None:
            logger.warning("No open position on %s to close", symbol)
            return {}
        pos_amt = float(pos["positionAmt"])
        if pos_amt == 0:
            logger.warning("Position qty is 0 for %s", symbol)
            return {}
        close_side = "SELL" if pos_amt > 0 else "BUY"
        close_qty = abs(pos_amt)
        # Close position FIRST — stop loss stays active as safety net
        result = self.place_market_order(symbol, close_side, close_qty, reduce_only=True)
        # Only cancel stop orders AFTER close succeeds
        if algo_id_to_cancel:
            # C-3: Cancel only the specific stop for this strategy
            try:
                self.cancel_algo_order(symbol, algo_id_to_cancel)
            except Exception as e:
                logger.warning("Failed to cancel algo %s on %s: %s", algo_id_to_cancel, symbol, e)
        else:
            # Fallback for emergency closes where we don't have the specific ID
            try:
                self.cancel_all_orders(symbol)
            except Exception as e:
                logger.warning("Failed to cancel orders after close on %s: %s", symbol, e)
        return result

    def set_leverage(self, symbol: str, leverage: int) -> Dict:
        """
        Set leverage for a symbol.

        Args:
            symbol:   e.g. "SOLUSDT"
            leverage: integer leverage (e.g. 2)

        Returns:
            Response dict with leverage and maxNotionalValue.
        """
        params = {
            "symbol": symbol,
            "leverage": int(leverage),
        }
        result = self._post("/fapi/v1/leverage", params)
        logger.info("Set leverage %dx on %s", leverage, symbol)
        return result

    def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> Dict:
        """
        Set margin type for a symbol (CROSSED or ISOLATED).
        Silently succeeds if already set to the requested type.
        """
        params = {
            "symbol": symbol,
            "marginType": margin_type.upper(),
        }
        try:
            result = self._post("/fapi/v1/marginType", params)
            logger.info("Set margin type %s on %s", margin_type, symbol)
            return result
        except RuntimeError as e:
            # Binance returns -4046 if margin type is already set
            if "-4046" in str(e):
                logger.debug("Margin type already %s for %s", margin_type, symbol)
                return {"msg": "No need to change margin type."}
            raise

    # ── PositionReader ────────────────────────────────────────────────

    def get_positions(self) -> List[Dict]:
        """
        Get all open positions on the account.
        Only returns positions with non-zero quantity.

        Returns:
            List of dicts with keys: symbol, positionAmt, entryPrice,
            unRealizedProfit, leverage, positionSide, etc.
        """
        data = self._get("/fapi/v2/positionRisk", signed=True)
        return [p for p in data if abs(float(p.get("positionAmt", 0))) > 0]

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get a single position for *symbol*, or None if flat."""
        data = self._get("/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True)
        for p in data:
            if abs(float(p.get("positionAmt", 0))) > 0:
                return p
        return None

    def has_open_position(self, symbol: str, side: str) -> bool:
        """
        Check if there's an open position on *symbol* in *side* direction.

        Args:
            side: "BUY"/"LONG" for long, "SELL"/"SHORT" for short
        """
        pos = self.get_position(symbol)
        if pos is None:
            return False
        pos_amt = float(pos["positionAmt"])
        if side.upper() in ("BUY", "LONG"):
            return pos_amt > 0
        return pos_amt < 0

    def get_unrealized_pnl(self) -> float:
        """Sum of unrealised P&L across all open positions."""
        positions = self.get_positions()
        return sum(float(p.get("unRealizedProfit", 0)) for p in positions)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all open orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._get("/fapi/v1/openOrders", params=params, signed=True)

    # ── AccountMonitor ────────────────────────────────────────────────

    def get_equity(self) -> float:
        """
        Get total account equity (wallet balance + unrealised PnL).

        Returns:
            Equity in USDT.
        """
        data = self._get("/fapi/v2/balance", signed=True)
        for asset in data:
            if asset["asset"] == "USDT":
                balance = float(asset["balance"])
                cross_pnl = float(asset["crossUnPnl"])
                return balance + cross_pnl
        raise RuntimeError("USDT not found in balance response")

    def get_wallet_balance(self) -> Dict:
        """
        Get full wallet balance details.

        Returns:
            {"equity": float, "available": float, "total_margin": float,
             "unrealized_pnl": float}
        """
        data = self._get("/fapi/v2/account", signed=True)
        return {
            "equity": float(data["totalWalletBalance"]) + float(data["totalUnrealizedProfit"]),
            "available": float(data["availableBalance"]),
            "total_margin": float(data["totalInitialMargin"]),
            "unrealized_pnl": float(data["totalUnrealizedProfit"]),
        }

    def get_margin_ratio(self) -> float:
        """Get current margin ratio (margin used / equity). Returns 0.0 if no margin used."""
        info = self.get_wallet_balance()
        equity = info["equity"]
        if equity <= 0:
            return 0.0
        return info["total_margin"] / equity

    def check_health(self) -> bool:
        """
        Basic connectivity / health check.
        Returns True if API is reachable and account is accessible.
        """
        try:
            self._get("/fapi/v1/ping")
            self.get_equity()
            return True
        except Exception:
            return False

    # ── Symbol Info ───────────────────────────────────────────────────

    def get_symbol_filters(self, symbol: str) -> Dict:
        """
        Get cached symbol filters (stepSize, tickSize, minQty, etc.).
        Returns empty dict if symbol not found.
        """
        return self._symbol_filters.get(symbol, {})

    def get_all_symbols(self) -> List[str]:
        """Return list of all cached symbol names."""
        return list(self._symbol_filters.keys())
