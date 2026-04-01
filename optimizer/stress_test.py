"""Market-regime stress testing for Project 3."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from optimizer.common import (
    EngineConfig,
    StrategyCandidate,
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


@dataclass(frozen=True, slots=True)
class RegimeWindow:
    """A named market regime with an explicit date window."""

    name: str
    start_date: str
    end_date: str
    description: str


DEFAULT_REGIMES: tuple[RegimeWindow, ...] = (
    RegimeWindow(
        name="bull_market",
        start_date="2020-04-01",
        end_date="2021-12-31",
        description="Post-crash expansion and persistent upside trend.",
    ),
    RegimeWindow(
        name="bear_market",
        start_date="2022-01-01",
        end_date="2022-10-31",
        description="Broad equity drawdown and tightening cycle.",
    ),
    RegimeWindow(
        name="high_volatility",
        start_date="2020-02-15",
        end_date="2020-06-30",
        description="Crash and immediate rebound with elevated realized volatility.",
    ),
    RegimeWindow(
        name="low_volatility_sideways",
        start_date="2024-04-01",
        end_date="2024-09-30",
        description="Lower-volatility consolidation and range-bound behavior.",
    ),
    RegimeWindow(
        name="recovery",
        start_date="2022-11-01",
        end_date="2023-07-31",
        description="Recovery phase after the 2022 drawdown.",
    ),
)


@dataclass(slots=True)
class StressTestResult:
    """Persisted regime stress-test outputs for one strategy."""

    candidate: StrategyCandidate
    summary: dict[str, Any]
    regimes: pd.DataFrame
    artifacts: dict[str, Path] = field(default_factory=dict)


def _build_stress_figure(frame: pd.DataFrame, candidate: StrategyCandidate) -> go.Figure:
    """Create grouped regime performance charts."""
    labels = frame["regime"].tolist()
    figure = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Sharpe by Regime",
            "Return by Regime",
            "Max Drawdown by Regime",
            "Market Return vs Strategy Return",
        ),
    )
    figure.add_trace(go.Bar(x=labels, y=frame["sharpe_ratio"], name="Sharpe"), row=1, col=1)
    figure.add_trace(go.Bar(x=labels, y=frame["total_return"], name="Return"), row=1, col=2)
    figure.add_trace(go.Bar(x=labels, y=frame["max_drawdown_percent"], name="Max Drawdown"), row=2, col=1)
    figure.add_trace(
        go.Scatter(
            x=frame["asset_return"],
            y=frame["total_return"],
            mode="markers+text",
            text=labels,
            textposition="top center",
            name="Strategy vs Market",
        ),
        row=2,
        col=2,
    )
    figure.update_layout(
        title=f"Stress Test: {candidate.symbol} | {candidate.strategy_name}",
        height=900,
        width=1400,
        hovermode="closest",
        showlegend=False,
    )
    figure.update_xaxes(title_text="Market Return", row=2, col=2)
    figure.update_yaxes(title_text="Strategy Return", row=2, col=2)
    return figure


def _load_cached_result(candidate: StrategyCandidate, artifact_dir: Path) -> StressTestResult | None:
    """Return cached regime stress-test artifacts when available."""
    summary_path = artifact_dir / "stress_test_summary.json"
    regimes_path = artifact_dir / "stress_test_regimes.csv"
    if not (summary_path.exists() and regimes_path.exists()):
        return None

    logger.info("Loading cached stress-test artifacts for %s.", candidate.safe_name)
    return StressTestResult(
        candidate=candidate,
        summary=load_json(summary_path),
        regimes=pd.read_csv(regimes_path),
        artifacts={
            "summary": summary_path,
            "regimes_csv": regimes_path,
            "html": artifact_dir / "stress_test.html",
        },
    )


def run_stress_test_analysis(
    candidate: StrategyCandidate,
    engine_config: EngineConfig,
    *,
    data: pd.DataFrame | None = None,
    artifact_dir: Path | None = None,
    resume: bool = True,
    regimes: tuple[RegimeWindow, ...] = DEFAULT_REGIMES,
) -> StressTestResult:
    """Evaluate a strategy across explicit market regime windows."""
    target_dir = artifact_dir or strategy_artifact_dir(candidate)
    if resume:
        cached = _load_cached_result(candidate, target_dir)
        if cached is not None:
            return cached

    dataset = data if data is not None else load_candidate_data(candidate)
    rows: list[dict[str, Any]] = []
    notes: list[str] = []

    for regime in regimes:
        regime_slice = dataset.loc[regime.start_date:regime.end_date].copy()
        if len(regime_slice) < 10:
            notes.append(
                f"Skipped {regime.name} because only {len(regime_slice)} bars overlapped the requested data range."
            )
            continue

        result = run_candidate_backtest(candidate, engine_config, data=regime_slice)
        close = pd.to_numeric(regime_slice["Close"], errors="coerce").dropna()
        asset_return = float((close.iloc[-1] / close.iloc[0]) - 1.0) if len(close) >= 2 else 0.0
        asset_volatility = float(close.pct_change().dropna().std(ddof=0) * np.sqrt(252)) if len(close) >= 3 else 0.0
        rows.append(
            {
                "regime": regime.name,
                "description": regime.description,
                "start_date": regime.start_date,
                "end_date": regime.end_date,
                "bars": len(regime_slice),
                "asset_return": asset_return,
                "asset_volatility": asset_volatility,
                "sharpe_ratio": float(result.metrics.get("sharpe_ratio", 0.0)),
                "total_return": float(result.metrics.get("total_return", 0.0)),
                "max_drawdown_percent": float(result.metrics.get("max_drawdown_percent", 0.0)),
                "win_rate": float(result.metrics.get("win_rate", 0.0)),
                "total_trades": float(result.metrics.get("total_trades", len(result.trades))),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError(f"No stress-test regimes overlapped the available data for {candidate.safe_name}.")

    positive_regimes = frame[(frame["sharpe_ratio"] > 0.0) & (frame["total_return"] > 0.0)]
    positive_regime_count = int(len(positive_regimes))
    regime_return_magnitude = frame["total_return"].abs().sum()
    dominant_regime_share = float(
        frame["total_return"].abs().max() / regime_return_magnitude
    ) if regime_return_magnitude else 1.0
    sharpe_std = float(frame["sharpe_ratio"].std(ddof=0)) if len(frame) > 1 else 0.0
    sharpe_mean = float(frame["sharpe_ratio"].mean()) if not frame.empty else 0.0
    stability_component = 1.0 / (1.0 + (sharpe_std / (abs(sharpe_mean) + 0.25)))
    breadth_component = positive_regime_count / len(frame)
    consistency_score = float(np.clip((0.55 * breadth_component) + (0.45 * stability_component), 0.0, 1.0))
    one_regime_flag = bool(positive_regime_count <= 1 or dominant_regime_share >= 0.70)
    if one_regime_flag:
        notes.append("Strategy appears regime-dependent and only performs well in one environment.")

    summary = {
        "candidate": candidate.to_dict(),
        "consistency_score": consistency_score,
        "positive_regime_count": positive_regime_count,
        "dominant_regime_share": dominant_regime_share,
        "one_regime_flag": one_regime_flag,
        "best_regime": str(frame.sort_values("sharpe_ratio", ascending=False)["regime"].iloc[0]),
        "worst_regime": str(frame.sort_values("sharpe_ratio", ascending=True)["regime"].iloc[0]),
        "notes": notes,
    }

    figure = _build_stress_figure(frame, candidate)
    summary_path = save_json(target_dir / "stress_test_summary.json", to_jsonable(summary))
    regimes_csv_path = write_dataframe(frame, target_dir / "stress_test_regimes.csv")
    html_path = write_plotly_html(figure, target_dir / "stress_test.html")

    return StressTestResult(
        candidate=candidate,
        summary=summary,
        regimes=frame,
        artifacts={
            "summary": summary_path,
            "regimes_csv": regimes_csv_path,
            "html": html_path,
        },
    )
