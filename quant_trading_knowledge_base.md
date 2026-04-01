# Quantitative Trading Knowledge Base
## Compiled from Unbiased Trading (Goshawk Trades), Delta Trend Trading & Sharp Research

---

## PART 1: CHANNEL INTELLIGENCE SUMMARY

### Channel 1: Unbiased Trading / Goshawk Trades (@GoshawkTrades)

**Profile:** Mounir (Goshawk Trades) — went from 0 to 12+ algos in 6 years, consistently profitable for 4+ years, multi-6-figure algo trader. Offers coding services for trading strategies, custom TradingView indicators, bots, and backtesting via unbiasedtrading.info. Also runs a "How To Backtest Bootcamp" for systematic traders.

**Core Philosophy (extracted from threads & interviews):**
- **Simple strategies outperform 90% of traders.** After backtesting 1,000+ strategies, the winners are "embarrassingly simple." Complexity = overfitting = death in live markets.
- **You need a quantifiable edge.** Without it, you're doing "sophisticated gambling." Turn every strategy into if/and/or logic. As Jim Simons says, "it's impossible to simulate one-off decisions."
- **Spend more time generating new ideas vs. optimizing backtests.** Idea generation is the bottleneck, not parameter tuning.
- **Time is an underrated variable.** Track how your edge performs at precise times (8:30am open, 11am after morning activity). Different times = vastly different expectancy.
- **Diversify by combining discretionary and algorithmic systems.** Having multiple strategies takes the psychological pressure off any single one.
- **Parameter sensitivity is king.** If tweaking your MA from 20 to 22 kills returns, you're overfit. Robust strategies show smooth performance across parameter ranges, not cliff edges.

**Key Backtesting Techniques (from Goshawk's threads):**
1. **Parameter Sensitivity Analysis** — Tests how small parameter changes affect performance. Look for smooth degradation, not cliff edges.
2. **Walk-Forward Optimization** — Train on one period, test on the next. Prevents overfitting to historical data.
3. **Stress Testing** — Run strategies through extreme market conditions (2008, 2020 COVID crash, etc.).
4. **Monte Carlo Simulation** — Randomize trade order/outcomes to understand the distribution of possible results.

**3 Ways to Automate Trading (from Jan 2026 thread):**
1. **Manual** — Execute trades yourself based on systematic rules
2. **Hybrid** — Alerts + manual execution (semi-automated)
3. **Full Automation** — Fully coded algo that enters/exits without human input

**Quantify First Process:**
1. Turn strategy into if/and/or logic
2. Break down every single part
3. Make it repeatable and testable
4. Backtest rigorously
5. Only then automate

---

### Channel 2: Delta Trend Trading (@deltatrendtrading)

**Profile:** Thomas Skinner — Ivy League finance education delivered free. Content covers options trading, institutional trading concepts, delta analysis, and trend-following strategies. Strong TikTok presence (90K+ followers, 1.5M+ likes). Shares free code via Linktree.

**Key Concepts:**
- **Understanding Delta in Options** — Delta as the key Greek for directional exposure
- **Institutional Trading Timeframes** — How institutions trade from seconds to years
- **Trend Delta Indicator Strategy** — A TradingView indicator that measures trend strength by calculating the percentage of candles opening and closing above/below a midline
  - Delta > 80% = trending market (take trades)
  - Delta < 80% = ranging market (avoid trades)
  - Filters out false signals in ranging markets
- **Entry Rules (Trend Delta Strategy):**
  - Wait for pullback to midline after gap of 5+ candles
  - Pullback should be subtle (wick touch only, not full candle close)
  - Confirm trend delta > 80% after pullback
  - Stop loss at low/high level line
  - Take profit at 2x risk

---

### Channel 3: Sharp Research (@sharp_research)

**Profile:** SharpEdge AI — AI-driven stock ratings and predictive models at sharpresearch.ai. Focuses on data-backed investment research with the goal of outperforming the S&P 500 using quantitative, AI-powered strategies.

**Key Approach:**
- AI-generated stock ratings using predictive models
- Data-backed research over opinion-based analysis
- Systematic approach to stock selection
- Focus on measurable alpha generation

---

### Channel 4: Moon Dev (@moondevonyt)

**Profile:** Moon Dev — algorithmic trader and developer who builds trading bots live on YouTube, shares all code via GitHub (github.com/moondevonyt), and runs Algo Trade Camp (algotradecamp.com). Created the "Quant App" for Hyperliquid trading with automated risk management. Has built a massive 48+ AI agent system for autonomous crypto trading research and execution.

**THIS CHANNEL IS EXTREMELY RELEVANT TO YOUR GOALS.** Moon Dev's entire philosophy is building trading bots with code and AI — exactly what you want to do with Claude Code.

**Core Philosophy & Key Contributions:**
- **The RBI System (Research → Backtest → Implement):** Moon Dev's signature 3-step framework:
  1. **Research** — Use AI/LLMs to research and generate trading strategy ideas
  2. **Backtest** — Test strategies against historical data using backtesting.py; find best variation without overfitting
  3. **Implement** — Code the bot and go live with small size. If it works for 30 days, increase size and run another 30 days
- **"If you don't have a bot, the bots will slowly but surely eat your lunch"** — Core belief that manual trading cannot compete with algorithmic trading
- **AI-Powered Strategy Generation** — Uses LLMs (Claude, DeepSeek, GPT-4) to automatically generate, debug, optimize, and backtest trading strategies
- **Open Source Everything** — All code from YouTube videos is posted at github.com/moondevonyt

**GitHub Repositories (FREE CODE):**

| Repository | Description |
|-----------|-------------|
| **Harvard-Algorithmic-Trading-with-AI** | Harvard-level algo trading course with AI integration (267 stars) |
| **Moon-Dev-Code** | All code from YouTube videos (178 stars) |
| **moon-dev-ai-agents** | 48+ specialized AI agents for crypto trading, backtesting, whale tracking |
| **Trading-Algos (TomData fork)** | Complete algos built on YouTube with backtests |

**Moon Dev's AI Agent System (48+ agents):**
- **RBI Agent** — Automated Research → Backtest → Implement pipeline using AI
- **Trading Agent** — Executes trades on HyperLiquid, Solana, Extended exchanges
- **Risk Agent** — Automated risk management and position sizing
- **Whale Tracker** — Monitors 22,500+ whale wallets for trade signals
- **Smart Money/Dumb Money Signals** — Tracks top 100 profitable vs. bottom 100 addresses
- **Orderflow Agent** — Tracks buy/sell imbalance across 130+ symbols
- **Video Agent** — Generates content with Sora 2
- **Compliance Agent** — Ad compliance analysis
- Uses ModelFactory for LLM abstraction (Claude, OpenAI, DeepSeek, Groq, Gemini)

**Algo Trade Camp Bootcamp Curriculum (15 days):**
- Day 1-3: Python basics for trading
- Day 4: Coding algorithmic orders (entry/exit automation)
- Day 5: Automated risk management systems
- Day 6-9: Coding indicators (SMA, RSI, VWAP, VWMA, Bollinger Bands)
- Day 10: Bot 1 — SMA + Orderbook Trading Bot
- Day 11: Bot 2 — Breakout Trading Bot
- Day 12: Bot 3 — Engulfing Pattern Trading Bot
- Day 13: Backtesting + RBI System (2.9 hours)
- Day 14: Machine Learning in Trading
- Day 15: How to scale & find unlimited winning strategies
- Bonus: DYDX "Goblin" Algorithm, Correlation/Mean Reversion Algo, Market Maker Algo

**Moon Dev API (moondev.com/docs):**
- Tick data for algorithmic trading (500ms polling)
- Funding rate analysis for crypto perps and tokenized assets
- Whale position tracking and smart money signals
- Orderflow data across 130+ Hyperliquid symbols
- Custom AI model trained on 5 years of quant trading research

**Quant App (Free Tool — moondev.com/quantapp):**
- Automated stop loss / take profit
- Max drawdown protection (kill switch)
- Session locking (prevents revenge trading)
- Liquidation heatmap visualization
- Multi-account support with encrypted storage
- Works on Hyperliquid exchange

**Key Technology Stack Used by Moon Dev:**
- Python + backtesting.py for all backtesting
- Claude/Anthropic API for AI-powered strategy generation
- DeepSeek-R1 for cost-effective backtesting research
- Hyperliquid SDK for crypto perpetuals trading
- Solana SDK for on-chain trading
- pandas-ta for 130+ technical indicators
- Conda environment management

**How Moon Dev's Approach Directly Maps to Your Goals:**
1. **Your Goal: Backtest multiple strategies** → Use Moon Dev's RBI Agent which auto-generates and backtests strategies using AI
2. **Your Goal: Create a trading bot** → Moon Dev's entire YouTube + GitHub is step-by-step bot building
3. **Your Goal: Use Claude Code** → Moon Dev's AI agents already use Claude API for strategy generation and the repo has a Claude Code skill file (.claude/skills/)

---

## PART 2: RECOMMENDED BOOKS LIST

### Books Directly Referenced by Goshawk Trades (from threads & interviews)

| # | Title | Author | Why It Matters |
|---|-------|--------|---------------|
| 1 | **Quantitative Trading: How to Build Your Own Algorithmic Trading Business** | Ernest P. Chan | Goshawk did a full thread breakdown. Core message: simple strategies beat complex ones, you don't need a PhD, focus on execution. |
| 2 | **Machine Trading** | Ernest P. Chan | Goshawk's favorite line: "In trading, complexity doesn't pay." Start simple before complex ML methods. |
| 3 | **Evidence-Based Technical Analysis** | David Aronson | Full thread breakdown by Goshawk. Subjective vs. objective analysis — confirm ideas with real data, not gut feel. |
| 4 | **Expected Returns: An Investor's Guide to Harvesting Market Rewards** | Antti Ilmanen | Goshawk read it "more than I can count." 979 pages on risk premiums, alpha vs. disguised risk, behavioral biases. |
| 5 | **Advances in Financial Machine Learning** | Marcos López de Prado | Referenced in quant trading circles Goshawk operates in. Fractional differencing, volume bar sampling, hierarchical risk parity. |
| 6 | **Market Wizards** (series) | Jack D. Schwager | Referenced in Analyzing Alpha podcast with Goshawk. Diverse approaches work — no single formula for success. |
| 7 | **Trading in the Zone** | Mark Douglas | Foundational psychology book referenced across the trading community Goshawk is part of. |

### Essential Quantitative Trading Books (Broader Research)

| # | Title | Author | Focus Area |
|---|-------|--------|-----------|
| 8 | **Algorithmic Trading** | Ernest P. Chan | Advanced strategies for backtesting and live execution |
| 9 | **Trading Systems and Methods** | Perry J. Kaufman | Comprehensive guide to designing and evaluating trading strategies |
| 10 | **Trade Your Way to Financial Freedom** | Van K. Tharp | Building personalized trading systems, position sizing, expectancy |
| 11 | **Technical Analysis of the Financial Markets** | John J. Murphy | The "bible" of technical analysis — charts, indicators, intermarket analysis |
| 12 | **The Way of the Turtle** | Curtis Faith | Simple, practical components of systematic trading |
| 13 | **Fooled by Randomness** | Nassim Nicholas Taleb | Distinguishing skill from luck in trading outcomes |
| 14 | **The Black Swan** | Nassim Nicholas Taleb | Rare, high-impact events and their implications for risk management |
| 15 | **Pit Bull** | Marty Schwartz | Motivation and practical day trading lessons |
| 16 | **Reminiscences of a Stock Operator** | Edwin Lefèvre | Timeless trading psychology through Jesse Livermore's story |
| 17 | **Finding Alphas: A Quantitative Approach to Building Trading Strategies** | Igor Tulchinsky (WorldQuant) | Alpha research process from one of the most successful quant hedge funds |
| 18 | **Machine Learning for Algorithmic Trading** | Stefan Jansen | Hands-on Python approach to ML-based trading |
| 19 | **The Evaluation and Optimization of Trading Strategies** | Robert Pardo | Walk-forward optimization, Monte Carlo, avoiding curve fitting |
| 20 | **Mechanical Trading Systems** | Richard Weissman | Momentum and mean reversion strategies with backtested results |
| 21 | **Following the Trend** | Andreas Clenow | One of the best books on trend following as a strategy class |
| 22 | **Mathematics of Money Management** | Ralph Vince | Mathematical risk management and optimal position sizing |
| 23 | **Cycle Analytics for Traders** | John Ehlers | Digital signal processing methods for financial applications |
| 24 | **How I Trade for a Living** | Gary Smith | 33-year trading journey from novice to rational trader |
| 25 | **Education of a Speculator** | Victor Niederhoffer | Metaphors from other fields applied to trading |
| 26 | **Thinking in Bets** | Annie Duke | Decision-making under uncertainty from a poker perspective |
| 27 | **Against the Gods** | Peter Bernstein | History of probability theory applied to financial modeling |
| 28 | **Dynamic Hedging** | Nassim Nicholas Taleb | Options hedging and arbitrage — practical risk measurement |
| 29 | **Option Volatility and Pricing** | Sheldon Natenberg | The "Options Bible" — from basics to advanced strategies |
| 30 | **Volatility Trading** | Euan Sinclair | Practical guide to capitalizing on market volatility |

---

## PART 3: KEY QUANTITATIVE STRATEGIES TO IMPLEMENT

### Strategy Category 1: Mean Reversion
- **Concept:** Prices tend to return to their average over time
- **Signals:** Bollinger Bands, RSI oversold/overbought, z-score of price vs. moving average
- **Best for:** Range-bound markets, pairs trading, ETF arbitrage

### Strategy Category 2: Momentum / Trend Following
- **Concept:** Assets that have been rising tend to continue rising (and vice versa)
- **Signals:** Moving average crossovers, breakouts, Donchian channels, ADX
- **Best for:** Strong trending markets, futures, commodities

### Strategy Category 3: Statistical Arbitrage
- **Concept:** Exploit pricing inefficiencies between correlated instruments
- **Signals:** Cointegration tests, spread z-scores, pair correlation
- **Best for:** Market-neutral strategies, pairs of stocks/ETFs

### Strategy Category 4: Volatility-Based
- **Concept:** Trade based on volatility expansion/contraction cycles
- **Signals:** ATR-based entries, VIX mean reversion, volatility breakouts
- **Best for:** Options strategies, volatility ETFs

### Strategy Category 5: Time-Based (Goshawk's emphasis)
- **Concept:** Edge varies by time of day, day of week, seasonality
- **Signals:** Intraday patterns, overnight gaps, end-of-month effects
- **Best for:** Intraday futures, overnight equity holds

### Strategy Category 6: Trend Delta (from Delta Trend Trading)
- **Concept:** Measure trend strength via candle position relative to midline
- **Signals:** Trend Delta > 80%, pullback to midline, candle confirmation
- **Best for:** Swing trading, filtering out ranging markets

### Strategy Category 7: Market Maker (from Moon Dev)
- **Concept:** Provide liquidity by placing orders on both sides of the spread
- **Signals:** Orderbook imbalance, spread width, inventory management
- **Best for:** High-frequency, works in any market condition (long + short)

### Strategy Category 8: Correlation / Mean Reversion Pairs (from Moon Dev)
- **Concept:** Track correlation between assets (e.g., ETH & BTC), wait for divergence, trade the convergence
- **Signals:** Rolling correlation, z-score of spread, cointegration tests
- **Best for:** Market-neutral strategies, crypto pairs

### Strategy Category 9: AI-Generated Strategies (Moon Dev's RBI System)
- **Concept:** Use LLMs to research, generate, and backtest trading strategies automatically
- **Process:** Feed strategy idea → AI generates backtestable Python code → Execute backtest → Pass/fail threshold → Implement if profitable
- **Best for:** Rapid strategy prototyping, discovering non-obvious patterns

---

## PART 4: TECHNOLOGY STACK RECOMMENDATION

### For Backtesting
| Tool | Purpose | Notes |
|------|---------|-------|
| **Python + pandas** | Data manipulation | Essential foundation |
| **Backtrader** | Backtesting framework | Event-driven, flexible, well-documented |
| **Backtesting.py** | Lightweight backtesting | Simpler alternative to Backtrader |
| **vectorbt** | Vectorized backtesting | Fast, good for parameter sweeps |
| **QuantConnect (Lean)** | Cloud backtesting | Free, multi-asset, C#/Python |
| **yfinance / Alpha Vantage** | Historical data | Free data sources |
| **ccxt** | Crypto exchange data | Unified API for 100+ exchanges |

### For Live Trading
| Tool | Purpose | Notes |
|------|---------|-------|
| **ccxt** | Crypto exchange connectivity | Unified trading API |
| **Alpaca API** | US equities (paper + live) | Commission-free, great for demo |
| **Interactive Brokers API** | Multi-asset live trading | Professional-grade, global |
| **MetaTrader 5 (MT5)** | Forex/CFD trading | Python integration available |
| **NinjaTrader** | Futures trading | C#-based, robust data feeds |
| **Hyperliquid SDK** | Crypto perpetuals | Moon Dev's preferred exchange |
| **Moon Dev API** | Tick data, whale tracking, orderflow | moondev.com/docs |
| **Moon Dev Quant App** | Risk mgmt / kill switches | Free, no code needed |

### For AI-Powered Strategy Research (Moon Dev's RBI approach)
| Tool | Purpose | Notes |
|------|---------|-------|
| **Claude API (Anthropic)** | Strategy generation & code writing | Best for complex reasoning |
| **DeepSeek-R1** | Cost-effective backtesting research | Moon Dev's go-to for RBI agent |
| **backtesting.py** | Backtesting framework | Moon Dev's preferred backtester |
| **Moon Dev AI Agents** | 48+ trading agents | github.com/moondevonyt/moon-dev-ai-agents |

### For Analysis & Visualization
| Tool | Purpose |
|------|---------|
| **matplotlib / plotly** | Charting equity curves, drawdowns |
| **scipy / statsmodels** | Statistical testing |
| **scikit-learn** | ML-based signal generation |
| **ta-lib / pandas-ta** | 130+ technical indicators |

---

## PART 5: ROADMAP — FROM RESEARCH TO LIVE BOT

### Phase 1: Knowledge Acquisition (Weeks 1-3)
- [ ] Read "Quantitative Trading" by Ernest Chan
- [ ] Read "Evidence-Based Technical Analysis" by David Aronson
- [ ] Watch Goshawk Trades YouTube playlist on backtesting
- [ ] Study the Trend Delta indicator strategy from Delta Trend Trading
- [ ] **Watch Moon Dev's Algo Trade Camp Day 1-12 videos on YouTube (free content)**
- [ ] **Clone Moon Dev's GitHub repos: Harvard-Algorithmic-Trading-with-AI, Moon-Dev-Code**
- [ ] **Study Moon Dev's RBI System (Research → Backtest → Implement)**
- [ ] Set up Python environment with backtesting libraries

### Phase 2: Strategy Development & Backtesting (Weeks 4-8)
- [ ] Implement 5-10 simple strategies (MA crossover, RSI mean reversion, breakout, etc.)
- [ ] Build the Multi-Strategy Backtester (see automation code — backtest_engine.py)
- [ ] **Set up Moon Dev's RBI Agent to auto-generate strategies with Claude/DeepSeek**
- [ ] Run parameter sensitivity analysis on each strategy
- [ ] Perform walk-forward optimization
- [ ] Run Monte Carlo simulations
- [ ] Select top 2-3 strategies based on Sharpe ratio, max drawdown, and consistency

### Phase 3: Paper Trading / Demo Account (Weeks 9-12)
- [ ] Deploy top strategies on paper/demo account (Alpaca Paper or exchange testnet)
- [ ] **Try Moon Dev's Quant App on Hyperliquid for automated risk management**
- [ ] Monitor for 4+ weeks minimum (Moon Dev recommends 30 days minimum)
- [ ] Compare live paper results vs. backtest expectations
- [ ] Track slippage, fill rates, execution timing
- [ ] Refine position sizing and risk management

### Phase 4: Live Trading (Week 13+)
- [ ] Start with minimal capital (1-5% of trading capital)
- [ ] Implement kill switches and risk limits (daily loss limit, max drawdown protection)
- [ ] Monitor daily, review weekly
- [ ] **Moon Dev's rule: If profitable for 30 days, increase size slightly, run another 30 days**
- [ ] Scale up gradually as confidence and data accumulate
- [ ] Never risk more than you can afford to lose

---

## PART 6: IMPORTANT DISCLAIMERS

> **This document is for educational purposes only.** Nothing here constitutes financial advice. Trading involves significant risk of loss. Past performance does not guarantee future results. Always do your own research and consult a qualified financial advisor before trading with real money. The strategies described have not been independently verified for profitability. Backtested results are hypothetical and subject to numerous biases including survivorship bias, look-ahead bias, and overfitting.

---

*Knowledge base compiled: March 28, 2026*
*Sources: Web research across Unbiased Trading, Analyzing Alpha, Thread Reader App, Moon Dev (moondev.com, GitHub, Algo Trade Camp), Delta Trend Trading, Sharp Research, QuantStart, PyQuant News, Robot Wealth, and related quantitative trading resources.*
