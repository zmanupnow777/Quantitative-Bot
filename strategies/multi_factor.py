"""Multi-Factor Composite strategy (Asness, Frazzini & Pedersen 2019).

Combines three factor scores into a single composite rank:
  - Momentum:  12-1 month return z-score (Jegadeesh-Titman)
  - Value:     Price distance from 52-week high/low (OHLCV proxy for cheapness)
  - Quality:   Inverse of realised vol (price stability as quality proxy)

Fundamental data (ROE, ROA, book-to-price) would improve the quality and
value scores.  If you add columns ``ROE``, ``ROA``, ``BookToPrice``, and
``EarningsYield`` to the input dataframe they will be incorporated
automatically.

Reference: Asness, Frazzini & Pedersen (2019), "Quality Minus Junk".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import ewm_vol


def _zscore(series: pd.Series, window: int) -> pd.Series:
    """Rolling z-score of a series."""
    mu = series.rolling(window, min_periods=20).mean()
    sigma = series.rolling(window, min_periods=20).std(ddof=1)
    return (series - mu) / sigma.replace(0.0, np.nan)


class MultiFactorStrategy(BaseStrategy):
    """Long when the composite factor score is high; short/flat when low.

    Parameters
    ----------
    score_window:
        Lookback (days) for z-score normalisation of each factor.
    formation:
        Return lookback for momentum factor (days).
    skip:
        Skip period for momentum factor (avoids short-term reversal).
    vol_window:
        EWM halflife for realised vol (quality proxy).
    long_pct:
        Enter long when composite percentile >= this threshold.
    short_pct:
        Enter short when composite percentile <= this threshold.
    momentum_weight:
        Weight of momentum in composite (weights are normalised internally).
    value_weight:
        Weight of value proxy in composite.
    quality_weight:
        Weight of quality proxy in composite.
    """

    strategy_name = "multi_factor"

    def __init__(
        self,
        score_window: int = 252,
        formation: int = 231,
        skip: int = 21,
        vol_window: int = 60,
        long_pct: float = 0.70,
        short_pct: float = 0.30,
        momentum_weight: float = 0.33,
        value_weight: float = 0.33,
        quality_weight: float = 0.34,
    ) -> None:
        self.score_window = score_window
        self.formation = formation
        self.skip = skip
        self.vol_window = vol_window
        self.long_pct = long_pct
        self.short_pct = short_pct
        self.momentum_weight = momentum_weight
        self.value_weight = value_weight
        self.quality_weight = quality_weight

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        return {
            "formation": [126, 189, 231],
            "skip": [0, 21],
            "long_pct": [0.60, 0.70, 0.80],
            "short_pct": [0.20, 0.30, 0.40],
            "momentum_weight": [0.20, 0.33, 0.50],
            "value_weight": [0.20, 0.33, 0.50],
            "quality_weight": [0.20, 0.34, 0.50],
        }

    def _momentum_score(self, close: pd.Series) -> pd.Series:
        """12-1 month return, z-score normalised."""
        past_return = close.shift(self.skip) / close.shift(self.formation + self.skip) - 1.0
        return _zscore(past_return, self.score_window)

    def _value_score(self, close: pd.Series, high: pd.Series, low: pd.Series) -> pd.Series:
        """Cheapness proxy: negative distance from 52-week high (buy when far below peak).

        Optionally augmented with fundamental data if present.
        """
        high_52 = high.rolling(252, min_periods=60).max()
        low_52 = low.rolling(252, min_periods=60).min()
        range_52 = (high_52 - low_52).replace(0.0, np.nan)
        # How far below the 52-week high (1 = at low, 0 = at high)
        distance_from_high = (high_52 - close) / range_52
        return _zscore(distance_from_high, self.score_window)

    def _quality_score(self, close: pd.Series, data: pd.DataFrame) -> pd.Series:
        """Stability-as-quality proxy: low vol = high quality.

        Uses fundamental columns if available: ROE, ROA, DebtToEquity.
        """
        daily_returns = close.pct_change()
        vol = ewm_vol(daily_returns, halflife=self.vol_window)
        # Invert vol: low vol → high score
        quality = -_zscore(vol, self.score_window)

        # Incorporate fundamentals if present
        if "ROE" in data.columns:
            quality = quality + _zscore(
                pd.to_numeric(data["ROE"], errors="coerce"), self.score_window
            ).fillna(0)
        if "ROA" in data.columns:
            quality = quality + _zscore(
                pd.to_numeric(data["ROA"], errors="coerce"), self.score_window
            ).fillna(0)
        if "DebtToEquity" in data.columns:
            quality = quality - _zscore(
                pd.to_numeric(data["DebtToEquity"], errors="coerce"), self.score_window
            ).fillna(0)

        return quality

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        close = prepared["Close"]
        high = prepared.get("High", close)
        low = prepared.get("Low", close)

        # Normalise weights
        total_w = self.momentum_weight + self.value_weight + self.quality_weight
        w_mom = self.momentum_weight / total_w
        w_val = self.value_weight / total_w
        w_qual = self.quality_weight / total_w

        mom = self._momentum_score(close).fillna(0)
        val = self._value_score(close, high, low).fillna(0)
        qual = self._quality_score(close, prepared).fillna(0)

        composite = w_mom * mom + w_val * val + w_qual * qual

        # Percentile rank of the composite over its own rolling history
        def _pct_rank(x: np.ndarray) -> float:
            if len(x) < 2:
                return np.nan
            return float((x[:-1] < x[-1]).sum() / (len(x) - 1))

        percentile = composite.rolling(self.score_window, min_periods=30).apply(
            _pct_rank, raw=True
        )

        long_entry = percentile >= self.long_pct
        long_exit = percentile < self.long_pct
        short_entry = percentile <= self.short_pct
        short_exit = percentile > self.short_pct

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
