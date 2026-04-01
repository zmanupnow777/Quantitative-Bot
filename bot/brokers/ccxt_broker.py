"""CCXT broker skeleton — crypto exchange connectivity.

This is a skeleton implementation. To use it:
1. pip install ccxt
2. Set exchange credentials in your .env file
3. Customize the exchange ID and configuration below
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from bot.brokers.base import BotConfig, BrokerInterface, Order, OrderSide, OrderType, Position

logger = logging.getLogger(__name__)

# Timeframe mapping from bot config to CCXT format
TIMEFRAME_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


class CCXTBroker(BrokerInterface):
    """
    Crypto exchange broker via CCXT.

    Supports any exchange that CCXT supports (Binance, Bybit, Hyperliquid, etc.).
    Configure the exchange ID and credentials in your .env or pass via BotConfig.

    Setup:
        1. pip install ccxt
        2. Set environment variables for your exchange:
           CCXT_EXCHANGE=binance
           CCXT_API_KEY=your_key
           CCXT_API_SECRET=your_secret
        3. For testnet, set CCXT_SANDBOX=true
    """

    def __init__(self, exchange_id: str = "binance", sandbox: bool = True) -> None:
        self.exchange_id = exchange_id
        self.sandbox = sandbox
        self.exchange = None

    def connect(self, config: BotConfig) -> bool:
        try:
            import ccxt
        except ImportError:
            logger.error("ccxt not installed. Run: pip install ccxt")
            return False

        import os

        exchange_id = os.getenv("CCXT_EXCHANGE", self.exchange_id)
        api_key = os.getenv("CCXT_API_KEY", "")
        api_secret = os.getenv("CCXT_API_SECRET", "")
        use_sandbox = os.getenv("CCXT_SANDBOX", str(self.sandbox)).lower() == "true"

        try:
            exchange_class = getattr(ccxt, exchange_id)
            self.exchange = exchange_class({
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            })
            if use_sandbox:
                self.exchange.set_sandbox_mode(True)

            self.exchange.load_markets()
            logger.info("CCXT connected to %s (sandbox=%s)", exchange_id, use_sandbox)
            return True
        except Exception as e:
            logger.error("CCXT connection failed: %s", e)
            return False

    def get_account_info(self) -> dict:
        try:
            balance = self.exchange.fetch_balance()
            total = balance.get("total", {})
            usdt = total.get("USDT", 0.0)
            return {
                "cash": float(usdt),
                "portfolio_value": float(usdt),
                "buying_power": float(usdt),
                "daily_pnl": 0.0,
                "positions_count": 0,
            }
        except Exception as e:
            logger.error("Failed to fetch CCXT account info: %s", e)
            return {"cash": 0, "portfolio_value": 0, "buying_power": 0, "daily_pnl": 0, "positions_count": 0}

    def get_positions(self) -> list[Position]:
        try:
            positions = self.exchange.fetch_positions()
            result = []
            for p in positions:
                if float(p.get("contracts", 0)) > 0:
                    result.append(Position(
                        symbol=p["symbol"],
                        side=p.get("side", "long"),
                        qty=float(p["contracts"]),
                        entry_price=float(p.get("entryPrice", 0)),
                        current_price=float(p.get("markPrice", 0)),
                        unrealized_pnl=float(p.get("unrealizedPnl", 0)),
                        entry_time=datetime.now(),
                        stop_loss=0.0,
                        take_profit=0.0,
                    ))
            return result
        except Exception as e:
            logger.error("Failed to fetch CCXT positions: %s", e)
            return []

    def submit_order(self, order: Order) -> Order:
        try:
            result = self.exchange.create_order(
                symbol=order.symbol,
                type=order.order_type.value,
                side=order.side.value,
                amount=order.qty,
                price=order.price if order.order_type == OrderType.LIMIT else None,
            )
            order.order_id = result["id"]
            order.status = result.get("status", "open")
            order.filled_price = float(result.get("average", 0) or 0)
            return order
        except Exception as e:
            order.status = "error"
            logger.error("CCXT order failed: %s", e)
            return order

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.exchange.cancel_order(order_id)
            return True
        except Exception as e:
            logger.error("CCXT cancel failed: %s", e)
            return False

    def get_historical_data(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        try:
            tf = TIMEFRAME_MAP.get(timeframe, timeframe)
            ohlcv = self.exchange.fetch_ohlcv(symbol, tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df
        except Exception as e:
            logger.error("CCXT data fetch failed: %s", e)
            return pd.DataFrame()

    def get_current_price(self, symbol: str) -> float:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return float(ticker.get("last", 0))
        except Exception:
            return 0.0
