"""Tests for the Project 2 strategy layer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies import (
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
from strategies.base import BaseStrategy


def _representative_data() -> pd.DataFrame:
    """Return deterministic OHLCV-style data for strategy tests."""
    index = pd.date_range("2021-01-01", periods=320, freq="B")
    trend = np.linspace(100.0, 145.0, len(index))
    cycle = 6.0 * np.sin(np.linspace(0.0, 12.0 * np.pi, len(index)))
    close = trend + cycle
    open_ = close + 0.75 * np.sin(np.linspace(0.0, 18.0 * np.pi, len(index)))
    high = np.maximum(open_, close) + 1.5
    low = np.minimum(open_, close) - 1.5
    volume = 1_000_000 + (80_000 * np.cos(np.linspace(0.0, 10.0 * np.pi, len(index))))
    pair_close = (trend * 0.98) + (5.5 * np.sin(np.linspace(0.2, 12.2 * np.pi, len(index))))

    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
            "PairClose": pair_close,
        },
        index=index,
    )


@pytest.fixture()
def representative_data() -> pd.DataFrame:
    """Provide deterministic data for all strategy tests."""
    return _representative_data()


@pytest.mark.parametrize(
    "strategy",
    [
        MACrossoverStrategy(),
        RSIMeanReversionStrategy(),
        BollingerBandStrategy(),
        DonchianBreakoutStrategy(),
        MACDTrendStrategy(),
        TrendDeltaStrategy(),
        MomentumStrategy(),
        VWAPReversionStrategy(),
        EngulfingStrategy(),
        PairsMeanReversionStrategy(pair_symbol="PAIR"),
    ],
    ids=lambda strategy: strategy.name,
)
def test_each_strategy_produces_valid_signals(strategy: BaseStrategy, representative_data: pd.DataFrame) -> None:
    """Every strategy should emit aligned action signals without crashing."""
    signals = strategy.generate_signals(representative_data)

    assert signals.index.equals(representative_data.index)
    assert set(signals.dropna().unique()).issubset({-1, 0, 1})
    assert signals.dtype.kind in {"i", "u"}


def test_strategy_serialization_round_trip(representative_data: pd.DataFrame) -> None:
    """Strategies should serialize and deserialize through the base JSON API."""
    original = MACrossoverStrategy(fast_window=10, slow_window=30)
    payload = original.to_json()
    restored = BaseStrategy.from_json(payload)
    signals = restored.generate_signals(representative_data)

    assert isinstance(restored, MACrossoverStrategy)
    assert restored.params == original.params
    assert signals.index.equals(representative_data.index)


def test_pairs_strategy_requires_secondary_series() -> None:
    """The pairs strategy should fail fast when the secondary close is missing."""
    data = _representative_data().drop(columns=["PairClose"])
    strategy = PairsMeanReversionStrategy()

    with pytest.raises(ValueError):
        strategy.generate_signals(data)
