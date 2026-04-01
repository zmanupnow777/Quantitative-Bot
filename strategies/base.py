"""Shared interfaces and helpers for reusable trading strategies."""

from __future__ import annotations

import importlib
import json
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import pandas as pd


class BaseStrategy(ABC):
    """Abstract base class for signal-generating trading strategies."""

    strategy_name: ClassVar[str] = "base_strategy"

    @property
    def name(self) -> str:
        """Return a stable strategy name for reporting and serialization."""
        return self.strategy_name

    @property
    def params(self) -> dict[str, Any]:
        """Return the strategy parameters as a serializable dictionary."""
        return {
            key: value
            for key, value in self.__dict__.items()
            if not key.startswith("_")
        }

    @property
    def trade_price_column(self) -> str:
        """Return the column used by the backtest engine for fills."""
        return "Close"

    def prepare_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Return a normalized dataframe before signal generation."""
        frame = data.copy()
        frame.index = pd.to_datetime(frame.index)
        return frame.sort_index()

    @classmethod
    @abstractmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Return candidate parameter ranges for optimization or sweeps."""

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return an action series aligned to `data.index` using -1, 0, and 1."""

    def get_trade_price_series(self, data: pd.DataFrame) -> pd.Series:
        """Return the price series used for position fills and valuation."""
        if self.trade_price_column not in data.columns:
            raise ValueError(
                f"{self.name} requires '{self.trade_price_column}' in the prepared data."
            )

        price_series = pd.to_numeric(data[self.trade_price_column], errors="coerce")
        if price_series.isna().all():
            raise ValueError(f"{self.name} produced an empty trade price series.")
        return price_series

    def to_dict(self) -> dict[str, Any]:
        """Serialize the strategy configuration into a plain dictionary."""
        return {
            "module": self.__class__.__module__,
            "class": self.__class__.__name__,
            "name": self.name,
            "params": self.params,
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the strategy configuration to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BaseStrategy":
        """Reconstruct a strategy instance from a dictionary payload."""
        if cls is BaseStrategy:
            module_name = payload["module"]
            class_name = payload["class"]
            module = importlib.import_module(module_name)
            strategy_cls = getattr(module, class_name)
        else:
            strategy_cls = cls

        if not issubclass(strategy_cls, BaseStrategy):
            raise TypeError(f"{strategy_cls!r} is not a BaseStrategy subclass.")

        params = payload.get("params", {})
        return strategy_cls(**params)

    @classmethod
    def from_json(cls, payload: str) -> "BaseStrategy":
        """Reconstruct a strategy instance from a JSON payload."""
        return cls.from_dict(json.loads(payload))

    @staticmethod
    def require_columns(data: pd.DataFrame, *columns: str) -> None:
        """Validate that a dataframe contains the expected columns."""
        missing = [column for column in columns if column not in data.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

    @staticmethod
    def _bool_series(data: pd.DataFrame, values: pd.Series | None) -> pd.Series:
        """Return a cleaned boolean series aligned to `data.index`."""
        if values is None:
            return pd.Series(False, index=data.index, dtype=bool)

        series = pd.Series(values, index=data.index)
        return series.reindex(data.index).fillna(False).astype(bool)

    def build_signals(
        self,
        data: pd.DataFrame,
        *,
        long_entry: pd.Series | None = None,
        long_exit: pd.Series | None = None,
        short_entry: pd.Series | None = None,
        short_exit: pd.Series | None = None,
    ) -> pd.Series:
        """Create stateful action signals from entry and exit conditions."""
        long_entry_series = self._bool_series(data, long_entry)
        long_exit_series = self._bool_series(data, long_exit)
        short_entry_series = self._bool_series(data, short_entry)
        short_exit_series = self._bool_series(data, short_exit)

        signals = pd.Series(0, index=data.index, dtype=int)
        position = 0

        for idx in range(len(data.index)):
            if position == 0:
                if long_entry_series.iat[idx]:
                    signals.iat[idx] = 1
                    position = 1
                elif short_entry_series.iat[idx]:
                    signals.iat[idx] = -1
                    position = -1
            elif position == 1:
                if long_exit_series.iat[idx]:
                    signals.iat[idx] = -1
                    position = 0
            else:
                if short_exit_series.iat[idx]:
                    signals.iat[idx] = 1
                    position = 0

        return signals.rename("signal")

    def finalize_signals(self, data: pd.DataFrame, signals: pd.Series) -> pd.Series:
        """Normalize a raw signal series to integer actions."""
        series = pd.Series(signals, index=data.index)
        series = series.reindex(data.index).fillna(0).clip(-1, 1).astype(int)
        return series.rename("signal")
