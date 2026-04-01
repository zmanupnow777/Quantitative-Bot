"""Trend-delta strategy based on candle location around a midline."""

from __future__ import annotations

import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import sma


class TrendDeltaStrategy(BaseStrategy):
    """Trade pullbacks only when a strong directional candle imbalance exists."""

    strategy_name = "trend_delta"

    def __init__(
        self,
        lookback: int = 20,
        midline_window: int = 20,
        delta_threshold: float = 0.80,
        exit_threshold: float = 0.55,
        pullback_tolerance: float = 0.01,
    ) -> None:
        if exit_threshold >= delta_threshold:
            raise ValueError("exit_threshold must be below delta_threshold.")
        self.lookback = lookback
        self.midline_window = midline_window
        self.delta_threshold = delta_threshold
        self.exit_threshold = exit_threshold
        self.pullback_tolerance = pullback_tolerance

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for the strategy."""
        return {
            "lookback": [10, 20, 30],
            "midline_window": [10, 20, 50],
            "delta_threshold": [0.70, 0.80, 0.90],
            "exit_threshold": [0.50, 0.55, 0.60],
            "pullback_tolerance": [0.005, 0.01, 0.02],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return action signals from strong directional imbalance plus pullback."""
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        midline = sma(prepared["Close"], self.midline_window)
        above_midline = prepared["Close"] > midline
        below_midline = prepared["Close"] < midline
        bullish_delta = above_midline.rolling(self.lookback, min_periods=self.lookback).mean()
        bearish_delta = below_midline.rolling(self.lookback, min_periods=self.lookback).mean()
        distance = (prepared["Close"] - midline) / midline

        long_entry = (
            (bullish_delta >= self.delta_threshold)
            & distance.between(0.0, self.pullback_tolerance)
        )
        long_exit = (prepared["Close"] < midline) | (bullish_delta <= self.exit_threshold)

        short_entry = (
            (bearish_delta >= self.delta_threshold)
            & distance.between(-self.pullback_tolerance, 0.0)
        )
        short_exit = (prepared["Close"] > midline) | (bearish_delta <= self.exit_threshold)

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
