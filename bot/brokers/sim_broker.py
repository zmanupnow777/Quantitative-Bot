"""Simulated broker with full JSON audit trail — no API keys needed."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from bot.brokers.base import BotConfig, BrokerInterface, Order, OrderSide, OrderType, Position

logger = logging.getLogger(__name__)


class SimBroker(BrokerInterface):
    """
    Local simulated broker that logs every order and fill to a JSON file.

    Unlike PaperBroker, this writes an immutable audit trail to disk so you
    can replay and inspect every action the bot took. Generates synthetic
    price data — no external dependencies required.
    """

    def __init__(self, log_dir: str | Path = "logs/sim_broker") -> None:
        self.log_dir = Path(log_dir)
        self.capital = 0.0
        self.starting_capital = 0.0
        self.positions: dict[str, Position] = {}
        self.orders: list[Order] = []
        self.trade_log: list[dict] = []
        self._order_counter = 0
        self._audit_file: Path | None = None
        self._price_cache: dict[str, pd.DataFrame] = {}
        self._pending_brackets: dict[str, dict] = {}
        self._bracket_lock = threading.Lock()

    def connect(self, config: BotConfig) -> bool:
        self.capital = config.initial_capital
        self.starting_capital = config.initial_capital
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._audit_file = self.log_dir / f"sim_audit_{datetime.now():%Y%m%d_%H%M%S}.json"
        self._write_audit({"event": "connect", "capital": self.capital, "timestamp": datetime.now().isoformat()})
        logger.info("Sim broker connected. Capital: $%.2f | Audit: %s", self.capital, self._audit_file)
        return True

    def get_account_info(self) -> dict:
        total_value = self.capital + sum(p.unrealized_pnl for p in self.positions.values())
        return {
            "cash": self.capital,
            "portfolio_value": total_value,
            "buying_power": self.capital,
            "daily_pnl": total_value - self.starting_capital,
            "positions_count": len(self.positions),
        }

    def get_positions(self) -> list[Position]:
        return list(self.positions.values())

    def submit_order(self, order: Order) -> Order:
        self._order_counter += 1
        order.order_id = f"SIM-{self._order_counter:06d}"
        order.status = "filled"
        order.filled_price = order.price or 0.0
        order.filled_at = datetime.now()

        if order.side == OrderSide.BUY:
            cost = order.filled_price * order.qty
            if cost <= self.capital:
                self.capital -= cost
                self.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    side="long",
                    qty=order.qty,
                    entry_price=order.filled_price,
                    current_price=order.filled_price,
                    unrealized_pnl=0.0,
                    entry_time=datetime.now(),
                    stop_loss=0.0,
                    take_profit=0.0,
                )
            else:
                order.status = "rejected"
                logger.warning("Order rejected: insufficient capital")

        elif order.side == OrderSide.SELL and order.symbol in self.positions:
            pos = self.positions[order.symbol]
            pnl = (order.filled_price - pos.entry_price) * pos.qty
            self.capital += order.filled_price * pos.qty
            self.trade_log.append({
                "symbol": order.symbol,
                "side": pos.side,
                "entry_price": pos.entry_price,
                "exit_price": order.filled_price,
                "qty": pos.qty,
                "pnl": pnl,
                "pnl_pct": pnl / (pos.entry_price * pos.qty) if pos.entry_price else 0,
                "entry_time": pos.entry_time.isoformat(),
                "exit_time": datetime.now().isoformat(),
            })
            del self.positions[order.symbol]
            with self._bracket_lock:
                self._pending_brackets.pop(order.symbol, None)
            logger.info("Sim position closed: %s | PnL: $%.2f", order.symbol, pnl)

        self.orders.append(order)
        self._write_audit({
            "event": "order",
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "type": order.order_type.value,
            "qty": order.qty,
            "price": order.filled_price,
            "status": order.status,
            "timestamp": datetime.now().isoformat(),
        })
        return order

    def cancel_order(self, order_id: str) -> bool:
        for order in self.orders:
            if order.order_id == order_id and order.status == "pending":
                order.status = "cancelled"
                self._write_audit({"event": "cancel", "order_id": order_id, "timestamp": datetime.now().isoformat()})
                return True
        return False

    def check_brackets(self, symbol: str, current_price: float) -> Order | None:
        """Check if a bracket (TP/SL) should trigger at the current price."""
        with self._bracket_lock:
            bracket = self._pending_brackets.get(symbol)
            if bracket is None:
                return None

            triggered = False
            fill_price = 0.0
            reason = ""

            if bracket["side"] == "long":
                if current_price >= bracket["take_profit"]:
                    triggered = True
                    fill_price = bracket["take_profit"]
                    reason = "take_profit"
                elif current_price <= bracket["stop_loss"]:
                    triggered = True
                    fill_price = bracket["stop_loss"]
                    reason = "stop_loss"
            else:
                if current_price <= bracket["take_profit"]:
                    triggered = True
                    fill_price = bracket["take_profit"]
                    reason = "take_profit"
                elif current_price >= bracket["stop_loss"]:
                    triggered = True
                    fill_price = bracket["stop_loss"]
                    reason = "stop_loss"

            if not triggered:
                return None

        close_side = OrderSide.SELL if bracket["side"] == "long" else OrderSide.BUY
        order = Order(
            symbol=symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            qty=bracket["qty"],
            price=fill_price,
        )
        logger.info(
            "Bracket %s triggered for %s at $%.2f (current $%.2f)",
            reason, symbol, fill_price, current_price,
        )
        return self.submit_order(order)

    def update_bracket_stop(self, symbol: str, new_stop: float) -> None:
        """Update the stop-loss leg of a pending bracket order."""
        with self._bracket_lock:
            bracket = self._pending_brackets.get(symbol)
            if bracket is not None:
                bracket["stop_loss"] = new_stop

    def get_historical_data(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        cache_key = f"{symbol}_{timeframe}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key].tail(limit)

        # Try yfinance first, fall back to synthetic
        try:
            import yfinance as yf

            end = datetime.now()
            start = end - timedelta(days=limit * 2)
            data = yf.download(symbol, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval=timeframe, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            if not data.empty:
                self._price_cache[cache_key] = data
                return data.tail(limit)
        except Exception:
            pass

        data = self._synthetic_data(limit)
        self._price_cache[cache_key] = data
        return data

    def get_current_price(self, symbol: str) -> float:
        data = self.get_historical_data(symbol, "1d", 5)
        return float(data["Close"].iloc[-1]) if not data.empty else 0.0

    def _write_audit(self, entry: dict) -> None:
        if self._audit_file is None:
            return
        with open(self._audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    @staticmethod
    def _synthetic_data(limit: int) -> pd.DataFrame:
        dates = pd.date_range(end=datetime.now(), periods=limit, freq="B")
        np.random.seed(42)
        prices = 450 * np.exp(np.cumsum(np.random.normal(0.0003, 0.012, limit)))
        return pd.DataFrame(
            {
                "Open": prices * 0.998,
                "High": prices * 1.005,
                "Low": prices * 0.995,
                "Close": prices,
                "Volume": np.random.randint(1_000_000, 10_000_000, limit),
            },
            index=dates,
        )
