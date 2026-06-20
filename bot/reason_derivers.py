"""Phase-1 reason derivation: recompute why a strategy signalled, from price data.

The Explainer re-derives the reason here so strategies stay untouched. Phase 2
(separate spec) will move structured reasons into the strategies themselves.
"""
from __future__ import annotations

import logging
from typing import Callable

import pandas as pd

from strategies.indicator_utils import bollinger_bands

logger = logging.getLogger(__name__)


def derive_bollinger_reason(data: pd.DataFrame, direction: str, params: dict) -> dict:
    """Recompute the Bollinger band the latest close crossed."""
    if data.empty:
        return derive_generic_reason(data, direction, params)
    length = int(params.get("length", 20))
    std_dev = float(params.get("std_dev", 2.0))
    close = float(data["Close"].iloc[-1])
    lower, _middle, upper = bollinger_bands(data["Close"], length, std_dev)

    if direction == "long":
        return {
            "rule": "close<=lower_band",
            "zone": "cheap",
            "close": close,
            "band": float(lower.iloc[-1]),
            "band_name": "lower Bollinger band",
        }
    return {
        "rule": "close>=upper_band",
        "zone": "expensive",
        "close": close,
        "band": float(upper.iloc[-1]),
        "band_name": "upper Bollinger band",
    }


def derive_generic_reason(data: pd.DataFrame, direction: str, params: dict) -> dict:
    """Fallback when no strategy-specific deriver exists."""
    close = float(data["Close"].iloc[-1]) if not data.empty else None
    return {
        "rule": "strategy_signal",
        "zone": None,
        "close": close,
        "band": None,
        "band_name": None,
    }


REASON_DERIVERS: dict[str, Callable[[pd.DataFrame, str, dict], dict]] = {
    "bollinger_band": derive_bollinger_reason,
}


def derive_reason(strategy_name: str, data: pd.DataFrame, direction: str, params: dict) -> dict:
    """Return a structured reason dict for ``strategy_name``'s latest signal."""
    deriver = REASON_DERIVERS.get(strategy_name, derive_generic_reason)
    return deriver(data, direction, params)
