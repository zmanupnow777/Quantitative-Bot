"""Check live/paper trading performance vs backtest expectations.

Usage:
    python check_performance.py                               # Default strategy
    python check_performance.py --strategy rsi                # Specific strategy
    python check_performance.py --strategy ma_crossover --capital 50000
"""

import argparse

from bot.performance import PerformanceTracker


def main() -> None:
    parser = argparse.ArgumentParser(description="Performance Comparison: Live vs Backtest")
    parser.add_argument("--strategy", default="ma_crossover", help="Strategy name to compare")
    parser.add_argument("--capital", type=float, default=100_000, help="Initial capital")
    parser.add_argument("--reports-dir", default="reports", help="Directory with backtest reports")
    parser.add_argument("--logs-dir", default="logs", help="Directory with trade logs")

    args = parser.parse_args()

    tracker = PerformanceTracker(reports_dir=args.reports_dir, logs_dir=args.logs_dir)
    tracker.print_report(args.strategy, initial_capital=args.capital)


if __name__ == "__main__":
    main()
