"""Donchian-channel breakout strategy in turtle style."""

from __future__ import annotations

import pandas as pd

from strategies.base import BaseStrategy


class DonchianBreakoutStrategy(BaseStrategy):
    """Trade channel breakouts with shorter exit channels."""

    strategy_name = "donchian_breakout"

    def __init__(self, entry_window: int = 20, exit_window: int = 10) -> None:
        if exit_window >= entry_window:
            raise ValueError("exit_window must be smaller than entry_window.")
        self.entry_window = entry_window
        self.exit_window = exit_window

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for the strategy."""
        return {
            "entry_window": [20, 30, 55],
            "exit_window": [5, 10, 15],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return action signals from Donchian breakouts and exits."""
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "High", "Low", "Close")

        entry_high = prepared["High"].rolling(self.entry_window, min_periods=self.entry_window).max()
        entry_low = prepared["Low"].rolling(self.entry_window, min_periods=self.entry_window).min()
        exit_high = prepared["High"].rolling(self.exit_window, min_periods=self.exit_window).max()
        exit_low = prepared["Low"].rolling(self.exit_window, min_periods=self.exit_window).min()

        long_entry = prepared["Close"] >= entry_high.shift(1)
        long_exit = prepared["Close"] <= exit_low.shift(1)
        short_entry = prepared["Close"] <= entry_low.shift(1)
        short_exit = prepared["Close"] >= exit_high.shift(1)

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
