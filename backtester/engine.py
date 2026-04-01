"""Backtest engine for reusable multi-strategy evaluations."""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategies import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TradeRecord:
    """A completed trade captured by the backtest engine."""

    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    direction: str
    pnl: float
    pnl_percent: float
    quantity: float


@dataclass(slots=True)
class BacktestResult:
    """Container for backtest outputs used by reports and comparisons."""

    strategy_name: str
    symbol: str
    params: dict[str, Any]
    initial_capital: float
    final_equity: float
    commission: float
    slippage: float
    risk_per_trade: float
    long_only: bool
    trades: pd.DataFrame
    equity_curve: pd.Series
    signals: pd.Series
    metrics: dict[str, float]
    prepared_data: pd.DataFrame


class BacktestEngine:
    """Run a strategy over price data and compute a common result bundle."""

    def __init__(
        self,
        *,
        initial_capital: float = 100_000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        risk_per_trade: float = 0.02,
        long_only: bool = True,
    ) -> None:
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive.")
        if not 0 <= commission < 1:
            raise ValueError("commission must be in [0, 1).")
        if not 0 <= slippage < 1:
            raise ValueError("slippage must be in [0, 1).")
        if not 0 < risk_per_trade <= 1:
            raise ValueError("risk_per_trade must be in (0, 1].")

        self.initial_capital = float(initial_capital)
        self.commission = float(commission)
        self.slippage = float(slippage)
        self.risk_per_trade = float(risk_per_trade)
        self.long_only = long_only

    def run(
        self,
        strategy: BaseStrategy,
        data: pd.DataFrame,
        *,
        symbol: str = "UNKNOWN",
    ) -> BacktestResult:
        """Execute a single-strategy backtest over a price dataframe."""
        if data.empty:
            raise ValueError("Backtest data cannot be empty.")

        prepared_data = strategy.prepare_data(data)
        signals = strategy.generate_signals(prepared_data)
        price_series = strategy.get_trade_price_series(prepared_data).reindex(prepared_data.index)

        cash = self.initial_capital
        quantity = 0.0
        active_trade: dict[str, Any] | None = None
        trade_records: list[TradeRecord] = []
        equity_values: list[float] = []
        last_valid_date: pd.Timestamp | None = None
        last_valid_price: float | None = None

        for idx, (date, raw_price) in enumerate(price_series.items()):
            signal = int(signals.iat[idx])
            market_price = float(raw_price) if pd.notna(raw_price) else math.nan
            is_valid_price = math.isfinite(market_price) and market_price > 0

            if is_valid_price:
                last_valid_date = pd.Timestamp(date)
                last_valid_price = market_price

                if quantity == 0.0:
                    if signal == 1:
                        quantity, cash, active_trade = self._open_position(
                            direction=1,
                            date=date,
                            price=market_price,
                            cash=cash,
                        )
                    elif signal == -1 and not self.long_only:
                        quantity, cash, active_trade = self._open_position(
                            direction=-1,
                            date=date,
                            price=market_price,
                            cash=cash,
                        )
                elif quantity > 0.0 and signal == -1:
                    cash, trade = self._close_position(
                        quantity=quantity,
                        active_trade=active_trade,
                        date=date,
                        price=market_price,
                        cash=cash,
                    )
                    quantity = 0.0
                    active_trade = None
                    trade_records.append(trade)
                elif quantity < 0.0 and signal == 1:
                    cash, trade = self._close_position(
                        quantity=quantity,
                        active_trade=active_trade,
                        date=date,
                        price=market_price,
                        cash=cash,
                    )
                    quantity = 0.0
                    active_trade = None
                    trade_records.append(trade)

            equity = cash
            if is_valid_price:
                equity += quantity * market_price
            elif equity_values:
                equity = equity_values[-1]
            equity_values.append(float(equity))

        if quantity != 0.0 and active_trade is not None and last_valid_date is not None and last_valid_price is not None:
            cash, trade = self._close_position(
                quantity=quantity,
                active_trade=active_trade,
                date=last_valid_date,
                price=last_valid_price,
                cash=cash,
            )
            trade_records.append(trade)
            equity_values[-1] = float(cash)

        equity_curve = pd.Series(equity_values, index=prepared_data.index, name="equity")
        trades = self._trade_frame(trade_records)
        metrics = self._calculate_metrics(equity_curve, trades)
        metrics["final_equity"] = float(equity_curve.iloc[-1])

        logger.info(
            "Completed backtest for %s on %s with %d trades.",
            strategy.name,
            symbol,
            len(trades),
        )

        return BacktestResult(
            strategy_name=strategy.name,
            symbol=symbol,
            params=strategy.params,
            initial_capital=self.initial_capital,
            final_equity=float(equity_curve.iloc[-1]),
            commission=self.commission,
            slippage=self.slippage,
            risk_per_trade=self.risk_per_trade,
            long_only=self.long_only,
            trades=trades,
            equity_curve=equity_curve,
            signals=signals,
            metrics=metrics,
            prepared_data=prepared_data,
        )

    def _open_position(
        self,
        *,
        direction: int,
        date: pd.Timestamp,
        price: float,
        cash: float,
    ) -> tuple[float, float, dict[str, Any] | None]:
        """Open a long or short position and return updated state."""
        equity = cash
        target_notional = equity * self.risk_per_trade
        if direction > 0:
            fill_price = price * (1.0 + self.slippage)
            max_affordable = cash / (1.0 + self.commission)
            notional = min(target_notional, max_affordable)
        else:
            fill_price = price * (1.0 - self.slippage)
            notional = target_notional

        if notional <= 0 or fill_price <= 0:
            return 0.0, cash, None

        quantity = notional / fill_price
        commission_cost = notional * self.commission

        if direction > 0:
            cash -= notional + commission_cost
        else:
            cash += notional - commission_cost
            quantity *= -1.0

        trade = {
            "entry_date": pd.Timestamp(date),
            "entry_price": float(fill_price),
            "direction": "long" if direction > 0 else "short",
            "quantity": abs(quantity),
            "entry_commission": float(commission_cost),
        }
        return quantity, cash, trade

    def _close_position(
        self,
        *,
        quantity: float,
        active_trade: dict[str, Any] | None,
        date: pd.Timestamp,
        price: float,
        cash: float,
    ) -> tuple[float, TradeRecord]:
        """Close an active position and return the updated cash plus trade record."""
        if active_trade is None:
            raise ValueError("Cannot close a position without an active trade.")

        absolute_quantity = abs(quantity)
        is_long = quantity > 0
        fill_price = price * (1.0 - self.slippage) if is_long else price * (1.0 + self.slippage)
        notional = absolute_quantity * fill_price
        exit_commission = notional * self.commission

        if is_long:
            cash += notional - exit_commission
            gross_pnl = (fill_price - active_trade["entry_price"]) * absolute_quantity
        else:
            cash -= notional + exit_commission
            gross_pnl = (active_trade["entry_price"] - fill_price) * absolute_quantity

        net_pnl = gross_pnl - active_trade["entry_commission"] - exit_commission
        entry_notional = active_trade["entry_price"] * absolute_quantity
        pnl_percent = net_pnl / entry_notional if entry_notional else 0.0

        trade = TradeRecord(
            entry_date=active_trade["entry_date"],
            exit_date=pd.Timestamp(date),
            entry_price=float(active_trade["entry_price"]),
            exit_price=float(fill_price),
            direction=active_trade["direction"],
            pnl=float(net_pnl),
            pnl_percent=float(pnl_percent),
            quantity=float(absolute_quantity),
        )
        return cash, trade

    @staticmethod
    def _trade_frame(trade_records: list[TradeRecord]) -> pd.DataFrame:
        """Convert trade records into a dataframe."""
        if not trade_records:
            return pd.DataFrame(
                columns=[
                    "entry_date",
                    "exit_date",
                    "entry_price",
                    "exit_price",
                    "direction",
                    "pnl",
                    "pnl_percent",
                    "quantity",
                ]
            )

        return pd.DataFrame([asdict(trade) for trade in trade_records])

    def _calculate_metrics(self, equity_curve: pd.Series, trades: pd.DataFrame) -> dict[str, float]:
        """Compute performance metrics from the equity curve and trade log."""
        returns = equity_curve.pct_change().dropna()
        running_max = equity_curve.cummax()
        drawdown = (equity_curve / running_max) - 1.0
        max_drawdown_percent = abs(float(drawdown.min())) if not drawdown.empty else 0.0
        max_drawdown_duration_days = self._max_drawdown_duration_days(equity_curve, running_max)

        years = self._elapsed_years(equity_curve.index)
        bars_per_year = self._bars_per_year(equity_curve.index)

        total_return = float((equity_curve.iloc[-1] / self.initial_capital) - 1.0)
        annual_return = self._annual_return(equity_curve.iloc[-1], years)
        sharpe_ratio = self._annualized_ratio(returns, bars_per_year)
        sortino_ratio = self._annualized_ratio(returns, bars_per_year, downside_only=True)

        total_trades = int(len(trades))
        winners = trades[trades["pnl"] > 0.0]
        losers = trades[trades["pnl"] < 0.0]
        gross_profit = float(winners["pnl"].sum()) if not winners.empty else 0.0
        gross_loss = float(losers["pnl"].sum()) if not losers.empty else 0.0
        win_rate = float(len(winners) / total_trades) if total_trades else 0.0
        profit_factor = float(gross_profit / abs(gross_loss)) if gross_loss else float("inf") if gross_profit > 0 else 0.0
        expectancy = float(trades["pnl"].mean()) if total_trades else 0.0
        calmar_ratio = float(annual_return / max_drawdown_percent) if max_drawdown_percent else 0.0
        trades_per_year = float(total_trades / years) if years else 0.0

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "max_drawdown_percent": max_drawdown_percent,
            "max_drawdown_duration_days": float(max_drawdown_duration_days),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "calmar_ratio": calmar_ratio,
            "average_trade_pnl": float(trades["pnl"].mean()) if total_trades else 0.0,
            "average_winner": float(winners["pnl"].mean()) if not winners.empty else 0.0,
            "average_loser": float(losers["pnl"].mean()) if not losers.empty else 0.0,
            "largest_winner": float(winners["pnl"].max()) if not winners.empty else 0.0,
            "largest_loser": float(losers["pnl"].min()) if not losers.empty else 0.0,
            "total_trades": float(total_trades),
            "trades_per_year": trades_per_year,
        }

    def _annual_return(self, final_equity: float, years: float) -> float:
        """Return the compounded annual growth rate."""
        if years <= 0 or final_equity <= 0:
            return 0.0
        return float((final_equity / self.initial_capital) ** (1.0 / years) - 1.0)

    @staticmethod
    def _annualized_ratio(
        returns: pd.Series,
        bars_per_year: float,
        *,
        downside_only: bool = False,
    ) -> float:
        """Return a Sharpe- or Sortino-style annualized ratio."""
        if returns.empty:
            return 0.0

        sample = returns[returns < 0.0] if downside_only else returns
        deviation = float(sample.std(ddof=0))
        if deviation == 0.0 or math.isnan(deviation):
            return 0.0
        return float((returns.mean() / deviation) * math.sqrt(bars_per_year))

    @staticmethod
    def _elapsed_years(index: pd.Index) -> float:
        """Infer the elapsed years covered by a datetime index."""
        if len(index) < 2:
            return 1 / 252

        start = pd.Timestamp(index[0])
        end = pd.Timestamp(index[-1])
        elapsed_days = max((end - start).days, 1)
        return max(elapsed_days / 365.25, 1 / 252)

    @staticmethod
    def _bars_per_year(index: pd.Index) -> float:
        """Infer an annualization factor from the data frequency."""
        if len(index) < 2:
            return 252.0

        deltas = pd.Series(pd.Index(index).to_series().diff().dropna())
        median_delta = deltas.median()
        if pd.isna(median_delta):
            return 252.0

        seconds = median_delta.total_seconds()
        if seconds <= 60:
            return 98_280.0
        if seconds <= 300:
            return 19_656.0
        if seconds <= 900:
            return 6_552.0
        if seconds <= 3_600:
            return 1_638.0
        if seconds <= 14_400:
            return 409.5
        if seconds <= 172_800:
            return 252.0
        if seconds <= 864_000:
            return 52.0
        if seconds <= 3_628_800:
            return 12.0
        return 1.0

    @staticmethod
    def _max_drawdown_duration_days(equity_curve: pd.Series, running_max: pd.Series) -> int:
        """Return the maximum drawdown duration in calendar days."""
        underwater = equity_curve < running_max
        max_duration = 0
        start_date: pd.Timestamp | None = None

        for date, is_underwater in underwater.items():
            current_date = pd.Timestamp(date)
            if is_underwater and start_date is None:
                start_date = current_date
            elif not is_underwater and start_date is not None:
                max_duration = max(max_duration, (current_date - start_date).days)
                start_date = None

        if start_date is not None:
            max_duration = max(max_duration, (pd.Timestamp(equity_curve.index[-1]) - start_date).days)
        return max_duration
