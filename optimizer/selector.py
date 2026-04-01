"""Robustness-aware strategy selection for Project 3."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backtester import BacktestResult
from optimizer.common import save_json, to_jsonable, write_dataframe
from optimizer.monte_carlo import MonteCarloResult
from optimizer.param_sensitivity import ParamSensitivityResult
from optimizer.stress_test import StressTestResult
from optimizer.walk_forward import WalkForwardResult

logger = logging.getLogger(__name__)

SCORING_RUBRIC: dict[str, float] = {
    "parameter_sensitivity_smoothness": 0.25,
    "walk_forward_oos_sharpe": 0.25,
    "monte_carlo_probability_of_profit": 0.20,
    "stress_test_consistency": 0.15,
    "raw_backtest_sharpe": 0.15,
}


@dataclass(slots=True)
class StrategyAnalysisBundle:
    """All Project 3 analysis outputs for one strategy candidate."""

    baseline_result: BacktestResult
    sensitivity: ParamSensitivityResult
    walk_forward: WalkForwardResult
    monte_carlo: MonteCarloResult
    stress_test: StressTestResult
    artifacts: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class StrategySelectionResult:
    """Persisted final ranking and report outputs."""

    ranking: pd.DataFrame
    recommendation: dict[str, Any]
    warnings: list[str]
    artifacts: dict[str, Path] = field(default_factory=dict)


def _min_max(series: pd.Series) -> pd.Series:
    """Return min-max normalized values with a flat-series fallback."""
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    if numeric.nunique(dropna=False) <= 1:
        return pd.Series(1.0, index=numeric.index)
    return (numeric - numeric.min()) / (numeric.max() - numeric.min())


def _choose_selected_params(bundle: StrategyAnalysisBundle) -> tuple[dict[str, Any], str]:
    """Return the final parameter recommendation for a strategy."""
    recommended = bundle.walk_forward.summary.get("recommended_params") or bundle.baseline_result.params
    if bundle.walk_forward.summary.get("overfitting_flag"):
        return dict(bundle.baseline_result.params), "baseline_defaults"
    return dict(recommended), "walk_forward"


def _build_rationale(row: pd.Series) -> str:
    """Create a short natural-language rationale for the chosen strategy."""
    parts: list[str] = []
    if row["parameter_sensitivity_smoothness"] >= 0.60:
        parts.append("a smooth parameter surface")
    if row["walk_forward_oos_sharpe"] > 0.0:
        parts.append("positive out-of-sample Sharpe")
    if row["monte_carlo_probability_of_profit"] >= 0.50:
        parts.append("favorable Monte Carlo profit odds")
    if row["stress_test_consistency"] >= 0.50:
        parts.append("balanced regime performance")
    if not parts:
        parts.append("the strongest combined robustness score in the candidate set")
    return ", ".join(parts[:-1]) + (", and " if len(parts) > 1 else "") + parts[-1]


def _build_report_figure(ranking: pd.DataFrame) -> go.Figure:
    """Create the comprehensive selector summary figure."""
    labels = [f"{row.symbol} | {row.strategy}" for row in ranking.itertuples()]
    figure = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Final Weighted Score",
            "Weighted Component Contributions",
            "Baseline Sharpe vs Walk-Forward OOS Sharpe",
            "Smoothness vs Stress Consistency",
        ),
    )
    figure.add_trace(
        go.Bar(
            x=labels,
            y=ranking["final_score"],
            name="Final score",
        ),
        row=1,
        col=1,
    )

    for metric, weight in SCORING_RUBRIC.items():
        normalized_column = f"{metric}_normalized"
        figure.add_trace(
            go.Bar(
                x=labels,
                y=ranking[normalized_column] * weight,
                name=metric,
            ),
            row=1,
            col=2,
        )

    figure.add_trace(
        go.Scatter(
            x=ranking["raw_backtest_sharpe"],
            y=ranking["walk_forward_oos_sharpe"],
            mode="markers+text",
            text=labels,
            textposition="top center",
            marker=dict(
                size=14,
                color=ranking["monte_carlo_probability_of_profit"],
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="MC Profit Prob"),
            ),
            name="Sharpe comparison",
        ),
        row=2,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=ranking["parameter_sensitivity_smoothness"],
            y=ranking["stress_test_consistency"],
            mode="markers+text",
            text=labels,
            textposition="top center",
            marker=dict(size=14, color=ranking["final_score"], colorscale="Blues"),
            name="Robustness",
        ),
        row=2,
        col=2,
    )
    figure.update_layout(
        title="Project 3 Strategy Selection",
        height=900,
        width=1500,
        barmode="stack",
        hovermode="closest",
    )
    figure.update_xaxes(title_text="Baseline Sharpe", row=2, col=1)
    figure.update_yaxes(title_text="Walk-Forward OOS Sharpe", row=2, col=1)
    figure.update_xaxes(title_text="Parameter Smoothness", row=2, col=2)
    figure.update_yaxes(title_text="Stress Consistency", row=2, col=2)
    return figure


def select_strategies(
    bundles: list[StrategyAnalysisBundle],
    *,
    report_path: Path,
    ranking_csv_path: Path | None = None,
) -> StrategySelectionResult:
    """Rank strategies using the Project 3 robustness rubric and write an HTML report."""
    if not bundles:
        raise ValueError("At least one strategy bundle is required for selection.")

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for bundle in bundles:
        baseline = bundle.baseline_result
        selected_params, selected_source = _choose_selected_params(bundle)
        overfitting_flag = bool(bundle.walk_forward.summary.get("overfitting_flag", False))
        regime_flag = bool(bundle.stress_test.summary.get("one_regime_flag", False))

        if overfitting_flag:
            warnings.append(
                f"{baseline.symbol} | {baseline.strategy_name}: walk-forward analysis flagged possible overfitting."
            )
        if regime_flag:
            warnings.append(
                f"{baseline.symbol} | {baseline.strategy_name}: strategy appears regime-dependent."
            )
        for note in bundle.monte_carlo.summary.get("notes", []):
            warnings.append(f"{baseline.symbol} | {baseline.strategy_name}: {note}")
        for note in bundle.stress_test.summary.get("notes", []):
            warnings.append(f"{baseline.symbol} | {baseline.strategy_name}: {note}")

        rows.append(
            {
                "symbol": baseline.symbol,
                "strategy": baseline.strategy_name,
                "final_params": selected_params,
                "final_params_json": json.dumps(selected_params, sort_keys=True),
                "final_params_source": selected_source,
                "parameter_sensitivity_smoothness": float(bundle.sensitivity.summary.get("smoothness_score", 0.0)),
                "walk_forward_oos_sharpe": float(
                    bundle.walk_forward.summary.get("aggregate_metrics", {})
                    .get("out_of_sample", {})
                    .get("sharpe_ratio", 0.0)
                ),
                "monte_carlo_probability_of_profit": float(
                    bundle.monte_carlo.summary.get("probability_of_profit", 0.0)
                ),
                "stress_test_consistency": float(bundle.stress_test.summary.get("consistency_score", 0.0)),
                "raw_backtest_sharpe": float(baseline.metrics.get("sharpe_ratio", 0.0)),
                "baseline_return": float(baseline.metrics.get("total_return", 0.0)),
                "overfitting_flag": overfitting_flag,
                "regime_dependency_flag": regime_flag,
                "sensitivity_html": str(bundle.sensitivity.artifacts.get("single_html", "")),
                "walk_forward_html": str(bundle.walk_forward.artifacts.get("html", "")),
                "monte_carlo_html": str(bundle.monte_carlo.artifacts.get("html", "")),
                "stress_test_html": str(bundle.stress_test.artifacts.get("html", "")),
            }
        )

    ranking = pd.DataFrame(rows)
    for metric in SCORING_RUBRIC:
        ranking[f"{metric}_normalized"] = _min_max(ranking[metric])

    ranking["final_score"] = 0.0
    for metric, weight in SCORING_RUBRIC.items():
        ranking["final_score"] += ranking[f"{metric}_normalized"] * weight

    ranking = ranking.sort_values("final_score", ascending=False).reset_index(drop=True)
    ranking.insert(0, "rank", range(1, len(ranking) + 1))
    if ranking["monte_carlo_probability_of_profit"].nunique(dropna=False) <= 1:
        warnings.append(
            "Monte Carlo probability of profit was identical across all candidates, so that rubric component did not affect the ranking in this run."
        )
    recommendation_row = ranking.iloc[0]
    recommendation = {
        "symbol": recommendation_row["symbol"],
        "strategy": recommendation_row["strategy"],
        "final_score": float(recommendation_row["final_score"]),
        "selected_params": json.loads(recommendation_row["final_params_json"]),
        "selected_params_source": recommendation_row["final_params_source"],
        "rationale": _build_rationale(recommendation_row),
    }

    figure = _build_report_figure(ranking)
    chart_html = figure.to_html(full_html=False, include_plotlyjs="cdn")
    ranking_table = ranking.drop(
        columns=[
            "final_params",
            "sensitivity_html",
            "walk_forward_html",
            "monte_carlo_html",
            "stress_test_html",
        ]
    ).to_html(index=False, float_format=lambda value: f"{value:,.4f}")

    detail_rows = []
    for row in ranking.itertuples(index=False):
        detail_rows.append(
            {
                "Rank": row.rank,
                "Symbol": row.symbol,
                "Strategy": row.strategy,
                "Final Params": row.final_params_json,
                "Param Sensitivity": f"<a href='{row.sensitivity_html}'>open</a>",
                "Walk Forward": f"<a href='{row.walk_forward_html}'>open</a>",
                "Monte Carlo": f"<a href='{row.monte_carlo_html}'>open</a>",
                "Stress Test": f"<a href='{row.stress_test_html}'>open</a>",
            }
        )
    details_table = pd.DataFrame(detail_rows).to_html(index=False, escape=False)

    warning_items = "".join(f"<li>{warning}</li>" for warning in sorted(set(warnings)))
    html = "\n".join(
        [
            "<html>",
            "<head><meta charset='utf-8'><title>Optimization Report</title></head>",
            "<body>",
            "<h1>Optimization Report</h1>",
            f"<p>Generated: {datetime.now().isoformat(timespec='seconds')}</p>",
            "<h2>Recommendation</h2>",
            f"<p><strong>{recommendation['symbol']} | {recommendation['strategy']}</strong> "
            f"was selected with final score {recommendation['final_score']:.4f} using "
            f"{recommendation['selected_params_source']} parameters.</p>",
            f"<p>Selected parameters: <code>{json.dumps(recommendation['selected_params'], sort_keys=True)}</code></p>",
            f"<p>Why it won: {recommendation['rationale']}.</p>",
            "<h2>Warnings</h2>",
            (f"<ul>{warning_items}</ul>" if warning_items else "<p>No material warnings were raised.</p>"),
            chart_html,
            "<h2>Ranking Table</h2>",
            ranking_table,
            "<h2>Artifact Links</h2>",
            details_table,
            "</body>",
            "</html>",
        ]
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(html, encoding="utf-8")
    csv_path = ranking_csv_path or report_path.with_suffix(".csv")
    write_dataframe(ranking.drop(columns=["final_params"]), csv_path)
    summary_path = save_json(report_path.with_name("optimization_summary.json"), to_jsonable(recommendation))
    warnings_path = save_json(report_path.with_name("optimization_warnings.json"), sorted(set(warnings)))

    return StrategySelectionResult(
        ranking=ranking,
        recommendation=recommendation,
        warnings=sorted(set(warnings)),
        artifacts={
            "report_html": report_path,
            "ranking_csv": csv_path,
            "summary_json": summary_path,
            "warnings_json": warnings_path,
        },
    )
