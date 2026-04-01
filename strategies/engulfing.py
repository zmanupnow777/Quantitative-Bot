"""Bullish and bearish engulfing candlestick strategy."""

from __future__ import annotations

import pandas as pd

from strategies.base import BaseStrategy


class EngulfingStrategy(BaseStrategy):
    """Trade directional engulfing patterns with a maximum holding period."""

    strategy_name = "engulfing"

    def __init__(self, max_hold_bars: int = 5) -> None:
        self.max_hold_bars = max_hold_bars

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for the strategy."""
        return {"max_hold_bars": [3, 5, 10]}

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return action signals from bullish and bearish engulfing candles."""
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Open", "Close")

        previous_open = prepared["Open"].shift(1)
        previous_close = prepared["Close"].shift(1)

        bullish = (
            (previous_close < previous_open)
            & (prepared["Close"] > prepared["Open"])
            & (prepared["Open"] <= previous_close)
            & (prepared["Close"] >= previous_open)
        )
        bearish = (
            (previous_close > previous_open)
            & (prepared["Close"] < prepared["Open"])
            & (prepared["Open"] >= previous_close)
            & (prepared["Close"] <= previous_open)
        )

        signals = pd.Series(0, index=prepared.index, dtype=int)
        position = 0
        bars_in_position = 0

        for idx in range(len(prepared.index)):
            if position == 0:
                if bullish.iat[idx]:
                    signals.iat[idx] = 1
                    position = 1
                    bars_in_position = 0
                elif bearish.iat[idx]:
                    signals.iat[idx] = -1
                    position = -1
                    bars_in_position = 0
            else:
                bars_in_position += 1
                if position == 1 and (bearish.iat[idx] or bars_in_position >= self.max_hold_bars):
                    signals.iat[idx] = -1
                    position = 0
                    bars_in_position = 0
                elif position == -1 and (bullish.iat[idx] or bars_in_position >= self.max_hold_bars):
                    signals.iat[idx] = 1
                    position = 0
                    bars_in_position = 0

        return self.finalize_signals(prepared, signals)
