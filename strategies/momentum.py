"""Momentum strategy using N-period return thresholds."""

from __future__ import annotations

import pandas as pd

from strategies.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    """Trade sustained directional moves once momentum clears a threshold."""

    strategy_name = "momentum"

    def __init__(
        self,
        lookback: int = 20,
        entry_threshold: float = 0.05,
        exit_threshold: float = 0.0,
    ) -> None:
        self.lookback = lookback
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for the strategy."""
        return {
            "lookback": [5, 10, 20, 60],
            "entry_threshold": [0.02, 0.05, 0.08],
            "exit_threshold": [0.0, 0.01, 0.02],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return action signals from rolling-return momentum regimes."""
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        momentum = prepared["Close"].pct_change(self.lookback)
        long_entry = momentum >= self.entry_threshold
        long_exit = momentum <= self.exit_threshold
        short_entry = momentum <= -self.entry_threshold
        short_exit = momentum >= -self.exit_threshold

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
