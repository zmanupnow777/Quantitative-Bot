"""Time-Series Momentum strategy (Moskowitz, Ooi & Pedersen 2012).

Signal: sign of the past 12-month return (skipping the most recent month).
Long when prior-year return is positive, short/flat when negative.
Volatility-scaling is noted in the docstring but position sizing is delegated
to the backtest engine's risk_per_trade parameter.

Reference: Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum",
           Journal of Financial Economics.
"""

from __future__ import annotations

import pandas as pd

from strategies.base import BaseStrategy
from strategies.indicator_utils import ewm_vol


class TimeSeriesMomentumStrategy(BaseStrategy):
    """Trade the sign of the prior-year return with a skip-period filter.

    Parameters
    ----------
    lookback:
        Total lookback in trading days (default 252 ≈ 12 months).
    skip:
        Days at the tail of the lookback to exclude (default 21 ≈ 1 month).
        Avoids short-term reversal contamination.
    vol_window:
        Halflife (days) for the EWM realised volatility estimate used to
        compute a vol-normalised momentum score.  The score is informational
        only — actual sizing is controlled by the engine.
    vol_scale:
        When True, only take positions when the annualised vol is below
        ``max_vol``; acts as a simple risk-off filter.
    max_vol:
        Annualised volatility ceiling (default 0.40 = 40%).  Positions are
        suppressed when realised vol exceeds this level.
    """

    strategy_name = "ts_momentum"

    def __init__(
        self,
        lookback: int = 252,
        skip: int = 21,
        vol_window: int = 60,
        vol_scale: bool = True,
        max_vol: float = 0.40,
    ) -> None:
        if skip >= lookback:
            raise ValueError("skip must be smaller than lookback.")
        self.lookback = lookback
        self.skip = skip
        self.vol_window = vol_window
        self.vol_scale = vol_scale
        self.max_vol = max_vol

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        return {
            "lookback": [126, 189, 252],
            "skip": [0, 10, 21],
            "vol_window": [20, 40, 60],
            "max_vol": [0.30, 0.40, 0.60],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        close = prepared["Close"]
        # Past return: close[t-lookback] to close[t-skip]
        past_return = close.shift(self.skip) / close.shift(self.lookback) - 1.0

        daily_returns = close.pct_change()
        realised_vol = ewm_vol(daily_returns, halflife=self.vol_window)

        long_entry = past_return > 0
        long_exit = past_return <= 0
        short_entry = past_return < 0
        short_exit = past_return >= 0

        # Vol filter: suppress signals when market is too choppy
        if self.vol_scale:
            vol_ok = realised_vol <= self.max_vol
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
