"""Risk management with kill switches, position sizing, and trailing stops."""

from __future__ import annotations

import logging

from bot.brokers.base import BotConfig, Position

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Protects capital with multiple safety layers.

    Features:
    - Daily loss kill switch (default 5%)
    - Position sizing based on fixed risk per trade (default 2%)
    - Automatic stop loss and take profit
    - Trailing stops that lock in profit
    - Max simultaneous positions limit
    - Max single-position size (25% of capital)
    """

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.max_daily_trades = 20
        self.killed = False
        self._kill_reason = ""

    @property
    def kill_reason(self) -> str:
        return self._kill_reason

    def check_daily_loss_limit(self, account_info: dict) -> bool:
        """Return False and activate kill switch if daily loss exceeds limit."""
        daily_pnl = account_info.get("daily_pnl", 0)
        daily_pnl_pct = daily_pnl / self.config.initial_capital
        if daily_pnl_pct < -self.config.max_daily_loss:
            self._kill_reason = (
                f"Daily loss {daily_pnl_pct:.2%} exceeds limit {-self.config.max_daily_loss:.2%}"
            )
            logger.critical("KILL SWITCH: %s", self._kill_reason)
            self.killed = True
            return False
        return True

    def check_max_positions(self, current_count: int) -> bool:
        """Return False if max positions reached."""
        if current_count >= self.config.max_positions:
            logger.info("Max positions reached (%d/%d)", current_count, self.config.max_positions)
            return False
        return True

    def check_max_daily_trades(self) -> bool:
        """Return False if max daily trades reached."""
        if self.daily_trades >= self.max_daily_trades:
            logger.info("Max daily trades reached (%d)", self.max_daily_trades)
            return False
        return True

    def calculate_position_size(self, price: float, stop_loss_price: float, capital: float) -> float:
        """
        Calculate shares based on fixed-risk position sizing.

        risk_amount = risk_per_trade * capital
        shares = risk_amount / (entry_price - stop_loss_price)
        Capped at 25% of capital in a single position.
        """
        risk_amount = self.config.risk_per_trade * capital
        risk_per_share = abs(price - stop_loss_price)

        if risk_per_share <= 0 or price <= 0:
            return 0.0

        shares = risk_amount / risk_per_share
        max_shares = capital * 0.25 / price
        return min(shares, max_shares)

    def calculate_stop_loss(self, entry_price: float, side: str) -> float:
        """Calculate initial stop loss price."""
        if side == "long":
            return entry_price * (1 - self.config.stop_loss_pct)
        return entry_price * (1 + self.config.stop_loss_pct)

    def calculate_take_profit(self, entry_price: float, side: str) -> float:
        """Calculate take profit price."""
        if side == "long":
            return entry_price * (1 + self.config.take_profit_pct)
        return entry_price * (1 - self.config.take_profit_pct)

    def update_trailing_stop(self, position: Position, current_price: float) -> float:
        """Update trailing stop — only moves in the profitable direction."""
        if position.side == "long":
            new_stop = current_price * (1 - self.config.trailing_stop_pct)
            floor = position.trailing_stop if position.trailing_stop else position.stop_loss
            return max(new_stop, floor)
        else:
            new_stop = current_price * (1 + self.config.trailing_stop_pct)
            ceiling = position.trailing_stop if position.trailing_stop else position.stop_loss
            return min(new_stop, ceiling)

    def should_close_on_risk(self, position: Position) -> str | None:
        """
        Check if a position should be closed for risk reasons.

        Returns the reason string if yes, None if no.
        """
        effective_stop = position.trailing_stop or position.stop_loss

        if position.side == "long":
            if position.current_price <= effective_stop:
                return f"stop loss hit (price {position.current_price:.2f} <= stop {effective_stop:.2f})"
            if position.take_profit > 0 and position.current_price >= position.take_profit:
                return f"take profit hit (price {position.current_price:.2f} >= target {position.take_profit:.2f})"
        else:
            if position.current_price >= effective_stop:
                return f"stop loss hit (price {position.current_price:.2f} >= stop {effective_stop:.2f})"
            if position.take_profit > 0 and position.current_price <= position.take_profit:
                return f"take profit hit (price {position.current_price:.2f} <= target {position.take_profit:.2f})"

        return None

    def reset_daily(self) -> None:
        """Reset daily counters (call at market open)."""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.killed = False
        self._kill_reason = ""
