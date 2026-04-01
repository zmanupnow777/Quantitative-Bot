"""Adapter that wraps existing BaseStrategy classes for live trading.

Instead of duplicating indicator logic, this module uses the exact same
strategy code from strategies/ and extracts entry/exit decisions from
the signal series it produces.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from bot.brokers.base import Position
from strategies import (
    BaseStrategy,
    BollingerBandStrategy,
    DonchianBreakoutStrategy,
    EngulfingStrategy,
    MACrossoverStrategy,
    MACDTrendStrategy,
    MomentumStrategy,
    RSIMeanReversionStrategy,
    TrendDeltaStrategy,
    VWAPReversionStrategy,
)

logger = logging.getLogger(__name__)


class LiveStrategyAdapter:
    """
    Wraps any BaseStrategy subclass for use in live trading.

    Calls generate_signals() on the full data window, then reads the
    latest signal to decide whether to enter or exit. This guarantees
    the live bot uses the exact same logic that was backtested.
    """

    def __init__(self, strategy: BaseStrategy) -> None:
        self.strategy = strategy
        self._last_signal = 0

    @property
    def name(self) -> str:
        return self.strategy.name

    @property
    def params(self) -> dict:
        return self.strategy.params

    def should_enter(self, data: pd.DataFrame) -> Optional[str]:
        """
        Check the latest bar for an entry signal.

        Returns 'long', 'short', or None.
        """
        signal = self._get_latest_signal(data)
        if signal is None:
            return None

        if signal == 1:
            logger.info("[%s] Entry signal: LONG", self.name)
            return "long"
        elif signal == -1:
            logger.info("[%s] Entry signal: SHORT", self.name)
            return "short"
        return None

    def should_exit(self, data: pd.DataFrame, position: Position) -> bool:
        """
        Check if the strategy says to exit the current position.

        A long position exits on a -1 signal.
        A short position exits on a +1 signal.
        """
        signal = self._get_latest_signal(data)
        if signal is None:
            return False

        if position.side == "long" and signal == -1:
            logger.info("[%s] Exit signal for long position", self.name)
            return True
        if position.side == "short" and signal == 1:
            logger.info("[%s] Exit signal for short position", self.name)
            return True
        return False

    def _get_latest_signal(self, data: pd.DataFrame) -> Optional[int]:
        """Run the strategy on the data window and return the last signal."""
        if data.empty or len(data) < 5:
            return None

        try:
            signals = self.strategy.generate_signals(data)
            latest = int(signals.iloc[-1])
            self._last_signal = latest
            return latest
        except Exception as e:
            logger.error("[%s] Signal generation failed: %s", self.name, e)
            return None


# ---------------------------------------------------------------------------
# Strategy registry — maps short names to factory functions
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "ma_crossover": MACrossoverStrategy,
    "rsi": RSIMeanReversionStrategy,
    "bollinger": BollingerBandStrategy,
    "donchian": DonchianBreakoutStrategy,
    "macd": MACDTrendStrategy,
    "trend_delta": TrendDeltaStrategy,
    "momentum": MomentumStrategy,
    "vwap": VWAPReversionStrategy,
    "engulfing": EngulfingStrategy,
}


def get_live_strategy(name: str, **overrides) -> LiveStrategyAdapter:
    """
    Create a LiveStrategyAdapter by strategy short name.

    Any keyword arguments override the strategy's default parameters.

    Example:
        adapter = get_live_strategy("ma_crossover", fast_window=10, slow_window=50)
    """
    if name not in STRATEGY_REGISTRY:
        available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")

    strategy_cls = STRATEGY_REGISTRY[name]
    strategy = strategy_cls(**overrides) if overrides else strategy_cls()
    return LiveStrategyAdapter(strategy)


def load_composite_strategy(config_path: str) -> LiveStrategyAdapter:
    """Load a CompositeStrategy from a JSON config file and wrap it for live trading.

    Args:
        config_path: Path to a JSON file saved by CompositeStrategy.save() or
                     the research pipeline (strategies/generated/*.json).

    Returns:
        A LiveStrategyAdapter wrapping the loaded CompositeStrategy.
    """
    from strategies.composite import CompositeStrategy

    strategy = CompositeStrategy.load(config_path)
    logger.info("Loaded composite strategy '%s' from %s", strategy.name, config_path)
    return LiveStrategyAdapter(strategy)
