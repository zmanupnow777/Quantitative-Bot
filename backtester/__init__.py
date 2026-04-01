"""Backtester exports for Project 2."""

from backtester.comparator import (
    DEFAULT_WEIGHTS,
    compare,
    generate_html_report,
    generate_report,
    rank_strategies,
)
from backtester.engine import BacktestEngine, BacktestResult, TradeRecord

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "DEFAULT_WEIGHTS",
    "TradeRecord",
    "compare",
    "generate_html_report",
    "generate_report",
    "rank_strategies",
]
