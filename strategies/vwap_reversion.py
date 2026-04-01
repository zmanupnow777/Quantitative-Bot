"""VWAP deviation mean-reversion strategy."""

from __future__ import annotations

import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import rolling_vwap


class VWAPReversionStrategy(BaseStrategy):
    """Trade deviations from a rolling VWAP-like reference level."""

    strategy_name = "vwap_reversion"

    def __init__(
        self,
        length: int = 20,
        entry_threshold: float = 0.03,
        exit_threshold: float = 0.005,
    ) -> None:
        if exit_threshold >= entry_threshold:
            raise ValueError("exit_threshold must be smaller than entry_threshold.")
        self.length = length
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for the strategy."""
        return {
            "length": [10, 20, 30],
            "entry_threshold": [0.02, 0.03, 0.05],
            "exit_threshold": [0.0025, 0.005, 0.01],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return action signals from rolling VWAP deviations."""
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "High", "Low", "Close", "Volume")

        vwap = rolling_vwap(
            prepared["High"],
            prepared["Low"],
            prepared["Close"],
            prepared["Volume"],
            self.length,
        )
        deviation = (prepared["Close"] / vwap) - 1.0
        long_entry = deviation <= -self.entry_threshold
        long_exit = deviation >= -self.exit_threshold
        short_entry = deviation >= self.entry_threshold
        short_exit = deviation <= self.exit_threshold

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
