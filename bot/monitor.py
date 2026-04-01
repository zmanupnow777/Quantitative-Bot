"""Terminal-based dashboard for monitoring the trading bot."""

from __future__ import annotations

import os
from datetime import datetime

from bot.brokers.base import BotConfig, Position


class TerminalMonitor:
    """
    Prints a live dashboard to the terminal showing:
    - Account status
    - Open positions with PnL
    - Recent trades
    - Risk manager status
    - Strategy signals
    """

    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def display(
        self,
        account_info: dict,
        positions: list[Position],
        recent_trades: list[dict],
        risk_status: dict,
        last_signal: dict | None = None,
    ) -> None:
        """Print the dashboard to terminal."""
        self._clear()
        lines = []

        # Header
        lines.append("=" * 60)
        lines.append(f"  TRADING BOT MONITOR  |  {datetime.now():%Y-%m-%d %H:%M:%S}")
        lines.append(f"  Mode: {self.config.mode.upper()}  |  Symbol: {self.config.symbol}  |  TF: {self.config.timeframe}")
        lines.append("=" * 60)

        # Account
        lines.append("")
        lines.append("  ACCOUNT")
        lines.append(f"  Portfolio Value:  ${account_info.get('portfolio_value', 0):>12,.2f}")
        lines.append(f"  Cash:             ${account_info.get('cash', 0):>12,.2f}")
        lines.append(f"  Daily PnL:        ${account_info.get('daily_pnl', 0):>12,.2f}")
        lines.append(f"  Positions:        {account_info.get('positions_count', 0):>12d}")

        # Positions
        lines.append("")
        lines.append("  OPEN POSITIONS")
        if positions:
            lines.append(f"  {'Symbol':<8} {'Side':<6} {'Qty':>8} {'Entry':>10} {'Current':>10} {'PnL':>12}")
            lines.append("  " + "-" * 56)
            for pos in positions:
                pnl_str = f"${pos.unrealized_pnl:>10,.2f}"
                lines.append(
                    f"  {pos.symbol:<8} {pos.side:<6} {pos.qty:>8.2f} "
                    f"${pos.entry_price:>9.2f} ${pos.current_price:>9.2f} {pnl_str}"
                )
                if pos.trailing_stop:
                    lines.append(f"           Trail: ${pos.trailing_stop:.2f}  SL: ${pos.stop_loss:.2f}  TP: ${pos.take_profit:.2f}")
        else:
            lines.append("  (no open positions)")

        # Recent trades
        lines.append("")
        lines.append("  RECENT TRADES (last 5)")
        if recent_trades:
            for trade in recent_trades[-5:]:
                pnl = trade.get("pnl", 0)
                symbol = trade.get("symbol", "?")
                side = trade.get("side", "?")
                marker = "+" if pnl > 0 else ""
                lines.append(f"  {symbol:<8} {side:<6} PnL: {marker}${pnl:,.2f}")
        else:
            lines.append("  (no trades yet)")

        # Risk status
        lines.append("")
        lines.append("  RISK MANAGER")
        lines.append(f"  Kill Switch:     {'ACTIVE' if risk_status.get('killed') else 'OK'}")
        lines.append(f"  Daily Trades:    {risk_status.get('daily_trades', 0)} / {risk_status.get('max_daily_trades', 20)}")
        lines.append(f"  Positions:       {len(positions)} / {self.config.max_positions}")
        if risk_status.get("kill_reason"):
            lines.append(f"  Kill Reason:     {risk_status['kill_reason']}")

        # Last signal
        if last_signal:
            lines.append("")
            lines.append("  LAST SIGNAL")
            lines.append(f"  Strategy:  {last_signal.get('strategy', '?')}")
            lines.append(f"  Direction: {last_signal.get('direction', 'none')}")
            lines.append(f"  Time:      {last_signal.get('time', '?')}")

        lines.append("")
        lines.append("=" * 60)

        print("\n".join(lines))

    @staticmethod
    def _clear() -> None:
        """Clear the terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")
