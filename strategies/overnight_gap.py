"""Overnight Gap Reversion strategy (Stübinger & Endres 2019).

Identifies stocks that gap significantly at the open and fades the gap,
expecting reversion toward the previous close within 1–N days.

The strategy fills at the Open price of the gap bar.

Reference: Stübinger & Endres (2019), "Statistical Arbitrage with
           Mean-Reverting Overnight Price Gaps".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy


class OvernightGapReversionStrategy(BaseStrategy):
    """Fade overnight gaps that exceed a volatility-scaled threshold.

    Parameters
    ----------
    gap_threshold:
        Minimum absolute gap size to trigger a trade.  If ``use_vol_scale``
        is True this is interpreted as a multiple of recent gap volatility;
        otherwise it is a fixed fraction (e.g. 0.01 = 1 %).
    vol_window:
        Rolling window (days) used to estimate gap volatility when
        ``use_vol_scale`` is True.
    use_vol_scale:
        Scale the threshold by recent gap standard deviation.
    max_hold_days:
        Force-exit after this many bars if the gap has not yet filled.
    """

    strategy_name = "overnight_gap"

    def __init__(
        self,
        gap_threshold: float = 0.01,
        vol_window: int = 20,
        use_vol_scale: bool = False,
        max_hold_days: int = 3,
    ) -> None:
        self.gap_threshold = gap_threshold
        self.vol_window = vol_window
        self.use_vol_scale = use_vol_scale
        self.max_hold_days = max_hold_days

    @property
    def trade_price_column(self) -> str:
        """Fill at the open price of the gap bar."""
        return "Open"

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        return {
            "gap_threshold": [0.005, 0.01, 0.015, 0.02],
            "vol_window": [10, 20, 30],
            "use_vol_scale": [False, True],
            "max_hold_days": [1, 2, 3, 5],
        }

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Open", "Close")

        close = prepared["Close"]
        open_ = prepared["Open"]

        # Overnight gap: open vs previous close
        gap = (open_ - close.shift(1)) / close.shift(1).replace(0.0, np.nan)

        if self.use_vol_scale:
            gap_std = gap.rolling(self.vol_window, min_periods=self.vol_window).std()
            threshold = self.gap_threshold * gap_std.fillna(self.gap_threshold)
        else:
            threshold = pd.Series(self.gap_threshold, index=prepared.index)

        signals = pd.Series(0, index=prepared.index, dtype=int)
        position = 0
        hold_count = 0

        prev_close = close.shift(1)

        for i in range(len(prepared)):
            g = gap.iat[i]
            thr = threshold.iat[i]
            pc = prev_close.iat[i]
            current_open = open_.iat[i]
            current_close = close.iat[i]

            if np.isnan(g) or np.isnan(thr):
                continue

            if position != 0:
                hold_count += 1
                # Gap filled: price crossed back through previous close
                gap_filled = (
                    (position == 1 and current_close >= pc) or
                    (position == -1 and current_close <= pc)
                )
                if gap_filled or hold_count >= self.max_hold_days:
                    signals.iat[i] = -position  # exit signal
                    position = 0
                    hold_count = 0
            else:
                if g < -thr:
                    # Gap down → expect reversion up → long
                    signals.iat[i] = 1
                    position = 1
                    hold_count = 0
                elif g > thr:
                    # Gap up → expect reversion down → short
                    signals.iat[i] = -1
                    position = -1
                    hold_count = 0

        return signals.rename("signal")
