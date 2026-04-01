"""Parameter sensitivity and robustness analysis for Project 3."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from itertools import combinations, product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from optimizer.common import (
    EngineConfig,
    StrategyCandidate,
    core_metrics_from_result,
    execute_parallel_tasks,
    get_strategy_param_ranges,
    load_candidate_data,
    load_json,
    run_candidate_backtest,
    save_json,
    strategy_artifact_dir,
    to_jsonable,
    write_dataframe,
    write_plotly_html,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ParamSweepTask:
    """A single sensitivity backtest evaluation."""

    candidate: StrategyCandidate
    engine_config: EngineConfig
    data: pd.DataFrame
    params: dict[str, Any]
    analysis_type: str
    param_names: tuple[str, ...]
    param_values: tuple[Any, ...]


@dataclass(slots=True)
class ParamSensitivityResult:
    """Saved outputs for a strategy parameter sensitivity run."""

    candidate: StrategyCandidate
    summary: dict[str, Any]
    single_param_results: pd.DataFrame
    grid_results: pd.DataFrame
    artifacts: dict[str, Path] = field(default_factory=dict)


def _evaluate_sweep_task(task: ParamSweepTask) -> dict[str, Any]:
    """Run a single sensitivity task and return tabular metrics."""
    record: dict[str, Any] = {
        "analysis_type": task.analysis_type,
        "param_names": list(task.param_names),
        "param_values": list(task.param_values),
        "params": dict(task.params),
    }

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

    record.update({"status": "ok", **core_metrics_from_result(result)})
    return record


def _neighbor_smoothness(values: pd.Series) -> tuple[float, str]:
    """Classify the smoothness of a 1D metric series across adjacent values."""
    clean = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if len(clean) <= 2:
        return 1.0, "smooth"

    total_range = float(clean.max() - clean.min())
    if total_range <= 1e-12:
        return 1.0, "smooth"

    jumps = clean.diff().abs().dropna()
    max_ratio = float(jumps.max() / total_range)
    mean_ratio = float(jumps.mean() / total_range)
    score = max(0.0, min(1.0, 1.0 - (0.65 * max_ratio + 0.35 * mean_ratio)))
    return score, "smooth" if score >= 0.60 else "cliff_like"


def _grid_smoothness(pivot: pd.DataFrame) -> tuple[float, str]:
    """Classify the smoothness of a 2D heatmap surface using neighbor jumps."""
    numeric = pivot.apply(pd.to_numeric, errors="coerce")
    finite_values = numeric.to_numpy(dtype=float)
    finite_values = finite_values[np.isfinite(finite_values)]
    if finite_values.size <= 1:
        return 1.0, "smooth"

    total_range = float(np.nanmax(finite_values) - np.nanmin(finite_values))
    if total_range <= 1e-12:
        return 1.0, "smooth"

    neighbor_jumps: list[float] = []
    grid = numeric.to_numpy(dtype=float)
    for row_index in range(grid.shape[0]):
        for col_index in range(grid.shape[1] - 1):
            left = grid[row_index, col_index]
            right = grid[row_index, col_index + 1]
            if np.isfinite(left) and np.isfinite(right):
                neighbor_jumps.append(abs(float(left - right)))
    for row_index in range(grid.shape[0] - 1):
        for col_index in range(grid.shape[1]):
            upper = grid[row_index, col_index]
            lower = grid[row_index + 1, col_index]
            if np.isfinite(upper) and np.isfinite(lower):
                neighbor_jumps.append(abs(float(upper - lower)))

    if not neighbor_jumps:
        return 1.0, "smooth"

    jumps = pd.Series(neighbor_jumps, dtype=float)
    max_ratio = float(jumps.max() / total_range)
    mean_ratio = float(jumps.mean() / total_range)
    score = max(0.0, min(1.0, 1.0 - (0.65 * max_ratio + 0.35 * mean_ratio)))
    return score, "smooth" if score >= 0.60 else "cliff_like"


def _build_single_param_figure(frame: pd.DataFrame, candidate: StrategyCandidate) -> go.Figure:
    """Create a multi-panel line chart for one-at-a-time sweeps."""
    metrics = [
        ("sharpe_ratio", "Sharpe"),
        ("total_return", "Return"),
        ("max_drawdown_percent", "Max Drawdown"),
        ("win_rate", "Win Rate"),
    ]
    param_names = list(frame["param_name"].dropna().unique())
    figure = make_subplots(
        rows=max(1, len(param_names)),
        cols=4,
        subplot_titles=tuple(
            f"{param} | {label}"
            for param in param_names
            for _, label in metrics
        ),
        horizontal_spacing=0.06,
        vertical_spacing=0.08,
    )

    for row_index, param_name in enumerate(param_names, start=1):
        param_frame = frame[frame["param_name"] == param_name].sort_values("param_sort_value")
        for col_index, (metric_name, label) in enumerate(metrics, start=1):
            figure.add_trace(
                go.Scatter(
                    x=param_frame["param_value_label"],
                    y=param_frame[metric_name],
                    mode="lines+markers",
                    name=f"{param_name} {label}",
                    showlegend=False,
                    hovertemplate=f"{param_name}: %{{x}}<br>{label}: %{{y:.4f}}<extra></extra>",
                ),
                row=row_index,
                col=col_index,
            )

    figure.update_layout(
        title=f"Parameter Sensitivity: {candidate.symbol} | {candidate.strategy_name}",
        height=max(420, 280 * max(1, len(param_names))),
        width=1500,
    )
    return figure


def _build_grid_figure(frame: pd.DataFrame, candidate: StrategyCandidate) -> go.Figure:
    """Create stacked Sharpe heatmaps for all requested parameter pairs."""
    pair_names = frame["pair_name"].dropna().unique().tolist()
    if not pair_names:
        figure = go.Figure()
        figure.update_layout(
            title=f"Parameter Heatmaps: {candidate.symbol} | {candidate.strategy_name}",
            annotations=[dict(text="No 2-parameter sweeps available.", showarrow=False)],
        )
        return figure

    figure = make_subplots(
        rows=len(pair_names),
        cols=1,
        subplot_titles=tuple(pair_names),
        vertical_spacing=0.08,
    )

    for row_index, pair_name in enumerate(pair_names, start=1):
        pair_frame = frame[frame["pair_name"] == pair_name]
        if pair_frame.empty:
            continue
        first_param = str(pair_frame["param_x"].iloc[0])
        second_param = str(pair_frame["param_y"].iloc[0])
        pivot = pair_frame.pivot(index="y_value_label", columns="x_value_label", values="sharpe_ratio")
        return_pivot = pair_frame.pivot(index="y_value_label", columns="x_value_label", values="total_return")
        drawdown_pivot = pair_frame.pivot(index="y_value_label", columns="x_value_label", values="max_drawdown_percent")
        win_rate_pivot = pair_frame.pivot(index="y_value_label", columns="x_value_label", values="win_rate")

        custom_data = np.dstack(
            [
                return_pivot.reindex(index=pivot.index, columns=pivot.columns).to_numpy(dtype=float),
                drawdown_pivot.reindex(index=pivot.index, columns=pivot.columns).to_numpy(dtype=float),
                win_rate_pivot.reindex(index=pivot.index, columns=pivot.columns).to_numpy(dtype=float),
            ]
        )
        figure.add_trace(
            go.Heatmap(
                x=list(pivot.columns),
                y=list(pivot.index),
                z=pivot.to_numpy(dtype=float),
                customdata=custom_data,
                colorbar=dict(title="Sharpe", len=max(0.20, 0.85 / len(pair_names))),
                hovertemplate=(
                    f"{first_param}: %{{x}}<br>"
                    f"{second_param}: %{{y}}<br>"
                    "Sharpe: %{z:.4f}<br>"
                    "Return: %{customdata[0]:.4f}<br>"
                    "Max DD: %{customdata[1]:.4f}<br>"
                    "Win Rate: %{customdata[2]:.4f}<extra></extra>"
                ),
            ),
            row=row_index,
            col=1,
        )
        figure.update_xaxes(title_text=first_param, row=row_index, col=1)
        figure.update_yaxes(title_text=second_param, row=row_index, col=1)

    figure.update_layout(
        title=f"2-Parameter Heatmaps: {candidate.symbol} | {candidate.strategy_name}",
        height=max(420, 360 * len(pair_names)),
        width=1100,
    )
    return figure


def _load_cached_result(candidate: StrategyCandidate, artifact_dir: Path) -> ParamSensitivityResult | None:
    """Return a cached sensitivity result when all expected artifacts exist."""
    summary_path = artifact_dir / "param_sensitivity_summary.json"
    single_path = artifact_dir / "param_sensitivity_single.csv"
    grid_path = artifact_dir / "param_sensitivity_grid.csv"
    if not (summary_path.exists() and single_path.exists() and grid_path.exists()):
        return None

    logger.info("Loading cached parameter sensitivity artifacts for %s.", candidate.safe_name)
    summary = load_json(summary_path)
    return ParamSensitivityResult(
        candidate=candidate,
        summary=summary,
        single_param_results=pd.read_csv(single_path),
        grid_results=pd.read_csv(grid_path),
        artifacts={
            "summary": summary_path,
            "single_csv": single_path,
            "grid_csv": grid_path,
            "single_html": artifact_dir / "param_sensitivity_single.html",
            "grid_html": artifact_dir / "param_sensitivity_grid.html",
        },
    )


def run_parameter_sensitivity(
    candidate: StrategyCandidate,
    engine_config: EngineConfig,
    *,
    data: pd.DataFrame | None = None,
    artifact_dir: Path | None = None,
    resume: bool = True,
    grid_param_pairs: list[tuple[str, str]] | None = None,
    max_workers: int | None = None,
    show_progress: bool = True,
) -> ParamSensitivityResult:
    """Run one-at-a-time and pairwise parameter sweeps for a strategy."""
    target_dir = artifact_dir or strategy_artifact_dir(candidate)
    if resume:
        cached = _load_cached_result(candidate, target_dir)
        if cached is not None:
            return cached

    dataset = data if data is not None else load_candidate_data(candidate)
    base_params = dict(candidate.params)
    param_ranges = get_strategy_param_ranges(candidate)
    ordered_params = list(param_ranges)
    pair_list = grid_param_pairs or list(combinations(ordered_params, 2))

    single_tasks: list[ParamSweepTask] = []
    for param_name, values in param_ranges.items():
        for param_value in values:
            params = dict(base_params)
            params[param_name] = param_value
            single_tasks.append(
                ParamSweepTask(
                    candidate=candidate,
                    engine_config=engine_config,
                    data=dataset,
                    params=params,
                    analysis_type="single",
                    param_names=(param_name,),
                    param_values=(param_value,),
                )
            )

    grid_tasks: list[ParamSweepTask] = []
    for first_param, second_param in pair_list:
        for first_value, second_value in product(param_ranges[first_param], param_ranges[second_param]):
            params = dict(base_params)
            params[first_param] = first_value
            params[second_param] = second_value
            grid_tasks.append(
                ParamSweepTask(
                    candidate=candidate,
                    engine_config=engine_config,
                    data=dataset,
                    params=params,
                    analysis_type="grid",
                    param_names=(first_param, second_param),
                    param_values=(first_value, second_value),
                )
            )

    logger.info(
        "Running parameter sensitivity for %s with %d single sweeps and %d grid sweeps.",
        candidate.safe_name,
        len(single_tasks),
        len(grid_tasks),
    )

    single_records = execute_parallel_tasks(
        single_tasks,
        _evaluate_sweep_task,
        description=f"{candidate.strategy_name} single sweep",
        max_workers=max_workers,
        show_progress=show_progress,
    )
    grid_records = execute_parallel_tasks(
        grid_tasks,
        _evaluate_sweep_task,
        description=f"{candidate.strategy_name} grid sweep",
        max_workers=max_workers,
        show_progress=show_progress,
    )

    single_frame = pd.DataFrame(single_records)
    if single_frame.empty:
        single_frame = pd.DataFrame(
            columns=[
                "analysis_type",
                "param_names",
                "param_values",
                "params",
                "status",
                "error",
                "sharpe_ratio",
                "total_return",
                "max_drawdown_percent",
                "win_rate",
            ]
        )
    else:
        single_frame["param_name"] = single_frame["param_names"].map(lambda values: values[0] if values else None)
        single_frame["param_value"] = single_frame["param_values"].map(lambda values: values[0] if values else None)
        single_frame["param_sort_value"] = pd.to_numeric(single_frame["param_value"], errors="coerce")
        single_frame["param_value_label"] = single_frame["param_value"].astype(str)
        single_frame["is_default"] = single_frame.apply(
            lambda row: row["param_value"] == base_params.get(row["param_name"]),
            axis=1,
        )

    grid_frame = pd.DataFrame(grid_records)
    if grid_frame.empty:
        grid_frame = pd.DataFrame(
            columns=[
                "analysis_type",
                "param_names",
                "param_values",
                "params",
                "status",
                "error",
                "sharpe_ratio",
                "total_return",
                "max_drawdown_percent",
                "win_rate",
            ]
        )
    else:
        grid_frame["param_x"] = grid_frame["param_names"].map(lambda values: values[0] if values else None)
        grid_frame["param_y"] = grid_frame["param_names"].map(lambda values: values[1] if len(values) > 1 else None)
        grid_frame["x_value"] = grid_frame["param_values"].map(lambda values: values[0] if values else None)
        grid_frame["y_value"] = grid_frame["param_values"].map(lambda values: values[1] if len(values) > 1 else None)
        grid_frame["pair_name"] = grid_frame.apply(lambda row: f"{row['param_x']} x {row['param_y']}", axis=1)
        grid_frame["x_value_label"] = grid_frame["x_value"].astype(str)
        grid_frame["y_value_label"] = grid_frame["y_value"].astype(str)

    single_scores: list[dict[str, Any]] = []
    for param_name, group in single_frame[single_frame["status"] == "ok"].groupby("param_name"):
        ordered_group = group.sort_values("param_sort_value")
        score, label = _neighbor_smoothness(ordered_group["sharpe_ratio"])
        single_scores.append(
            {
                "parameter": param_name,
                "smoothness_score": score,
                "classification": label,
                "best_sharpe": float(ordered_group["sharpe_ratio"].max()),
                "worst_sharpe": float(ordered_group["sharpe_ratio"].min()),
            }
        )

    grid_scores: list[dict[str, Any]] = []
    for pair_name, group in grid_frame[grid_frame["status"] == "ok"].groupby("pair_name"):
        pivot = group.pivot(index="y_value_label", columns="x_value_label", values="sharpe_ratio")
        score, label = _grid_smoothness(pivot)
        grid_scores.append(
            {
                "parameter_pair": pair_name,
                "smoothness_score": score,
                "classification": label,
                "best_sharpe": float(group["sharpe_ratio"].max()),
                "worst_sharpe": float(group["sharpe_ratio"].min()),
            }
        )

    all_scores = [entry["smoothness_score"] for entry in single_scores + grid_scores]
    smoothness_score = float(np.mean(all_scores)) if all_scores else 0.0
    smoothness_label = "smooth" if smoothness_score >= 0.60 else "cliff_like"
    invalid_runs = int((single_frame["status"] == "invalid").sum() + (grid_frame["status"] == "invalid").sum())
    summary = {
        "candidate": candidate.to_dict(),
        "single_parameter_scores": single_scores,
        "grid_scores": grid_scores,
        "smoothness_score": smoothness_score,
        "classification": smoothness_label,
        "invalid_runs": invalid_runs,
        "notes": [
            (
                "Performance is relatively smooth across neighboring parameter values."
                if smoothness_label == "smooth"
                else "Performance shows cliff-like jumps across neighboring parameter values."
            )
        ],
    }

    single_figure = _build_single_param_figure(single_frame[single_frame["status"] == "ok"], candidate)
    grid_figure = _build_grid_figure(grid_frame[grid_frame["status"] == "ok"], candidate)

    summary_path = save_json(target_dir / "param_sensitivity_summary.json", to_jsonable(summary))
    single_csv_path = write_dataframe(single_frame, target_dir / "param_sensitivity_single.csv")
    grid_csv_path = write_dataframe(grid_frame, target_dir / "param_sensitivity_grid.csv")
    single_html_path = write_plotly_html(single_figure, target_dir / "param_sensitivity_single.html")
    grid_html_path = write_plotly_html(grid_figure, target_dir / "param_sensitivity_grid.html")

    return ParamSensitivityResult(
        candidate=candidate,
        summary=summary,
        single_param_results=single_frame,
        grid_results=grid_frame,
        artifacts={
            "summary": summary_path,
            "single_csv": single_csv_path,
            "grid_csv": grid_csv_path,
            "single_html": single_html_path,
            "grid_html": grid_html_path,
        },
    )
