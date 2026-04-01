"""Load OHLCV data from local CSV files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

_STANDARD_COLUMNS: list[str] = ["Open", "High", "Low", "Close", "Volume"]


class CSVFetcher:
    """Read OHLCV data from local CSV files on disk."""

    def __init__(self, base_dir: str | Path = ".") -> None:
        self.base_dir = Path(base_dir)

    def fetch(
        self,
        symbol: str,
        start_date: str = settings.DEFAULT_START_DATE,
        end_date: str = settings.DEFAULT_END_DATE,
        timeframe: str = settings.DEFAULT_TIMEFRAME,
    ) -> Optional[pd.DataFrame]:
        """Load and filter a CSV file for `symbol`."""
        if timeframe not in settings.VALID_TIMEFRAMES:
            logger.error("Invalid timeframe %s", timeframe)
            return None

        csv_path = self._find_file(symbol)
        if csv_path is None:
            logger.error("No CSV file found for %s in %s", symbol, self.base_dir)
            return None

        try:
            logger.info("Loading CSV data for %s from %s", symbol, csv_path)
            frame = pd.read_csv(csv_path)
            frame = self._standardise(frame)
            frame = frame.loc[start_date:end_date]
            return frame if not frame.empty else None
        except Exception:
            logger.exception("CSV load failed for %s", csv_path)
            return None

    def _find_file(self, symbol: str) -> Optional[Path]:
        """Return the case-insensitive CSV path for `symbol`, if present."""
        clean_symbol = symbol.replace("/", "_")
        if not self.base_dir.exists():
            return None

        for path in self.base_dir.iterdir():
            if path.suffix.lower() == ".csv" and path.stem.lower() == clean_symbol.lower():
                return path
        return None

    @staticmethod
    def _standardise(df: pd.DataFrame) -> pd.DataFrame:
        """Normalise column names and set a datetime index."""
        frame = df.copy()
        frame.columns = [column.strip().capitalize() for column in frame.columns]

        date_column = next(
            (column for column in ("Date", "Datetime", "Timestamp", "Time") if column in frame.columns),
            frame.columns[0],
        )

        frame[date_column] = pd.to_datetime(frame[date_column], utc=True).dt.tz_localize(None)
        frame = frame.set_index(date_column)
        frame.index.name = "Date"

        missing = [column for column in _STANDARD_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"Missing OHLCV columns: {missing}")

        return frame[_STANDARD_COLUMNS].sort_index()
