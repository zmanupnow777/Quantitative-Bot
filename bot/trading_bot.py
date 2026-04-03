"""Main trading bot orchestrator — connects broker, strategy, risk, and logging."""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
from datetime import datetime

from bot.brokers.base import BotConfig, BrokerInterface, Order, OrderSide, OrderType
from bot.brokers.paper_broker import PaperBroker
from bot.brokers.sim_broker import SimBroker
from bot.live_strategy import LiveStrategyAdapter
from bot.monitor import TerminalMonitor
from bot.price_monitor import PriceMonitor
from bot.risk_manager import RiskManager
from bot.trade_logger import TradeLogger

logger = logging.getLogger(__name__)

TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


class TradingBot:
    """
    Main trading bot loop.

    Workflow each cycle:
    1. Check kill switches
    2. Fetch account info
    3. Fetch latest price data
    4. Update existing positions (trailing stops, risk checks)
    5. Check strategy for entry/exit signals
    6. Execute orders
    7. Log everything
    8. Sleep until next cycle
    """

    def __init__(
        self,
        config: BotConfig,
        strategy: LiveStrategyAdapter,
        broker: BrokerInterface | None = None,
    ) -> None:
        self.config = config
        self.strategy = strategy
        self.risk_manager = RiskManager(config)
        self.trade_logger = TradeLogger(log_dir="logs")
        self.monitor = TerminalMonitor(config)
        self.running = False
        self._last_signal: dict | None = None
        self._price_monitor: PriceMonitor | None = None

        # Select broker if not provided
        if broker is not None:
            self.broker = broker
        elif config.mode == "sim":
            self.broker = SimBroker()
        elif config.mode == "paper":
            self.broker = PaperBroker()
        else:
            # For live/alpaca/ccxt, caller should pass the broker explicitly
            self.broker = PaperBroker()

        # Setup logging
        log_dir = "logs"
        import os
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(
            level=getattr(logging, config.log_level, logging.INFO),
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            handlers=[
                logging.FileHandler(config.log_file),
                logging.StreamHandler(),
            ],
            force=True,
        )

    def start(self, max_cycles: int | None = None) -> None:
        """
        Start the trading bot.

        Args:
            max_cycles: If set, stop after this many cycles (for testing).
                        If None, run indefinitely until shutdown signal.
        """
        logger.info("=" * 50)
        logger.info("TRADING BOT STARTING")
        logger.info("Strategy:  %s (%s)", self.strategy.name, self.strategy.params)
        logger.info("Symbol:    %s", self.config.symbol)
        logger.info("Mode:      %s", self.config.mode)
        logger.info("Timeframe: %s", self.config.timeframe)
        logger.info("Risk/trade: %.1f%%", self.config.risk_per_trade * 100)
        logger.info("=" * 50)

        if not self.broker.connect(self.config):
            logger.error("Failed to connect to broker. Exiting.")
            return

        # Start background price monitor for sub-cycle bracket checking
        from bot.brokers.ccxt_broker import CCXTBroker
        if self.config.use_bracket_orders and isinstance(self.broker, (SimBroker, PaperBroker, CCXTBroker)):
            self._price_monitor = PriceMonitor(
                broker=self.broker,
                symbol=self.config.symbol,
                on_bracket_fill=lambda order: self.trade_logger.log_risk_event({
                    "reason": "bracket_order_triggered_by_monitor",
                    "symbol": order.symbol,
                    "fill_price": order.filled_price,
                }),
                check_interval=5.0,
            )
            self._price_monitor.start()
            logger.info("PriceMonitor started for sub-cycle bracket checking")

        # Graceful shutdown on Ctrl+C
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        self.running = True
        cycle = 0

        while self.running:
            cycle += 1
            if max_cycles and cycle > max_cycles:
                logger.info("Max cycles (%d) reached. Stopping.", max_cycles)
                break

            try:
                self._run_cycle(cycle)
            except Exception as e:
                logger.error("Error in cycle %d: %s", cycle, e, exc_info=True)
                time.sleep(60)
                continue

            sleep_time = TIMEFRAME_SECONDS.get(self.config.timeframe, 3600)
            if max_cycles:
                sleep_time = 1  # fast cycles for testing
            logger.info("Sleeping %ds until next cycle...", sleep_time)
            time.sleep(sleep_time)

        self._on_stop()

    def _run_cycle(self, cycle: int) -> None:
        """Execute one trading cycle."""
        # 1. Kill switch check
        if self.risk_manager.killed:
            logger.critical("Bot killed by risk manager: %s", self.risk_manager.kill_reason)
            self.running = False
            return

        # 2. Account info
        account = self.broker.get_account_info()
        logger.info(
            "Cycle %d | Value: $%.2f | Cash: $%.2f | Daily PnL: $%.2f",
            cycle,
            account["portfolio_value"],
            account["cash"],
            account.get("daily_pnl", 0),
        )

        # 3. Daily loss limit check
        if not self.risk_manager.check_daily_loss_limit(account):
            self.trade_logger.log_risk_event({"reason": self.risk_manager.kill_reason})
            self.running = False
            return

        # 4. Fetch data
        data = self.broker.get_historical_data(self.config.symbol, self.config.timeframe, 200)
        if data.empty:
            logger.warning("No data received. Skipping cycle.")
            return

        current_price = float(data["Close"].iloc[-1])
        logger.info("%s price: $%.2f", self.config.symbol, current_price)

        # 4b. Check broker-level bracket triggers (TP/SL at broker level)
        if self.config.use_bracket_orders:
            bracket_result = self.broker.check_brackets(self.config.symbol, current_price)
            if bracket_result and bracket_result.status == "filled":
                logger.info("Bracket order triggered for %s — position closed by broker", self.config.symbol)
                self.trade_logger.log_risk_event({
                    "reason": "bracket_order_triggered",
                    "symbol": self.config.symbol,
                    "fill_price": bracket_result.filled_price,
                })
                self.risk_manager.daily_trades += 1
                # Position already closed by broker — update monitor and return
                positions = self.broker.get_positions()
                risk_status = {
                    "killed": self.risk_manager.killed,
                    "kill_reason": self.risk_manager.kill_reason,
                    "daily_trades": self.risk_manager.daily_trades,
                    "max_daily_trades": self.risk_manager.max_daily_trades,
                }
                broker_trades = getattr(self.broker, "trade_log", [])
                self.monitor.display(
                    self.broker.get_account_info(), positions, broker_trades,
                    risk_status, self._last_signal,
                )
                return

        # 5. Check existing positions
        positions = self.broker.get_positions()
        has_position = any(p.symbol == self.config.symbol for p in positions)

        if has_position:
            pos = next(p for p in positions if p.symbol == self.config.symbol)
            pos.current_price = current_price
            pos.unrealized_pnl = (current_price - pos.entry_price) * pos.qty
            if pos.side == "short":
                pos.unrealized_pnl = (pos.entry_price - current_price) * pos.qty

            # Update trailing stop
            pos.trailing_stop = self.risk_manager.update_trailing_stop(pos, current_price)
            if self.config.use_bracket_orders:
                self.broker.update_bracket_stop(pos.symbol, pos.trailing_stop)

            # Check risk-based exit
            risk_reason = self.risk_manager.should_close_on_risk(pos)
            if risk_reason:
                logger.info("Risk exit: %s", risk_reason)
                self.trade_logger.log_risk_event({"reason": risk_reason, "symbol": pos.symbol})
                self._close_position(pos, current_price)
            elif self.strategy.should_exit(data, pos):
                logger.info("Strategy exit signal for %s", pos.symbol)
                self._close_position(pos, current_price)
        else:
            # 6. Check for entry
            if not self.risk_manager.check_max_positions(len(positions)):
                return
            if not self.risk_manager.check_max_daily_trades():
                return

            direction = self.strategy.should_enter(data)
            self._last_signal = {
                "strategy": self.strategy.name,
                "direction": direction or "none",
                "time": datetime.now().isoformat(),
            }
            self.trade_logger.log_signal(self._last_signal)

            if direction:
                logger.info("Entry signal: %s %s", direction, self.config.symbol)
                self._open_position(direction, current_price, account["cash"])

        # 7. Display monitor
        risk_status = {
            "killed": self.risk_manager.killed,
            "kill_reason": self.risk_manager.kill_reason,
            "daily_trades": self.risk_manager.daily_trades,
            "max_daily_trades": self.risk_manager.max_daily_trades,
        }
        broker_trades = getattr(self.broker, "trade_log", [])
        self.monitor.display(account, positions, broker_trades, risk_status, self._last_signal)

    def _open_position(self, direction: str, price: float, available_cash: float) -> None:
        """Open a new position with risk-managed sizing."""
        stop_loss = self.risk_manager.calculate_stop_loss(price, direction)
        take_profit = self.risk_manager.calculate_take_profit(price, direction)
        qty = self.risk_manager.calculate_position_size(price, stop_loss, available_cash)

        if qty <= 0:
            logger.warning("Position size is 0. Skipping.")
            return

        # Use fractional qty for crypto (e.g. 0.001 BTC); whole shares for stocks.
        if qty >= 1:
            qty = max(int(qty), 1)
        else:
            qty = round(qty, 6)

        # For Alpaca: price=TP and stop_price=SL enable server-side brackets.
        # For Paper/Sim/CCXT: price=market price for fill; brackets registered separately.
        from bot.brokers.alpaca_broker import AlpacaBroker
        is_alpaca = isinstance(self.broker, AlpacaBroker)
        order = Order(
            symbol=self.config.symbol,
            side=OrderSide.BUY if direction == "long" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            qty=qty,
            price=round(take_profit, 2) if is_alpaca else round(price, 2),
            stop_price=round(stop_loss, 2) if is_alpaca else None,
        )

        result = self.broker.submit_order(order)

        # Register bracket on sim/paper brokers after fill
        if not is_alpaca and self.config.use_bracket_orders and result.status == "filled":
            from bot.brokers.base import Order as _O  # avoid shadowing
            with getattr(self.broker, "_bracket_lock", __import__("threading").Lock()):
                brackets = getattr(self.broker, "_pending_brackets", {})
                brackets[self.config.symbol] = {
                    "stop_loss": round(stop_loss, 2),
                    "take_profit": round(take_profit, 2),
                    "qty": qty,
                    "side": "long" if direction == "long" else "short",
                }
            logger.info(
                "Bracket registered: %s SL=$%.2f TP=$%.2f",
                self.config.symbol, stop_loss, take_profit,
            )
        self.risk_manager.daily_trades += 1

        if result.status in ("filled", "accepted", "new"):
            # Set stop/take-profit on the broker position
            positions = self.broker.get_positions()
            for pos in positions:
                if pos.symbol == self.config.symbol:
                    pos.stop_loss = stop_loss
                    pos.take_profit = take_profit

            self.trade_logger.log_position_opened({
                "symbol": self.config.symbol,
                "direction": direction,
                "qty": qty,
                "price": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            })
            logger.info(
                "Opened %s %d %s @ $%.2f | SL: $%.2f | TP: $%.2f",
                direction, qty, self.config.symbol, price, stop_loss, take_profit,
            )
        else:
            logger.warning("Order not filled: %s", result.status)

    def _close_position(self, position, price: float) -> None:
        """Close an existing position."""
        order = Order(
            symbol=position.symbol,
            side=OrderSide.SELL if position.side == "long" else OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty=position.qty,
            price=price,
        )
        self.broker.submit_order(order)
        self.risk_manager.daily_trades += 1

        pnl = position.unrealized_pnl
        pnl_pct = pnl / (position.entry_price * position.qty) if position.entry_price else 0

        self.trade_logger.log_position_closed({
            "symbol": position.symbol,
            "side": position.side,
            "qty": position.qty,
            "entry_price": position.entry_price,
            "exit_price": price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        })
        logger.info("Closed %s | PnL: $%.2f (%.2f%%)", position.symbol, pnl, pnl_pct * 100)

    def _on_stop(self) -> None:
        """Clean up on bot stop."""
        if self._price_monitor is not None:
            self._price_monitor.stop()
            self._price_monitor.join(timeout=10)
            logger.info("PriceMonitor stopped")
        account = self.broker.get_account_info()
        self.trade_logger.write_daily_summary(account)
        logger.info("Bot stopped. Final portfolio value: $%.2f", account["portfolio_value"])

    def _shutdown(self, signum, frame) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received.")
        self.running = False
