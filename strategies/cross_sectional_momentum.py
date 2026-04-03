"""Cross-Sectional Momentum strategy (Jegadeesh & Titman 1993).

Single-asset implementation: computes the rolling percentile rank of the
asset's own past return vs its historical return distribution.

In a multi-asset context (e.g. the research pipeline run across multiple
symbols), the backtester evaluates each symbol independently, so the
strategy naturally selects those currently in the upper percentile of
their own history — approximating cross-sectional ranking behaviour.

For a true cross-sectional sort, use the research pipeline with multiple
symbols and compare Sharpe ratios to identify which assets are currently
in momentum.

Reference: Jegadeesh & Titman (1993), "Returns to Buying Winners and
           Selling Losers: Implications for Stock Market Efficiency".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import ewm_vol


class CrossSectionalMomentumStrategy(BaseStrategy):
    """Trade based on the rolling percentile rank of past return.

    Parameters
    ----------
    formation:
        Return lookback in trading days (default 252 - 21 = 231 ≈ 11 months).
    skip:
        Days at the end of the formation window to skip (avoids short-term
        reversal; default 21 ≈ 1 month).
    long_pct:
        Enter long when past-return percentile exceeds this threshold.
    short_pct:
        Enter short when past-return percentile is below this threshold.
    rank_window:
        Rolling history (days) used to compute the percentile rank.
    vol_scale:
        Suppress signals when realised vol is too high (risk-off filter).
    max_vol:
        Maximum annualised vol before signals are suppressed.
    """

    strategy_name = "cross_sectional_momentum"

    def __init__(
        self,
        formation: int = 231,
        skip: int = 21,
        long_pct: float = 0.70,
        short_pct: float = 0.30,
        rank_window: int = 252,
        vol_scale: bool = True,
        max_vol: float = 0.40,
    ) -> None:
        self.formation = formation
        self.skip = skip
        self.long_pct = long_pct
        self.short_pct = short_pct
        self.rank_window = rank_window
        self.vol_scale = vol_scale
        self.max_vol = max_vol

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        return {
            "formation": [126, 189, 231, 252],
            "skip": [0, 10, 21],
            "long_pct": [0.60, 0.70, 0.80],
            "short_pct": [0.20, 0.30, 0.40],
            "rank_window": [126, 252],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        close = prepared["Close"]
        total_lookback = self.formation + self.skip

        # Past return: skip most recent ``skip`` days to avoid reversal
        past_return = close.shift(self.skip) / close.shift(total_lookback) - 1.0

        # Rolling percentile rank of the current return vs its own history
        def _pct_rank(x: np.ndarray) -> float:
            if len(x) < 2 or np.isnan(x[-1]):
                return np.nan
            valid = x[~np.isnan(x)]
            if len(valid) < 2:
                return np.nan
            return float((valid[:-1] < valid[-1]).sum() / (len(valid) - 1))

        percentile = past_return.rolling(self.rank_window, min_periods=30).apply(
            _pct_rank, raw=True
        )

        daily_returns = close.pct_change()
        realized_vol = ewm_vol(daily_returns, halflife=60)

        long_entry = percentile >= self.long_pct
        long_exit = percentile < self.long_pct
        short_entry = percentile <= self.short_pct
        short_exit = percentile > self.short_pct

        if self.vol_scale:
            vol_ok = realized_vol <= self.max_vol
            long_entry = long_entry & vol_ok
            short_entry = short_entry & vol_ok

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
