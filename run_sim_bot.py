"""Entry point for simulated trading — no API keys needed.

The sim broker logs every order to a JSON audit file in logs/sim_broker/.
Uses real yfinance data if available, otherwise synthetic data.

Usage:
    python run_sim_bot.py                                      # Default settings
    python run_sim_bot.py --strategy rsi --symbol AAPL         # RSI on Apple
    python run_sim_bot.py --cycles 5                           # Run 5 cycles then stop
"""

import argparse

from bot.brokers.base import BotConfig
from bot.brokers.sim_broker import SimBroker
from bot.live_strategy import STRATEGY_REGISTRY, get_live_strategy
from bot.trading_bot import TradingBot


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulated Trading Bot (no API keys needed)")
    parser.add_argument("--strategy", default="ma_crossover", choices=sorted(STRATEGY_REGISTRY.keys()))
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--capital", type=float, default=100_000)
    parser.add_argument("--risk", type=float, default=0.02)
    parser.add_argument("--cycles", type=int, default=None, help="Max cycles to run (None = infinite)")

    args = parser.parse_args()

    config = BotConfig(
        symbol=args.symbol,
        timeframe=args.timeframe,
        initial_capital=args.capital,
        risk_per_trade=args.risk,
        mode="sim",
        broker="sim",
    )

    strategy = get_live_strategy(args.strategy)
    broker = SimBroker()

    bot = TradingBot(config, strategy, broker=broker)
    bot.start(max_cycles=args.cycles)


if __name__ == "__main__":
    main()
