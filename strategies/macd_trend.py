"""MACD crossover strategy with a long-term trend filter."""

from __future__ import annotations

import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import macd, sma


class MACDTrendStrategy(BaseStrategy):
    """Trade MACD momentum only when aligned with the 200-SMA trend."""

    strategy_name = "macd_trend"

    def __init__(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        trend_window: int = 200,
    ) -> None:
        if fast >= slow:
            raise ValueError("fast must be smaller than slow.")
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.trend_window = trend_window

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for the strategy."""
        return {
            "fast": [8, 12, 16],
            "slow": [21, 26, 35],
            "signal": [5, 9, 12],
            "trend_window": [100, 150, 200],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return action signals from MACD trend-aligned regimes."""
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        macd_line, signal_line, _ = macd(
            prepared["Close"],
            fast=self.fast,
            slow=self.slow,
            signal=self.signal,
        )
        trend = sma(prepared["Close"], self.trend_window)
        long_entry = (macd_line > signal_line) & (prepared["Close"] > trend)
        long_exit = (macd_line < signal_line) | (prepared["Close"] < trend)
        short_entry = (macd_line < signal_line) & (prepared["Close"] < trend)
        short_exit = (macd_line > signal_line) | (prepared["Close"] > trend)

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
