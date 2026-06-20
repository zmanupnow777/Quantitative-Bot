from __future__ import annotations

from pathlib import Path

import pandas as pd

import bot.dashboard_data as dd


def _make_cache(tmp_path: Path) -> Path:
    cache = tmp_path / "cache"
    (cache / "SPY").mkdir(parents=True)
    idx = pd.date_range("2024-01-01", periods=300, freq="D", name="Date")
    df = pd.DataFrame(
        {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": range(300), "Volume": 10},
        index=idx,
    )
    df.to_parquet(cache / "SPY" / "1d.parquet")
    return cache


def test_list_cached_symbols(tmp_path, monkeypatch):
    cache = _make_cache(tmp_path)
    monkeypatch.setattr(dd.settings, "DATA_DIR", cache)
    assert dd.list_cached_symbols() == ["SPY"]


def test_list_cached_symbols_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dd.settings, "DATA_DIR", tmp_path / "nope")
    assert dd.list_cached_symbols() == []


def test_load_price_window_returns_last_bars(tmp_path, monkeypatch):
    cache = _make_cache(tmp_path)
    monkeypatch.setattr(dd.settings, "DATA_DIR", cache)
    df = dd.load_price_window("SPY", "1d", bars=50)
    assert len(df) == 50
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df["Close"].iloc[-1] == 299


def test_load_price_window_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(dd.settings, "DATA_DIR", tmp_path)
    assert dd.load_price_window("NOPE", "1d").empty
