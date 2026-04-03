"""Run the Project 2 backtesting suite across one or more symbols."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from backtester import BacktestEngine, compare, generate_html_report, generate_report, rank_strategies
from config import settings
from data.storage import DataStore
from strategies import (
    BBRSICombinedStrategy,
    BollingerBandStrategy,
    CointegrationPairsStrategy,
    CrossSectionalMomentumStrategy,
    DonchianBreakoutStrategy,
    EngulfingStrategy,
    MACrossoverStrategy,
    MACDTrendStrategy,
    MomentumStrategy,
    MultiFactorStrategy,
    OUMeanReversionStrategy,
    OvernightGapReversionStrategy,
    PairsMeanReversionStrategy,
    RSIMeanReversionStrategy,
    TimeSeriesMomentumStrategy,
    TrendDeltaStrategy,
    VRPRegimeStrategy,
    VWAPReversionStrategy,
)

logger = logging.getLogger(__name__)

DEFAULT_PAIR_MAP: dict[str, str] = {
    "SPY": "IVV",
    "IVV": "SPY",
    "VOO": "SPY",
    "QQQ": "QQQM",
    "QQQM": "QQQ",
    "IWM": "VTWO",
    "VTWO": "IWM",
    "GLD": "IAU",
    "TLT": "IEF",
}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the backtest runner."""
    parser = argparse.ArgumentParser(description="Run multi-strategy backtests.")
    parser.add_argument("--symbols", nargs="+", default=["SPY"], help="Symbols to backtest.")
    parser.add_argument("--start", default="2020-01-01", help="Backtest start date.")
    parser.add_argument("--end", default="2025-12-31", help="Backtest end date.")
    parser.add_argument("--timeframe", default="1d", help="Data timeframe, such as 1d.")
    parser.add_argument("--initial-capital", type=float, default=100_000.0, help="Starting capital.")
    parser.add_argument("--commission", type=float, default=0.001, help="Commission rate.")
    parser.add_argument("--slippage", type=float, default=0.0005, help="Slippage rate.")
    parser.add_argument("--risk-per-trade", type=float, default=0.02, help="Capital fraction per trade.")
    parser.add_argument("--long-short", action="store_true", help="Enable short selling.")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cached market data.")
    parser.add_argument(
        "--research", action="store_true",
        help="Include the 8 research-grade strategies (TS momentum, OU, cointegration pairs, etc.).",
    )
    parser.add_argument(
        "--pair-map",
        nargs="*",
        default=[],
        help="Optional pair overrides in PRIMARY=SECONDARY format.",
    )
    return parser.parse_args()


def configure_logging() -> None:
    """Configure process-wide logging for the runner."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format=settings.LOG_FORMAT,
    )


def parse_pair_map(raw_items: list[str]) -> dict[str, str]:
    """Parse `PRIMARY=SECONDARY` pair mappings from CLI arguments."""
    mappings: dict[str, str] = {}
    for item in raw_items:
        if "=" not in item:
            raise ValueError(f"Invalid pair mapping: {item!r}")
        primary, secondary = item.split("=", maxsplit=1)
        mappings[primary.strip().upper()] = secondary.strip().upper()
    return mappings


def build_strategy_suite(pair_symbol: str | None, *, research: bool = False) -> list:
    """Build the strategy suite for a symbol.

    Args:
        pair_symbol: Secondary symbol for pairs strategies, or None.
        research:    When True, include the 8 new research-grade strategies in
                     addition to the original Project 2 suite.
                     Pass ``--research`` on the CLI to enable.
    """
    strategies = [
        MACrossoverStrategy(),
        RSIMeanReversionStrategy(),
        BollingerBandStrategy(),
        DonchianBreakoutStrategy(),
        MACDTrendStrategy(),
        TrendDeltaStrategy(),
        MomentumStrategy(),
        VWAPReversionStrategy(),
        EngulfingStrategy(),
    ]
    if pair_symbol:
        strategies.append(PairsMeanReversionStrategy(pair_symbol=pair_symbol))

    if research:
        strategies += [
            TimeSeriesMomentumStrategy(),
            OvernightGapReversionStrategy(),
            OUMeanReversionStrategy(),
            BBRSICombinedStrategy(),
            VRPRegimeStrategy(),
            CrossSectionalMomentumStrategy(),
            MultiFactorStrategy(),
        ]
        if pair_symbol:
            strategies.append(CointegrationPairsStrategy(pair_symbol=pair_symbol))

    return strategies


def prepare_pair_frame(primary: pd.DataFrame, secondary: pd.DataFrame) -> pd.DataFrame:
    """Merge a primary and secondary dataframe for the pairs strategy."""
    merged = primary.join(
        secondary[["Close"]].rename(columns={"Close": "PairClose"}),
        how="inner",
    )
    return merged.dropna(subset=["Close", "PairClose"])


def save_result_artifacts(results, comparison_frame: pd.DataFrame, prefix: str) -> dict[str, Path]:
    """Save CSV and report artifacts under `reports/`."""
    settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    comparison_path = settings.REPORTS_DIR / f"{prefix}_comparison.csv"
    comparison_frame.to_csv(comparison_path, index=False)

    metrics_payload = [
        {
            "symbol": result.symbol,
            "strategy": result.strategy_name,
            "params": result.params,
            "metrics": result.metrics,
        }
        for result in results
    ]
    metrics_path = settings.REPORTS_DIR / f"{prefix}_metrics.json"
    metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

    equity_frame = pd.concat(
        [
            result.equity_curve.rename(f"{result.symbol}|{result.strategy_name}")
            for result in results
        ],
        axis=1,
    )
    equity_path = settings.REPORTS_DIR / f"{prefix}_equity_curves.csv"
    equity_frame.to_csv(equity_path)

    for result in results:
        safe_name = f"{result.symbol}_{result.strategy_name}".replace("/", "_").replace(" ", "_")
        trades_path = settings.REPORTS_DIR / f"{prefix}_{safe_name}_trades.csv"
        result.trades.to_csv(trades_path, index=False)

    text_report = generate_report(results, report_name=f"{prefix}_report.txt")
    html_report = generate_html_report(results, report_name=f"{prefix}_report.html")

    return {
        "comparison": comparison_path,
        "metrics": metrics_path,
        "equity": equity_path,
        "text_report": text_report,
        "html_report": html_report,
    }


def run_suite(args: argparse.Namespace) -> tuple[list, dict[str, Path], pd.DataFrame]:
    """Run the configured strategy suite and persist summary artifacts."""
    store = DataStore()
    pair_overrides = parse_pair_map(args.pair_map)
    engine = BacktestEngine(
        initial_capital=args.initial_capital,
        commission=args.commission,
        slippage=args.slippage,
        risk_per_trade=args.risk_per_trade,
        long_only=not args.long_short,
    )

    results = []
    for symbol in args.symbols:
        normalized_symbol = symbol.upper()
        logger.info("Fetching data for %s", normalized_symbol)
        primary = store.get(
            normalized_symbol,
            timeframe=args.timeframe,
            start_date=args.start,
            end_date=args.end,
            force_refresh=args.force_refresh,
        )
        if primary is None or primary.empty:
            logger.warning("Skipping %s because no market data was returned.", normalized_symbol)
            continue

        pair_symbol = pair_overrides.get(normalized_symbol, DEFAULT_PAIR_MAP.get(normalized_symbol))
        pair_frame: pd.DataFrame | None = None
        if pair_symbol:
            logger.info("Fetching pair data for %s vs %s", normalized_symbol, pair_symbol)
            secondary = store.get(
                pair_symbol,
                timeframe=args.timeframe,
                start_date=args.start,
                end_date=args.end,
                force_refresh=args.force_refresh,
            )
            if secondary is not None and not secondary.empty:
                pair_frame = prepare_pair_frame(primary, secondary)
            else:
                logger.warning("Pair data unavailable for %s; skipping pairs strategy.", pair_symbol)

        _pairs = (PairsMeanReversionStrategy, CointegrationPairsStrategy)
        for strategy in build_strategy_suite(
            pair_symbol if pair_frame is not None else None,
            research=args.research,
        ):
            dataset = pair_frame if isinstance(strategy, _pairs) else primary
            if dataset is None or dataset.empty:
                logger.warning("Skipping %s on %s due to missing input data.", strategy.name, normalized_symbol)
                continue
            try:
                results.append(engine.run(strategy, dataset, symbol=normalized_symbol))
            except Exception:
                logger.exception("Backtest failed for %s on %s.", strategy.name, normalized_symbol)

    comparison_frame = compare(results)
    prefix = f"backtest_{'_'.join(symbol.upper() for symbol in args.symbols)}_{args.start}_{args.end}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    artifacts = save_result_artifacts(results, comparison_frame, prefix) if results else {}
    return results, artifacts, comparison_frame


def print_summary(results, comparison_frame: pd.DataFrame) -> None:
    """Print a concise terminal summary of the ranked results."""
    if not results or comparison_frame.empty:
        print("No backtest results were produced.")
        return

    ranked = rank_strategies(results)
    summary = ranked[
        [
            "symbol",
            "strategy",
            "total_return",
            "annual_return",
            "sharpe_ratio",
            "max_drawdown_percent",
            "total_trades",
            "score",
        ]
    ].copy()
    print(summary.to_string(index=False, float_format=lambda value: f"{value:,.4f}"))


def main() -> None:
    """Run the backtest suite from the command line."""
    configure_logging()
    args = parse_args()
    results, artifacts, comparison_frame = run_suite(args)
    print_summary(results, comparison_frame)
    if artifacts:
        print("\nSaved artifacts:")
        for label, path in artifacts.items():
            print(f"{label}: {path}")


if __name__ == "__main__":
    main()
