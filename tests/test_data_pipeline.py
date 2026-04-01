"""Tests for the environment and data pipeline project."""

from __future__ import annotations

import os
import sys
import types

import pandas as pd

from config import settings
from data.fetchers import AlpacaFetcher, CCXTFetcher, CSVFetcher, YFinanceFetcher
from data.storage import DataStore


def _sample_ohlcv(index: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Return a small deterministic OHLCV dataframe for tests."""
    if index is None:
        index = pd.date_range("2024-01-01", periods=3, freq="D")
    index.name = "Date"

    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Volume": [1000, 1100, 1200],
        },
        index=index,
    )


def test_yfinance_fetcher_returns_standardised_dataframe(monkeypatch) -> None:
    """The Yahoo Finance fetcher should return the standard OHLCV shape."""

    class DummyTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, **_: object) -> pd.DataFrame:
            return _sample_ohlcv()

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=DummyTicker))

    frame = YFinanceFetcher().fetch("SPY", "2024-01-01", "2024-01-03", "1d")

    assert frame is not None
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert frame.shape == (3, 5)


def test_ccxt_fetcher_returns_standardised_dataframe(monkeypatch) -> None:
    """The CCXT fetcher should return the standard OHLCV shape."""

    class DummyExchange:
        def __init__(self, _: dict[str, object]) -> None:
            self.calls = 0

        def fetch_ohlcv(
            self,
            symbol: str,
            timeframe: str,
            since: int | None = None,
            limit: int = 1000,
        ) -> list[list[float]]:
            del symbol, timeframe, limit
            self.calls += 1
            if self.calls > 1:
                return []
            return [
                [1704067200000, 100.0, 101.0, 99.0, 100.5, 1000.0],
                [1704153600000, 101.0, 102.0, 100.0, 101.5, 1100.0],
            ]

    monkeypatch.setitem(sys.modules, "ccxt", types.SimpleNamespace(binance=DummyExchange))

    frame = CCXTFetcher().fetch("BTC/USDT", "2024-01-01", "2024-01-03", "1d")

    assert frame is not None
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert frame.shape == (2, 5)


def test_alpaca_fetcher_returns_standardised_dataframe(monkeypatch) -> None:
    """The Alpaca fetcher should return the standard OHLCV shape."""

    class DummyTimeFrame:
        def __init__(self, amount: int, unit: str) -> None:
            self.amount = amount
            self.unit = unit

    class DummyTimeFrameUnit:
        Minute = "minute"
        Hour = "hour"
        Day = "day"

    class DummyREST:
        def __init__(self, **_: object) -> None:
            pass

        def get_bars(self, *args: object, **kwargs: object) -> types.SimpleNamespace:
            del args, kwargs
            frame = _sample_ohlcv().rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            return types.SimpleNamespace(df=frame)

    rest_module = types.ModuleType("alpaca_trade_api.rest")
    rest_module.REST = DummyREST
    rest_module.TimeFrame = DummyTimeFrame
    rest_module.TimeFrameUnit = DummyTimeFrameUnit

    package = types.ModuleType("alpaca_trade_api")
    package.rest = rest_module

    monkeypatch.setitem(sys.modules, "alpaca_trade_api", package)
    monkeypatch.setitem(sys.modules, "alpaca_trade_api.rest", rest_module)

    frame = AlpacaFetcher().fetch("AAPL", "2024-01-01", "2024-01-03", "1d")

    assert frame is not None
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert frame.shape == (3, 5)


def test_csv_fetcher_returns_standardised_dataframe(tmp_path) -> None:
    """The CSV fetcher should return the standard OHLCV shape."""
    csv_path = tmp_path / "SPY.csv"
    csv_path.write_text(
        "\n".join(
            [
                "date,open,high,low,close,volume",
                "2024-01-01,100,101,99,100.5,1000",
                "2024-01-02,101,102,100,101.5,1100",
                "2024-01-03,102,103,101,102.5,1200",
            ]
        ),
        encoding="utf-8",
    )

    frame = CSVFetcher(base_dir=tmp_path).fetch("SPY", "2024-01-01", "2024-01-03", "1d")

    assert frame is not None
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert frame.shape == (3, 5)


def test_data_store_saves_and_loads_correctly(tmp_path) -> None:
    """The parquet cache should round-trip OHLCV data without loss."""
    store = DataStore(cache_dir=tmp_path)
    original = _sample_ohlcv()

    path = store.save("SPY", "1d", original)
    loaded = store.load("SPY", "1d")

    assert path.exists()
    assert loaded is not None
    pd.testing.assert_frame_equal(loaded, original, check_freq=False)


def test_data_store_falls_back_to_cached_data_when_fetch_fails(tmp_path) -> None:
    """The store should return cached data when a refresh fails."""
    store = DataStore(cache_dir=tmp_path)
    cached = _sample_ohlcv()
    store.save("SPY", "1d", cached)
    store._yf = types.SimpleNamespace(fetch=lambda *args, **kwargs: None)
    store._alpaca = types.SimpleNamespace(fetch=lambda *args, **kwargs: None)

    frame = store.get("SPY", "1d", "2024-01-01", "2024-01-03", force_refresh=True)

    assert frame is not None
    pd.testing.assert_frame_equal(frame, cached, check_freq=False)


def test_settings_loads_environment_variables_from_dotenv() -> None:
    """Reloading settings should read values from the project `.env` file."""
    env_path = settings.ENV_FILE
    backup = env_path.read_text(encoding="utf-8") if env_path.exists() else None
    managed_keys = [
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "CACHE_MAX_AGE_HOURS",
        "MAX_RETRIES",
        "RETRY_DELAY_SECONDS",
        "LOG_LEVEL",
    ]

    try:
        env_path.write_text(
            "\n".join(
                [
                    "ALPACA_API_KEY=test-key",
                    "ALPACA_SECRET_KEY=test-secret",
                    "CACHE_MAX_AGE_HOURS=12",
                    "MAX_RETRIES=5",
                    "RETRY_DELAY_SECONDS=1.5",
                    "LOG_LEVEL=DEBUG",
                ]
            ),
            encoding="utf-8",
        )

        for key in managed_keys:
            os.environ.pop(key, None)

        settings.refresh(env_path, override=True)

        assert settings.ALPACA_API_KEY == "test-key"
        assert settings.ALPACA_SECRET_KEY == "test-secret"
        assert settings.CACHE_MAX_AGE_HOURS == 12
        assert settings.MAX_RETRIES == 5
        assert settings.RETRY_DELAY_SECONDS == 1.5
        assert settings.LOG_LEVEL == "DEBUG"
    finally:
        for key in managed_keys:
            os.environ.pop(key, None)
        if backup is None:
            env_path.unlink(missing_ok=True)
        else:
            env_path.write_text(backup, encoding="utf-8")
        settings.refresh(settings.ENV_FILE, override=True)
