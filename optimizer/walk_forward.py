"""Walk-forward optimization and out-of-sample validation for Project 3."""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from optimizer.common import (
    EngineConfig,
    StrategyCandidate,
    aggregate_backtest_results,
    execute_parallel_tasks,
    get_strategy_param_ranges,
    linked_equity_curve,
    load_candidate_data,
    run_candidate_backtest,
    save_json,
    strategy_artifact_dir,
    to_jsonable,
    write_dataframe,
    write_plotly_html,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WalkForwardOptimizationTask:
    """A train-window parameter evaluation task."""

    candidate: StrategyCandidate
    engine_config: EngineConfig
    data: pd.DataFrame
    params: dict[str, Any]


@dataclass(slots=True)
class WalkForwardResult:
    """Persisted walk-forward outputs for one strategy."""

    candidate: StrategyCandidate
    summary: dict[str, Any]
    windows: pd.DataFrame
    parameter_trials: pd.DataFrame
    artifacts: dict[str, Path] = field(default_factory=dict)


def _evaluate_train_task(task: WalkForwardOptimizationTask) -> dict[str, Any]:
    """Run a train-window parameter trial."""
    record: dict[str, Any] = {"params": dict(task.params)}
    try:
        result = run_candidate_backtest(
            task.candidate,
            task.engine_config,
            data=task.data,
            params=task.params,
        )
    except Exception as exc:  # pragma: no cover - exercised via integration pipeline
        record.update(
            {
                "status": "invalid",
                "error": str(exc),
                "sharpe_ratio": np.nan,
                "total_return": np.nan,
                "max_drawdown_percent": np.nan,
                "win_rate": np.nan,
            }
        )
        return record

    record.update(
        {
            "status": "ok",
            "sharpe_ratio": float(result.metrics.get("sharpe_ratio", 0.0)),
            "total_return": float(result.metrics.get("total_return", 0.0)),
            "max_drawdown_percent": float(result.metrics.get("max_drawdown_percent", 0.0)),
            "win_rate": float(result.metrics.get("win_rate", 0.0)),
        }
    )
    return record


def _split_walk_forward_windows(data: pd.DataFrame, n_windows: int) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Split a dataframe into sequential train/test windows."""
    if data.empty:
        raise ValueError("Walk-forward analysis requires non-empty data.")
    if n_windows <= 0:
        raise ValueError("n_windows must be positive.")

    index_blocks = np.array_split(np.arange(len(data)), n_windows)
    windows: list[tuple[pd.DataFrame, pd.DataFrame]] = []

    for block in index_blocks:
        if len(block) < 4:
            continue
        split_at = max(1, int(len(block) * 0.70))
        split_at = min(split_at, len(block) - 1)

        train_index = block[:split_at]
        test_index = block[split_at:]
        train_frame = data.iloc[train_index].copy()
        test_frame = data.iloc[test_index].copy()
        if train_frame.empty or test_frame.empty:
            continue
        windows.append((train_frame, test_frame))

    if not windows:
        raise ValueError("Unable to produce valid walk-forward windows from the available data.")
    return windows


def _parameter_grid(candidate: StrategyCandidate) -> list[dict[str, Any]]:
    """Build a full parameter grid for train-window optimization."""
    base_params = dict(candidate.params)
    param_ranges = get_strategy_param_ranges(candidate)
    if not param_ranges:
        return [base_params]

    param_names = list(param_ranges)
    combinations_list: list[dict[str, Any]] = []
    for values in product(*(param_ranges[name] for name in param_names)):
        params = dict(base_params)
        params.update(dict(zip(param_names, values)))
        combinations_list.append(params)
    return combinations_list


def _select_best_trial(trials: pd.DataFrame) -> pd.Series:
    """Select the best train-window trial using a deterministic ranking."""
    valid = trials[trials["status"] == "ok"].copy()
    if valid.empty:
        raise ValueError("No valid parameter trials were produced for the training window.")
    ranked = valid.sort_values(
        ["sharpe_ratio", "total_return", "max_drawdown_percent"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    return ranked.iloc[0]


def _recommended_params(window_frame: pd.DataFrame, fallback: dict[str, Any]) -> dict[str, Any]:
    """Return the most frequently selected parameter set across windows."""
    if window_frame.empty or "selected_params_json" not in window_frame.columns:
        return dict(fallback)

    counts = Counter(window_frame["selected_params_json"])
    if not counts:
        return dict(fallback)

    top_count = counts.most_common(1)[0][1]
    finalists = [
        params_json
        for params_json, count in counts.items()
        if count == top_count
    ]
    finalists_frame = window_frame[window_frame["selected_params_json"].isin(finalists)].copy()
    finalists_frame["test_sharpe_ratio"] = pd.to_numeric(finalists_frame["test_sharpe_ratio"], errors="coerce").fillna(0.0)
    selected_json = finalists_frame.sort_values("test_sharpe_ratio", ascending=False)["selected_params_json"].iloc[0]
    return json.loads(selected_json)


def _build_walk_forward_figure(
    window_frame: pd.DataFrame,
    linked_test_curve: pd.Series,
    candidate: StrategyCandidate,
) -> go.Figure:
    """Create the walk-forward summary visualization."""
    figure = make_subplots(
        rows=2,
        cols=2,
        specs=[[{"colspan": 2}, None], [{}, {}]],
        subplot_titles=(
            "Linked Out-of-Sample Equity Curve",
            "Train vs Test Sharpe by Window",
            "Train vs Test Return by Window",
        ),
    )
    figure.add_trace(
        go.Scatter(
            x=linked_test_curve.index,
            y=linked_test_curve.values,
            mode="lines",
            name="Out-of-sample equity",
        ),
        row=1,
        col=1,
    )

    labels = [f"Window {value}" for value in window_frame["window"]]
    figure.add_trace(
        go.Bar(
            x=labels,
            y=window_frame["train_sharpe_ratio"],
            name="Train Sharpe",
        ),
        row=2,
        col=1,
    )
    figure.add_trace(
        go.Bar(
            x=labels,
            y=window_frame["test_sharpe_ratio"],
            name="Test Sharpe",
        ),
        row=2,
        col=1,
    )
    figure.add_trace(
        go.Bar(
            x=labels,
            y=window_frame["train_total_return"],
            name="Train Return",
            showlegend=False,
        ),
        row=2,
        col=2,
    )
    figure.add_trace(
        go.Bar(
            x=labels,
            y=window_frame["test_total_return"],
            name="Test Return",
            showlegend=False,
        ),
        row=2,
        col=2,
    )
    figure.update_layout(
        title=f"Walk-Forward Analysis: {candidate.symbol} | {candidate.strategy_name}",
        barmode="group",
        height=900,
        width=1400,
        hovermode="x unified",
    )
    return figure


def _load_cached_result(candidate: StrategyCandidate, artifact_dir: Path) -> WalkForwardResult | None:
    """Return cached walk-forward outputs when available."""
    summary_path = artifact_dir / "walk_forward_summary.json"
    windows_path = artifact_dir / "walk_forward_windows.csv"
    trials_path = artifact_dir / "walk_forward_parameter_trials.csv"
    if not (summary_path.exists() and windows_path.exists() and trials_path.exists()):
        return None

    logger.info("Loading cached walk-forward artifacts for %s.", candidate.safe_name)
    return WalkForwardResult(
        candidate=candidate,
        summary=json.loads(summary_path.read_text(encoding="utf-8")),
        windows=pd.read_csv(windows_path),
        parameter_trials=pd.read_csv(trials_path),
        artifacts={
            "summary": summary_path,
            "windows_csv": windows_path,
            "trials_csv": trials_path,
            "html": artifact_dir / "walk_forward.html",
            "linked_equity_csv": artifact_dir / "walk_forward_linked_test_equity.csv",
        },
    )


def run_walk_forward_analysis(
    candidate: StrategyCandidate,
    engine_config: EngineConfig,
    *,
    data: pd.DataFrame | None = None,
    artifact_dir: Path | None = None,
    resume: bool = True,
    n_windows: int = 5,
    optimize_on_train: bool = True,
    max_workers: int | None = None,
    show_progress: bool = True,
) -> WalkForwardResult:
    """Run walk-forward optimization and out-of-sample evaluation."""
    target_dir = artifact_dir or strategy_artifact_dir(candidate)
    if resume:
        cached = _load_cached_result(candidate, target_dir)
        if cached is not None:
            return cached

    dataset = data if data is not None else load_candidate_data(candidate)
    windows = _split_walk_forward_windows(dataset, n_windows=n_windows)
    full_grid = _parameter_grid(candidate)

    window_rows: list[dict[str, Any]] = []
    trial_rows: list[dict[str, Any]] = []
    train_results = []
    test_results = []

    for window_number, (train_data, test_data) in enumerate(windows, start=1):
        logger.info(
            "Running walk-forward window %d/%d for %s.",
            window_number,
            len(windows),
            candidate.safe_name,
        )

        if optimize_on_train:
            tasks = [
                WalkForwardOptimizationTask(
                    candidate=candidate,
                    engine_config=engine_config,
                    data=train_data,
                    params=params,
                )
                for params in full_grid
            ]
            trial_records = execute_parallel_tasks(
                tasks,
                _evaluate_train_task,
                description=f"{candidate.strategy_name} train optimize",
                max_workers=max_workers,
                show_progress=show_progress,
            )
            trial_frame = pd.DataFrame(trial_records)
            if trial_frame.empty:
                raise ValueError(f"No parameter trials ran for walk-forward window {window_number}.")
            trial_frame["window"] = window_number
            trial_frame["params_json"] = trial_frame["params"].map(lambda value: json.dumps(value, sort_keys=True))
            trial_rows.extend(trial_frame.to_dict(orient="records"))
            best_trial = _select_best_trial(trial_frame)
            selected_params = dict(best_trial["params"])
        else:
            selected_params = dict(candidate.params)
            trial_frame = pd.DataFrame(
                [
                    {
                        "window": window_number,
                        "status": "skipped",
                        "params": selected_params,
                        "params_json": json.dumps(selected_params, sort_keys=True),
                    }
                ]
            )
            trial_rows.extend(trial_frame.to_dict(orient="records"))

        train_result = run_candidate_backtest(candidate, engine_config, data=train_data, params=selected_params)
        test_result = run_candidate_backtest(candidate, engine_config, data=test_data, params=selected_params)
        train_results.append(train_result)
        test_results.append(test_result)

        window_rows.append(
            {
                "window": window_number,
                "train_start": str(train_data.index.min().date()),
                "train_end": str(train_data.index.max().date()),
                "test_start": str(test_data.index.min().date()),
                "test_end": str(test_data.index.max().date()),
                "selected_params_json": json.dumps(selected_params, sort_keys=True),
                "selected_params": selected_params,
                "train_sharpe_ratio": float(train_result.metrics.get("sharpe_ratio", 0.0)),
                "test_sharpe_ratio": float(test_result.metrics.get("sharpe_ratio", 0.0)),
                "train_total_return": float(train_result.metrics.get("total_return", 0.0)),
                "test_total_return": float(test_result.metrics.get("total_return", 0.0)),
                "train_max_drawdown_percent": float(train_result.metrics.get("max_drawdown_percent", 0.0)),
                "test_max_drawdown_percent": float(test_result.metrics.get("max_drawdown_percent", 0.0)),
                "train_win_rate": float(train_result.metrics.get("win_rate", 0.0)),
                "test_win_rate": float(test_result.metrics.get("win_rate", 0.0)),
                "train_total_trades": float(train_result.metrics.get("total_trades", len(train_result.trades))),
                "test_total_trades": float(test_result.metrics.get("total_trades", len(test_result.trades))),
            }
        )

    window_frame = pd.DataFrame(window_rows)
    trials_frame = pd.DataFrame(trial_rows)
    linked_test_curve = linked_equity_curve(test_results, initial_capital=engine_config.initial_capital)

    train_metrics = aggregate_backtest_results(train_results, engine_config)
    test_metrics = aggregate_backtest_results(test_results, engine_config)
    mean_train_sharpe = float(window_frame["train_sharpe_ratio"].mean()) if not window_frame.empty else 0.0
    mean_test_sharpe = float(window_frame["test_sharpe_ratio"].mean()) if not window_frame.empty else 0.0
    sharpe_gap = mean_train_sharpe - mean_test_sharpe
    overfitting_flag = bool(
        mean_train_sharpe > mean_test_sharpe + 0.35
        and mean_train_sharpe > max(0.10, mean_test_sharpe * 1.5)
    )
    notes = []
    if overfitting_flag:
        notes.append(
            "Potential overfitting: in-sample Sharpe materially exceeds out-of-sample Sharpe."
        )

    recommended_params = _recommended_params(window_frame, candidate.params)
    summary = {
        "candidate": candidate.to_dict(),
        "n_windows": len(windows),
        "optimize_on_train": optimize_on_train,
        "aggregate_metrics": {
            "in_sample": to_jsonable(train_metrics),
            "out_of_sample": to_jsonable(test_metrics),
        },
        "mean_train_sharpe": mean_train_sharpe,
        "mean_test_sharpe": mean_test_sharpe,
        "sharpe_gap": sharpe_gap,
        "overfitting_flag": overfitting_flag,
        "recommended_params": recommended_params,
        "notes": notes,
    }

    figure = _build_walk_forward_figure(window_frame, linked_test_curve, candidate)

    summary_path = save_json(target_dir / "walk_forward_summary.json", to_jsonable(summary))
    windows_csv_path = write_dataframe(window_frame, target_dir / "walk_forward_windows.csv")
    trials_csv_path = write_dataframe(trials_frame, target_dir / "walk_forward_parameter_trials.csv")
    linked_equity_path = linked_test_curve.rename("equity").to_frame().reset_index(names="Date")
    linked_equity_csv_path = write_dataframe(linked_equity_path, target_dir / "walk_forward_linked_test_equity.csv")
    html_path = write_plotly_html(figure, target_dir / "walk_forward.html")

    return WalkForwardResult(
        candidate=candidate,
        summary=summary,
        windows=window_frame,
        parameter_trials=trials_frame,
        artifacts={
            "summary": summary_path,
            "windows_csv": windows_csv_path,
            "trials_csv": trials_csv_path,
            "linked_equity_csv": linked_equity_csv_path,
            "html": html_path,
        },
    )
