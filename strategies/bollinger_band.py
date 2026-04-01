"""Bollinger Band mean-reversion strategy."""

from __future__ import annotations

import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import bollinger_bands


class BollingerBandStrategy(BaseStrategy):
    """Trade reversion from stretched Bollinger Band moves."""

    strategy_name = "bollinger_band"

    def __init__(
        self,
        length: int = 20,
        std_dev: float = 2.0,
        band_buffer: float = 0.0,
    ) -> None:
        self.length = length
        self.std_dev = std_dev
        self.band_buffer = band_buffer

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for the strategy."""
        return {
            "length": [10, 20, 30],
            "std_dev": [1.5, 2.0, 2.5],
            "band_buffer": [0.0, 0.005, 0.01],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return action signals based on band touches and mean reversion."""
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        lower, middle, upper = bollinger_bands(prepared["Close"], self.length, self.std_dev)
        long_entry = prepared["Close"] <= (lower * (1.0 + self.band_buffer))
        long_exit = prepared["Close"] >= middle
        short_entry = prepared["Close"] >= (upper * (1.0 - self.band_buffer))
        short_exit = prepared["Close"] <= middle

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
