"""Fetch OHLCV data from Yahoo Finance via the `yfinance` library."""

from __future__ import annotations

import logging
import time
from typing import Optional

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

_TF_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "1h",
    "1d": "1d",
}

_STANDARD_COLUMNS: list[str] = ["Open", "High", "Low", "Close", "Volume"]


class YFinanceFetcher:
    """Download equity and ETF OHLCV bars from Yahoo Finance."""

    def fetch(
        self,
        symbol: str,
        start_date: str = settings.DEFAULT_START_DATE,
        end_date: str = settings.DEFAULT_END_DATE,
        timeframe: str = settings.DEFAULT_TIMEFRAME,
    ) -> Optional[pd.DataFrame]:
        """Return a standardised OHLCV dataframe, or `None` on failure."""
        if timeframe not in settings.VALID_TIMEFRAMES:
            logger.error("Invalid timeframe %s", timeframe)
            return None

        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance is not installed")
            return None

        interval = _TF_MAP[timeframe]

        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                logger.info(
                    "yfinance request for %s %s from %s to %s (attempt %d)",
                    symbol,
                    timeframe,
                    start_date,
                    end_date,
                    attempt,
                )
                history = yf.Ticker(symbol).history(
                    start=start_date,
                    end=end_date,
                    interval=interval,
                    auto_adjust=False,
                    actions=False,
                )
                if history.empty:
                    logger.warning("yfinance returned no data for %s", symbol)
                    return None

                frame = self._standardise(history)
                if timeframe == "4h":
                    frame = self._resample_4h(frame)

                frame = frame.loc[start_date:end_date]
                return frame if not frame.empty else None
            except Exception:
                logger.exception("yfinance attempt %d failed for %s", attempt, symbol)
                if attempt < settings.MAX_RETRIES:
                    time.sleep(settings.RETRY_DELAY_SECONDS)

        logger.error("yfinance retries exhausted for %s", symbol)
        return None

    @staticmethod
    def _standardise(df: pd.DataFrame) -> pd.DataFrame:
        """Keep the standard OHLCV columns and normalise the index."""
        missing = [column for column in _STANDARD_COLUMNS if column not in df.columns]
        if missing:
            raise ValueError(f"Missing OHLCV columns: {missing}")

        frame = df[_STANDARD_COLUMNS].copy()
        frame.index = pd.to_datetime(frame.index, utc=True).tz_localize(None)
        frame.index.name = "Date"
        return frame.sort_index()

    @staticmethod
    def _resample_4h(df: pd.DataFrame) -> pd.DataFrame:
        """Resample 1-hour bars into 4-hour bars."""
        return (
            df.resample("4h")
            .agg(
                {
                    "Open": "first",
                    "High": "max",
                    "Low": "min",
                    "Close": "last",
                    "Volume": "sum",
                }
            )
            .dropna()
        )
