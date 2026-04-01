"""Automated strategy research pipeline — generate, screen, backtest, filter, rank."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from backtester.engine import BacktestEngine, BacktestResult
from data.storage.data_store import DataStore
from research.config import ResearchConfig
from research.generator import StrategyGenerator
from strategies.composite import CompositeStrategy

logger = logging.getLogger(__name__)


@dataclass
class CandidateResult:
    """Wrapper for a strategy and its evaluation metrics."""

    strategy: CompositeStrategy
    screen_result: BacktestResult | None = None
    full_result: BacktestResult | None = None
    robustness_score: float = 0.0
    phase: str = "generated"  # generated, screened, backtested, filtered, robust

    @property
    def metrics(self) -> dict[str, float]:
        result = self.full_result or self.screen_result
        return result.metrics if result else {}

    @property
    def description(self) -> str:
        return self.strategy.describe()


@dataclass
class ResearchResult:
    """Final output of the research pipeline."""

    total_generated: int = 0
    total_screened: int = 0
    total_backtested: int = 0
    total_filtered: int = 0
    total_robust: int = 0
    elapsed_seconds: float = 0.0
    winners: list[CandidateResult] = field(default_factory=list)
    all_results: list[CandidateResult] = field(default_factory=list)


class ResearchPipeline:
    """Orchestrate the 6-phase strategy discovery pipeline.

    Phases:
        1. Generate — create N composite strategy candidates
        2. Quick screen — short-window backtest, reject obvious losers
        3. Full backtest — longer window on survivors
        4. Filter — apply strict performance thresholds
        5. Robustness — walk-forward + Monte Carlo on top performers
        6. Rank & report
    """

    def __init__(self, config: ResearchConfig) -> None:
        self.config = config
        self.generator = StrategyGenerator(seed=config.seed)
        self.store = DataStore()

    def run(self) -> ResearchResult:
        """Execute the full research pipeline."""
        start_time = time.time()
        result = ResearchResult()

        # Phase 1: Generate candidates
        logger.info("=" * 60)
        logger.info("PHASE 1: Generating %d candidates (mode=%s)", self.config.n_candidates, self.config.generation_mode)
        logger.info("=" * 60)

        if self.config.generation_mode == "exhaustive":
            candidates = self.generator.generate_exhaustive(self.config.max_indicators_per_condition)
        else:
            candidates = self.generator.generate_random(self.config.n_candidates)

        result.total_generated = len(candidates)
        logger.info("Generated %d candidates", len(candidates))

        if not candidates:
            logger.warning("No candidates generated. Exiting.")
            return result

        # Phase 2: Quick screen
        logger.info("=" * 60)
        logger.info("PHASE 2: Quick screen (%s to %s)", self.config.screen_start, self.config.screen_end)
        logger.info("=" * 60)

        screen_data = self._load_data(self.config.screen_start, self.config.screen_end)
        screened = self._quick_screen(candidates, screen_data)
        result.total_screened = len(screened)
        logger.info("%d / %d passed quick screen", len(screened), len(candidates))

        if not screened:
            logger.warning("No candidates passed quick screen.")
            result.elapsed_seconds = time.time() - start_time
            return result

        # Phase 3: Full backtest
        logger.info("=" * 60)
        logger.info("PHASE 3: Full backtest (%s to %s)", self.config.full_start, self.config.full_end)
        logger.info("=" * 60)

        full_data = self._load_data(self.config.full_start, self.config.full_end)
        backtested = self._full_backtest(screened, full_data)
        result.total_backtested = len(backtested)
        logger.info("%d strategies fully backtested", len(backtested))

        # Phase 4: Filter
        logger.info("=" * 60)
        logger.info("PHASE 4: Applying performance filters")
        logger.info("=" * 60)

        filtered = self._apply_filters(backtested)
        result.total_filtered = len(filtered)
        logger.info("%d / %d passed filters", len(filtered), len(backtested))

        if not filtered:
            logger.warning("No candidates passed performance filters.")
            result.all_results = backtested
            result.elapsed_seconds = time.time() - start_time
            return result

        # Phase 5: Robustness checks
        logger.info("=" * 60)
        logger.info("PHASE 5: Robustness analysis on top %d", self.config.top_n_for_robustness)
        logger.info("=" * 60)

        top_n = sorted(filtered, key=lambda c: c.metrics.get("sharpe_ratio", 0), reverse=True)
        top_n = top_n[: self.config.top_n_for_robustness]

        robust = self._robustness_check(top_n, full_data)
        result.total_robust = len(robust)

        # Phase 6: Rank
        logger.info("=" * 60)
        logger.info("PHASE 6: Final ranking")
        logger.info("=" * 60)

        ranked = sorted(robust, key=lambda c: c.robustness_score, reverse=True)
        result.winners = ranked
        result.all_results = backtested
        result.elapsed_seconds = time.time() - start_time

        logger.info(
            "Research complete: %d generated → %d screened → %d backtested → %d filtered → %d robust (%.1fs)",
            result.total_generated, result.total_screened, result.total_backtested,
            result.total_filtered, result.total_robust, result.elapsed_seconds,
        )

        return result

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _load_data(self, start: str, end: str) -> dict[str, pd.DataFrame]:
        """Load OHLCV data for all configured symbols."""
        data = {}
        for symbol in self.config.symbols:
            df = self.store.get(symbol, self.config.timeframe, start, end)
            if df is not None and not df.empty:
                data[symbol] = df
            else:
                logger.warning("No data for %s", symbol)
        return data

    def _quick_screen(
        self, candidates: list[CompositeStrategy], data: dict[str, pd.DataFrame],
    ) -> list[CandidateResult]:
        """Run a short backtest on each candidate and reject obvious losers."""
        engine = BacktestEngine(
            initial_capital=self.config.initial_capital,
            commission=self.config.commission,
            slippage=self.config.slippage,
            risk_per_trade=self.config.risk_per_trade,
        )
        survivors: list[CandidateResult] = []

        for i, strategy in enumerate(candidates):
            if (i + 1) % 50 == 0:
                logger.info("Screening %d / %d ...", i + 1, len(candidates))

            passed = True
            best_result: BacktestResult | None = None

            for symbol, df in data.items():
                try:
                    result = engine.run(strategy, df, symbol=symbol)
                except Exception:
                    logger.debug("Screen failed for %s on %s", strategy.name, symbol, exc_info=True)
                    passed = False
                    break

                metrics = result.metrics
                if metrics.get("sharpe_ratio", -999) < self.config.screen_min_sharpe:
                    passed = False
                    break
                if metrics.get("win_rate", 0) < self.config.screen_min_win_rate:
                    passed = False
                    break
                if metrics.get("total_trades", 0) < self.config.screen_min_trades:
                    passed = False
                    break

                if best_result is None or metrics.get("sharpe_ratio", 0) > best_result.metrics.get("sharpe_ratio", 0):
                    best_result = result

            if passed and best_result:
                survivors.append(CandidateResult(strategy=strategy, screen_result=best_result, phase="screened"))

        return survivors

    def _full_backtest(
        self, screened: list[CandidateResult], data: dict[str, pd.DataFrame],
    ) -> list[CandidateResult]:
        """Run full backtests on screened candidates."""
        engine = BacktestEngine(
            initial_capital=self.config.initial_capital,
            commission=self.config.commission,
            slippage=self.config.slippage,
            risk_per_trade=self.config.risk_per_trade,
        )
        results: list[CandidateResult] = []

        for i, candidate in enumerate(screened):
            if (i + 1) % 20 == 0:
                logger.info("Full backtest %d / %d ...", i + 1, len(screened))

            best_result: BacktestResult | None = None
            for symbol, df in data.items():
                try:
                    result = engine.run(candidate.strategy, df, symbol=symbol)
                    if best_result is None or result.metrics.get("sharpe_ratio", 0) > best_result.metrics.get("sharpe_ratio", 0):
                        best_result = result
                except Exception:
                    logger.debug("Full backtest failed for %s on %s", candidate.strategy.name, symbol, exc_info=True)

            if best_result:
                candidate.full_result = best_result
                candidate.phase = "backtested"
                results.append(candidate)

        return results

    def _apply_filters(self, backtested: list[CandidateResult]) -> list[CandidateResult]:
        """Apply strict performance thresholds."""
        filtered: list[CandidateResult] = []

        for candidate in backtested:
            m = candidate.metrics
            if m.get("sharpe_ratio", -999) < self.config.min_sharpe:
                continue
            if m.get("win_rate", 0) < self.config.min_win_rate:
                continue
            if m.get("profit_factor", 0) < self.config.min_profit_factor:
                continue
            if abs(m.get("max_drawdown", 1.0)) > self.config.max_drawdown:
                continue

            total_trades = m.get("total_trades", 0)
            result = candidate.full_result
            if result and result.trades is not None and not result.trades.empty:
                date_range = result.equity_curve.index
                if len(date_range) > 1:
                    years = (date_range[-1] - date_range[0]).days / 365.25
                    if years > 0 and total_trades / years < self.config.min_trades_per_year:
                        continue

            candidate.phase = "filtered"
            filtered.append(candidate)

        return filtered

    def _robustness_check(
        self, top_candidates: list[CandidateResult], data: dict[str, pd.DataFrame],
    ) -> list[CandidateResult]:
        """Run walk-forward and Monte Carlo analysis on top candidates.

        Uses simplified in-house analysis rather than the full optimizer pipeline
        to avoid the StrategyCandidate coupling. Scores based on:
        - Out-of-sample performance consistency (walk-forward)
        - Trade order independence (Monte Carlo)
        """
        for candidate in top_candidates:
            score = 0.0
            m = candidate.metrics

            # Base score from metrics (40% weight)
            sharpe = m.get("sharpe_ratio", 0)
            win_rate = m.get("win_rate", 0)
            profit_factor = m.get("profit_factor", 0)
            max_dd = abs(m.get("max_drawdown", 1.0))

            score += min(sharpe / 2.0, 1.0) * 15  # Up to 15 pts for Sharpe
            score += min(win_rate / 0.7, 1.0) * 10  # Up to 10 pts for win rate
            score += min(profit_factor / 3.0, 1.0) * 10  # Up to 10 pts for profit factor
            score += max(0, (0.25 - max_dd) / 0.25) * 5  # Up to 5 pts for low drawdown

            # Walk-forward score (30% weight)
            wf_score = self._walk_forward_score(candidate, data)
            score += wf_score * 30

            # Monte Carlo score (30% weight)
            mc_score = self._monte_carlo_score(candidate)
            score += mc_score * 30

            candidate.robustness_score = round(score, 2)
            candidate.phase = "robust"
            logger.info(
                "%s — robustness: %.1f (WF: %.2f, MC: %.2f, metrics: %.1f)",
                candidate.strategy.name, score, wf_score, mc_score, score - wf_score * 30 - mc_score * 30,
            )

        return top_candidates

    def _walk_forward_score(
        self, candidate: CandidateResult, data: dict[str, pd.DataFrame],
    ) -> float:
        """Simplified walk-forward: split data into windows, check OOS consistency."""
        engine = BacktestEngine(
            initial_capital=self.config.initial_capital,
            commission=self.config.commission,
            slippage=self.config.slippage,
            risk_per_trade=self.config.risk_per_trade,
        )

        n_windows = self.config.walk_forward_windows
        oos_sharpes: list[float] = []

        for symbol, df in data.items():
            window_size = len(df) // n_windows
            if window_size < 50:
                continue

            for w in range(n_windows):
                start = w * window_size
                end = start + window_size
                window_data = df.iloc[start:end]

                # Split 70/30 train/test
                split = int(len(window_data) * 0.7)
                test_data = window_data.iloc[split:]

                if len(test_data) < 20:
                    continue

                try:
                    result = engine.run(candidate.strategy, test_data, symbol=symbol)
                    oos_sharpes.append(result.metrics.get("sharpe_ratio", 0))
                except Exception:
                    oos_sharpes.append(-1.0)

        if not oos_sharpes:
            return 0.0

        # Score: proportion of windows with positive OOS Sharpe
        positive = sum(1 for s in oos_sharpes if s > 0)
        return positive / len(oos_sharpes)

    def _monte_carlo_score(self, candidate: CandidateResult) -> float:
        """Simplified Monte Carlo: shuffle trade PnLs and check consistency."""
        result = candidate.full_result
        if result is None or result.trades is None or result.trades.empty:
            return 0.0

        import random as rng
        rng.seed(self.config.seed or 42)

        trades_pnl = result.trades["pnl"].tolist() if "pnl" in result.trades.columns else []
        if len(trades_pnl) < 5:
            return 0.0

        n_sims = min(self.config.monte_carlo_sims, 500)  # cap for speed
        profitable_runs = 0

        for _ in range(n_sims):
            shuffled = list(trades_pnl)
            rng.shuffle(shuffled)
            cumulative = 0.0
            profitable = True
            max_dd = 0.0
            peak = 0.0
            for pnl in shuffled:
                cumulative += pnl
                if cumulative > peak:
                    peak = cumulative
                dd = (peak - cumulative) / max(peak, 1.0)
                if dd > max_dd:
                    max_dd = dd

            if cumulative > 0 and max_dd < self.config.max_drawdown:
                profitable_runs += 1

        return profitable_runs / n_sims


def save_winners(
    result: ResearchResult,
    output_dir: str | Path = "strategies/generated",
) -> list[Path]:
    """Save winning strategy configs to JSON files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for i, candidate in enumerate(result.winners):
        filename = f"{candidate.strategy.name}.json"
        path = output_dir / filename
        candidate.strategy.save(path)
        saved.append(path)
        logger.info("Saved winner #%d: %s → %s", i + 1, candidate.strategy.name, path)

    return saved
