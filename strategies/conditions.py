"""Composable indicator conditions for programmatic strategy generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from strategies.indicator_utils import (
    bollinger_bands,
    ema,
    macd,
    rolling_vwap,
    rsi,
    sma,
)


@dataclass
class IndicatorCondition:
    """A single entry/exit condition comparing an indicator value to a threshold.

    Attributes:
        indicator: Indicator function name ("sma", "ema", "rsi", "bbands", "macd", "vwap").
        condition_type: How to compare ("crosses_above", "crosses_below", "above",
                        "below", "between").
        params: Parameters for the indicator (e.g. {"length": 14}).
        threshold: Numeric threshold or second indicator reference for comparison.
        threshold_params: Parameters for a second indicator if threshold is an indicator name.
    """

    indicator: str
    condition_type: str
    params: dict[str, Any] = field(default_factory=dict)
    threshold: float | str = 0.0
    threshold_params: dict[str, Any] = field(default_factory=dict)

    def evaluate(self, data: pd.DataFrame) -> pd.Series:
        """Evaluate this condition against OHLCV data, returning a boolean Series."""
        indicator_series = _compute_indicator(self.indicator, data, self.params)

        if isinstance(self.threshold, str):
            threshold_series = _compute_indicator(self.threshold, data, self.threshold_params)
        else:
            threshold_series = pd.Series(self.threshold, index=data.index)

        return _apply_comparison(indicator_series, threshold_series, self.condition_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "indicator",
            "indicator": self.indicator,
            "condition_type": self.condition_type,
            "params": self.params,
            "threshold": self.threshold,
            "threshold_params": self.threshold_params,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IndicatorCondition:
        return cls(
            indicator=d["indicator"],
            condition_type=d["condition_type"],
            params=d.get("params", {}),
            threshold=d.get("threshold", 0.0),
            threshold_params=d.get("threshold_params", {}),
        )

    def describe(self) -> str:
        """Return a human-readable description of this condition."""
        param_str = ", ".join(f"{k}={v}" for k, v in self.params.items())
        ind_str = f"{self.indicator}({param_str})" if param_str else self.indicator
        if isinstance(self.threshold, str):
            thr_param_str = ", ".join(f"{k}={v}" for k, v in self.threshold_params.items())
            thr_str = f"{self.threshold}({thr_param_str})" if thr_param_str else self.threshold
        else:
            thr_str = str(self.threshold)
        return f"{ind_str} {self.condition_type} {thr_str}"


@dataclass
class CompositeCondition:
    """Combine multiple conditions with AND/OR logic.

    Attributes:
        operator: "and" or "or".
        conditions: List of IndicatorCondition or nested CompositeCondition.
    """

    operator: str  # "and" or "or"
    conditions: list[IndicatorCondition | CompositeCondition] = field(default_factory=list)

    def evaluate(self, data: pd.DataFrame) -> pd.Series:
        """Recursively evaluate the condition tree, returning a boolean Series."""
        if not self.conditions:
            return pd.Series(False, index=data.index, dtype=bool)

        results = [c.evaluate(data) for c in self.conditions]

        if self.operator == "and":
            combined = results[0]
            for r in results[1:]:
                combined = combined & r
            return combined
        else:  # "or"
            combined = results[0]
            for r in results[1:]:
                combined = combined | r
            return combined

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "composite",
            "operator": self.operator,
            "conditions": [c.to_dict() for c in self.conditions],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CompositeCondition:
        conditions = []
        for c in d.get("conditions", []):
            if c.get("type") == "composite":
                conditions.append(CompositeCondition.from_dict(c))
            else:
                conditions.append(IndicatorCondition.from_dict(c))
        return cls(operator=d["operator"], conditions=conditions)

    def describe(self) -> str:
        parts = [c.describe() for c in self.conditions]
        joiner = f" {self.operator.upper()} "
        return f"({joiner.join(parts)})"

    def get_all_params(self) -> dict[str, Any]:
        """Extract all tunable parameters from the condition tree as a flat dict."""
        params: dict[str, Any] = {}
        for i, cond in enumerate(self.conditions):
            if isinstance(cond, IndicatorCondition):
                for k, v in cond.params.items():
                    params[f"c{i}_{cond.indicator}_{k}"] = v
                if isinstance(cond.threshold, (int, float)):
                    params[f"c{i}_{cond.indicator}_threshold"] = cond.threshold
                for k, v in cond.threshold_params.items():
                    params[f"c{i}_{cond.threshold}_{k}"] = v
            elif isinstance(cond, CompositeCondition):
                sub_params = cond.get_all_params()
                params.update({f"c{i}_{k}": v for k, v in sub_params.items()})
        return params


def condition_from_dict(d: dict[str, Any]) -> IndicatorCondition | CompositeCondition:
    """Deserialize a condition from a dictionary."""
    if d.get("type") == "composite":
        return CompositeCondition.from_dict(d)
    return IndicatorCondition.from_dict(d)


# ---------------------------------------------------------------------------
# Indicator computation helpers
# ---------------------------------------------------------------------------

def _compute_indicator(name: str, data: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
    """Compute a named indicator from OHLCV data."""
    close = data["Close"]

    if name == "sma":
        return sma(close, length=params.get("length", 20))
    elif name == "ema":
        return ema(close, length=params.get("length", 20))
    elif name == "rsi":
        return rsi(close, length=params.get("length", 14))
    elif name == "bbands_lower":
        lower, _, _ = bollinger_bands(close, length=params.get("length", 20), std_dev=params.get("std_dev", 2.0))
        return lower
    elif name == "bbands_middle":
        _, middle, _ = bollinger_bands(close, length=params.get("length", 20), std_dev=params.get("std_dev", 2.0))
        return middle
    elif name == "bbands_upper":
        _, _, upper = bollinger_bands(close, length=params.get("length", 20), std_dev=params.get("std_dev", 2.0))
        return upper
    elif name == "macd_line":
        line, _, _ = macd(close, fast=params.get("fast", 12), slow=params.get("slow", 26), signal=params.get("signal", 9))
        return line
    elif name == "macd_signal":
        _, sig, _ = macd(close, fast=params.get("fast", 12), slow=params.get("slow", 26), signal=params.get("signal", 9))
        return sig
    elif name == "macd_histogram":
        _, _, hist = macd(close, fast=params.get("fast", 12), slow=params.get("slow", 26), signal=params.get("signal", 9))
        return hist
    elif name == "vwap":
        return rolling_vwap(data["High"], data["Low"], close, data["Volume"], length=params.get("length", 20))
    elif name == "close":
        return close
    elif name == "volume":
        return data["Volume"]
    else:
        raise ValueError(f"Unknown indicator: {name}")


def _apply_comparison(
    indicator: pd.Series,
    threshold: pd.Series,
    condition_type: str,
) -> pd.Series:
    """Apply a comparison operation between indicator and threshold series."""
    indicator = indicator.ffill().fillna(0)
    threshold = threshold.ffill().fillna(0)

    if condition_type == "above":
        return indicator > threshold
    elif condition_type == "below":
        return indicator < threshold
    elif condition_type == "crosses_above":
        prev_ind = indicator.shift(1)
        prev_thr = threshold.shift(1)
        return (prev_ind <= prev_thr) & (indicator > threshold)
    elif condition_type == "crosses_below":
        prev_ind = indicator.shift(1)
        prev_thr = threshold.shift(1)
        return (prev_ind >= prev_thr) & (indicator < threshold)
    elif condition_type == "above_eq":
        return indicator >= threshold
    elif condition_type == "below_eq":
        return indicator <= threshold
    else:
        raise ValueError(f"Unknown condition type: {condition_type}")
