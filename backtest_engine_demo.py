"""
MULTI-STRATEGY BACKTESTING ENGINE
==================================
A comprehensive backtesting framework inspired by Goshawk Trades' methodology.
Implements multiple strategies, parameter sensitivity analysis, walk-forward 
optimization, Monte Carlo simulation, and strategy comparison.

Usage with Claude Code:
    python backtest_engine.py

Requirements:
    pip install pandas numpy yfinance matplotlib scipy ta

Disclaimer: This is for educational purposes only. Not financial advice.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Callable
from abc import ABC, abstractmethod
import warnings
import json
import os

warnings.filterwarnings("ignore")

# ============================================================
# CORE DATA STRUCTURES
# ============================================================

@dataclass
class Trade:
    entry_date: datetime
    exit_date: datetime
    direction: str  # 'long' or 'short'
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    strategy_name: str

@dataclass
class BacktestResult:
    strategy_name: str
    params: Dict
    trades: List[Trade]
    equity_curve: pd.Series
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_duration: int  # in days
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_pnl: float
    avg_win: float
    avg_loss: float
    expectancy: float
    calmar_ratio: float


# ============================================================
# DATA FETCHER
# ============================================================

class DataFetcher:
    """Fetches historical price data from multiple sources."""
    
    @staticmethod
    def from_yfinance(symbol: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
        """Fetch data from Yahoo Finance."""
        try:
            import yfinance as yf
            data = yf.download(symbol, start=start, end=end, interval=interval, progress=False)
            if data.empty:
                raise ValueError(f"No data returned for {symbol}")
            # Flatten multi-level columns if present
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            return data
        except ImportError:
            print("yfinance not installed. Install with: pip install yfinance")
            return DataFetcher.generate_synthetic(start, end)
    
    @staticmethod
    def from_csv(filepath: str) -> pd.DataFrame:
        """Load data from a CSV file."""
        data = pd.read_csv(filepath, index_col=0, parse_dates=True)
        return data
    
    @staticmethod
    def generate_synthetic(start: str, end: str, initial_price: float = 100.0) -> pd.DataFrame:
        """Generate synthetic price data for testing when no data source available."""
        dates = pd.date_range(start=start, end=end, freq='B')
        n = len(dates)
        np.random.seed(42)
        
        # Geometric Brownian Motion
        mu = 0.0002  # daily drift
        sigma = 0.015  # daily volatility
        returns = np.random.normal(mu, sigma, n)
        prices = initial_price * np.exp(np.cumsum(returns))
        
        # Generate OHLCV
        data = pd.DataFrame(index=dates)
        data['Close'] = prices
        data['Open'] = data['Close'].shift(1).fillna(initial_price)
        data['High'] = data[['Open', 'Close']].max(axis=1) * (1 + np.abs(np.random.normal(0, 0.005, n)))
        data['Low'] = data[['Open', 'Close']].min(axis=1) * (1 - np.abs(np.random.normal(0, 0.005, n)))
        data['Volume'] = np.random.randint(1000000, 10000000, n)
        
        return data


# ============================================================
# STRATEGY BASE CLASS
# ============================================================

class Strategy(ABC):
    """Abstract base class for all trading strategies."""
    
    def __init__(self, name: str, params: Dict = None):
        self.name = name
        self.params = params or {}
    
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals from price data.
        Returns a Series with values: 1 (buy), -1 (sell), 0 (no signal)
        """
        pass
    
    def get_param_ranges(self) -> Dict[str, List]:
        """Return parameter ranges for sensitivity analysis."""
        return {}


# ============================================================
# STRATEGY IMPLEMENTATIONS
# ============================================================

class MACrossoverStrategy(Strategy):
    """
    Moving Average Crossover Strategy.
    Buy when fast MA crosses above slow MA, sell on opposite.
    One of the simplest trend-following strategies.
    """
    
    def __init__(self, fast_period: int = 10, slow_period: int = 50):
        super().__init__(
            name="MA_Crossover",
            params={"fast_period": fast_period, "slow_period": slow_period}
        )
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        fast_ma = data['Close'].rolling(self.params['fast_period']).mean()
        slow_ma = data['Close'].rolling(self.params['slow_period']).mean()
        
        signals = pd.Series(0, index=data.index)
        signals[fast_ma > slow_ma] = 1
        signals[fast_ma <= slow_ma] = -1
        
        # Only signal on crossover points
        signal_changes = signals.diff().fillna(0)
        trade_signals = pd.Series(0, index=data.index)
        trade_signals[signal_changes > 0] = 1   # buy signal
        trade_signals[signal_changes < 0] = -1  # sell signal
        
        return trade_signals
    
    def get_param_ranges(self) -> Dict[str, List]:
        return {
            "fast_period": list(range(5, 30, 2)),
            "slow_period": list(range(20, 100, 5))
        }


class RSIMeanReversionStrategy(Strategy):
    """
    RSI Mean Reversion Strategy.
    Buy when RSI is oversold, sell when overbought.
    Classic mean-reversion approach.
    """
    
    def __init__(self, rsi_period: int = 14, oversold: int = 30, overbought: int = 70):
        super().__init__(
            name="RSI_MeanReversion",
            params={"rsi_period": rsi_period, "oversold": oversold, "overbought": overbought}
        )
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        delta = data['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(self.params['rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.params['rsi_period']).mean()
        
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        signals = pd.Series(0, index=data.index)
        signals[rsi < self.params['oversold']] = 1    # buy when oversold
        signals[rsi > self.params['overbought']] = -1  # sell when overbought
        
        return signals
    
    def get_param_ranges(self) -> Dict[str, List]:
        return {
            "rsi_period": list(range(7, 28, 3)),
            "oversold": list(range(20, 40, 5)),
            "overbought": list(range(60, 85, 5))
        }


class BollingerBandStrategy(Strategy):
    """
    Bollinger Band Mean Reversion Strategy.
    Buy when price touches lower band, sell at upper band.
    """
    
    def __init__(self, bb_period: int = 20, bb_std: float = 2.0):
        super().__init__(
            name="Bollinger_Band",
            params={"bb_period": bb_period, "bb_std": bb_std}
        )
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        ma = data['Close'].rolling(self.params['bb_period']).mean()
        std = data['Close'].rolling(self.params['bb_period']).std()
        
        upper = ma + self.params['bb_std'] * std
        lower = ma - self.params['bb_std'] * std
        
        signals = pd.Series(0, index=data.index)
        signals[data['Close'] < lower] = 1    # buy at lower band
        signals[data['Close'] > upper] = -1   # sell at upper band
        
        return signals
    
    def get_param_ranges(self) -> Dict[str, List]:
        return {
            "bb_period": list(range(10, 40, 5)),
            "bb_std": [1.5, 2.0, 2.5, 3.0]
        }


class BreakoutStrategy(Strategy):
    """
    Donchian Channel Breakout Strategy.
    Buy on new N-period high, sell on new N-period low.
    Classic trend-following / momentum strategy (Turtle Trading).
    """
    
    def __init__(self, entry_period: int = 20, exit_period: int = 10):
        super().__init__(
            name="Breakout",
            params={"entry_period": entry_period, "exit_period": exit_period}
        )
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        high_channel = data['High'].rolling(self.params['entry_period']).max()
        low_channel = data['Low'].rolling(self.params['entry_period']).min()
        exit_low = data['Low'].rolling(self.params['exit_period']).min()
        exit_high = data['High'].rolling(self.params['exit_period']).max()
        
        signals = pd.Series(0, index=data.index)
        signals[data['Close'] > high_channel.shift(1)] = 1   # breakout long
        signals[data['Close'] < low_channel.shift(1)] = -1   # breakout short
        
        return signals
    
    def get_param_ranges(self) -> Dict[str, List]:
        return {
            "entry_period": list(range(10, 60, 5)),
            "exit_period": list(range(5, 30, 5))
        }


class MACDStrategy(Strategy):
    """
    MACD Strategy with 200 SMA trend filter.
    Long when MACD crosses above signal and price > 200 SMA.
    Short when MACD crosses below signal and price < 200 SMA.
    """
    
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9, trend_filter: int = 200):
        super().__init__(
            name="MACD_Trend",
            params={"fast": fast, "slow": slow, "signal": signal, "trend_filter": trend_filter}
        )
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        ema_fast = data['Close'].ewm(span=self.params['fast'], adjust=False).mean()
        ema_slow = data['Close'].ewm(span=self.params['slow'], adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.params['signal'], adjust=False).mean()
        sma_trend = data['Close'].rolling(self.params['trend_filter']).mean()
        
        signals = pd.Series(0, index=data.index)
        
        # Long: MACD crosses above signal + price above trend SMA
        long_cond = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1)) & (data['Close'] > sma_trend)
        short_cond = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1)) & (data['Close'] < sma_trend)
        
        signals[long_cond] = 1
        signals[short_cond] = -1
        
        return signals
    
    def get_param_ranges(self) -> Dict[str, List]:
        return {
            "fast": [8, 10, 12, 15],
            "slow": [21, 26, 30],
            "signal": [7, 9, 12],
            "trend_filter": [100, 150, 200]
        }


class TrendDeltaStrategy(Strategy):
    """
    Trend Delta Strategy (inspired by Delta Trend Trading channel).
    Measures trend strength by % of candles opening/closing above midline.
    Only takes trades when trend delta > threshold (default 80%).
    """
    
    def __init__(self, lookback: int = 20, threshold: float = 0.80, pullback_gap: int = 5):
        super().__init__(
            name="Trend_Delta",
            params={"lookback": lookback, "threshold": threshold, "pullback_gap": pullback_gap}
        )
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        midline = data['Close'].rolling(self.params['lookback']).mean()
        
        # Calculate trend delta: % of candles above midline in lookback window
        above_mid = (data['Open'] > midline) & (data['Close'] > midline)
        below_mid = (data['Open'] < midline) & (data['Close'] < midline)
        
        bullish_delta = above_mid.rolling(self.params['lookback']).mean()
        bearish_delta = below_mid.rolling(self.params['lookback']).mean()
        
        # Detect pullback to midline (price touches midline with wick but closes above/below)
        bull_pullback = (data['Low'] <= midline) & (data['Close'] > midline)
        bear_pullback = (data['High'] >= midline) & (data['Close'] < midline)
        
        signals = pd.Series(0, index=data.index)
        
        # Long signal: strong bullish trend + pullback to midline
        long_cond = (bullish_delta > self.params['threshold']) & bull_pullback
        short_cond = (bearish_delta > self.params['threshold']) & bear_pullback
        
        signals[long_cond] = 1
        signals[short_cond] = -1
        
        return signals
    
    def get_param_ranges(self) -> Dict[str, List]:
        return {
            "lookback": [10, 15, 20, 30],
            "threshold": [0.70, 0.75, 0.80, 0.85, 0.90],
            "pullback_gap": [3, 5, 7]
        }


class MomentumRankStrategy(Strategy):
    """
    Simple Momentum Strategy.
    Buy when N-period return is positive and above threshold.
    Captures trend continuation.
    """
    
    def __init__(self, momentum_period: int = 20, threshold: float = 0.02):
        super().__init__(
            name="Momentum",
            params={"momentum_period": momentum_period, "threshold": threshold}
        )
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        momentum = data['Close'].pct_change(self.params['momentum_period'])
        
        signals = pd.Series(0, index=data.index)
        signals[momentum > self.params['threshold']] = 1
        signals[momentum < -self.params['threshold']] = -1
        
        return signals
    
    def get_param_ranges(self) -> Dict[str, List]:
        return {
            "momentum_period": [5, 10, 20, 40, 60],
            "threshold": [0.01, 0.02, 0.03, 0.05]
        }


# ============================================================
# BACKTESTING ENGINE
# ============================================================

class BacktestEngine:
    """
    Core backtesting engine. Runs strategies on historical data,
    calculates performance metrics, and supports analysis tools.
    """
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission: float = 0.001,  # 0.1% per trade
        slippage: float = 0.0005,   # 0.05% slippage
        risk_per_trade: float = 0.02  # 2% risk per trade
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.risk_per_trade = risk_per_trade
    
    def run(self, strategy: Strategy, data: pd.DataFrame, long_only: bool = False) -> BacktestResult:
        """Run a single backtest."""
        signals = strategy.generate_signals(data)
        trades = []
        equity = [self.initial_capital]
        capital = self.initial_capital
        position = 0  # 0 = flat, 1 = long, -1 = short
        entry_price = 0
        entry_date = None
        
        for i in range(1, len(data)):
            date = data.index[i]
            price = data['Close'].iloc[i]
            signal = signals.iloc[i]
            
            # Close existing position on opposite signal
            if position != 0 and signal != 0 and signal != position:
                exit_price = price * (1 - self.slippage if position == 1 else 1 + self.slippage)
                size = capital * self.risk_per_trade / abs(entry_price)
                
                if position == 1:
                    pnl = (exit_price - entry_price) * size
                else:
                    pnl = (entry_price - exit_price) * size
                
                pnl -= abs(exit_price * size * self.commission)  # commission
                pnl_pct = pnl / capital
                capital += pnl
                
                trades.append(Trade(
                    entry_date=entry_date,
                    exit_date=date,
                    direction='long' if position == 1 else 'short',
                    entry_price=entry_price,
                    exit_price=exit_price,
                    size=size,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    strategy_name=strategy.name
                ))
                position = 0
            
            # Open new position
            if position == 0 and signal != 0:
                if long_only and signal == -1:
                    equity.append(capital)
                    continue
                
                entry_price = price * (1 + self.slippage if signal == 1 else 1 - self.slippage)
                entry_date = date
                position = signal
            
            equity.append(capital)
        
        # Close any open position at end
        if position != 0:
            exit_price = data['Close'].iloc[-1]
            size = capital * self.risk_per_trade / abs(entry_price)
            pnl = ((exit_price - entry_price) if position == 1 else (entry_price - exit_price)) * size
            pnl -= abs(exit_price * size * self.commission)
            capital += pnl
            trades.append(Trade(
                entry_date=entry_date,
                exit_date=data.index[-1],
                direction='long' if position == 1 else 'short',
                entry_price=entry_price,
                exit_price=exit_price,
                size=size,
                pnl=pnl,
                pnl_pct=pnl / (capital - pnl),
                strategy_name=strategy.name
            ))
            equity[-1] = capital
        
        equity_series = pd.Series(equity, index=data.index[:len(equity)])
        metrics = self._calculate_metrics(trades, equity_series, strategy)
        
        return metrics
    
    def _calculate_metrics(self, trades: List[Trade], equity: pd.Series, strategy: Strategy) -> BacktestResult:
        """Calculate comprehensive performance metrics."""
        if not trades:
            return BacktestResult(
                strategy_name=strategy.name, params=strategy.params,
                trades=[], equity_curve=equity,
                total_return=0, annual_return=0, sharpe_ratio=0,
                max_drawdown=0, max_drawdown_duration=0,
                win_rate=0, profit_factor=0, total_trades=0,
                avg_trade_pnl=0, avg_win=0, avg_loss=0,
                expectancy=0, calmar_ratio=0
            )
        
        # Returns
        total_return = (equity.iloc[-1] / equity.iloc[0]) - 1
        n_days = (equity.index[-1] - equity.index[0]).days
        annual_return = (1 + total_return) ** (365 / max(n_days, 1)) - 1 if n_days > 0 else 0
        
        # Sharpe Ratio
        daily_returns = equity.pct_change().dropna()
        sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() > 0 else 0
        
        # Max Drawdown
        peak = equity.expanding().max()
        drawdown = (equity - peak) / peak
        max_dd = drawdown.min()
        
        # Drawdown duration
        dd_duration = 0
        max_dd_dur = 0
        for i in range(1, len(drawdown)):
            if drawdown.iloc[i] < 0:
                dd_duration += 1
                max_dd_dur = max(max_dd_dur, dd_duration)
            else:
                dd_duration = 0
        
        # Trade stats
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        win_rate = len(wins) / len(trades) if trades else 0
        
        gross_profit = sum(t.pnl for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        avg_win = np.mean([t.pnl for t in wins]) if wins else 0
        avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
        avg_pnl = np.mean([t.pnl for t in trades])
        
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0
        
        return BacktestResult(
            strategy_name=strategy.name,
            params=strategy.params,
            trades=trades,
            equity_curve=equity,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_dur,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(trades),
            avg_trade_pnl=avg_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            expectancy=expectancy,
            calmar_ratio=calmar
        )
    
    def parameter_sensitivity(
        self,
        strategy_class: type,
        data: pd.DataFrame,
        param_name: str,
        param_values: List,
        base_params: Dict = None
    ) -> pd.DataFrame:
        """
        Parameter Sensitivity Analysis (Goshawk's #1 tool).
        Tests how changing one parameter affects performance.
        """
        results = []
        base = base_params or {}
        
        for val in param_values:
            params = {**base, param_name: val}
            try:
                strat = strategy_class(**params)
                result = self.run(strat, data)
                results.append({
                    param_name: val,
                    'sharpe_ratio': result.sharpe_ratio,
                    'total_return': result.total_return,
                    'max_drawdown': result.max_drawdown,
                    'win_rate': result.win_rate,
                    'total_trades': result.total_trades,
                    'profit_factor': result.profit_factor
                })
            except Exception as e:
                print(f"  Error with {param_name}={val}: {e}")
        
        return pd.DataFrame(results)
    
    def walk_forward(
        self,
        strategy_class: type,
        data: pd.DataFrame,
        train_pct: float = 0.7,
        n_splits: int = 5,
        params: Dict = None
    ) -> List[BacktestResult]:
        """
        Walk-Forward Optimization.
        Splits data into train/test windows and tests out-of-sample.
        """
        results = []
        total_len = len(data)
        split_size = total_len // n_splits
        
        for i in range(n_splits):
            start = i * split_size
            end = min(start + split_size, total_len)
            window = data.iloc[start:end]
            
            train_end = int(len(window) * train_pct)
            test_data = window.iloc[train_end:]
            
            if len(test_data) < 20:
                continue
            
            try:
                strat = strategy_class(**(params or {}))
                result = self.run(strat, test_data)
                result.strategy_name = f"{strat.name}_WF_{i+1}"
                results.append(result)
            except Exception as e:
                print(f"  Walk-forward split {i+1} error: {e}")
        
        return results
    
    def monte_carlo(
        self,
        result: BacktestResult,
        n_simulations: int = 1000
    ) -> Dict:
        """
        Monte Carlo Simulation.
        Randomizes trade order to understand distribution of outcomes.
        """
        if not result.trades:
            return {"median_return": 0, "p5_return": 0, "p95_return": 0,
                    "prob_profit": 0, "median_drawdown": 0}
        
        trade_pnls = [t.pnl for t in result.trades]
        final_returns = []
        max_drawdowns = []
        
        for _ in range(n_simulations):
            shuffled = np.random.permutation(trade_pnls)
            equity = self.initial_capital + np.cumsum(shuffled)
            final_ret = (equity[-1] / self.initial_capital) - 1
            final_returns.append(final_ret)
            
            peak = np.maximum.accumulate(equity)
            dd = (equity - peak) / peak
            max_drawdowns.append(dd.min())
        
        return {
            "median_return": np.median(final_returns),
            "p5_return": np.percentile(final_returns, 5),
            "p95_return": np.percentile(final_returns, 95),
            "prob_profit": np.mean([r > 0 for r in final_returns]),
            "median_drawdown": np.median(max_drawdowns),
            "p5_drawdown": np.percentile(max_drawdowns, 5),
            "worst_drawdown": np.min(max_drawdowns)
        }


# ============================================================
# STRATEGY COMPARISON & REPORTING
# ============================================================

class StrategyComparator:
    """Compares multiple strategies and generates reports."""
    
    @staticmethod
    def compare(results: List[BacktestResult]) -> pd.DataFrame:
        """Generate comparison table of all strategy results."""
        rows = []
        for r in results:
            rows.append({
                'Strategy': r.strategy_name,
                'Total Return': f"{r.total_return:.2%}",
                'Annual Return': f"{r.annual_return:.2%}",
                'Sharpe Ratio': f"{r.sharpe_ratio:.2f}",
                'Max Drawdown': f"{r.max_drawdown:.2%}",
                'Win Rate': f"{r.win_rate:.2%}",
                'Profit Factor': f"{r.profit_factor:.2f}",
                'Total Trades': r.total_trades,
                'Expectancy': f"${r.expectancy:.2f}",
                'Calmar Ratio': f"{r.calmar_ratio:.2f}"
            })
        
        df = pd.DataFrame(rows)
        return df
    
    @staticmethod
    def rank_strategies(results: List[BacktestResult], weights: Dict = None) -> List[Tuple[str, float]]:
        """
        Rank strategies using weighted scoring.
        Default weights emphasize Sharpe, drawdown control, and consistency.
        """
        if not weights:
            weights = {
                'sharpe_ratio': 0.30,
                'calmar_ratio': 0.20,
                'win_rate': 0.15,
                'profit_factor': 0.15,
                'max_drawdown': 0.20  # inverted - lower is better
            }
        
        scores = []
        for r in results:
            score = 0
            score += weights.get('sharpe_ratio', 0) * max(r.sharpe_ratio, 0)
            score += weights.get('calmar_ratio', 0) * max(r.calmar_ratio, 0)
            score += weights.get('win_rate', 0) * r.win_rate * 10
            score += weights.get('profit_factor', 0) * min(r.profit_factor, 5)
            score += weights.get('max_drawdown', 0) * max(1 + r.max_drawdown, 0) * 5
            scores.append((r.strategy_name, round(score, 4)))
        
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    @staticmethod
    def generate_report(results: List[BacktestResult], mc_results: Dict = None) -> str:
        """Generate a text-based performance report."""
        report = []
        report.append("=" * 70)
        report.append("MULTI-STRATEGY BACKTEST REPORT")
        report.append("=" * 70)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        report.append("")
        
        comparison = StrategyComparator.compare(results)
        report.append(comparison.to_string(index=False))
        report.append("")
        
        rankings = StrategyComparator.rank_strategies(results)
        report.append("-" * 40)
        report.append("STRATEGY RANKINGS (Weighted Score):")
        report.append("-" * 40)
        for rank, (name, score) in enumerate(rankings, 1):
            report.append(f"  #{rank}: {name} (score: {score})")
        
        if mc_results:
            report.append("")
            report.append("-" * 40)
            report.append("MONTE CARLO RESULTS (Top Strategy):")
            report.append("-" * 40)
            for key, val in mc_results.items():
                if 'return' in key or 'drawdown' in key:
                    report.append(f"  {key}: {val:.2%}")
                else:
                    report.append(f"  {key}: {val:.2%}")
        
        report.append("")
        report.append("=" * 70)
        report.append("DISCLAIMER: For educational purposes only. Not financial advice.")
        report.append("Past performance does not guarantee future results.")
        report.append("=" * 70)
        
        return "\n".join(report)


# ============================================================
# MAIN EXECUTION
# ============================================================

def run_full_analysis():
    """
    Run the complete multi-strategy analysis pipeline.
    This is what you execute to test everything.
    """
    print("=" * 60)
    print("MULTI-STRATEGY BACKTESTING ENGINE")
    print("Inspired by Goshawk Trades / Unbiased Trading methodology")
    print("=" * 60)
    
    # 1. Fetch Data
    print("\n[1/6] Fetching historical data...")
    try:
        data = DataFetcher.from_yfinance("SPY", "2020-01-01", "2025-12-31")
        symbol_name = "SPY"
    except Exception:
        print("  Using synthetic data (install yfinance for real data)")
        data = DataFetcher.generate_synthetic("2020-01-01", "2025-12-31")
        symbol_name = "SYNTHETIC"
    
    print(f"  Data: {symbol_name} | {len(data)} bars | {data.index[0].date()} to {data.index[-1].date()}")
    
    # 2. Initialize Engine & Strategies
    print("\n[2/6] Initializing backtesting engine and strategies...")
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.001,
        slippage=0.0005,
        risk_per_trade=0.02
    )
    
    strategies = [
        MACrossoverStrategy(fast_period=10, slow_period=50),
        MACrossoverStrategy(fast_period=20, slow_period=100),
        RSIMeanReversionStrategy(rsi_period=14, oversold=30, overbought=70),
        RSIMeanReversionStrategy(rsi_period=7, oversold=25, overbought=75),
        BollingerBandStrategy(bb_period=20, bb_std=2.0),
        BreakoutStrategy(entry_period=20, exit_period=10),
        BreakoutStrategy(entry_period=55, exit_period=20),
        MACDStrategy(fast=12, slow=26, signal=9, trend_filter=200),
        TrendDeltaStrategy(lookback=20, threshold=0.80, pullback_gap=5),
        MomentumRankStrategy(momentum_period=20, threshold=0.02),
    ]
    
    # 3. Run Backtests
    print(f"\n[3/6] Running {len(strategies)} strategy backtests...")
    results = []
    for strat in strategies:
        result = engine.run(strat, data)
        results.append(result)
        print(f"  {strat.name} ({strat.params}): "
              f"Return={result.total_return:.2%} | "
              f"Sharpe={result.sharpe_ratio:.2f} | "
              f"MaxDD={result.max_drawdown:.2%} | "
              f"Trades={result.total_trades}")
    
    # 4. Parameter Sensitivity (on top strategy)
    print("\n[4/6] Running parameter sensitivity analysis on MA Crossover...")
    sensitivity = engine.parameter_sensitivity(
        MACrossoverStrategy, data,
        param_name="fast_period",
        param_values=list(range(5, 50, 3)),
        base_params={"slow_period": 50}
    )
    if not sensitivity.empty:
        print(f"  Best fast_period: {sensitivity.loc[sensitivity['sharpe_ratio'].idxmax(), 'fast_period']}")
        print(f"  Sharpe range: {sensitivity['sharpe_ratio'].min():.2f} to {sensitivity['sharpe_ratio'].max():.2f}")
    
    # 5. Monte Carlo on best strategy
    print("\n[5/6] Running Monte Carlo simulation on best strategy...")
    rankings = StrategyComparator.rank_strategies(results)
    best_name = rankings[0][0] if rankings else results[0].strategy_name
    best_result = next(r for r in results if r.strategy_name == best_name)
    
    mc = engine.monte_carlo(best_result, n_simulations=1000)
    print(f"  Strategy: {best_name}")
    print(f"  Median Return: {mc['median_return']:.2%}")
    print(f"  5th Percentile: {mc['p5_return']:.2%}")
    print(f"  95th Percentile: {mc['p95_return']:.2%}")
    print(f"  Probability of Profit: {mc['prob_profit']:.2%}")
    
    # 6. Generate Report
    print("\n[6/6] Generating final report...")
    report = StrategyComparator.generate_report(results, mc)
    print("\n" + report)
    
    # Save results
    report_path = "backtest_report.txt"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")
    
    # Save comparison CSV
    comparison = StrategyComparator.compare(results)
    csv_path = "strategy_comparison.csv"
    comparison.to_csv(csv_path, index=False)
    print(f"Comparison CSV saved to: {csv_path}")
    
    return results, rankings, mc


if __name__ == "__main__":
    results, rankings, mc = run_full_analysis()
