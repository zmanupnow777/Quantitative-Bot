"""Fetch crypto OHLCV data via the `ccxt` library."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

_TF_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


class CCXTFetcher:
    """Download crypto OHLCV bars from a CCXT-supported exchange."""

    def __init__(self, exchange_id: str = "binance", exchange: Any | None = None) -> None:
        self.exchange_id = exchange_id
        self.exchange = exchange

        if self.exchange is not None:
            return

        try:
            import ccxt
        except ImportError:
            logger.warning("ccxt is not installed; crypto fetching is unavailable")
            return

        exchange_cls = getattr(ccxt, exchange_id, None)
        if exchange_cls is None:
            raise ValueError(f"Unsupported exchange: {exchange_id}")

        self.exchange = exchange_cls({"enableRateLimit": True})

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

        if self.exchange is None:
            logger.error("CCXT exchange client is not available")
            return None

        since = int(pd.Timestamp(start_date).timestamp() * 1000)
        end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)
        ccxt_timeframe = _TF_MAP[timeframe]

        for attempt in range(1, settings.MAX_RETRIES + 1):
            candles: list[list[float]] = []
            try:
                logger.info(
                    "ccxt request for %s %s from %s to %s (attempt %d)",
                    symbol,
                    timeframe,
                    start_date,
                    end_date,
                    attempt,
                )

                cursor = since
                while cursor < end_ts:
                    batch = self.exchange.fetch_ohlcv(
                        symbol,
                        ccxt_timeframe,
                        since=cursor,
                        limit=1000,
                    )
                    if not batch:
                        break

                    candles.extend(batch)
                    cursor = int(batch[-1][0]) + 1

                if not candles:
                    logger.warning("ccxt returned no data for %s", symbol)
                    return None

                frame = self._to_dataframe(candles, end_ts)
                frame = frame.loc[start_date:end_date]
                return frame if not frame.empty else None
            except Exception:
                logger.exception("ccxt attempt %d failed for %s", attempt, symbol)
                if attempt < settings.MAX_RETRIES:
                    time.sleep(settings.RETRY_DELAY_SECONDS)

        logger.error("ccxt retries exhausted for %s", symbol)
        return None

    @staticmethod
    def _to_dataframe(candles: list[list[float]], end_ts: int) -> pd.DataFrame:
        """Convert raw CCXT candles into the standard dataframe shape."""
        frame = pd.DataFrame(
            candles,
            columns=["timestamp", "Open", "High", "Low", "Close", "Volume"],
        )
        frame["Date"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
        frame = frame.set_index("Date").drop(columns=["timestamp"])
        frame = frame[frame.index <= pd.Timestamp(end_ts, unit="ms")]
        frame = frame[~frame.index.duplicated(keep="last")]
        return frame.sort_index()
