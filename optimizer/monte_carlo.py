"""Monte Carlo trade-order analysis for Project 3."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backtester import BacktestResult
from optimizer.common import (
    default_workers,
    execute_parallel_tasks,
    load_json,
    save_json,
    to_jsonable,
    write_dataframe,
    write_plotly_html,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MonteCarloChunkTask:
    """A chunk of Monte Carlo trade-order simulations."""

    trade_pnls: list[float]
    initial_capital: float
    simulation_count: int
    seed: int


@dataclass(slots=True)
class MonteCarloResult:
    """Persisted Monte Carlo outputs for one baseline backtest."""

    strategy_name: str
    symbol: str
    summary: dict[str, Any]
    simulations: pd.DataFrame
    equity_curves: pd.DataFrame
    artifacts: dict[str, Path] = field(default_factory=dict)


def _simulate_chunk(task: MonteCarloChunkTask) -> dict[str, Any]:
    """Run a chunk of Monte Carlo simulations for shuffled trade order."""
    rng = np.random.default_rng(task.seed)
    trade_pnls = np.asarray(task.trade_pnls, dtype=float)
    trade_count = len(trade_pnls)

    final_returns: list[float] = []
    drawdowns: list[float] = []
    curves: list[list[float]] = []

    for _ in range(task.simulation_count):
        shuffled = rng.permutation(trade_pnls) if trade_count > 1 else trade_pnls.copy()
        equity = task.initial_capital + np.concatenate([[0.0], np.cumsum(shuffled)])
        running_max = np.maximum.accumulate(equity)
        drawdown = np.abs(np.min((equity / running_max) - 1.0)) if running_max.size else 0.0

        final_returns.append(float((equity[-1] / task.initial_capital) - 1.0))
        drawdowns.append(float(drawdown))
        curves.append(equity.astype(float).tolist())

    return {
        "final_returns": final_returns,
        "max_drawdowns": drawdowns,
        "equity_curves": curves,
    }


def _build_distribution_figure(
    simulations: pd.DataFrame,
    equity_curves: pd.DataFrame,
    baseline_result: BacktestResult,
) -> go.Figure:
    """Create Monte Carlo distribution plots and percentile bands."""
    baseline_trade_equity = baseline_result.initial_capital + baseline_result.trades["pnl"].cumsum()
    baseline_trade_equity = pd.concat(
        [
            pd.Series([baseline_result.initial_capital], index=[0], dtype=float),
            baseline_trade_equity.reset_index(drop=True),
        ]
    )
    percentile_frame = equity_curves.quantile([0.05, 0.50, 0.95]).T

    figure = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Return Distribution",
            "Max Drawdown Distribution",
            "Simulated Equity Curves Percentiles",
            "Return vs Max Drawdown",
        ),
    )
    figure.add_trace(
        go.Histogram(x=simulations["final_return"], nbinsx=40, name="Final return"),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Histogram(x=simulations["max_drawdown"], nbinsx=40, name="Max drawdown"),
        row=1,
        col=2,
    )
    figure.add_trace(
        go.Scatter(
            x=percentile_frame.index,
            y=percentile_frame[0.05],
            mode="lines",
            name="5th percentile",
        ),
        row=2,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=percentile_frame.index,
            y=percentile_frame[0.50],
            mode="lines",
            name="Median",
        ),
        row=2,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=percentile_frame.index,
            y=percentile_frame[0.95],
            mode="lines",
            name="95th percentile",
        ),
        row=2,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=baseline_trade_equity.index,
            y=baseline_trade_equity.values,
            mode="lines",
            name="Baseline path",
            line=dict(width=3, dash="dash"),
        ),
        row=2,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=simulations["max_drawdown"],
            y=simulations["final_return"],
            mode="markers",
            name="Simulations",
            marker=dict(size=7, opacity=0.55),
        ),
        row=2,
        col=2,
    )

    figure.update_xaxes(title_text="Final Return", row=1, col=1)
    figure.update_xaxes(title_text="Max Drawdown", row=1, col=2)
    figure.update_xaxes(title_text="Trade Number", row=2, col=1)
    figure.update_xaxes(title_text="Max Drawdown", row=2, col=2)
    figure.update_yaxes(title_text="Count", row=1, col=1)
    figure.update_yaxes(title_text="Count", row=1, col=2)
    figure.update_yaxes(title_text="Equity", row=2, col=1)
    figure.update_yaxes(title_text="Final Return", row=2, col=2)
    figure.update_layout(
        title=f"Monte Carlo Analysis: {baseline_result.symbol} | {baseline_result.strategy_name}",
        height=900,
        width=1400,
        bargap=0.08,
    )
    return figure


def _load_cached_result(result: BacktestResult, artifact_dir: Path) -> MonteCarloResult | None:
    """Return cached Monte Carlo outputs when they already exist."""
    summary_path = artifact_dir / "monte_carlo_summary.json"
    simulations_path = artifact_dir / "monte_carlo_simulations.csv"
    curves_path = artifact_dir / "monte_carlo_equity_curves.csv"
    if not (summary_path.exists() and simulations_path.exists() and curves_path.exists()):
        return None

    logger.info("Loading cached Monte Carlo artifacts for %s.", result.strategy_name)
    return MonteCarloResult(
        strategy_name=result.strategy_name,
        symbol=result.symbol,
        summary=load_json(summary_path),
        simulations=pd.read_csv(simulations_path),
        equity_curves=pd.read_csv(curves_path),
        artifacts={
            "summary": summary_path,
            "simulations_csv": simulations_path,
            "equity_curves_csv": curves_path,
            "html": artifact_dir / "monte_carlo.html",
        },
    )


def run_monte_carlo_analysis(
    baseline_result: BacktestResult,
    *,
    n_simulations: int = 1000,
    artifact_dir: Path,
    resume: bool = True,
    seed: int = 42,
    max_workers: int | None = None,
    show_progress: bool = True,
) -> MonteCarloResult:
    """Shuffle trade order repeatedly and summarize the distribution of outcomes."""
    if resume:
        cached = _load_cached_result(baseline_result, artifact_dir)
        if cached is not None:
            return cached

    trade_pnls = baseline_result.trades["pnl"].astype(float).tolist()
    if not trade_pnls:
        summary = {
            "strategy_name": baseline_result.strategy_name,
            "symbol": baseline_result.symbol,
            "n_simulations": 0,
            "trade_count": 0,
            "median_return": 0.0,
            "return_5th_percentile": 0.0,
            "return_95th_percentile": 0.0,
            "probability_of_profit": 0.0,
            "worst_case_drawdown": 0.0,
            "notes": ["Monte Carlo analysis skipped because the trade list is empty."],
        }
        simulations = pd.DataFrame(columns=["simulation_id", "final_return", "max_drawdown"])
        equity_curves = pd.DataFrame()
        summary_path = save_json(artifact_dir / "monte_carlo_summary.json", summary)
        simulations_path = write_dataframe(simulations, artifact_dir / "monte_carlo_simulations.csv")
        curves_path = write_dataframe(equity_curves, artifact_dir / "monte_carlo_equity_curves.csv")
        html_path = write_plotly_html(go.Figure(), artifact_dir / "monte_carlo.html")
        return MonteCarloResult(
            strategy_name=baseline_result.strategy_name,
            symbol=baseline_result.symbol,
            summary=summary,
            simulations=simulations,
            equity_curves=equity_curves,
            artifacts={
                "summary": summary_path,
                "simulations_csv": simulations_path,
                "equity_curves_csv": curves_path,
                "html": html_path,
            },
        )

    worker_count = default_workers(max_workers)
    base_chunk = max(1, n_simulations // worker_count)
    chunk_sizes = [base_chunk] * worker_count
    for index in range(n_simulations - (base_chunk * worker_count)):
        chunk_sizes[index] += 1
    tasks = [
        MonteCarloChunkTask(
            trade_pnls=trade_pnls,
            initial_capital=baseline_result.initial_capital,
            simulation_count=size,
            seed=seed + index,
        )
        for index, size in enumerate(chunk_sizes)
        if size > 0
    ]

    logger.info(
        "Running %d Monte Carlo simulations for %s with %d chunks.",
        n_simulations,
        baseline_result.strategy_name,
        len(tasks),
    )
    chunk_results = execute_parallel_tasks(
        tasks,
        _simulate_chunk,
        description=f"{baseline_result.strategy_name} monte carlo",
        max_workers=max_workers,
        show_progress=show_progress,
    )

    final_returns = [
        simulation_return
        for chunk in chunk_results
        for simulation_return in chunk["final_returns"]
    ]
    drawdowns = [
        drawdown
        for chunk in chunk_results
        for drawdown in chunk["max_drawdowns"]
    ]
    curves = [
        curve
        for chunk in chunk_results
        for curve in chunk["equity_curves"]
    ]

    simulations = pd.DataFrame(
        {
            "simulation_id": np.arange(1, len(final_returns) + 1),
            "final_return": final_returns,
            "max_drawdown": drawdowns,
        }
    )
    equity_curves = pd.DataFrame(curves).transpose()
    equity_curves.columns = [f"simulation_{index + 1}" for index in range(equity_curves.shape[1])]
    equity_curves.insert(0, "trade_number", np.arange(equity_curves.shape[0]))

    notes: list[str] = []
    if len(trade_pnls) < 10:
        notes.append("Monte Carlo distribution is based on fewer than 10 trades and may be unstable.")

    summary = {
        "strategy_name": baseline_result.strategy_name,
        "symbol": baseline_result.symbol,
        "n_simulations": len(simulations),
        "trade_count": len(trade_pnls),
        "median_return": float(np.median(final_returns)),
        "return_5th_percentile": float(np.percentile(final_returns, 5)),
        "return_95th_percentile": float(np.percentile(final_returns, 95)),
        "probability_of_profit": float(np.mean(np.asarray(final_returns) > 0.0)),
        "worst_case_drawdown": float(np.max(drawdowns)),
        "baseline_return": float(baseline_result.metrics.get("total_return", 0.0)),
        "baseline_max_drawdown": float(baseline_result.metrics.get("max_drawdown_percent", 0.0)),
        "notes": notes,
    }

    figure = _build_distribution_figure(simulations, equity_curves.drop(columns="trade_number"), baseline_result)

    summary_path = save_json(artifact_dir / "monte_carlo_summary.json", to_jsonable(summary))
    simulations_path = write_dataframe(simulations, artifact_dir / "monte_carlo_simulations.csv")
    curves_path = write_dataframe(equity_curves, artifact_dir / "monte_carlo_equity_curves.csv")
    html_path = write_plotly_html(figure, artifact_dir / "monte_carlo.html")

    return MonteCarloResult(
        strategy_name=baseline_result.strategy_name,
        symbol=baseline_result.symbol,
        summary=summary,
        simulations=simulations,
        equity_curves=equity_curves,
        artifacts={
            "summary": summary_path,
            "simulations_csv": simulations_path,
            "equity_curves_csv": curves_path,
            "html": html_path,
        },
    )
