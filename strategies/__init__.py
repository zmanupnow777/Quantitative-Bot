"""Strategy exports for the multi-strategy backtesting project."""

from strategies.base import BaseStrategy
from strategies.bollinger_band import BollingerBandStrategy
from strategies.donchian_breakout import DonchianBreakoutStrategy
from strategies.engulfing import EngulfingStrategy
from strategies.ma_crossover import MACrossoverStrategy
from strategies.macd_trend import MACDTrendStrategy
from strategies.momentum import MomentumStrategy
from strategies.pairs_mean_reversion import PairsMeanReversionStrategy
from strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from strategies.trend_delta import TrendDeltaStrategy
from strategies.vwap_reversion import VWAPReversionStrategy


def build_default_strategies(*, pair_symbol: str | None = None) -> list[BaseStrategy]:
    """Return the default Project 2 strategy suite."""
    return [
        MACrossoverStrategy(),
        RSIMeanReversionStrategy(),
        BollingerBandStrategy(),
        DonchianBreakoutStrategy(),
        MACDTrendStrategy(),
        TrendDeltaStrategy(),
        MomentumStrategy(),
        VWAPReversionStrategy(),
        EngulfingStrategy(),
        PairsMeanReversionStrategy(pair_symbol=pair_symbol),
    ]


__all__ = [
    "BaseStrategy",
    "BollingerBandStrategy",
    "DonchianBreakoutStrategy",
    "EngulfingStrategy",
    "MACrossoverStrategy",
    "MACDTrendStrategy",
    "MomentumStrategy",
    "PairsMeanReversionStrategy",
    "RSIMeanReversionStrategy",
    "TrendDeltaStrategy",
    "VWAPReversionStrategy",
    "build_default_strategies",
]
