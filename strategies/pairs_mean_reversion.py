"""Pairs-trading mean-reversion strategy on a price ratio spread."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy


class PairsMeanReversionStrategy(BaseStrategy):
    """Trade z-score mean reversion on a price-ratio spread."""

    strategy_name = "pairs_mean_reversion"

    def __init__(
        self,
        lookback: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
        secondary_close_column: str = "PairClose",
        pair_symbol: str | None = None,
    ) -> None:
        if exit_z >= entry_z:
            raise ValueError("exit_z must be smaller than entry_z.")
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.secondary_close_column = secondary_close_column
        self.pair_symbol = pair_symbol

    @property
    def trade_price_column(self) -> str:
        """Return the synthetic ratio column used for fills."""
        return "PairRatio"

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for the strategy."""
        return {
            "lookback": [30, 60, 90],
            "entry_z": [1.5, 2.0, 2.5],
            "exit_z": [0.25, 0.5, 1.0],
        }

    def prepare_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Add the synthetic spread columns required by the strategy."""
        prepared = super().prepare_data(data)
        self.require_columns(prepared, "Close", self.secondary_close_column)

        secondary_close = pd.to_numeric(prepared[self.secondary_close_column], errors="coerce")
        prepared["PairRatio"] = prepared["Close"] / secondary_close.replace(0.0, np.nan)
        rolling_mean = prepared["PairRatio"].rolling(self.lookback, min_periods=self.lookback).mean()
        rolling_std = prepared["PairRatio"].rolling(self.lookback, min_periods=self.lookback).std(ddof=0)
        prepared["PairZScore"] = (
            (prepared["PairRatio"] - rolling_mean) / rolling_std.replace(0.0, np.nan)
        )
        return prepared

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return action signals from pair-ratio z-score extremes."""
        prepared = self.prepare_data(data)
        zscore = prepared["PairZScore"]

        long_entry = zscore <= -self.entry_z
        long_exit = zscore >= -self.exit_z
        short_entry = zscore >= self.entry_z
        short_exit = zscore <= self.exit_z

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
