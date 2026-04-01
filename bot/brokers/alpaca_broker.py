"""Alpaca Markets broker — paper and live trading for US equities."""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from bot.brokers.base import BotConfig, BrokerInterface, Order, OrderSide, OrderType, Position
from bot.brokers.paper_broker import PaperBroker
from config import settings

logger = logging.getLogger(__name__)


class AlpacaBroker(BrokerInterface):
    """
    Alpaca Markets broker interface for paper and live trading.

    Setup:
        1. Create account at alpaca.markets
        2. Get API keys from dashboard
        3. Set in your .env file:
           ALPACA_API_KEY=your_key
           ALPACA_SECRET_KEY=your_secret
           ALPACA_BASE_URL=https://paper-api.alpaca.markets
    """

    def __init__(self) -> None:
        self.api = None

    def connect(self, config: BotConfig) -> bool:
        try:
            import alpaca_trade_api as tradeapi
        except ImportError:
            logger.error("alpaca-trade-api not installed. Run: pip install alpaca-trade-api")
            return False

        api_key = settings.ALPACA_API_KEY
        secret_key = settings.ALPACA_SECRET_KEY
        base_url = settings.ALPACA_BASE_URL

        if not api_key or not secret_key:
            logger.error("Alpaca API keys not set. Add ALPACA_API_KEY and ALPACA_SECRET_KEY to your .env file.")
            return False

        try:
            self.api = tradeapi.REST(api_key, secret_key, base_url, api_version="v2")
            account = self.api.get_account()
            logger.info("Alpaca connected (%s). Cash: $%s", base_url, account.cash)
            return True
        except Exception as e:
            logger.error("Alpaca connection failed: %s", e)
            return False

    def get_account_info(self) -> dict:
        account = self.api.get_account()
        return {
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "buying_power": float(account.buying_power),
            "daily_pnl": float(account.equity) - float(account.last_equity),
            "positions_count": len(self.api.list_positions()),
        }

    def get_positions(self) -> list[Position]:
        positions = []
        for p in self.api.list_positions():
            positions.append(Position(
                symbol=p.symbol,
                side="long" if float(p.qty) > 0 else "short",
                qty=abs(float(p.qty)),
                entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                unrealized_pnl=float(p.unrealized_pl),
                entry_time=datetime.now(),
                stop_loss=0.0,
                take_profit=0.0,
            ))
        return positions

    def submit_order(self, order: Order) -> Order:
        try:
            kwargs = {
                "symbol": order.symbol,
                "qty": order.qty,
                "side": order.side.value,
                "type": order.order_type.value,
                "time_in_force": order.time_in_force,
            }
            if order.order_type == OrderType.LIMIT:
                kwargs["limit_price"] = order.price
            if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
                kwargs["stop_price"] = order.stop_price

            # Attach bracket (stop loss + take profit) if provided.
            # These are held by Alpaca's servers 24/7 — the bot does not need
            # to be running for them to trigger.
            if order.stop_price and order.price and order.side == OrderSide.BUY:
                kwargs["order_class"] = "bracket"
                kwargs["stop_loss"] = {"stop_price": str(round(order.stop_price, 2))}
                kwargs["take_profit"] = {"limit_price": str(round(order.price, 2))}
            elif order.stop_price and order.price and order.side == OrderSide.SELL:
                kwargs["order_class"] = "bracket"
                kwargs["stop_loss"] = {"stop_price": str(round(order.stop_price, 2))}
                kwargs["take_profit"] = {"limit_price": str(round(order.price, 2))}

            result = self.api.submit_order(**kwargs)
            order.order_id = result.id
            order.status = result.status
            return order
        except Exception as e:
            order.status = "error"
            logger.error("Alpaca order submission failed: %s", e)
            return order

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.api.cancel_order(order_id)
            return True
        except Exception as e:
            logger.error("Alpaca cancel failed: %s", e)
            return False

    def get_historical_data(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        try:
            from alpaca_trade_api.rest import TimeFrame, TimeFrameUnit
            from datetime import datetime, timedelta

            # Map timeframe string to Alpaca TimeFrame
            tf_map = {
                "1m": TimeFrame(1, TimeFrameUnit.Minute),
                "5m": TimeFrame(5, TimeFrameUnit.Minute),
                "15m": TimeFrame(15, TimeFrameUnit.Minute),
                "1h": TimeFrame(1, TimeFrameUnit.Hour),
                "4h": TimeFrame(4, TimeFrameUnit.Hour),
                "1d": TimeFrame(1, TimeFrameUnit.Day),
            }
            tf = tf_map.get(timeframe, TimeFrame(1, TimeFrameUnit.Day))

            end = datetime.utcnow()
            # Request extra days to account for weekends/holidays
            start = end - timedelta(days=limit * 2)

            bars = self.api.get_bars(
                symbol,
                tf,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                adjustment="raw",
            ).df

            if bars.empty:
                raise ValueError("Empty response from Alpaca")

            # Standardise column names
            bars.index = pd.to_datetime(bars.index, utc=True).tz_localize(None)
            bars = bars.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
            return bars[["Open", "High", "Low", "Close", "Volume"]].tail(limit)

        except Exception as e:
            logger.warning("Alpaca data fetch failed for %s (%s), falling back to yfinance", symbol, e)
            return PaperBroker().get_historical_data(symbol, timeframe, limit)

    def get_current_price(self, symbol: str) -> float:
        try:
            quote = self.api.get_latest_trade(symbol)
            return float(quote.price)
        except Exception:
            return 0.0
