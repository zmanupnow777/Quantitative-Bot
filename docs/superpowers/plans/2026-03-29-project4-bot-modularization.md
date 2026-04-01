# Project 4: Modular Trading Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose the monolithic `trading_bot.py` prototype into a modular `bot/` package that reuses existing `strategies/` classes, adds missing modules (sim broker, trade logger, monitor, performance tracker), and creates clean entry-point scripts.

**Architecture:** The bot package follows the same layered pattern as the rest of the project. `bot/brokers/` contains broker implementations behind a common ABC. `bot/live_strategy.py` wraps existing `BaseStrategy` subclasses (no logic duplication). `bot/trading_bot.py` is the orchestrator loop. New modules add trade logging, terminal monitoring, and backtest-vs-live performance comparison.

**Tech Stack:** Python 3.12, pandas, numpy, yfinance, alpaca-trade-api (optional), ccxt (optional), existing `strategies/`, `data/`, `config/` modules.

---

## File Structure

### Files to create:
- `bot/brokers/__init__.py` — broker package exports
- `bot/brokers/base.py` — `BrokerInterface` ABC + shared dataclasses (`Order`, `Position`, `OrderSide`, `OrderType`)
- `bot/brokers/paper_broker.py` — `PaperBroker` using yfinance for prices
- `bot/brokers/sim_broker.py` — `SimBroker` with full JSON trade logging (no API keys)
- `bot/brokers/alpaca_broker.py` — `AlpacaBroker` for paper/live via Alpaca API
- `bot/brokers/ccxt_broker.py` — `CCXTBroker` skeleton for crypto exchanges
- `bot/risk_manager.py` — `RiskManager` with kill switches, position sizing, trailing stops
- `bot/live_strategy.py` — `LiveStrategyAdapter` wrapping any `BaseStrategy`
- `bot/trading_bot.py` — `TradingBot` main loop
- `bot/trade_logger.py` — `TradeLogger` (JSON + daily human-readable logs)
- `bot/monitor.py` — `TerminalMonitor` dashboard
- `bot/performance.py` — `PerformanceTracker` comparing live vs backtest
- `bot/__init__.py` — updated package exports
- `run_paper_bot.py` — entry point for paper trading
- `run_sim_bot.py` — entry point for simulated broker
- `check_performance.py` — entry point for performance reports

### Files to rename:
- `backtest_engine.py` → `backtest_engine_demo.py` (standalone demo, superseded by modular system)

### Files to delete:
- `trading_bot.py` (root) — replaced by modular `bot/` package

---

### Task 1: Rename backtest_engine.py and clean up

**Files:**
- Rename: `backtest_engine.py` → `backtest_engine_demo.py`
- Delete: `trading_bot.py` (root-level, after modules are built)

- [ ] **Step 1: Rename backtest_engine.py**
```bash
cd "c:/Users/zanea/Downloads/Zane's Docs/M/T Bot/ENVIRONMENT & DATA PIPELINE/quant-trading-system"
mv backtest_engine.py backtest_engine_demo.py
```

- [ ] **Step 2: Verify rename**
```bash
ls backtest_engine_demo.py
```

---

### Task 2: Create broker base module

**Files:**
- Create: `bot/brokers/__init__.py`
- Create: `bot/brokers/base.py`

Contains: `BrokerInterface` ABC, `Order`, `Position`, `OrderSide`, `OrderType`, `BotConfig` dataclasses.

---

### Task 3: Create paper broker

**Files:**
- Create: `bot/brokers/paper_broker.py`

`PaperBroker` — simulated broker that uses yfinance for price data, tracks positions/cash in memory.

---

### Task 4: Create sim broker

**Files:**
- Create: `bot/brokers/sim_broker.py`

`SimBroker` — like PaperBroker but logs every order/fill to a JSON file. No API keys needed. Perfect for testing bot logic offline.

---

### Task 5: Create Alpaca broker

**Files:**
- Create: `bot/brokers/alpaca_broker.py`

`AlpacaBroker` — connects to Alpaca paper or live API. Uses credentials from `config/settings.py`.

---

### Task 6: Create CCXT broker skeleton

**Files:**
- Create: `bot/brokers/ccxt_broker.py`

`CCXTBroker` — skeleton for crypto exchange connectivity. Implements BrokerInterface with ccxt library.

---

### Task 7: Create risk manager

**Files:**
- Create: `bot/risk_manager.py`

`RiskManager` — daily loss kill switch, position sizing (2% risk), stop loss, take profit, trailing stops, max position count, max position size (25% of capital).

---

### Task 8: Create live strategy adapter

**Files:**
- Create: `bot/live_strategy.py`

`LiveStrategyAdapter` — wraps any `BaseStrategy` subclass for live trading. Calls `generate_signals()` on rolling data window and extracts entry/exit decisions from the latest signal. No duplicated indicator logic.

---

### Task 9: Create trade logger

**Files:**
- Create: `bot/trade_logger.py`

`TradeLogger` — logs orders, fills, positions, and daily summaries. Writes JSON (machine-readable) + daily text log (human-readable) to `logs/` directory.

---

### Task 10: Create terminal monitor

**Files:**
- Create: `bot/monitor.py`

`TerminalMonitor` — prints current positions, today's trades, account value, daily PnL, risk manager status. Refresh on demand.

---

### Task 11: Create performance tracker

**Files:**
- Create: `bot/performance.py`

`PerformanceTracker` — loads backtest results from `reports/` and compares to live trading results. Tracks return, Sharpe, drawdown, win rate, slippage divergence.

---

### Task 12: Create trading bot core

**Files:**
- Create: `bot/trading_bot.py`

`TradingBot` — main orchestrator loop. Connects broker, runs strategy, checks risk, executes trades, logs everything, graceful shutdown.

---

### Task 13: Update bot __init__.py

**Files:**
- Modify: `bot/__init__.py`

Export all bot package classes.

---

### Task 14: Create entry-point scripts

**Files:**
- Create: `run_paper_bot.py`
- Create: `run_sim_bot.py`
- Create: `check_performance.py`

CLI entry points with argparse.

---

### Task 15: Delete root-level trading_bot.py

**Files:**
- Delete: `trading_bot.py`

Now superseded by `bot/` package.

---

### Task 16: Smoke test

- [ ] Run `python run_sim_bot.py --help` to verify CLI works
- [ ] Run a quick 3-cycle sim test
