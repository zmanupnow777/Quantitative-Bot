"""Cointegration-Based Pairs Trading (Gatev, Goetzmann & Rouwenhorst 2006).

Upgrades the simple price-ratio pairs strategy to use:
- OLS hedge ratio (regression coefficient) rather than raw ratio
- ADF test on the spread to confirm stationarity (requires statsmodels)
- Half-life filter to reject pairs with too-slow or too-fast reversion

Falls back gracefully if statsmodels is not installed (skips the ADF gate).

Reference: Gatev, Goetzmann & Rouwenhorst (2006), "Pairs Trading:
           Performance of a Relative-Value Arbitrage Rule".
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

try:
    from statsmodels.tsa.stattools import adfuller
    _HAS_STATSMODELS = True
except ImportError:
    _HAS_STATSMODELS = False
    logger.info("statsmodels unavailable; ADF test skipped in CointegrationPairsStrategy.")


def _ols_hedge_ratio(y: np.ndarray, x: np.ndarray) -> float:
    """Return OLS slope coefficient (hedge ratio) of y regressed on x."""
    xm = x - x.mean()
    ym = y - y.mean()
    denom = (xm * xm).sum()
    return float((xm * ym).sum() / denom) if abs(denom) > 1e-12 else 1.0


def _halflife(spread: np.ndarray) -> float:
    """Estimate mean-reversion half-life via AR(1) on spread differences."""
    lag = spread[:-1]
    delta = np.diff(spread)
    xm = lag - lag.mean()
    denom = (xm * xm).sum()
    if abs(denom) < 1e-12:
        return np.inf
    b = (xm * (delta - delta.mean())).sum() / denom
    if b >= 0:
        return np.inf
    return float(-np.log(2) / np.log(1 + b))


class CointegrationPairsStrategy(BaseStrategy):
    """Trade OLS-spread mean reversion with cointegration validation.

    Requires a ``PairClose`` column in the data (same convention as
    ``PairsMeanReversionStrategy``).

    Parameters
    ----------
    lookback:
        Rolling window (days) for OLS hedge ratio estimation and spread stats.
    entry_z:
        Z-score at which to open a position.
    exit_z:
        Z-score at which to close a position.
    stop_z:
        Hard stop when spread diverges beyond this z-score.
    min_halflife:
        Minimum acceptable mean-reversion half-life in days.
    max_halflife:
        Maximum acceptable mean-reversion half-life in days.
    adf_pvalue:
        Maximum ADF p-value for the spread to be tradeable (only used when
        statsmodels is available).
    """

    strategy_name = "cointegration_pairs"

    def __init__(
        self,
        lookback: int = 120,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
        stop_z: float = 4.0,
        min_halflife: float = 5.0,
        max_halflife: float = 60.0,
        adf_pvalue: float = 0.05,
        pair_symbol: str | None = None,
    ) -> None:
        if exit_z >= entry_z:
            raise ValueError("exit_z must be smaller than entry_z.")
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.stop_z = stop_z
        self.min_halflife = min_halflife
        self.max_halflife = max_halflife
        self.adf_pvalue = adf_pvalue
        self.pair_symbol = pair_symbol

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        return {
            "lookback": [60, 90, 120, 180],
            "entry_z": [1.5, 2.0, 2.5],
            "exit_z": [0.0, 0.25, 0.5],
            "stop_z": [3.0, 4.0],
            "min_halflife": [5.0, 10.0],
            "max_halflife": [40.0, 60.0, 90.0],
        }

    def prepare_data(self, data: pd.DataFrame) -> pd.DataFrame:
        prepared = super().prepare_data(data)
        self.require_columns(prepared, "Close", "PairClose")
        return prepared

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        prepared = self.prepare_data(data)
        y = prepared["Close"].to_numpy()
        x = pd.to_numeric(prepared["PairClose"], errors="coerce").to_numpy()
        n = len(prepared)

        zscore = np.full(n, np.nan)

        for i in range(self.lookback, n):
            yw = y[i - self.lookback: i]
            xw = x[i - self.lookback: i]

            if np.any(np.isnan(yw)) or np.any(np.isnan(xw)):
                continue

            hr = _ols_hedge_ratio(yw, xw)
            spread_window = yw - hr * xw

            hl = _halflife(spread_window)
            if hl < self.min_halflife or hl > self.max_halflife:
                continue

            if _HAS_STATSMODELS:
                try:
                    pval = adfuller(spread_window, maxlag=1, autolag=None)[1]
                    if pval > self.adf_pvalue:
                        continue
                except Exception:
                    pass  # skip ADF gate on error

            mu = spread_window.mean()
            sigma = spread_window.std(ddof=1)
            if sigma < 1e-10:
                continue

            current_spread = y[i] - hr * x[i]
            zscore[i] = (current_spread - mu) / sigma

        zscore_series = pd.Series(zscore, index=prepared.index)

        long_entry = zscore_series < -self.entry_z
        long_exit = (zscore_series > -self.exit_z) | (zscore_series < -self.stop_z)
        short_entry = zscore_series > self.entry_z
        short_exit = (zscore_series < self.exit_z) | (zscore_series > self.stop_z)

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
