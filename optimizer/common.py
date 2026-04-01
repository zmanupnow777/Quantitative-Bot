"""Shared helpers for Project 3 optimization and robustness analysis."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from hashlib import sha1
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Callable, Sequence, TypeVar

import numpy as np
import pandas as pd

from backtester import DEFAULT_WEIGHTS, BacktestEngine, BacktestResult
from config import settings
from data.storage import DataStore
from run_backtest import DEFAULT_PAIR_MAP, prepare_pair_frame
from strategies import (
    BaseStrategy,
    BollingerBandStrategy,
    DonchianBreakoutStrategy,
    EngulfingStrategy,
    MACrossoverStrategy,
    MACDTrendStrategy,
    MomentumStrategy,
    PairsMeanReversionStrategy,
    RSIMeanReversionStrategy,
    TrendDeltaStrategy,
    VWAPReversionStrategy,
)

logger = logging.getLogger(__name__)

try:
    from tqdm.auto import tqdm
except ImportError:  # pragma: no cover
    T = TypeVar("T")

    def tqdm(  # type: ignore[no-redef]
        iterable: Sequence[T] | None = None,
        *,
        total: int | None = None,
        **_: Any,
    ) -> Sequence[T] | "_NullTqdm":
        """Return a no-op progress helper when tqdm is unavailable."""
        if iterable is None:
            return _NullTqdm(total=total)
        return iterable

    class _NullTqdm:  # pragma: no cover
        """Fallback progress bar with the subset of tqdm's API used here."""

        def __init__(self, *, total: int | None = None) -> None:
            self.total = total

        def update(self, _: int = 1) -> None:
            """Ignore progress updates."""

        def close(self) -> None:
            """Ignore close calls."""


StrategyClass = type[BaseStrategy]
TaskT = TypeVar("TaskT")
ResultT = TypeVar("ResultT")

STRATEGY_REGISTRY: dict[str, StrategyClass] = {
    MACrossoverStrategy.strategy_name: MACrossoverStrategy,
    RSIMeanReversionStrategy.strategy_name: RSIMeanReversionStrategy,
    BollingerBandStrategy.strategy_name: BollingerBandStrategy,
    DonchianBreakoutStrategy.strategy_name: DonchianBreakoutStrategy,
    MACDTrendStrategy.strategy_name: MACDTrendStrategy,
    TrendDeltaStrategy.strategy_name: TrendDeltaStrategy,
    MomentumStrategy.strategy_name: MomentumStrategy,
    VWAPReversionStrategy.strategy_name: VWAPReversionStrategy,
    EngulfingStrategy.strategy_name: EngulfingStrategy,
    PairsMeanReversionStrategy.strategy_name: PairsMeanReversionStrategy,
}

BACKTEST_ARTIFACT_PATTERN = re.compile(
    r"^backtest_(?P<symbols>.+)_(?P<start>\d{4}-\d{2}-\d{2})_(?P<end>\d{4}-\d{2}-\d{2})_(?P<timestamp>\d{8}_\d{6})$"
)


@dataclass(slots=True)
class EngineConfig:
    """Serializable engine settings shared across optimization analyses."""

    initial_capital: float = 100_000.0
    commission: float = 0.001
    slippage: float = 0.0005
    risk_per_trade: float = 0.02
    long_only: bool = True

    def build_engine(self) -> BacktestEngine:
        """Return a Project 2 backtest engine configured for this run."""
        return BacktestEngine(
            initial_capital=self.initial_capital,
            commission=self.commission,
            slippage=self.slippage,
            risk_per_trade=self.risk_per_trade,
            long_only=self.long_only,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the config as plain JSON-serializable values."""
        return {
            "initial_capital": self.initial_capital,
            "commission": self.commission,
            "slippage": self.slippage,
            "risk_per_trade": self.risk_per_trade,
            "long_only": self.long_only,
        }


@dataclass(slots=True)
class StrategyCandidate:
    """A Project 2 strategy configuration selected for Project 3 analysis."""

    symbol: str
    strategy_name: str
    params: dict[str, Any]
    start_date: str
    end_date: str
    timeframe: str = settings.DEFAULT_TIMEFRAME
    baseline_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def strategy_class(self) -> StrategyClass:
        """Return the concrete strategy class for this candidate."""
        return get_strategy_class(self.strategy_name)

    @property
    def pair_symbol(self) -> str | None:
        """Return the companion symbol when the candidate is a pairs strategy."""
        raw_value = self.params.get("pair_symbol")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip().upper()
        return DEFAULT_PAIR_MAP.get(self.symbol.upper())

    @property
    def safe_name(self) -> str:
        """Return a filesystem-safe identifier for reports and cache folders."""
        payload = json.dumps(self.params, sort_keys=True, default=json_default)
        suffix = sha1(payload.encode("utf-8")).hexdigest()[:10]
        return f"{self.symbol}_{self.strategy_name}_{self.start_date}_{self.end_date}_{suffix}".replace("/", "_")

    def build_strategy(self, *, params: dict[str, Any] | None = None) -> BaseStrategy:
        """Return a concrete strategy instance using stored or overridden params."""
        return instantiate_strategy(self.strategy_name, params or self.params)

    def to_dict(self) -> dict[str, Any]:
        """Return the candidate as plain serializable data."""
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "params": to_jsonable(self.params),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "timeframe": self.timeframe,
            "baseline_metrics": to_jsonable(self.baseline_metrics),
        }


def get_strategy_class(strategy_name: str) -> StrategyClass:
    """Return the concrete class for a strategy name."""
    normalized_name = strategy_name.strip()
    if normalized_name not in STRATEGY_REGISTRY:
        raise KeyError(f"Unknown strategy: {strategy_name!r}")
    return STRATEGY_REGISTRY[normalized_name]


def instantiate_strategy(strategy_name: str, params: dict[str, Any]) -> BaseStrategy:
    """Instantiate a strategy by name and parameter dictionary."""
    strategy_class = get_strategy_class(strategy_name)
    return strategy_class(**params)


def load_candidate_data(
    candidate: StrategyCandidate,
    *,
    store: DataStore | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Load the data slice required for a strategy candidate."""
    data_store = store or DataStore()
    symbol = candidate.symbol.upper()
    primary = data_store.get(
        symbol,
        timeframe=candidate.timeframe,
        start_date=candidate.start_date,
        end_date=candidate.end_date,
        force_refresh=force_refresh,
    )
    if primary is None or primary.empty:
        raise ValueError(f"No primary market data available for {symbol}.")

    if candidate.strategy_name != PairsMeanReversionStrategy.strategy_name:
        return primary

    pair_symbol = candidate.pair_symbol
    if not pair_symbol:
        raise ValueError(f"{candidate.strategy_name} requires a pair symbol.")

    secondary = data_store.get(
        pair_symbol,
        timeframe=candidate.timeframe,
        start_date=candidate.start_date,
        end_date=candidate.end_date,
        force_refresh=force_refresh,
    )
    if secondary is None or secondary.empty:
        raise ValueError(f"No pair market data available for {pair_symbol}.")

    merged = prepare_pair_frame(primary, secondary)
    if merged.empty:
        raise ValueError(f"No overlapping pair data for {symbol} and {pair_symbol}.")
    return merged


def run_candidate_backtest(
    candidate: StrategyCandidate,
    engine_config: EngineConfig,
    *,
    data: pd.DataFrame | None = None,
    params: dict[str, Any] | None = None,
    force_refresh: bool = False,
) -> BacktestResult:
    """Run a candidate strategy using the shared Project 2 backtest engine."""
    dataset = data if data is not None else load_candidate_data(candidate, force_refresh=force_refresh)
    strategy = candidate.build_strategy(params=params)
    engine = engine_config.build_engine()
    return engine.run(strategy, dataset, symbol=candidate.symbol)


def get_strategy_param_ranges(candidate: StrategyCandidate) -> dict[str, list[Any]]:
    """Return only the tunable parameter ranges for a candidate."""
    param_ranges = candidate.strategy_class.get_param_ranges()
    return {
        name: list(values)
        for name, values in param_ranges.items()
        if name in candidate.params or name not in {"pair_symbol", "secondary_close_column"}
    }


def core_metrics_from_result(result: BacktestResult) -> dict[str, float]:
    """Extract the core performance metrics reused throughout Project 3."""
    return {
        "sharpe_ratio": float(result.metrics.get("sharpe_ratio", 0.0)),
        "total_return": float(result.metrics.get("total_return", 0.0)),
        "max_drawdown_percent": float(result.metrics.get("max_drawdown_percent", 0.0)),
        "win_rate": float(result.metrics.get("win_rate", 0.0)),
        "final_equity": float(result.metrics.get("final_equity", result.final_equity)),
        "total_trades": float(result.metrics.get("total_trades", len(result.trades))),
    }


def strategy_artifact_dir(candidate: StrategyCandidate) -> Path:
    """Return the deterministic output directory for a strategy candidate."""
    path = settings.REPORTS_DIR / "optimization" / candidate.symbol.upper() / candidate.safe_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(path: Path, payload: Any) -> Path:
    """Write JSON to disk using a consistent serializer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=json_default), encoding="utf-8")
    return path


def load_json(path: Path) -> Any:
    """Read JSON from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_dataframe(frame: pd.DataFrame, path: Path) -> Path:
    """Persist a dataframe as CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def write_series(series: pd.Series, path: Path) -> Path:
    """Persist a series as CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    series.to_csv(path, header=True)
    return path


def write_plotly_html(figure: Any, path: Path) -> Path:
    """Write a Plotly figure to an HTML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(str(path), include_plotlyjs="cdn", full_html=True)
    return path


def default_workers(max_workers: int | None = None) -> int:
    """Return a bounded worker count suitable for local optimization tasks."""
    if max_workers is not None:
        return max(1, max_workers)
    cpu_count = os.cpu_count() or 1
    return max(1, min(4, cpu_count - 1))


def should_show_progress(show_progress: bool) -> bool:
    """Return whether a progress bar should be rendered."""
    return show_progress and sys.stderr.isatty()


def execute_parallel_tasks(
    tasks: Sequence[TaskT],
    worker: Callable[[TaskT], ResultT],
    *,
    description: str,
    max_workers: int | None = None,
    use_multiprocessing: bool = True,
    show_progress: bool = True,
) -> list[ResultT]:
    """Execute tasks sequentially or in parallel with an optional progress bar."""
    if not tasks:
        return []

    worker_count = default_workers(max_workers)
    should_parallelize = use_multiprocessing and worker_count > 1 and len(tasks) >= max(6, worker_count * 2)
    progress = tqdm(total=len(tasks), desc=description, disable=not should_show_progress(show_progress))

    try:
        if not should_parallelize:
            results: list[ResultT] = []
            for task in tasks:
                results.append(worker(task))
                progress.update(1)
            return results

        ordered_results: list[ResultT | None] = [None] * len(tasks)
        with ProcessPoolExecutor(
            max_workers=worker_count,
            mp_context=get_context("spawn"),
        ) as executor:
            future_map = {
                executor.submit(worker, task): index
                for index, task in enumerate(tasks)
            }
            for future in as_completed(future_map):
                ordered_results[future_map[future]] = future.result()
                progress.update(1)

        return [result for result in ordered_results if result is not None]
    finally:
        progress.close()


def linked_equity_curve(results: Sequence[BacktestResult], *, initial_capital: float) -> pd.Series:
    """Link multiple segmented equity curves into a single synthetic curve."""
    if not results:
        return pd.Series([initial_capital], name="equity")

    linked_parts: list[pd.Series] = []
    current_equity = float(initial_capital)

    for result in results:
        curve = result.equity_curve.astype(float)
        if curve.empty:
            continue

        scaled_curve = (curve / result.initial_capital) * current_equity
        linked_parts.append(scaled_curve)
        current_equity = float(scaled_curve.iloc[-1])

    if not linked_parts:
        return pd.Series([initial_capital], name="equity")
    return pd.concat(linked_parts).rename("equity")


def aggregate_backtest_results(
    results: Sequence[BacktestResult],
    engine_config: EngineConfig,
) -> dict[str, float]:
    """Aggregate segmented backtest results into a single Project 2 metric bundle."""
    if not results:
        return {
            "total_return": 0.0,
            "annual_return": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown_percent": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_trades": 0.0,
            "final_equity": engine_config.initial_capital,
        }

    engine = engine_config.build_engine()
    combined_curve = linked_equity_curve(results, initial_capital=engine_config.initial_capital)
    combined_trades = pd.concat([result.trades for result in results], ignore_index=True)
    metrics = engine._calculate_metrics(combined_curve, combined_trades)
    metrics["final_equity"] = float(combined_curve.iloc[-1])
    return metrics


def rank_metric_frame(
    frame: pd.DataFrame,
    weights: dict[str, float],
    *,
    higher_is_better: set[str] | None = None,
) -> pd.DataFrame:
    """Return a min-max-weighted ranking over a metric frame."""
    if frame.empty:
        return frame.copy()

    higher_is_better = higher_is_better or {name for name, weight in weights.items() if weight >= 0}
    ranked = frame.copy()
    score = pd.Series(0.0, index=ranked.index)

    for metric, weight in weights.items():
        if metric not in ranked.columns:
            continue

        values = pd.to_numeric(ranked[metric], errors="coerce").replace([math.inf, -math.inf], np.nan)
        fill_value = float(values.median()) if values.notna().any() else 0.0
        values = values.fillna(fill_value)

        if values.nunique(dropna=False) <= 1:
            normalized = pd.Series(1.0, index=ranked.index)
        else:
            normalized = (values - values.min()) / (values.max() - values.min())

        if metric not in higher_is_better:
            normalized = 1.0 - normalized

        score += normalized * abs(weight)

    ranked["score"] = score
    return ranked.sort_values("score", ascending=False).reset_index(drop=True)


def find_latest_project2_artifacts(reports_dir: Path | None = None) -> tuple[Path, Path | None, dict[str, str]]:
    """Return the newest Project 2 metrics artifact and optional comparison file."""
    target_dir = reports_dir or settings.REPORTS_DIR
    metrics_candidates = sorted(
        target_dir.glob("backtest_*_metrics.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not metrics_candidates:
        raise FileNotFoundError("No Project 2 metrics artifacts were found in reports/.")

    metrics_path = metrics_candidates[0]
    prefix = metrics_path.stem.removesuffix("_metrics")
    comparison_path = target_dir / f"{prefix}_comparison.csv"
    metadata = parse_backtest_artifact_prefix(prefix)
    metadata["prefix"] = prefix
    return metrics_path, comparison_path if comparison_path.exists() else None, metadata


def parse_backtest_artifact_prefix(prefix: str) -> dict[str, str]:
    """Parse the date metadata from a Project 2 artifact prefix."""
    match = BACKTEST_ARTIFACT_PATTERN.match(prefix)
    if not match:
        logger.warning("Could not parse Project 2 artifact prefix %s; using default date settings.", prefix)
        return {
            "symbols": "",
            "start": settings.DEFAULT_START_DATE,
            "end": settings.DEFAULT_END_DATE,
            "timestamp": "",
        }
    return match.groupdict()


def load_top_project2_candidates(
    *,
    top_n: int,
    timeframe: str,
    start_date: str | None = None,
    end_date: str | None = None,
    reports_dir: Path | None = None,
) -> tuple[list[StrategyCandidate], pd.DataFrame, dict[str, str], Path]:
    """Load and rank the top Project 2 strategies for Project 3 analysis."""
    metrics_path, comparison_path, metadata = find_latest_project2_artifacts(reports_dir)
    metrics_payload = load_json(metrics_path)

    if comparison_path is not None:
        comparison_frame = pd.read_csv(comparison_path)
    else:
        comparison_rows: list[dict[str, Any]] = []
        for entry in metrics_payload:
            row = {
                "symbol": entry["symbol"],
                "strategy": entry["strategy"],
                "params": json.dumps(entry["params"], sort_keys=True, default=json_default),
            }
            row.update(entry.get("metrics", {}))
            comparison_rows.append(row)
        comparison_frame = pd.DataFrame(comparison_rows)

    ranked = rank_metric_frame(
        comparison_frame,
        DEFAULT_WEIGHTS,
        higher_is_better={name for name, weight in DEFAULT_WEIGHTS.items() if weight >= 0},
    )
    top_rows = ranked.head(top_n)

    metric_lookup = {
        (entry["symbol"], entry["strategy"]): entry
        for entry in metrics_payload
    }
    resolved_start = start_date or metadata.get("start") or settings.DEFAULT_START_DATE
    resolved_end = end_date or metadata.get("end") or settings.DEFAULT_END_DATE

    candidates: list[StrategyCandidate] = []
    for row in top_rows.itertuples(index=False):
        key = (row.symbol, row.strategy)
        payload = metric_lookup[key]
        candidates.append(
            StrategyCandidate(
                symbol=str(row.symbol),
                strategy_name=str(row.strategy),
                params=dict(payload["params"]),
                start_date=resolved_start,
                end_date=resolved_end,
                timeframe=timeframe,
                baseline_metrics={
                    key: float(value)
                    for key, value in payload.get("metrics", {}).items()
                    if isinstance(value, (int, float))
                },
            )
        )

    return candidates, ranked, metadata, metrics_path


def to_jsonable(value: Any) -> Any:
    """Convert nested pandas and numpy objects into JSON-friendly values."""
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def json_default(value: Any) -> Any:
    """Fallback JSON serializer used across optimizer artifacts."""
    return to_jsonable(value)
