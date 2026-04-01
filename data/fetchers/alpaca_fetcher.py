"""Fetch stock OHLCV data from the Alpaca Markets API."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

_TF_MAP: dict[str, str] = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "1h": "1Hour",
    "4h": "1Hour",
    "1d": "1Day",
}

_STANDARD_COLUMNS: list[str] = ["Open", "High", "Low", "Close", "Volume"]


class AlpacaFetcher:
    """Download equity OHLCV bars from Alpaca."""

    def __init__(self) -> None:
        if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
            logger.warning("Alpaca API keys are not configured")

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
            from alpaca_trade_api.rest import REST, TimeFrame, TimeFrameUnit
        except ImportError:
            logger.error("alpaca-trade-api is not installed")
            return None

        api = REST(
            key_id=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
            base_url=settings.ALPACA_BASE_URL,
        )
        request_timeframe = self._parse_timeframe(_TF_MAP[timeframe], TimeFrame, TimeFrameUnit)

        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                logger.info(
                    "alpaca request for %s %s from %s to %s (attempt %d)",
                    symbol,
                    timeframe,
                    start_date,
                    end_date,
                    attempt,
                )
                bars = api.get_bars(
                    symbol,
                    request_timeframe,
                    start=start_date,
                    end=end_date,
                    adjustment="raw",
                ).df

                if bars.empty:
                    logger.warning("alpaca returned no data for %s", symbol)
                    return None

                frame = self._standardise(bars)
                if timeframe == "4h":
                    frame = self._resample_4h(frame)

                frame = frame.loc[start_date:end_date]
                return frame if not frame.empty else None
            except Exception:
                logger.exception("alpaca attempt %d failed for %s", attempt, symbol)
                if attempt < settings.MAX_RETRIES:
                    time.sleep(settings.RETRY_DELAY_SECONDS)

        logger.error("alpaca retries exhausted for %s", symbol)
        return None

    @staticmethod
    def _parse_timeframe(timeframe: str, time_frame_cls: Any, time_frame_unit_cls: Any) -> Any:
        """Convert a configured timeframe string into an Alpaca `TimeFrame`."""
        mapping = {
            "1Min": time_frame_cls(1, time_frame_unit_cls.Minute),
            "5Min": time_frame_cls(5, time_frame_unit_cls.Minute),
            "15Min": time_frame_cls(15, time_frame_unit_cls.Minute),
            "1Hour": time_frame_cls(1, time_frame_unit_cls.Hour),
            "1Day": time_frame_cls(1, time_frame_unit_cls.Day),
        }
        return mapping[timeframe]

    @staticmethod
    def _standardise(df: pd.DataFrame) -> pd.DataFrame:
        """Keep the standard OHLCV columns and normalise the index."""
        frame = df.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            }
        )
        missing = [column for column in _STANDARD_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"Missing OHLCV columns: {missing}")

        frame = frame[_STANDARD_COLUMNS].copy()
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
