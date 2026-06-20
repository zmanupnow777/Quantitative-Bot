from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import bot.dashboard_charts as dc


def _price():
    idx = pd.date_range("2024-01-01", periods=60, freq="D", name="Date")
    return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0,
                         "Close": range(60), "Volume": 10}, index=idx)


def _markers():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-10", "2024-02-01"]),
        "price": [9.0, 31.0], "side": ["buy", "sell"], "kind": ["entry", "exit"],
    })


def test_price_band_figure_returns_figure():
    fig = dc.price_band_figure(_price(), _markers())
    assert isinstance(fig, go.Figure)
    # close line + 3 bands + 2 marker groups (buy/sell) = at least 4 traces
    assert len(fig.data) >= 4


def test_equity_figure_returns_figure():
    eq = pd.Series([100100.0, 100060.0],
                   index=pd.to_datetime(["2024-02-02", "2024-02-03"]))
    assert isinstance(dc.equity_figure(eq), go.Figure)


def test_trade_pnl_figure_returns_figure():
    pnls = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-02-02", "2024-02-03"]),
        "symbol": ["SPY", "SPY"], "pnl": [100.0, -40.0], "won": [True, False],
    })
    assert isinstance(dc.trade_pnl_figure(pnls), go.Figure)


def test_drawdown_figure_returns_figure():
    dd_series = pd.Series([0.0, -0.004],
                          index=pd.to_datetime(["2024-02-02", "2024-02-03"]))
    assert isinstance(dc.drawdown_figure(dd_series), go.Figure)
