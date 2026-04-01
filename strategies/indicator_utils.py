"""Indicator helpers with `pandas-ta` integration and native fallbacks."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import pandas_ta as ta
except ImportError:  # pragma: no cover - exercised only when pandas-ta is unavailable.
    ta = None
    logger.info("pandas_ta is unavailable; falling back to pandas implementations.")


def sma(series: pd.Series, length: int) -> pd.Series:
    """Return a simple moving average."""
    if ta is not None:
        result = ta.sma(series, length=length)
        if result is not None:
            return result
    return series.rolling(length, min_periods=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    """Return an exponential moving average."""
    if ta is not None:
        result = ta.ema(series, length=length)
        if result is not None:
            return result
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def rsi(series: pd.Series, length: int) -> pd.Series:
    """Return a relative strength index series."""
    if ta is not None:
        result = ta.rsi(series, length=length)
        if result is not None:
            return result

    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    relative_strength = avg_gain / avg_loss.replace(0.0, np.nan)
    result = 100.0 - (100.0 / (1.0 + relative_strength))
    return result.fillna(50.0)


def bollinger_bands(series: pd.Series, length: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return lower, middle, and upper Bollinger Bands."""
    if ta is not None:
        bands = ta.bbands(series, length=length, std=std_dev)
        if bands is not None and not bands.empty:
            lower = bands.iloc[:, 0]
            middle = bands.iloc[:, 1]
            upper = bands.iloc[:, 2]
            return lower, middle, upper

    middle = sma(series, length=length)
    deviation = series.rolling(length, min_periods=length).std(ddof=0)
    upper = middle + (deviation * std_dev)
    lower = middle - (deviation * std_dev)
    return lower, middle, upper


def macd(
    series: pd.Series,
    fast: int,
    slow: int,
    signal: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return MACD line, signal line, and histogram."""
    if ta is not None:
        macd_frame = ta.macd(series, fast=fast, slow=slow, signal=signal)
        if macd_frame is not None and not macd_frame.empty:
            macd_line = macd_frame.iloc[:, 0]
            histogram = macd_frame.iloc[:, 1]
            signal_line = macd_frame.iloc[:, 2]
            return macd_line, signal_line, histogram

    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def rolling_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    length: int,
) -> pd.Series:
    """Return a rolling VWAP-like mean using typical price and volume."""
    typical_price = (high + low + close) / 3.0
    pv = typical_price * volume
    volume_sum = volume.rolling(length, min_periods=length).sum()
    pv_sum = pv.rolling(length, min_periods=length).sum()
    return pv_sum / volume_sum.replace(0.0, np.nan)
