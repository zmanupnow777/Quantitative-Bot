"""CLI entry point for the automated strategy research pipeline.

Usage:
    python run_research.py --candidates 200 --symbols SPY --mode random
    python run_research.py --candidates 50 --symbols SPY QQQ --mode exhaustive --seed 42
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import settings
from research.config import ResearchConfig
from research.pipeline import ResearchPipeline, save_winners
from research.report import generate_report

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated strategy research — generate, test, and rank trading strategies",
    )
    parser.add_argument(
        "--candidates", "-n", type=int, default=200,
        help="Number of candidate strategies to generate (default: 200)",
    )
    parser.add_argument(
        "--symbols", nargs="+", default=["SPY"],
        help="Symbols to test on (default: SPY)",
    )
    parser.add_argument(
        "--mode", choices=["random", "exhaustive", "mutation"], default="random",
        help="Generation mode (default: random)",
    )
    parser.add_argument(
        "--timeframe", default="1d",
        help="Data timeframe (default: 1d)",
    )
    parser.add_argument(
        "--screen-start", default="2022-01-01",
        help="Start date for quick screen window (default: 2022-01-01)",
    )
    parser.add_argument(
        "--screen-end", default="2023-12-31",
        help="End date for quick screen window (default: 2023-12-31)",
    )
    parser.add_argument(
        "--full-start", default="2018-01-01",
        help="Start date for full backtest window (default: 2018-01-01)",
    )
    parser.add_argument(
        "--full-end", default="2025-12-31",
        help="End date for full backtest window (default: 2025-12-31)",
    )
    parser.add_argument(
        "--min-sharpe", type=float, default=0.5,
        help="Minimum Sharpe ratio for full backtest filter (default: 0.5)",
    )
    parser.add_argument(
        "--min-win-rate", type=float, default=0.45,
        help="Minimum win rate for filter (default: 0.45)",
    )
    parser.add_argument(
        "--top-n", type=int, default=10,
        help="Top N strategies for robustness analysis (default: 10)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--capital", type=float, default=100_000,
        help="Initial capital for backtesting (default: 100000)",
    )
    parser.add_argument(
        "--save-winners", action="store_true", default=True,
        help="Save winning strategy configs to strategies/generated/ (default: True)",
    )
    parser.add_argument(
        "--report-dir", default=None,
        help="Directory for HTML report (default: reports/)",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/research.log"),
        ],
        force=True,
    )

    Path("logs").mkdir(exist_ok=True)

    config = ResearchConfig(
        n_candidates=args.candidates,
        generation_mode=args.mode,
        symbols=args.symbols,
        timeframe=args.timeframe,
        screen_start=args.screen_start,
        screen_end=args.screen_end,
        full_start=args.full_start,
        full_end=args.full_end,
        initial_capital=args.capital,
        min_sharpe=args.min_sharpe,
        min_win_rate=args.min_win_rate,
        top_n_for_robustness=args.top_n,
        seed=args.seed,
    )

    logger.info("=" * 60)
    logger.info("AUTOMATED STRATEGY RESEARCH")
    logger.info("Candidates: %d | Mode: %s | Symbols: %s", config.n_candidates, config.generation_mode, config.symbols)
    logger.info("Screen: %s to %s | Full: %s to %s", config.screen_start, config.screen_end, config.full_start, config.full_end)
    logger.info("=" * 60)

    pipeline = ResearchPipeline(config)
    result = pipeline.run()

    # Report
    report_dir = Path(args.report_dir) if args.report_dir else Path(settings.REPORTS_DIR)
    report_path = report_dir / "research_report.html"
    generate_report(result, report_path)

    # Save winners
    if args.save_winners and result.winners:
        saved = save_winners(result)
        logger.info("Saved %d winning strategies to strategies/generated/", len(saved))

    # Print summary
    print("\n" + "=" * 60)
    print("RESEARCH COMPLETE")
    print("=" * 60)
    print(f"Generated:    {result.total_generated}")
    print(f"Screened:     {result.total_screened}")
    print(f"Backtested:   {result.total_backtested}")
    print(f"Filtered:     {result.total_filtered}")
    print(f"Robust:       {result.total_robust}")
    print(f"Time:         {result.elapsed_seconds:.1f}s")
    print(f"Report:       {report_path}")

    if result.winners:
        print(f"\nTop {min(5, len(result.winners))} strategies:")
        for i, w in enumerate(result.winners[:5], 1):
            m = w.metrics
            print(
                f"  {i}. {w.strategy.name:30s} | Sharpe: {m.get('sharpe_ratio', 0):.3f} | "
                f"Win: {m.get('win_rate', 0):.1%} | PF: {m.get('profit_factor', 0):.2f} | "
                f"Robustness: {w.robustness_score:.1f}"
            )
    else:
        print("\nNo winning strategies found. Try adjusting thresholds or generating more candidates.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
