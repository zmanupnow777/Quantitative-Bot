"""Trading bot package — Project 4 of the quant trading system."""

from bot.brokers.base import BotConfig, BrokerInterface, Order, OrderSide, OrderType, Position
from bot.live_strategy import LiveStrategyAdapter, get_live_strategy
from bot.monitor import TerminalMonitor
from bot.performance import PerformanceTracker
from bot.risk_manager import RiskManager
from bot.trade_logger import TradeLogger
from bot.trading_bot import TradingBot

__all__ = [
    "BotConfig",
    "BrokerInterface",
    "LiveStrategyAdapter",
    "Order",
    "OrderSide",
    "OrderType",
    "PerformanceTracker",
    "Position",
    "RiskManager",
    "TerminalMonitor",
    "TradingBot",
    "TradeLogger",
    "get_live_strategy",
]
