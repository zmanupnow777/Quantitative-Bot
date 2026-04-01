"""Comparison and reporting helpers for backtest results."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backtester.engine import BacktestResult
from config import settings

DEFAULT_WEIGHTS: dict[str, float] = {
    "total_return": 0.30,
    "annual_return": 0.15,
    "sharpe_ratio": 0.20,
    "sortino_ratio": 0.10,
    "max_drawdown_percent": -0.15,
    "win_rate": 0.05,
    "profit_factor": 0.05,
}


def compare(results: list[BacktestResult]) -> pd.DataFrame:
    """Return a comparison table for a set of backtest results."""
    rows: list[dict[str, object]] = []
    for result in results:
        row: dict[str, object] = {
            "symbol": result.symbol,
            "strategy": result.strategy_name,
            "params": json.dumps(result.params, sort_keys=True),
        }
        row.update(result.metrics)
        rows.append(row)

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["symbol", "strategy"]).reset_index(drop=True)


def rank_strategies(
    results: list[BacktestResult],
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Rank strategies by a weighted normalized score."""
    frame = compare(results)
    if frame.empty:
        return frame

    weights = weights or DEFAULT_WEIGHTS
    score = pd.Series(0.0, index=frame.index)

    for metric, weight in weights.items():
        if metric not in frame.columns:
            continue

        values = pd.to_numeric(frame[metric], errors="coerce").replace([float("inf"), float("-inf")], pd.NA)
        values = values.fillna(values.median() if values.notna().any() else 0.0)

        if values.nunique(dropna=False) <= 1:
            normalized = pd.Series(1.0, index=frame.index)
        else:
            normalized = (values - values.min()) / (values.max() - values.min())

        if weight < 0:
            normalized = 1.0 - normalized

        score += normalized * abs(weight)

    ranked = frame.copy()
    ranked["score"] = score
    return ranked.sort_values("score", ascending=False).reset_index(drop=True)


def generate_report(
    results: list[BacktestResult],
    *,
    report_name: str | None = None,
) -> Path:
    """Write a plain-text comparison report to `reports/`."""
    comparison = compare(results)
    ranked = rank_strategies(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = report_name or f"backtest_report_{timestamp}.txt"
    report_path = settings.REPORTS_DIR / file_name

    lines = [
        "Quant Trading System Backtest Report",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "Ranked Strategies",
        ranked.to_string(index=False) if not ranked.empty else "No results available.",
        "",
        "Comparison Table",
        comparison.to_string(index=False) if not comparison.empty else "No results available.",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def generate_html_report(
    results: list[BacktestResult],
    *,
    report_name: str | None = None,
) -> Path:
    """Write an interactive HTML report with Plotly charts to `reports/`."""
    comparison = compare(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = report_name or f"backtest_report_{timestamp}.html"
    report_path = settings.REPORTS_DIR / file_name

    figure = make_subplots(
        rows=2,
        cols=2,
        specs=[[{"colspan": 2}, None], [{}, {}]],
        subplot_titles=(
            "Equity Curves",
            "Return vs. Drawdown",
            "Sharpe vs. Win Rate",
        ),
    )

    for result in results:
        label = f"{result.symbol} | {result.strategy_name}"
        figure.add_trace(
            go.Scatter(
                x=result.equity_curve.index,
                y=result.equity_curve.values,
                mode="lines",
                name=label,
            ),
            row=1,
            col=1,
        )

    if not comparison.empty:
        figure.add_trace(
            go.Scatter(
                x=comparison["max_drawdown_percent"],
                y=comparison["total_return"],
                mode="markers+text",
                text=[f"{row.symbol} | {row.strategy}" for row in comparison.itertuples()],
                textposition="top center",
                name="Return vs Drawdown",
                showlegend=False,
            ),
            row=2,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=comparison["sharpe_ratio"],
                y=comparison["win_rate"],
                mode="markers+text",
                text=[f"{row.symbol} | {row.strategy}" for row in comparison.itertuples()],
                textposition="top center",
                name="Sharpe vs Win Rate",
                showlegend=False,
            ),
            row=2,
            col=2,
        )

    figure.update_layout(height=900, width=1400, title_text="Backtest Comparison", hovermode="x unified")
    plot_div = figure.to_html(full_html=False, include_plotlyjs="cdn")

    table_html = (
        comparison.to_html(index=False, float_format=lambda value: f"{value:,.4f}")
        if not comparison.empty
        else "<p>No results available.</p>"
    )
    html = "\n".join(
        [
            "<html>",
            "<head><meta charset='utf-8'><title>Backtest Report</title></head>",
            "<body>",
            "<h1>Backtest Report</h1>",
            plot_div,
            "<h2>Comparison Table</h2>",
            table_html,
            "</body>",
            "</html>",
        ]
    )
    report_path.write_text(html, encoding="utf-8")
    return report_path
