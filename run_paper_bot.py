"""Entry point for paper trading with the Alpaca paper API, local paper broker, or CCXT testnet.

Usage:
    python run_paper_bot.py                                             # Default: MA crossover on SPY
    python run_paper_bot.py --strategy rsi --symbol AAPL               # RSI on Apple
    python run_paper_bot.py --strategy trend_delta --timeframe 1h
    python run_paper_bot.py --broker alpaca                            # Use Alpaca paper API (needs keys)
    python run_paper_bot.py --broker ccxt --symbol BTC/USDT            # HyperLiquid testnet (default)
    python run_paper_bot.py --broker ccxt --exchange binance --symbol ETH/USDT  # Other exchange testnet

CCXT testnet setup (.env):
    CCXT_EXCHANGE=hyperliquid   # or binance, bybit, etc.
    CCXT_API_KEY=your_key
    CCXT_API_SECRET=your_secret
    CCXT_SANDBOX=true           # always true for paper trading
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
    parser.add_argument("--broker", default="paper", choices=["paper", "alpaca", "ccxt"],
                        help="paper = local sim; alpaca = Alpaca paper API; ccxt = crypto exchange testnet")
    parser.add_argument("--exchange", default=None,
                        help="CCXT exchange ID (e.g. hyperliquid, binance, bybit). "
                             "Overrides CCXT_EXCHANGE env var. Default: hyperliquid")
    parser.add_argument("--cycles", type=int, default=None, help="Max cycles to run (None = infinite)")

    args = parser.parse_args()

    # Give each bot its own log file so running two in parallel doesn't interleave logs.
    safe_symbol = args.symbol.replace("/", "-")
    log_file = f"logs/bot_{args.broker}_{safe_symbol}.log"

    config = BotConfig(
        symbol=args.symbol,
        timeframe=args.timeframe,
        initial_capital=args.capital,
        risk_per_trade=args.risk,
        mode="paper",
        broker=args.broker,
        log_file=log_file,
    )

    strategy = get_live_strategy(args.strategy)

    if args.broker == "alpaca":
        from bot.brokers.alpaca_broker import AlpacaBroker
        broker = AlpacaBroker()
    elif args.broker == "ccxt":
        import os
        from bot.brokers.ccxt_broker import CCXTBroker
        exchange_id = args.exchange or os.getenv("CCXT_EXCHANGE", "hyperliquid")
        broker = CCXTBroker(exchange_id=exchange_id, sandbox=True)
        print(f"[CCXT] Connecting to {exchange_id} testnet (sandbox=True)")
    else:
        broker = PaperBroker()

    bot = TradingBot(config, strategy, broker=broker)
    bot.start(max_cycles=args.cycles)


if __name__ == "__main__":
    main()
