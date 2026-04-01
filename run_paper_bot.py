"""Entry point for paper trading with the Alpaca paper API or local paper broker.

Usage:
    python run_paper_bot.py                                    # Default: MA crossover on SPY
    python run_paper_bot.py --strategy rsi --symbol AAPL       # RSI on Apple
    python run_paper_bot.py --strategy trend_delta --timeframe 1h
    python run_paper_bot.py --broker alpaca                    # Use Alpaca paper API (needs keys)
"""

import argparse
import sys

from bot.brokers.base import BotConfig
from bot.brokers.paper_broker import PaperBroker
from bot.live_strategy import STRATEGY_REGISTRY, get_live_strategy
from bot.trading_bot import TradingBot


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper Trading Bot")
    parser.add_argument("--strategy", default="ma_crossover", choices=sorted(STRATEGY_REGISTRY.keys()))
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--capital", type=float, default=100_000)
    parser.add_argument("--risk", type=float, default=0.02, help="Risk per trade as decimal (default 0.02 = 2%%)")
    parser.add_argument("--broker", default="paper", choices=["paper", "alpaca"],
                        help="paper = local sim with real prices; alpaca = Alpaca paper API")
    parser.add_argument("--cycles", type=int, default=None, help="Max cycles to run (None = infinite)")

    args = parser.parse_args()

    config = BotConfig(
        symbol=args.symbol,
        timeframe=args.timeframe,
        initial_capital=args.capital,
        risk_per_trade=args.risk,
        mode="paper",
        broker=args.broker,
    )

    strategy = get_live_strategy(args.strategy)

    if args.broker == "alpaca":
        from bot.brokers.alpaca_broker import AlpacaBroker
        broker = AlpacaBroker()
    else:
        broker = PaperBroker()

    bot = TradingBot(config, strategy, broker=broker)
    bot.start(max_cycles=args.cycles)


if __name__ == "__main__":
    main()
