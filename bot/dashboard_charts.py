"""Pure Plotly figure builders for the dashboard Charts tab.

Each builder assumes non-empty, well-formed input; the UI layer guards
emptiness before calling. Builders never read files or events themselves.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from strategies.indicator_utils import bollinger_bands


def price_band_figure(
    price: pd.DataFrame, markers: pd.DataFrame, length: int = 20, std_dev: float = 2.0
) -> go.Figure:
    """Price line with Bollinger bands and buy/sell trade markers."""
    close = price["Close"]
    lower, middle, upper = bollinger_bands(close, length, std_dev)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=price.index, y=upper, mode="lines",
                             line=dict(width=1, color="rgba(150,150,150,0.5)"), name="Upper band"))
    fig.add_trace(go.Scatter(x=price.index, y=middle, mode="lines",
                             line=dict(width=1, color="rgba(150,150,150,0.8)", dash="dot"), name="Mid"))
    fig.add_trace(go.Scatter(x=price.index, y=lower, mode="lines",
                             line=dict(width=1, color="rgba(150,150,150,0.5)"),
                             fill="tonexty", fillcolor="rgba(150,150,150,0.08)", name="Lower band"))
    fig.add_trace(go.Scatter(x=price.index, y=close, mode="lines",
                             line=dict(width=2, color="#2b8cbe"), name="Close"))

    if not markers.empty:
        lo, hi = price.index.min(), price.index.max()
        in_window = markers[(markers["timestamp"] >= lo) & (markers["timestamp"] <= hi)]
        buys = in_window[in_window["side"] == "buy"]
        sells = in_window[in_window["side"] == "sell"]
        if not buys.empty:
            fig.add_trace(go.Scatter(x=buys["timestamp"], y=buys["price"], mode="markers",
                                     marker=dict(symbol="triangle-up", size=12, color="#1a7a4a"),
                                     name="Buy"))
        if not sells.empty:
            fig.add_trace(go.Scatter(x=sells["timestamp"], y=sells["price"], mode="markers",
                                     marker=dict(symbol="triangle-down", size=12, color="#a02020"),
                                     name="Sell"))

    fig.update_layout(title="Price & Bollinger Bands", xaxis_title="Date",
                      yaxis_title="Price ($)", hovermode="x unified", height=480,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def equity_figure(equity: pd.Series) -> go.Figure:
    """Account value over time."""
    fig = go.Figure(go.Scatter(x=equity.index, y=equity.values, mode="lines",
                               line=dict(width=2, color="#1a7a4a"), name="Account value"))
    fig.update_layout(title="Account Value", xaxis_title="Date",
                      yaxis_title="Value ($)", hovermode="x unified", height=360)
    return fig


def trade_pnl_figure(pnls: pd.DataFrame) -> go.Figure:
    """Per-trade PnL bars, green for wins and red for losses."""
    colors = ["#1a7a4a" if w else "#a02020" for w in pnls["won"]]
    fig = go.Figure(go.Bar(x=pnls["timestamp"], y=pnls["pnl"], marker_color=colors,
                           name="Trade PnL"))
    fig.update_layout(title="Per-Trade PnL", xaxis_title="Trade time",
                      yaxis_title="PnL ($)", height=360)
    return fig


def drawdown_figure(drawdown: pd.Series) -> go.Figure:
    """Underwater curve of drawdown percentage."""
    fig = go.Figure(go.Scatter(x=drawdown.index, y=drawdown.values * 100.0, mode="lines",
                               fill="tozeroy", line=dict(width=1, color="#a02020"),
                               name="Drawdown"))
    fig.update_layout(title="Drawdown (Underwater)", xaxis_title="Date",
                      yaxis_title="Drawdown (%)", height=320)
    return fig
