"""Dynamically configured strategy built from composable condition blocks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd

from strategies.base import BaseStrategy
from strategies.conditions import (
    CompositeCondition,
    IndicatorCondition,
    condition_from_dict,
)


class CompositeStrategy(BaseStrategy):
    """A strategy assembled from indicator condition building blocks.

    Instead of hard-coded indicator logic, this strategy evaluates a tree
    of IndicatorCondition / CompositeCondition objects to produce entry
    and exit signals.  Fully JSON-serializable so discovered strategies
    can be saved and reloaded.
    """

    strategy_name: ClassVar[str] = "composite"

    def __init__(
        self,
        name: str = "composite",
        long_entry: CompositeCondition | IndicatorCondition | None = None,
        long_exit: CompositeCondition | IndicatorCondition | None = None,
        short_entry: CompositeCondition | IndicatorCondition | None = None,
        short_exit: CompositeCondition | IndicatorCondition | None = None,
    ) -> None:
        self._name = name
        self._long_entry = long_entry
        self._long_exit = long_exit
        self._short_entry = short_entry
        self._short_exit = short_exit

    @property
    def name(self) -> str:
        return self._name

    @property
    def params(self) -> dict[str, Any]:
        """Collect all tunable parameters from the condition trees."""
        params: dict[str, Any] = {}
        for label, cond in [
            ("le", self._long_entry),
            ("lx", self._long_exit),
            ("se", self._short_entry),
            ("sx", self._short_exit),
        ]:
            if cond is None:
                continue
            if isinstance(cond, CompositeCondition):
                sub = cond.get_all_params()
            else:
                sub = {}
                for k, v in cond.params.items():
                    sub[f"{cond.indicator}_{k}"] = v
                if isinstance(cond.threshold, (int, float)):
                    sub[f"{cond.indicator}_threshold"] = cond.threshold
            params.update({f"{label}_{k}": v for k, v in sub.items()})
        return params

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        """Composite strategies have dynamic params — return empty ranges.

        The research pipeline handles parameter variation via the generator.
        """
        return {}

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        prepared = self.prepare_data(data)

        long_entry = self._long_entry.evaluate(prepared) if self._long_entry else None
        long_exit = self._long_exit.evaluate(prepared) if self._long_exit else None
        short_entry = self._short_entry.evaluate(prepared) if self._short_entry else None
        short_exit = self._short_exit.evaluate(prepared) if self._short_exit else None

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)

    def describe(self) -> str:
        """Return a human-readable description of this composite strategy."""
        parts = [f"Strategy: {self._name}"]
        if self._long_entry:
            parts.append(f"  Long Entry:  {self._long_entry.describe()}")
        if self._long_exit:
            parts.append(f"  Long Exit:   {self._long_exit.describe()}")
        if self._short_entry:
            parts.append(f"  Short Entry: {self._short_entry.describe()}")
        if self._short_exit:
            parts.append(f"  Short Exit:  {self._short_exit.describe()}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "module": self.__class__.__module__,
            "class": "CompositeStrategy",
            "name": self._name,
            "long_entry": self._long_entry.to_dict() if self._long_entry else None,
            "long_exit": self._long_exit.to_dict() if self._long_exit else None,
            "short_entry": self._short_entry.to_dict() if self._short_entry else None,
            "short_exit": self._short_exit.to_dict() if self._short_exit else None,
        }
        return d

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CompositeStrategy:
        return cls(
            name=payload.get("name", "composite"),
            long_entry=condition_from_dict(payload["long_entry"]) if payload.get("long_entry") else None,
            long_exit=condition_from_dict(payload["long_exit"]) if payload.get("long_exit") else None,
            short_entry=condition_from_dict(payload["short_entry"]) if payload.get("short_entry") else None,
            short_exit=condition_from_dict(payload["short_exit"]) if payload.get("short_exit") else None,
        )

    def save(self, path: str | Path) -> None:
        """Save strategy config to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> CompositeStrategy:
        """Load a strategy from a JSON config file."""
        with open(path) as f:
            return cls.from_dict(json.load(f))
