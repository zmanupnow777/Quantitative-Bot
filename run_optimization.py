"""Run the full Project 3 optimization and robustness pipeline."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from config import settings
from optimizer.common import (
    EngineConfig,
    load_candidate_data,
    load_top_project2_candidates,
    save_json,
    strategy_artifact_dir,
    write_dataframe,
)
from optimizer.monte_carlo import run_monte_carlo_analysis
from optimizer.param_sensitivity import run_parameter_sensitivity
from optimizer.selector import StrategyAnalysisBundle, select_strategies
from optimizer.stress_test import run_stress_test_analysis
from optimizer.walk_forward import run_walk_forward_analysis
from run_backtest import configure_logging

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the Project 3 pipeline."""
    parser = argparse.ArgumentParser(description="Run Project 3 optimization and robustness analysis.")
    parser.add_argument("--top-n", type=int, default=5, help="Number of Project 2 strategies to analyze.")
    parser.add_argument("--timeframe", default="1d", help="Timeframe used for Project 3 reruns.")
    parser.add_argument("--start", default=None, help="Override the Project 2 start date.")
    parser.add_argument("--end", default=None, help="Override the Project 2 end date.")
    parser.add_argument("--initial-capital", type=float, default=100_000.0, help="Starting capital.")
    parser.add_argument("--commission", type=float, default=0.001, help="Commission rate.")
    parser.add_argument("--slippage", type=float, default=0.0005, help="Slippage rate.")
    parser.add_argument("--risk-per-trade", type=float, default=0.02, help="Capital fraction per trade.")
    parser.add_argument("--long-short", action="store_true", help="Enable short selling.")
    parser.add_argument("--workers", type=int, default=None, help="Maximum worker processes per analysis.")
    parser.add_argument("--walk-forward-windows", type=int, default=5, help="Number of walk-forward windows.")
    parser.add_argument("--monte-carlo-sims", type=int, default=1000, help="Monte Carlo simulation count.")
    parser.add_argument("--no-train-optimize", action="store_true", help="Disable train-only parameter optimization.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore cached artifacts and recompute everything.")
    parser.add_argument(
        "--report-path",
        default=str(settings.REPORTS_DIR / "optimization_report.html"),
        help="Final HTML report path.",
    )
    return parser.parse_args()


def _save_baseline_artifacts(
    artifact_dir: Path,
    *,
    candidate_payload: dict[str, object],
    engine_config: EngineConfig,
    baseline_result,
) -> dict[str, Path]:
    """Persist the baseline backtest artifacts used by Project 3."""
    summary_path = save_json(
        artifact_dir / "baseline_summary.json",
        {
            "candidate": candidate_payload,
            "engine_config": engine_config.to_dict(),
            "metrics": baseline_result.metrics,
            "params": baseline_result.params,
            "symbol": baseline_result.symbol,
            "strategy": baseline_result.strategy_name,
        },
    )
    trades_path = write_dataframe(baseline_result.trades, artifact_dir / "baseline_trades.csv")
    equity_path = write_dataframe(
        baseline_result.equity_curve.rename("equity").to_frame().reset_index(names="Date"),
        artifact_dir / "baseline_equity_curve.csv",
    )
    signals_path = write_dataframe(
        baseline_result.signals.rename("signal").to_frame().reset_index(names="Date"),
        artifact_dir / "baseline_signals.csv",
    )
    return {
        "summary": summary_path,
        "trades_csv": trades_path,
        "equity_csv": equity_path,
        "signals_csv": signals_path,
    }


def print_summary(ranking: pd.DataFrame, recommendation: dict[str, object]) -> None:
    """Print the concise final ranking required by the Project 3 handoff."""
    summary_columns = [
        "rank",
        "symbol",
        "strategy",
        "final_score",
        "parameter_sensitivity_smoothness",
        "walk_forward_oos_sharpe",
        "monte_carlo_probability_of_profit",
        "stress_test_consistency",
        "raw_backtest_sharpe",
        "overfitting_flag",
    ]
    print("Final Strategy Ranking")
    print(
        ranking[summary_columns].to_string(
            index=False,
            float_format=lambda value: f"{value:,.4f}",
        )
    )
    print("\nTop Recommendation")
    print(f"{recommendation['symbol']} | {recommendation['strategy']}")
    print(f"Selected params: {json.dumps(recommendation['selected_params'], sort_keys=True)}")
    print(f"Why: {recommendation['rationale']}")


def main() -> None:
    """Run Project 3 from the command line."""
    configure_logging()
    args = parse_args()
    engine_config = EngineConfig(
        initial_capital=args.initial_capital,
        commission=args.commission,
        slippage=args.slippage,
        risk_per_trade=args.risk_per_trade,
        long_only=not args.long_short,
    )
    report_path = Path(args.report_path)
    resume = not args.no_resume

    candidates, ranked_project2, metadata, metrics_path = load_top_project2_candidates(
        top_n=args.top_n,
        timeframe=args.timeframe,
        start_date=args.start,
        end_date=args.end,
    )
    logger.info(
        "Loaded %d Project 2 candidates from %s covering %s to %s.",
        len(candidates),
        metrics_path,
        candidates[0].start_date if candidates else metadata.get("start"),
        candidates[0].end_date if candidates else metadata.get("end"),
    )

    selection_bundles: list[StrategyAnalysisBundle] = []
    for candidate in candidates:
        logger.info("Running Project 3 analyses for %s.", candidate.safe_name)
        artifact_dir = strategy_artifact_dir(candidate)
        dataset = load_candidate_data(candidate)
        baseline_result = engine_config.build_engine().run(candidate.build_strategy(), dataset, symbol=candidate.symbol)
        baseline_artifacts = _save_baseline_artifacts(
            artifact_dir,
            candidate_payload=candidate.to_dict(),
            engine_config=engine_config,
            baseline_result=baseline_result,
        )

        sensitivity = run_parameter_sensitivity(
            candidate,
            engine_config,
            data=dataset,
            artifact_dir=artifact_dir,
            resume=resume,
            max_workers=args.workers,
        )
        walk_forward = run_walk_forward_analysis(
            candidate,
            engine_config,
            data=dataset,
            artifact_dir=artifact_dir,
            resume=resume,
            n_windows=args.walk_forward_windows,
            optimize_on_train=not args.no_train_optimize,
            max_workers=args.workers,
        )
        monte_carlo = run_monte_carlo_analysis(
            baseline_result,
            n_simulations=args.monte_carlo_sims,
            artifact_dir=artifact_dir,
            resume=resume,
            max_workers=args.workers,
        )
        stress_test = run_stress_test_analysis(
            candidate,
            engine_config,
            data=dataset,
            artifact_dir=artifact_dir,
            resume=resume,
        )

        selection_bundles.append(
            StrategyAnalysisBundle(
                baseline_result=baseline_result,
                sensitivity=sensitivity,
                walk_forward=walk_forward,
                monte_carlo=monte_carlo,
                stress_test=stress_test,
                artifacts=baseline_artifacts,
            )
        )

    ranking_csv_path = report_path.with_suffix(".csv")
    selection = select_strategies(
        selection_bundles,
        report_path=report_path,
        ranking_csv_path=ranking_csv_path,
    )
    save_json(
        report_path.with_name("project2_top_candidates.json"),
        {
            "source_metrics_path": str(metrics_path),
            "project2_ranking": ranked_project2.head(args.top_n).to_dict(orient="records"),
            "selected_candidates": [candidate.to_dict() for candidate in candidates],
        },
    )

    print_summary(selection.ranking, selection.recommendation)
    print(f"\nFinal report: {report_path}")
    print(f"Ranking CSV: {ranking_csv_path}")


if __name__ == "__main__":
    main()
