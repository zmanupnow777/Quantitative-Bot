"""Fast/slow moving-average crossover strategy."""

from __future__ import annotations

import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import sma


class MACrossoverStrategy(BaseStrategy):
    """Trade with the prevailing relationship between fast and slow averages."""

    strategy_name = "ma_crossover"

    def __init__(self, fast_window: int = 20, slow_window: int = 50) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window.")
        self.fast_window = fast_window
        self.slow_window = slow_window

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for the strategy."""
        return {
            "fast_window": [5, 10, 20, 30],
            "slow_window": [50, 100, 150, 200],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return buy/sell signals from moving-average regimes."""
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        fast_ma = sma(prepared["Close"], self.fast_window)
        slow_ma = sma(prepared["Close"], self.slow_window)
        bullish = fast_ma > slow_ma
        bearish = fast_ma < slow_ma

        signals = self.build_signals(
            prepared,
            long_entry=bullish,
            long_exit=bearish,
            short_entry=bearish,
            short_exit=bullish,
        )
        return self.finalize_signals(prepared, signals)
