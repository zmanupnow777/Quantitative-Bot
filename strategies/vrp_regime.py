"""Volatility Risk Premium (VRP) Regime Filter strategy.

Uses the spread between implied volatility (VIX) and realised volatility
as a regime signal.  When fear (VIX) is elevated relative to realised vol,
the market is contrarian-bullish.  When the spread collapses, reduce exposure.

If a ``VIX`` column is present in the data it is used directly.
Otherwise, a proxy is constructed from the rolling realised vol percentile.

Can be used as a standalone strategy OR as a regime overlay on top of
any other strategy's signals by passing ``base_signals`` to
``apply_regime_filter()``.

Reference: AQR (2018), "Understanding the Volatility Risk Premium".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import ewm_vol


class VRPRegimeStrategy(BaseStrategy):
    """Equity positioning based on the volatility risk premium regime.

    Standalone mode: long when VRP percentile is high, flat/short when low.
    Overlay mode: scale a base signal series by the regime multiplier via
    ``apply_regime_filter(data, base_signals)``.

    Parameters
    ----------
    realized_vol_window:
        Days for realised volatility calculation.
    percentile_window:
        Rolling lookback (days) for computing VRP percentile rank.
    high_vrp_pct:
        VRP percentile above which a full long is taken (bullish fear regime).
    low_vrp_pct:
        VRP percentile below which positions are flat or short (complacency).
    allow_short:
        When True, take a short position in the low-VRP regime.
    """

    strategy_name = "vrp_regime"

    def __init__(
        self,
        realized_vol_window: int = 20,
        percentile_window: int = 252,
        high_vrp_pct: float = 0.80,
        low_vrp_pct: float = 0.20,
        allow_short: bool = False,
    ) -> None:
        self.realized_vol_window = realized_vol_window
        self.percentile_window = percentile_window
        self.high_vrp_pct = high_vrp_pct
        self.low_vrp_pct = low_vrp_pct
        self.allow_short = allow_short

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        return {
            "realized_vol_window": [10, 20, 30],
            "percentile_window": [126, 252],
            "high_vrp_pct": [0.70, 0.80],
            "low_vrp_pct": [0.20, 0.30],
        }

    def _compute_vrp(self, data: pd.DataFrame) -> pd.Series:
        """Return the VRP series (implied vol minus realised vol)."""
        close = data["Close"]
        daily_returns = close.pct_change()
        realized_vol_ann = ewm_vol(daily_returns, halflife=self.realized_vol_window)

        if "VIX" in data.columns:
            implied_vol = pd.to_numeric(data["VIX"], errors="coerce") / 100.0
        else:
            # Proxy: use a longer-window vol as a smooth "implied" estimate
            implied_vol = ewm_vol(daily_returns, halflife=self.realized_vol_window * 3)

        return implied_vol - realized_vol_ann

    def _vrp_percentile(self, vrp: pd.Series) -> pd.Series:
        """Rolling percentile rank of the VRP series."""
        def _pct_rank(x: np.ndarray) -> float:
            if len(x) < 2:
                return 0.5
            return float((x[:-1] < x[-1]).sum() / (len(x) - 1))

        return vrp.rolling(self.percentile_window, min_periods=30).apply(
            _pct_rank, raw=True
        )

    def apply_regime_filter(
        self, data: pd.DataFrame, base_signals: pd.Series
    ) -> pd.Series:
        """Scale ``base_signals`` by the VRP regime (overlay mode).

        High VRP → pass signals through unchanged.
        Low VRP  → suppress or flip signals.
        """
        prepared = self.prepare_data(data)
        vrp = self._compute_vrp(prepared)
        pct = self._vrp_percentile(vrp)

        filtered = base_signals.copy()
        # Suppress longs in low-VRP (complacency) regime
        suppress = pct < self.low_vrp_pct
        filtered[suppress & (base_signals == 1)] = 0
        return filtered

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        vrp = self._compute_vrp(prepared)
        pct = self._vrp_percentile(vrp)

        long_entry = pct >= self.high_vrp_pct
        long_exit = pct < self.high_vrp_pct
        short_entry = (pct <= self.low_vrp_pct) & self.allow_short
        short_exit = pct > self.low_vrp_pct

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry if self.allow_short else None,
            short_exit=short_exit if self.allow_short else None,
        )
        return self.finalize_signals(prepared, signals)
