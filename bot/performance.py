"""Compare live trading results against backtest expectations."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """
    Loads backtest results from reports/ and compares them to live/paper
    trading results from the trade logger.

    Tracks: return, Sharpe approximation, drawdown, win rate, and
    flags significant divergence from backtest expectations.
    """

    def __init__(self, reports_dir: str | Path = "reports", logs_dir: str | Path = "logs") -> None:
        self.reports_dir = Path(reports_dir)
        self.logs_dir = Path(logs_dir)

    def load_backtest_metrics(self, strategy_name: str) -> dict | None:
        """Load backtest metrics for a strategy from the reports directory."""
        # Look for JSON metrics files from run_backtest.py output
        for path in sorted(self.reports_dir.glob("*_metrics.json"), reverse=True):
            try:
                with open(path) as f:
                    all_metrics = json.load(f)
                for entry in all_metrics:
                    if entry.get("strategy_name") == strategy_name:
                        return entry.get("metrics", entry)
            except (json.JSONDecodeError, KeyError):
                continue
        return None

    def load_live_trades(self) -> list[dict]:
        """Load completed trades from the trade logger's JSONL file."""
        trades_file = self.logs_dir / "trades.jsonl"
        if not trades_file.exists():
            return []

        trades = []
        with open(trades_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("event") == "position_closed":
                    trades.append(entry)
        return trades

    def compute_live_metrics(self, trades: list[dict], initial_capital: float = 100_000) -> dict:
        """Compute performance metrics from live trade data."""
        if not trades:
            return {
                "total_return": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
                "average_pnl": 0.0,
                "total_pnl": 0.0,
                "max_drawdown_approx": 0.0,
            }

        pnls = [t.get("pnl", 0) for t in trades]
        equity = initial_capital + np.cumsum(pnls)
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak

        wins = sum(1 for p in pnls if p > 0)

        return {
            "total_return": float((equity[-1] / initial_capital) - 1),
            "win_rate": wins / len(pnls) if pnls else 0.0,
            "total_trades": len(pnls),
            "average_pnl": float(np.mean(pnls)),
            "total_pnl": float(sum(pnls)),
            "max_drawdown_approx": float(drawdown.min()) if len(drawdown) else 0.0,
        }

    def compare(self, strategy_name: str, initial_capital: float = 100_000) -> dict:
        """
        Compare live results to backtest expectations.

        Returns a dict with both sets of metrics and divergence flags.
        """
        backtest = self.load_backtest_metrics(strategy_name)
        live_trades = self.load_live_trades()
        live = self.compute_live_metrics(live_trades, initial_capital)

        result = {
            "strategy": strategy_name,
            "live": live,
            "backtest": backtest,
            "divergence_flags": [],
        }

        if backtest:
            bt_wr = backtest.get("win_rate", 0)
            if bt_wr > 0 and live["win_rate"] > 0:
                wr_diff = abs(live["win_rate"] - bt_wr)
                if wr_diff > 0.15:
                    result["divergence_flags"].append(
                        f"Win rate diverged: live {live['win_rate']:.1%} vs backtest {bt_wr:.1%}"
                    )

            bt_dd = backtest.get("max_drawdown_percent", 0)
            if bt_dd > 0 and abs(live["max_drawdown_approx"]) > bt_dd * 1.5:
                result["divergence_flags"].append(
                    f"Drawdown worse than expected: live {live['max_drawdown_approx']:.1%} vs backtest {bt_dd:.1%}"
                )

        return result

    def print_report(self, strategy_name: str, initial_capital: float = 100_000) -> str:
        """Generate a human-readable comparison report."""
        comp = self.compare(strategy_name, initial_capital)
        live = comp["live"]
        bt = comp["backtest"]

        lines = [
            "=" * 55,
            "  PERFORMANCE: LIVE vs BACKTEST",
            f"  Strategy: {strategy_name}",
            "=" * 55,
            "",
            f"  {'Metric':<25} {'Live':>12} {'Backtest':>12}",
            "  " + "-" * 51,
        ]

        def fmt(val, pct=False):
            if val is None:
                return "N/A"
            return f"{val:.2%}" if pct else f"${val:,.2f}"

        lines.append(f"  {'Total Return':<25} {fmt(live['total_return'], True):>12} {fmt(bt.get('total_return') if bt else None, True):>12}")
        lines.append(f"  {'Win Rate':<25} {fmt(live['win_rate'], True):>12} {fmt(bt.get('win_rate') if bt else None, True):>12}")
        lines.append(f"  {'Total Trades':<25} {live['total_trades']:>12} {str(int(bt.get('total_trades', 0))) if bt else 'N/A':>12}")
        lines.append(f"  {'Avg Trade PnL':<25} {fmt(live['average_pnl']):>12} {fmt(bt.get('average_trade_pnl') if bt else None):>12}")
        lines.append(f"  {'Max Drawdown':<25} {fmt(live['max_drawdown_approx'], True):>12} {fmt(bt.get('max_drawdown_percent') if bt else None, True):>12}")

        if comp["divergence_flags"]:
            lines.append("")
            lines.append("  WARNINGS:")
            for flag in comp["divergence_flags"]:
                lines.append(f"  ! {flag}")

        lines.append("")
        lines.append("=" * 55)

        report = "\n".join(lines)
        print(report)
        return report
