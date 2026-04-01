"""Background price monitor for sub-cycle bracket order checking."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from bot.brokers.base import BrokerInterface, Order

logger = logging.getLogger(__name__)


class PriceMonitor(threading.Thread):
    """Background thread that checks bracket triggers more frequently than the main loop.

    For sim/paper brokers, the main trading loop only checks TP/SL once per
    cycle (e.g., every 5 minutes). This thread polls price and checks bracket
    triggers at a higher frequency (default 5 seconds) so exits happen closer
    to the actual trigger price.
    """

    def __init__(
        self,
        broker: BrokerInterface,
        symbol: str,
        on_bracket_fill: Callable[[Order], None] | None = None,
        check_interval: float = 5.0,
    ) -> None:
        super().__init__(daemon=True, name=f"PriceMonitor-{symbol}")
        self.broker = broker
        self.symbol = symbol
        self.check_interval = check_interval
        self._on_bracket_fill = on_bracket_fill
        self._running = threading.Event()
        self._running.set()

    def run(self) -> None:
        logger.info(
            "PriceMonitor started for %s (interval: %.1fs)",
            self.symbol, self.check_interval,
        )
        while self._running.is_set():
            try:
                price = self.broker.get_current_price(self.symbol)
                if price > 0:
                    result = self.broker.check_brackets(self.symbol, price)
                    if result and result.status == "filled":
                        logger.info(
                            "PriceMonitor: bracket triggered for %s at $%.2f",
                            self.symbol, result.filled_price,
                        )
                        if self._on_bracket_fill:
                            self._on_bracket_fill(result)
            except Exception:
                logger.debug("PriceMonitor check failed for %s", self.symbol, exc_info=True)

            # Sleep in small increments so stop() is responsive
            for _ in range(int(self.check_interval * 10)):
                if not self._running.is_set():
                    break
                time.sleep(0.1)

        logger.info("PriceMonitor stopped for %s", self.symbol)

    def stop(self) -> None:
        """Signal the monitor to stop."""
        self._running.clear()
