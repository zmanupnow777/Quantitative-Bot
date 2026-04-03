"""Strategy exports for the multi-strategy backtesting project."""

from strategies.base import BaseStrategy
from strategies.bb_rsi_combined import BBRSICombinedStrategy
from strategies.bollinger_band import BollingerBandStrategy
from strategies.cointegration_pairs import CointegrationPairsStrategy
from strategies.cross_sectional_momentum import CrossSectionalMomentumStrategy
from strategies.donchian_breakout import DonchianBreakoutStrategy
from strategies.engulfing import EngulfingStrategy
from strategies.ma_crossover import MACrossoverStrategy
from strategies.macd_trend import MACDTrendStrategy
from strategies.momentum import MomentumStrategy
from strategies.multi_factor import MultiFactorStrategy
from strategies.ou_mean_reversion import OUMeanReversionStrategy
from strategies.overnight_gap import OvernightGapReversionStrategy
from strategies.pairs_mean_reversion import PairsMeanReversionStrategy
from strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from strategies.trend_delta import TrendDeltaStrategy
from strategies.ts_momentum import TimeSeriesMomentumStrategy
from strategies.vrp_regime import VRPRegimeStrategy
from strategies.vwap_reversion import VWAPReversionStrategy


def build_default_strategies(*, pair_symbol: str | None = None) -> list[BaseStrategy]:
    """Return the original Project 2 strategy suite."""
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


def build_research_strategies(*, pair_symbol: str | None = None) -> list[BaseStrategy]:
    """Return the full strategy suite including the new research-grade strategies."""
    base = build_default_strategies(pair_symbol=pair_symbol)
    research = [
        TimeSeriesMomentumStrategy(),
        OvernightGapReversionStrategy(),
        OUMeanReversionStrategy(),
        CointegrationPairsStrategy(pair_symbol=pair_symbol),
        BBRSICombinedStrategy(),
        VRPRegimeStrategy(),
        CrossSectionalMomentumStrategy(),
        MultiFactorStrategy(),
    ]
    return base + research


__all__ = [
    "BaseStrategy",
    "BBRSICombinedStrategy",
    "BollingerBandStrategy",
    "CointegrationPairsStrategy",
    "CrossSectionalMomentumStrategy",
    "DonchianBreakoutStrategy",
    "EngulfingStrategy",
    "MACrossoverStrategy",
    "MACDTrendStrategy",
    "MomentumStrategy",
    "MultiFactorStrategy",
    "OUMeanReversionStrategy",
    "OvernightGapReversionStrategy",
    "PairsMeanReversionStrategy",
    "RSIMeanReversionStrategy",
    "TimeSeriesMomentumStrategy",
    "TrendDeltaStrategy",
    "VRPRegimeStrategy",
    "VWAPReversionStrategy",
    "build_default_strategies",
    "build_research_strategies",
]
