"""Configuration for the automated strategy research pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResearchConfig:
    """Controls how many candidates to generate, how to filter, and what data to use."""

    # Generation
    n_candidates: int = 200
    generation_mode: str = "random"  # "random", "exhaustive", "mutation"
    max_indicators_per_condition: int = 2
    seed: int | None = None

    # Data
    symbols: list[str] = field(default_factory=lambda: ["SPY"])
    timeframe: str = "1d"

    # Quick screen window (shorter, for fast rejection)
    screen_start: str = "2022-01-01"
    screen_end: str = "2023-12-31"

    # Full backtest window (longer, for proper validation)
    full_start: str = "2018-01-01"
    full_end: str = "2025-12-31"

    # Backtest parameters
    initial_capital: float = 100_000.0
    commission: float = 0.001
    slippage: float = 0.0005
    risk_per_trade: float = 0.02

    # Quick screen thresholds (lenient — just reject obvious losers)
    screen_min_sharpe: float = 0.0
    screen_min_win_rate: float = 0.35
    screen_min_trades: int = 10

    # Full backtest filter thresholds (stricter)
    min_sharpe: float = 0.5
    min_win_rate: float = 0.45
    min_profit_factor: float = 1.2
    max_drawdown: float = 0.25
    min_trades_per_year: float = 20.0

    # Robustness
    top_n_for_robustness: int = 10
    walk_forward_windows: int = 5
    monte_carlo_sims: int = 1000

    # Parallelization
    max_workers: int | None = None  # None = cpu_count
