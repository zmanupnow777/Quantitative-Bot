"""RSI oversold/overbought mean-reversion strategy."""

from __future__ import annotations

import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import rsi


class RSIMeanReversionStrategy(BaseStrategy):
    """Buy oversold conditions and sell overbought conditions."""

    strategy_name = "rsi_mean_reversion"

    def __init__(
        self,
        length: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        exit_level: float = 50.0,
    ) -> None:
        if oversold >= exit_level or exit_level >= overbought:
            raise ValueError("Expected oversold < exit_level < overbought.")
        self.length = length
        self.oversold = oversold
        self.overbought = overbought
        self.exit_level = exit_level

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for the strategy."""
        return {
            "length": [7, 14, 21],
            "oversold": [20.0, 25.0, 30.0],
            "overbought": [70.0, 75.0, 80.0],
            "exit_level": [45.0, 50.0, 55.0],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return action signals from RSI extremes and reversion exits."""
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        rsi_value = rsi(prepared["Close"], self.length)
        long_entry = rsi_value <= self.oversold
        long_exit = rsi_value >= self.exit_level
        short_entry = rsi_value >= self.overbought
        short_exit = rsi_value <= self.exit_level

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
