"""Comprehensive trade logging — JSON (machine-readable) + daily text logs."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TradeLogger:
    """
    Logs every order, fill, position change, and daily summary.

    Writes two formats:
    - JSON lines file: one event per line, machine-parseable
    - Daily text log: human-readable summary per day
    """

    def __init__(self, log_dir: str | Path = "logs") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._json_path = self.log_dir / "trades.jsonl"
        self._daily_dir = self.log_dir / "daily"
        self._daily_dir.mkdir(parents=True, exist_ok=True)

        self._today_trades: list[dict] = []
        self._today_date = datetime.now().date()

    def log_order(self, order_data: dict) -> None:
        """Log an order submission."""
        entry = {
            "event": "order_submitted",
            "timestamp": datetime.now().isoformat(),
            **order_data,
        }
        self._write_json(entry)
        logger.info("Order logged: %s %s %s @ $%s", order_data.get("side"), order_data.get("qty"), order_data.get("symbol"), order_data.get("price"))

    def log_fill(self, fill_data: dict) -> None:
        """Log an order fill."""
        entry = {
            "event": "order_filled",
            "timestamp": datetime.now().isoformat(),
            **fill_data,
        }
        self._write_json(entry)

    def log_position_opened(self, position_data: dict) -> None:
        """Log a new position."""
        entry = {
            "event": "position_opened",
            "timestamp": datetime.now().isoformat(),
            **position_data,
        }
        self._write_json(entry)
        self._today_trades.append(entry)

    def log_position_closed(self, position_data: dict) -> None:
        """Log a closed position with PnL."""
        entry = {
            "event": "position_closed",
            "timestamp": datetime.now().isoformat(),
            **position_data,
        }
        self._write_json(entry)
        self._today_trades.append(entry)

    def log_signal(self, signal_data: dict) -> None:
        """Log a strategy signal (even if not acted on)."""
        entry = {
            "event": "signal",
            "timestamp": datetime.now().isoformat(),
            **signal_data,
        }
        self._write_json(entry)

    def log_risk_event(self, event_data: dict) -> None:
        """Log a risk management event (kill switch, stop loss, etc.)."""
        entry = {
            "event": "risk_event",
            "timestamp": datetime.now().isoformat(),
            **event_data,
        }
        self._write_json(entry)
        logger.warning("Risk event: %s", event_data.get("reason", "unknown"))

    def write_daily_summary(self, account_info: dict) -> None:
        """Write end-of-day summary to daily log file."""
        self._check_day_rollover()
        today = datetime.now().date()
        daily_file = self._daily_dir / f"{today}.txt"

        opens = [t for t in self._today_trades if t["event"] == "position_opened"]
        closes = [t for t in self._today_trades if t["event"] == "position_closed"]
        total_pnl = sum(t.get("pnl", 0) for t in closes)
        wins = sum(1 for t in closes if t.get("pnl", 0) > 0)
        losses = sum(1 for t in closes if t.get("pnl", 0) <= 0)

        lines = [
            f"=== Daily Summary: {today} ===",
            f"Account Value:  ${account_info.get('portfolio_value', 0):,.2f}",
            f"Cash:           ${account_info.get('cash', 0):,.2f}",
            f"Daily PnL:      ${account_info.get('daily_pnl', 0):,.2f}",
            f"Trades Opened:  {len(opens)}",
            f"Trades Closed:  {len(closes)}",
            f"Wins / Losses:  {wins} / {losses}",
            f"Total PnL:      ${total_pnl:,.2f}",
            "",
        ]

        if closes:
            lines.append("Closed Trades:")
            for t in closes:
                lines.append(
                    f"  {t.get('symbol', '?')} | {t.get('side', '?')} | "
                    f"PnL: ${t.get('pnl', 0):,.2f} ({t.get('pnl_pct', 0):.2%})"
                )

        with open(daily_file, "w") as f:
            f.write("\n".join(lines))

        logger.info("Daily summary written to %s", daily_file)

    def get_all_trades(self) -> list[dict]:
        """Load all trade events from the JSON log."""
        if not self._json_path.exists():
            return []
        trades = []
        with open(self._json_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    trades.append(json.loads(line))
        return trades

    def _write_json(self, entry: dict) -> None:
        self._check_day_rollover()
        with open(self._json_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _check_day_rollover(self) -> None:
        today = datetime.now().date()
        if today != self._today_date:
            self._today_trades = []
            self._today_date = today
