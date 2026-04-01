"""Shared interfaces and dataclasses for all broker implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


@dataclass
class BotConfig:
    """Central configuration for the trading bot."""

    symbol: str = "SPY"
    timeframe: str = "1d"
    initial_capital: float = 100_000.0
    risk_per_trade: float = 0.02
    max_positions: int = 3
    max_daily_loss: float = 0.05

    mode: str = "paper"
    broker: str = "sim"

    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04
    trailing_stop_pct: float = 0.03

    use_bracket_orders: bool = True

    log_file: str = "logs/trading_bot.log"
    log_level: str = "INFO"


@dataclass
class Order:
    """A trade order submitted to a broker."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "gtc"
    order_id: str = ""
    status: str = "pending"
    filled_price: float = 0.0
    filled_at: Optional[datetime] = None


@dataclass
class Position:
    """An open position held by the broker."""

    symbol: str
    side: str  # 'long' or 'short'
    qty: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    trailing_stop: Optional[float] = None


class BrokerInterface(ABC):
    """Abstract broker interface — implement for each broker backend."""

    @abstractmethod
    def connect(self, config: BotConfig) -> bool:
        """Connect to the broker. Returns True on success."""

    @abstractmethod
    def get_account_info(self) -> dict:
        """Return account summary: cash, portfolio_value, daily_pnl, etc."""

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Return all open positions."""

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit an order and return it with updated status/fill info."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True on success."""

    @abstractmethod
    def get_historical_data(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Fetch recent OHLCV bars."""

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """Return the latest price for a symbol."""

    def check_brackets(self, symbol: str, current_price: float) -> Order | None:
        """Check if any bracket (TP/SL) order should trigger.

        Returns a filled close order if triggered, None otherwise.
        Default no-op for brokers that handle brackets server-side (e.g. Alpaca).
        """
        return None

    def update_bracket_stop(self, symbol: str, new_stop: float) -> None:
        """Update the stop-loss leg of a bracket order (for trailing stops).

        Default no-op for brokers that handle brackets server-side.
        """
