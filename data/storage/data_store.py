"""Parquet-backed local data cache with transparent fetch-on-miss behaviour."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from config import settings
from data.fetchers.alpaca_fetcher import AlpacaFetcher
from data.fetchers.ccxt_fetcher import CCXTFetcher
from data.fetchers.yfinance_fetcher import YFinanceFetcher

logger = logging.getLogger(__name__)


class DataStore:
    """Save, load, fetch, and merge OHLCV data as parquet files."""

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        yfinance_fetcher: YFinanceFetcher | None = None,
        ccxt_fetcher: CCXTFetcher | None = None,
        alpaca_fetcher: AlpacaFetcher | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else settings.DATA_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._yf = yfinance_fetcher or YFinanceFetcher()
        self._ccxt = ccxt_fetcher or CCXTFetcher()
        self._alpaca = alpaca_fetcher or AlpacaFetcher()

    def get(
        self,
        symbol: str,
        timeframe: str = settings.DEFAULT_TIMEFRAME,
        start_date: str = settings.DEFAULT_START_DATE,
        end_date: str = settings.DEFAULT_END_DATE,
        force_refresh: bool = False,
    ) -> Optional[pd.DataFrame]:
        """Return OHLCV data, fetching and caching as needed."""
        cached = self.load(symbol, timeframe)
        cached_window = self._filter_range(cached, start_date, end_date)

        if (
            cached_window is not None
            and not force_refresh
            and self._is_fresh(symbol, timeframe)
            and self._covers_range(cached_window, start_date, end_date)
        ):
            logger.info("Fresh cache hit for %s/%s", symbol, timeframe)
            return cached_window

        fresh = self._fetch(symbol, start_date, end_date, timeframe)
        if fresh is None:
            if cached_window is not None:
                logger.warning("Fetch failed for %s/%s; falling back to cached data", symbol, timeframe)
            return cached_window

        merged = self._merge_frames(cached, fresh)
        self.save(symbol, timeframe, merged)
        return self._filter_range(merged, start_date, end_date)

    def save(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Path:
        """Persist a dataframe as a parquet file and return the written path."""
        path = self._path_for(symbol, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)

        frame = self._prepare(df)
        frame.to_parquet(path, engine="pyarrow")
        logger.info("Saved %d rows to %s", len(frame), path)
        return path

    def load(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Load a cached parquet file, or `None` if no cache exists."""
        path = self._path_for(symbol, timeframe)
        if not path.exists():
            return None

        try:
            frame = pd.read_parquet(path, engine="pyarrow")
            frame = self._prepare(frame)
            logger.info("Loaded %d rows from %s", len(frame), path)
            return frame
        except Exception:
            logger.exception("Failed to read cache at %s", path)
            return None

    def _path_for(self, symbol: str, timeframe: str) -> Path:
        clean_symbol = symbol.replace("/", "_").replace(":", "_")
        return self.cache_dir / clean_symbol / f"{timeframe}.parquet"

    def _is_fresh(self, symbol: str, timeframe: str) -> bool:
        path = self._path_for(symbol, timeframe)
        if not path.exists():
            return False
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        return age < timedelta(hours=settings.CACHE_MAX_AGE_HOURS)

    def _fetch(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str,
    ) -> Optional[pd.DataFrame]:
        """Pick a fetcher based on the symbol format and available sources."""
        if "/" in symbol:
            return self._ccxt.fetch(symbol, start_date, end_date, timeframe)

        frame = self._yf.fetch(symbol, start_date, end_date, timeframe)
        if frame is not None:
            return frame

        logger.info("yfinance failed for %s; trying alpaca", symbol)
        return self._alpaca.fetch(symbol, start_date, end_date, timeframe)

    @staticmethod
    def _prepare(df: pd.DataFrame) -> pd.DataFrame:
        """Normalise the dataframe for storage and comparison."""
        frame = df.copy()
        frame.index = pd.to_datetime(frame.index, utc=True).tz_localize(None)
        frame.index.name = "Date"
        frame = frame[~frame.index.duplicated(keep="last")]
        return frame.sort_index()

    @staticmethod
    def _merge_frames(existing: Optional[pd.DataFrame], fresh: pd.DataFrame) -> pd.DataFrame:
        """Merge cached and newly fetched data into a single sorted dataframe."""
        if existing is None or existing.empty:
            return DataStore._prepare(fresh)

        merged = pd.concat([existing, fresh])
        return DataStore._prepare(merged)

    @staticmethod
    def _filter_range(
        df: Optional[pd.DataFrame],
        start_date: str,
        end_date: str,
    ) -> Optional[pd.DataFrame]:
        """Return the requested date slice, preserving `None`."""
        if df is None:
            return None

        frame = df.loc[start_date:end_date]
        return frame if not frame.empty else None

    @staticmethod
    def _covers_range(df: pd.DataFrame, start_date: str, end_date: str) -> bool:
        """Return `True` when cached data spans the requested date range."""
        if df.empty:
            return False

        requested_start = pd.Timestamp(start_date).normalize()
        requested_end = pd.Timestamp(end_date).normalize()
        available_start = pd.Timestamp(df.index.min()).normalize()
        available_end = pd.Timestamp(df.index.max()).normalize()
        return available_start <= requested_start and available_end >= requested_end
