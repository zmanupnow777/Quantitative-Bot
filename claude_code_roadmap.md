# Claude Code Implementation Roadmap
## From Research to Live Trading Bot — Complete Project Plan

---

## HOW MANY PROJECTS IS THIS?

This breaks down into **5 distinct Claude Code projects**, done sequentially. Each one builds on the last. Don't try to do them all at once — that's how you get overwhelmed and build something fragile.

| # | Project | Est. Time | Depends On |
|---|---------|-----------|------------|
| 1 | **Environment & Data Pipeline** | 1-2 days | Nothing |
| 2 | **Multi-Strategy Backtester** | 3-5 days | Project 1 |
| 3 | **Strategy Optimizer & Selector** | 2-3 days | Project 2 |
| 4 | **Paper Trading Bot** | 3-5 days | Project 3 |
| 5 | **Live Trading Bot** | 2-3 days | Project 4 (after 30+ days paper results) |

**Total active coding time: ~2-3 weeks**
**Total time including paper trading validation: ~2-3 months**

The gap between Project 4 and 5 is intentional. You need to paper trade for at least 30 days (Moon Dev's rule) before going live. During that waiting period you can research more strategies, read the books, and refine.

---

## GENERAL ROADMAP (The Big Picture)

### Step 1: Set Up Your Foundation
- Install Claude Code (`npm install -g @anthropic-ai/claude-code`)
- Create a project folder structure
- Set up Python environment with all dependencies
- Get API keys for data sources (free: yfinance, Alpha Vantage) and paper trading (Alpaca)
- Clone Moon Dev's repos for reference code

### Step 2: Build the Backtesting Engine
- Implement 8-10 strategies from the knowledge base
- Build data fetching for multiple asset classes
- Create the backtesting loop with proper metrics (Sharpe, drawdown, win rate, profit factor)
- This is where 80% of the intellectual work happens

### Step 3: Find Your Edge
- Run parameter sensitivity analysis (Goshawk's #1 tool)
- Walk-forward optimization to prevent overfitting
- Monte Carlo simulation to understand worst-case scenarios
- Rank strategies and pick the top 2-3
- This is the step most people skip — don't skip it

### Step 4: Paper Trade
- Deploy winning strategies on Alpaca paper account (stocks) or exchange testnet (crypto)
- Automated logging of every trade
- Compare real execution vs. backtest expectations
- Track slippage, timing, and unexpected behavior
- Run for 30+ days minimum

### Step 5: Go Live (Small)
- Start with 1-5% of your intended capital
- Kill switches for daily loss limits
- Automated monitoring and alerting
- Scale up only after sustained profitability

---

## PROJECT 1: ENVIRONMENT & DATA PIPELINE

### What This Project Does
Sets up your entire development environment, installs all dependencies, creates the folder structure, connects to data sources, and builds reusable data fetching utilities. This is the boring but critical foundation.

### Claude Code Prompt

```
I'm building a quantitative trading system from scratch. This is Project 1 of 5 — setting up the environment and data pipeline.

## What I Need You To Build

### 1. Project Structure
Create this folder structure in my current directory:

quant-trading-system/
├── config/
│   ├── settings.py          # All configuration (API keys from env vars, defaults)
│   └── symbols.py           # Symbol lists by asset class
├── data/
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── yfinance_fetcher.py   # Yahoo Finance (stocks, ETFs)
│   │   ├── ccxt_fetcher.py       # Crypto via CCXT
│   │   ├── alpaca_fetcher.py     # Alpaca (stocks, paper trading data)
│   │   └── csv_fetcher.py        # Local CSV files
│   ├── storage/
│   │   ├── __init__.py
│   │   └── data_store.py         # Save/load data locally as parquet
│   └── __init__.py
├── strategies/                    # Will be populated in Project 2
│   └── __init__.py
├── backtester/                    # Will be populated in Project 2
│   └── __init__.py
├── optimizer/                     # Will be populated in Project 3
│   └── __init__.py
├── bot/                           # Will be populated in Project 4
│   └── __init__.py
├── reports/                       # Output directory for reports
├── logs/                          # Trading logs
├── tests/
│   └── test_data_pipeline.py
├── requirements.txt
├── .env.example                   # Template for API keys
├── .gitignore
└── README.md

### 2. Dependencies (requirements.txt)
pandas, numpy, yfinance, ccxt, alpaca-trade-api, backtesting, 
pandas-ta, scipy, matplotlib, plotly, python-dotenv, schedule, 
requests, websocket-client, pytest

### 3. Data Fetchers
Each fetcher should:
- Accept symbol, start_date, end_date, timeframe
- Return a standardized pandas DataFrame with columns: Open, High, Low, Close, Volume
- Handle errors gracefully (retry logic, fallback to cached data)
- Cache data locally as parquet files to avoid re-downloading
- Support multiple timeframes: 1m, 5m, 15m, 1h, 4h, 1d

### 4. Data Store
- Save fetched data as parquet files organized by symbol/timeframe
- Load cached data if it exists and is recent enough
- Merge new data with existing cached data
- Simple API: store.get("SPY", "1d", "2020-01-01", "2025-12-31")

### 5. Config
- Load all API keys from .env file using python-dotenv
- settings.py should have defaults for everything
- symbols.py should have lists: US_STOCKS, CRYPTO, ETFs, FOREX

### 6. Tests
Write tests that verify:
- Each fetcher returns the correct DataFrame shape
- Data store saves and loads correctly
- Config loads environment variables properly

### Technical Requirements
- Python 3.10+
- Type hints everywhere
- Docstrings on all public methods
- Use logging module (not print statements)

Run the tests after building everything to make sure it works.
```

---

## PROJECT 2: MULTI-STRATEGY BACKTESTER

### What This Project Does
Builds the core backtesting engine with 8-10 strategy implementations, proper trade simulation with commission/slippage, and comprehensive performance metrics. This is the heart of the system.

### Claude Code Prompt

```
I'm building a quantitative trading system. This is Project 2 of 5 — the multi-strategy backtesting engine. Project 1 (data pipeline) is already complete in the quant-trading-system/ directory.

## Context
I'm following the methodology of these quantitative traders:
- Goshawk Trades: "Simple strategies outperform 90% of traders." Focus on parameter sensitivity, walk-forward optimization, and Monte Carlo simulation.
- Moon Dev: RBI system (Research → Backtest → Implement). Uses backtesting.py library.
- Key principle: Every strategy must be expressible as if/and/or logic.

## What I Need You To Build

### 1. Strategy Base Class (strategies/base.py)
Abstract base class with:
- generate_signals(data: DataFrame) → Series of 1 (buy), -1 (sell), 0 (hold)
- get_param_ranges() → Dict of parameter names to lists of values for optimization
- name, params properties
- Serialization (save/load strategy configs as JSON)

### 2. Strategy Implementations (strategies/)
Build these 10 strategies, each in its own file:

a) **MA Crossover** (ma_crossover.py) — Fast/slow moving average crossover
b) **RSI Mean Reversion** (rsi_mean_reversion.py) — Buy oversold, sell overbought
c) **Bollinger Band** (bollinger_band.py) — Buy at lower band, sell at upper band
d) **Donchian Breakout** (donchian_breakout.py) — Turtle trading style breakouts
e) **MACD + Trend Filter** (macd_trend.py) — MACD crossover with 200 SMA filter
f) **Trend Delta** (trend_delta.py) — From Delta Trend Trading channel: measure % of candles above/below midline, only trade when delta > 80%, enter on pullback to midline
g) **Momentum** (momentum.py) — N-period return threshold strategy
h) **VWAP Reversion** (vwap_reversion.py) — Trade deviations from VWAP
i) **Engulfing Pattern** (engulfing.py) — Bullish/bearish engulfing candlestick pattern
j) **Mean Reversion Pairs** (pairs_mean_reversion.py) — Z-score of spread between two correlated assets

### 3. Backtesting Engine (backtester/engine.py)
The engine should:
- Accept any Strategy object + DataFrame of price data
- Simulate trades with configurable:
  - Initial capital (default $100,000)
  - Commission (default 0.1%)
  - Slippage (default 0.05%)
  - Risk per trade (default 2% of capital)
  - Long-only or long/short mode
- Track every trade: entry/exit date, price, direction, PnL, PnL%
- Generate equity curve as a time series
- Calculate these metrics for every backtest:
  - Total return, Annual return, Sharpe ratio, Sortino ratio
  - Max drawdown (%), Max drawdown duration (days)
  - Win rate, Profit factor, Expectancy
  - Calmar ratio, Average trade PnL
  - Average winner, Average loser, Largest winner, Largest loser
  - Total trades, Trades per year

### 4. Strategy Comparator (backtester/comparator.py)
- compare(results: List[BacktestResult]) → formatted DataFrame
- rank_strategies(results, weights) → sorted list with weighted composite score
- generate_report(results) → full text report saved to reports/ directory
- generate_html_report(results) → interactive HTML with plotly charts

### 5. Runner Script (run_backtest.py)
A main script that:
- Fetches data for a configurable list of symbols
- Runs all 10 strategies on each symbol
- Generates comparison report
- Saves results to reports/ directory
- Prints summary to console

### Technical Requirements
- Use the data pipeline from Project 1 (import from data/)
- Use pandas-ta for indicator calculations where possible
- Type hints and docstrings everywhere
- Each strategy file should be independently testable
- Write tests in tests/test_strategies.py that verify each strategy generates valid signals

Run the full backtest on SPY from 2020-2025 after building and show me the comparison results.
```

---

## PROJECT 3: STRATEGY OPTIMIZER & SELECTOR

### What This Project Does
Takes the backtester from Project 2 and adds the three critical analysis layers that Goshawk Trades emphasizes: parameter sensitivity, walk-forward optimization, and Monte Carlo simulation. This is what separates real quant work from "I backtested once and it looked good."

### Claude Code Prompt

```
I'm building a quantitative trading system. This is Project 3 of 5 — the strategy optimizer and selector. Projects 1 (data pipeline) and 2 (backtester with 10 strategies) are already complete in quant-trading-system/.

## Context
Goshawk Trades says these are the 4 techniques he used to find his 10 profitable algos:
1. Parameter Sensitivity — "If tweaking your MA from 20 to 22 kills your returns, you're overfit"
2. Walk-Forward Optimization — Train on one period, test on the next
3. Stress Testing — Run through extreme market conditions
4. Monte Carlo — Randomize trade order to understand distribution of outcomes

## What I Need You To Build

### 1. Parameter Sensitivity Analyzer (optimizer/param_sensitivity.py)
- For a given strategy, sweep one parameter at a time across its range
- Hold all other parameters at their defaults
- Record Sharpe ratio, return, max drawdown, win rate for each value
- Generate a heatmap for 2-parameter combinations (e.g., fast_period vs slow_period)
- Output: DataFrame of results + visualization saved as HTML
- KEY INSIGHT: We're looking for SMOOTH performance across parameter ranges. If there's a cliff edge (small change = huge performance drop), the strategy is overfit.

### 2. Walk-Forward Optimizer (optimizer/walk_forward.py)
- Split data into N windows (default 5)
- For each window: train on first 70%, test on last 30%
- Optionally optimize parameters on training set, then test on out-of-sample
- Report out-of-sample performance for each window
- Calculate aggregate out-of-sample metrics
- Flag strategies where in-sample >> out-of-sample (overfitting signal)

### 3. Monte Carlo Simulator (optimizer/monte_carlo.py)
- Take a BacktestResult's list of trades
- Shuffle trade order N times (default 1000 simulations)
- For each shuffle: calculate equity curve, final return, max drawdown
- Report: median return, 5th/95th percentile, probability of profit, worst-case drawdown
- Generate distribution plots of returns and drawdowns

### 4. Stress Tester (optimizer/stress_test.py)
- Run strategy across different market regimes:
  - Bull market (e.g., 2021)
  - Bear market (e.g., 2022)
  - High volatility (e.g., March 2020)
  - Low volatility / sideways
  - Recovery (e.g., 2023)
- Report how the strategy performs in each regime
- Flag strategies that only work in one regime

### 5. Strategy Selector (optimizer/selector.py)
- Take results from all 4 analyses above
- Apply scoring rubric:
  - Parameter sensitivity smoothness: 25%
  - Walk-forward out-of-sample Sharpe: 25%
  - Monte Carlo probability of profit: 20%
  - Stress test consistency across regimes: 15%
  - Raw backtest Sharpe ratio: 15%
- Rank all strategies and output final recommendation
- Generate a comprehensive PDF or HTML report with all charts

### 6. Full Pipeline Script (run_optimization.py)
A script that:
- Takes the top 5 strategies from Project 2's backtest results
- Runs all 4 analyses on each
- Generates the final ranking
- Outputs a complete report to reports/optimization_report.html
- Prints the recommended strategy and its parameters to console

### Technical Requirements
- Use multiprocessing for parameter sweeps (they're embarrassingly parallel)
- All visualizations in plotly (interactive HTML)
- Progress bars for long-running operations (tqdm)
- Save intermediate results so you can resume if interrupted
- Add tqdm to requirements.txt if not already there

Run the full optimization pipeline on the top 5 strategies from Project 2 and show me the final ranking.
```

---

## PROJECT 4: PAPER TRADING BOT

### What This Project Does
Takes the winning strategy from Project 3 and deploys it as a live paper trading bot. This bot connects to Alpaca's paper trading API (stocks) or an exchange testnet (crypto), executes real orders with fake money, and logs everything for analysis.

### Claude Code Prompt

```
I'm building a quantitative trading system. This is Project 4 of 5 — the paper trading bot. Projects 1-3 are complete. The strategy optimizer selected [WINNING_STRATEGY_NAME] with parameters [PARAMS] as the best strategy.

## Context
- Moon Dev's implementation rule: "Code the bot, go live with small size. If it works for 30 days, increase size a bit and run for another 30 days."
- Goshawk Trades: "Turn the strategy into if/and/or logic. Without this, it's impossible to simulate one-off decisions."
- I want to paper trade for at least 30 days before risking real money.

## What I Need You To Build

### 1. Broker Interface (bot/brokers/base.py)
Abstract base class with methods:
- connect(config) → bool
- get_account_info() → Dict (cash, portfolio value, daily PnL)
- get_positions() → List[Position]
- submit_order(order) → Order (with fill confirmation)
- cancel_order(order_id) → bool
- get_current_price(symbol) → float
- get_historical_data(symbol, timeframe, limit) → DataFrame

### 2. Alpaca Paper Broker (bot/brokers/alpaca_broker.py)
Implement the interface for Alpaca's paper trading API:
- Connect using API keys from .env
- Base URL: https://paper-api.alpaca.markets
- Handle order submission, position tracking, account info
- Support market and limit orders

### 3. Simulated Broker (bot/brokers/sim_broker.py)
A local paper broker that doesn't need any API keys:
- Simulates fills instantly at current price
- Tracks positions, cash, PnL locally
- Perfect for testing the bot logic before connecting to Alpaca
- Logs every order and fill to a JSON file

### 4. Risk Manager (bot/risk_manager.py)
This is critical — it protects your capital:
- **Daily loss limit**: Kill switch that stops all trading if daily loss exceeds 5%
- **Position sizing**: Risk 2% of capital per trade, calculated from entry price to stop loss
- **Max positions**: Never hold more than 3 simultaneous positions
- **Stop loss**: Automatic stop loss on every position (configurable %)
- **Take profit**: Automatic take profit (default 2:1 reward:risk)
- **Trailing stop**: Update stop loss as price moves in your favor
- **Max position size**: Never use more than 25% of capital on one trade
- **Correlation check**: Don't open same-direction trades on highly correlated assets

### 5. Live Strategy Adapter (bot/live_strategy.py)
Adapt the winning strategy from the backtester to work in live mode:
- should_enter(data) → 'long', 'short', or None
- should_exit(data, position) → bool
- Use the exact same logic as the backtest version
- Add logging for every signal generated (even if not acted on)

### 6. Trading Bot Core (bot/trading_bot.py)
The main bot loop:
- Connect to broker
- Every cycle (based on timeframe):
  1. Fetch latest price data
  2. Update existing position prices and trailing stops
  3. Check risk manager for any forced exits (stop loss, take profit, kill switch)
  4. Run strategy — check for entry/exit signals
  5. Execute orders if signals fire
  6. Log everything
  7. Sleep until next cycle
- Graceful shutdown on Ctrl+C (close all positions, save state)
- Resume capability (load last state on restart)

### 7. Trade Logger (bot/trade_logger.py)
Comprehensive logging:
- Every order submitted (with timestamp, symbol, side, qty, price)
- Every fill received
- Every position opened/closed with PnL
- Daily summary: total PnL, win/loss count, account value
- Save to both JSON (machine-readable) and a human-readable daily log file
- Performance tracker that compares actual results to backtest expectations

### 8. Dashboard / Monitor (bot/monitor.py)
A simple terminal-based dashboard that shows:
- Current positions and their PnL
- Today's trades and results
- Account value and daily PnL
- Strategy signals (last N signals)
- Risk manager status (daily loss used, positions open vs max)
- Refreshes every 30 seconds

### 9. Entry Point Scripts
- run_paper_bot.py — Start paper trading with the winning strategy
- run_sim_bot.py — Start with simulated broker (no API keys needed)
- check_performance.py — Print performance summary vs backtest expectations

### Technical Requirements
- Use the strategies from Project 2 and config from Project 1
- All API keys loaded from .env file
- Logging to both file and console
- Signal handlers for graceful shutdown (SIGINT, SIGTERM)
- The bot should be runnable as: python run_paper_bot.py --symbol SPY --strategy [name]
- Include a --dry-run flag that generates signals but doesn't execute orders

Start by building and testing with the simulated broker. Run it for 10 simulated cycles and show me the output.
```

---

## PROJECT 5: LIVE TRADING BOT

### What This Project Does
After 30+ days of successful paper trading, this project transitions the paper bot to live trading with real money. The code changes are minimal — mostly swapping the broker and adding extra safety checks.

### Claude Code Prompt

```
I'm building a quantitative trading system. This is Project 5 of 5 — transitioning from paper trading to live. Projects 1-4 are complete and the paper trading bot has been running for [X] days with these results: [PASTE YOUR PAPER TRADING RESULTS HERE].

## What I Need You To Build

### 1. Live Broker Implementation
Depending on what I'm trading:
- **Stocks**: Modify Alpaca broker to use live URL (https://api.alpaca.markets)
- **Crypto**: Add CCXT-based broker for [Binance/Bybit/Hyperliquid]
- Same interface as paper broker — just different connection

### 2. Enhanced Safety Layer (bot/safety.py)
Additional safety for real money:
- **Capital lock**: Hard-coded maximum capital the bot can ever use
- **Cooldown period**: After 3 consecutive losses, pause trading for 24 hours
- **Weekend/holiday check**: Don't trade when markets are closed
- **Heartbeat monitor**: If the bot hasn't executed in expected timeframe, send alert
- **Emergency stop**: A separate script that can kill the bot and close all positions from anywhere
- **Audit log**: Immutable log of every action (append-only file)

### 3. Alerting (bot/alerts.py)
- Send notifications on: trade executed, daily summary, risk limit hit, error
- Support at least one of: email (SMTP), Telegram bot, or Discord webhook
- Configurable alert levels (info, warning, critical)

### 4. Performance Comparison (bot/performance.py)
- Compare live results vs paper results vs backtest expectations
- Track: return, Sharpe, drawdown, win rate, slippage
- Generate weekly performance report
- Flag if live performance deviates significantly from backtest (possible regime change)

### 5. Scaling Plan
- Start at [X]% of intended capital
- After 30 days profitable: increase to [Y]%
- After 60 days: increase to [Z]%
- If drawdown exceeds [threshold]: reduce back to minimum
- Implement this as configurable logic in the bot

### 6. Entry Points
- run_live_bot.py — Start live trading (requires explicit --confirm-live flag)
- emergency_stop.py — Kill everything and flatten all positions
- weekly_report.py — Generate weekly performance report

### Technical Requirements
- The --confirm-live flag is mandatory. The bot should refuse to run live without it.
- Print a clear WARNING message at startup: "YOU ARE TRADING WITH REAL MONEY"
- 5-second countdown before first trade to allow cancellation
- All the safety mechanisms from Project 4's risk manager still apply
- Double-check that kill switches work before deploying

IMPORTANT: I want you to be very conservative with the safety mechanisms. I would rather miss a trade than lose money to a bug. Err on the side of caution everywhere.
```

---

## BEFORE YOU START: SETUP CHECKLIST

### Accounts to Create (Free)
- [ ] **Alpaca Markets** (alpaca.markets) — Paper trading account for US stocks. Get API key + secret.
- [ ] **Alpha Vantage** (alphavantage.co) — Free API key for market data (backup to yfinance)
- [ ] **Optional: Hyperliquid** — If you want to trade crypto (Moon Dev's preferred exchange)
- [ ] **Optional: Binance Testnet** — Crypto paper trading

### Environment Variables (.env file)
```
ALPACA_API_KEY=your_key_here
ALPACA_API_SECRET=your_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPHA_VANTAGE_KEY=your_key_here
```

### Software to Install
```bash
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Create project directory
mkdir quant-trading-system && cd quant-trading-system

# Initialize git
git init

# You'll create a Python virtual environment in Project 1
```

### Reference Repos to Clone (Moon Dev's code)
```bash
# Clone these for reference — don't modify them, just learn from them
git clone https://github.com/moondevonyt/Harvard-Algorithmic-Trading-with-AI.git ~/reference/harvard-algo
git clone https://github.com/moondevonyt/Moon-Dev-Code.git ~/reference/moondev-code
git clone https://github.com/moondevonyt/moon-dev-ai-agents.git ~/reference/moondev-agents
```

---

## WHAT TO DO BETWEEN PROJECTS

### Between Project 1 → 2 (data pipeline → backtester)
- Verify you can fetch clean data for SPY, BTC, ETH, AAPL
- Read Ernest Chan's "Quantitative Trading" chapters 1-3

### Between Project 2 → 3 (backtester → optimizer)
- Run the backtester on 5+ different symbols to see which strategies work where
- Read the Goshawk Trades thread on parameter sensitivity
- Study Moon Dev's RBI system on GitHub

### Between Project 3 → 4 (optimizer → paper bot)
- Sign up for Alpaca paper trading if you haven't
- Read Chapter 4-6 of "Quantitative Trading" (risk management, execution)
- Pick your top 1-2 strategies to deploy

### Between Project 4 → 5 (paper bot → live bot)
- **THIS IS THE MOST IMPORTANT GAP**
- Run paper trading for minimum 30 days
- Compare paper results to backtest expectations weekly
- If paper performance is significantly worse than backtest: go back to Project 3 and investigate
- Only proceed to live if paper trading is consistently profitable
- Start reading "Evidence-Based Technical Analysis" by Aronson

---

## QUICK REFERENCE: KEY PRINCIPLES

1. **Simple > Complex** (Goshawk): After backtesting 1000 strategies, the winners are embarrassingly simple
2. **RBI System** (Moon Dev): Research → Backtest → Implement. Never skip a step.
3. **Parameter Sensitivity** (Goshawk): If small parameter changes kill performance, you're overfit
4. **30-Day Rule** (Moon Dev): Profitable for 30 days on paper → increase size. Repeat.
5. **Risk First** (All): 2% risk per trade, 5% daily loss limit, kill switches on everything
6. **Edge or Nothing** (Goshawk): Without a quantifiable edge, you're just gambling
7. **Time Matters** (Goshawk): Same strategy can have vastly different results at different times of day

---

*Document created: March 28, 2026*
*This roadmap is for educational purposes only. Trading involves significant risk of loss.*
