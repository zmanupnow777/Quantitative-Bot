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


def _trade_events():
    return [
        {"event": "position_opened", "timestamp": "2024-02-01T10:00:00", "symbol": "SPY",
         "direction": "long", "qty": 10, "price": 100.0},
        {"event": "position_closed", "timestamp": "2024-02-02T10:00:00", "symbol": "SPY",
         "side": "long", "qty": 10, "entry_price": 100.0, "exit_price": 110.0,
         "pnl": 100.0, "pnl_pct": 0.10, "exit_reason": "take_profit"},
        {"event": "position_closed", "timestamp": "2024-02-03T10:00:00", "symbol": "SPY",
         "side": "long", "qty": 10, "entry_price": 110.0, "exit_price": 106.0,
         "pnl": -40.0, "pnl_pct": -0.036, "exit_reason": "stop_loss"},
        {"event": "signal", "timestamp": "2024-02-04T10:00:00", "direction": "none"},
    ]


def test_get_trade_markers():
    m = dd.get_trade_markers(_trade_events())
    assert list(m["kind"]) == ["entry", "exit", "exit"]
    assert list(m["side"]) == ["buy", "sell", "sell"]
    assert list(m["price"]) == [100.0, 110.0, 106.0]


def test_get_trade_markers_empty():
    assert dd.get_trade_markers([{"event": "signal"}]).empty


def test_build_equity_series_accumulates():
    eq = dd.build_equity_series(_trade_events(), initial_capital=100_000.0)
    assert list(eq.values) == [100100.0, 100060.0]
    assert str(eq.index[0]) == "2024-02-02 10:00:00"


def test_build_equity_series_empty():
    assert dd.build_equity_series([]).empty


def test_build_trade_pnls_won_flag():
    p = dd.build_trade_pnls(_trade_events())
    assert list(p["pnl"]) == [100.0, -40.0]
    assert list(p["won"]) == [True, False]


def test_compute_drawdown():
    eq = dd.build_equity_series(_trade_events(), initial_capital=100_000.0)
    dd_series = dd.compute_drawdown(eq)
    # peak at first point -> 0; second point down 40 from peak 100100
    assert dd_series.iloc[0] == 0.0
    assert abs(dd_series.iloc[1] - (-40.0 / 100100.0)) < 1e-9


def test_compute_drawdown_empty():
    assert dd.compute_drawdown(pd.Series(dtype=float)).empty


def test_build_trade_pnls_empty():
    assert dd.build_trade_pnls([]).empty


def test_empty_marker_and_pnl_frames_have_columns():
    assert list(dd.get_trade_markers([]).columns) == ["timestamp", "price", "side", "kind"]
    assert list(dd.build_trade_pnls([]).columns) == ["timestamp", "symbol", "pnl", "won"]


def test_compute_drawdown_handles_zero_peak():
    import numpy as np
    eq = pd.Series([0.0, -10.0], index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    out = dd.compute_drawdown(eq)
    assert not out.isna().any()
    assert not np.isinf(out).any()
    assert out.iloc[0] == 0.0
