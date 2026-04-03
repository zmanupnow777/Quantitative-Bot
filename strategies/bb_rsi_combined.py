"""Bollinger Band + RSI Combined Mean-Reversion strategy.

Requires both indicators to confirm simultaneously before entering,
reducing false signals compared to using either indicator alone.
An optional ADX trend filter suppresses trades in strongly trending markets.

Mathematical core follows the research document:
  Long entry:  Close < BB_lower  AND  RSI < rsi_oversold
  Short entry: Close > BB_upper  AND  RSI > rsi_overbought
  Exit:        Close crosses BB_middle (20-SMA)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import atr, bollinger_bands, rsi, sma


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    """Compute a simplified ADX (average directional index)."""
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr_s = tr.rolling(length, min_periods=length).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).rolling(length).mean() / atr_s.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).rolling(length).mean() / atr_s.replace(0, np.nan)

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.rolling(length, min_periods=length).mean()


class BBRSICombinedStrategy(BaseStrategy):
    """Dual-confirmation mean-reversion: Bollinger Band touch + RSI extreme.

    Parameters
    ----------
    bb_length:
        Lookback for Bollinger Band calculation.
    bb_std:
        Standard deviation multiplier for the bands.
    rsi_length:
        RSI period.
    rsi_oversold:
        RSI threshold below which a long entry is confirmed.
    rsi_overbought:
        RSI threshold above which a short entry is confirmed.
    atr_length:
        ATR period used for informational stop reference.
    use_adx_filter:
        When True, suppress signals when ADX exceeds ``adx_max`` (trending market).
    adx_length:
        Period for ADX calculation.
    adx_max:
        Maximum ADX value for mean-reversion trades (default 25).
    """

    strategy_name = "bb_rsi_combined"

    def __init__(
        self,
        bb_length: int = 20,
        bb_std: float = 2.0,
        rsi_length: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        atr_length: int = 14,
        use_adx_filter: bool = True,
        adx_length: int = 14,
        adx_max: float = 25.0,
    ) -> None:
        self.bb_length = bb_length
        self.bb_std = bb_std
        self.rsi_length = rsi_length
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.atr_length = atr_length
        self.use_adx_filter = use_adx_filter
        self.adx_length = adx_length
        self.adx_max = adx_max

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        return {
            "bb_length": [15, 20, 30],
            "bb_std": [1.5, 2.0, 2.5],
            "rsi_length": [10, 14, 20],
            "rsi_oversold": [25.0, 30.0, 35.0],
            "rsi_overbought": [65.0, 70.0, 75.0],
            "adx_max": [20.0, 25.0, 30.0],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "High", "Low", "Close")

        close = prepared["Close"]
        high = prepared["High"]
        low = prepared["Low"]

        lower, middle, upper = bollinger_bands(close, self.bb_length, self.bb_std)
        rsi_vals = rsi(close, self.rsi_length)

        long_entry = (close < lower) & (rsi_vals < self.rsi_oversold)
        long_exit = close >= middle
        short_entry = (close > upper) & (rsi_vals > self.rsi_overbought)
        short_exit = close <= middle

        if self.use_adx_filter:
            adx_vals = _adx(high, low, close, self.adx_length)
            ranging = adx_vals < self.adx_max
            long_entry = long_entry & ranging
            short_entry = short_entry & ranging

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
