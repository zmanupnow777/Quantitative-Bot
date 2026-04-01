"""Strategy generator — creates composite strategy candidates programmatically."""

from __future__ import annotations

import itertools
import logging
import random
from typing import Any

from strategies.composite import CompositeStrategy
from strategies.conditions import CompositeCondition, IndicatorCondition

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Indicator catalog: every indicator with its parameter options
# ---------------------------------------------------------------------------

INDICATOR_CATALOG: dict[str, dict[str, list]] = {
    "sma": {"length": [10, 20, 50, 100, 200]},
    "ema": {"length": [10, 20, 50, 100]},
    "rsi": {"length": [7, 14, 21]},
    "bbands_lower": {"length": [10, 20, 30], "std_dev": [1.5, 2.0, 2.5]},
    "bbands_upper": {"length": [10, 20, 30], "std_dev": [1.5, 2.0, 2.5]},
    "bbands_middle": {"length": [10, 20, 30], "std_dev": [2.0]},
    "macd_line": {"fast": [8, 12, 16], "slow": [21, 26, 30], "signal": [7, 9, 11]},
    "macd_signal": {"fast": [12], "slow": [26], "signal": [9]},
    "macd_histogram": {"fast": [8, 12], "slow": [21, 26], "signal": [7, 9]},
    "vwap": {"length": [10, 20, 30]},
}

# ---------------------------------------------------------------------------
# Strategy pattern templates
# ---------------------------------------------------------------------------

PATTERN_TEMPLATES = {
    "trend_following": {
        "description": "Enter on fast indicator crossing above slow, exit on reverse",
        "entry_type": "crosses_above",
        "exit_type": "crosses_below",
        "indicator_pairs": [
            ("sma", "sma"),  # fast SMA crosses slow SMA
            ("ema", "ema"),
            ("ema", "sma"),
            ("macd_line", "macd_signal"),
        ],
    },
    "mean_reversion": {
        "description": "Enter when indicator oversold, exit at mean",
        "entry_combos": [
            {"indicator": "rsi", "condition_type": "below", "threshold": [20, 25, 30]},
            {"indicator": "close", "condition_type": "below", "threshold_indicator": "bbands_lower"},
            {"indicator": "close", "condition_type": "below", "threshold_indicator": "vwap"},
        ],
        "exit_combos": [
            {"indicator": "rsi", "condition_type": "above", "threshold": [45, 50, 55]},
            {"indicator": "close", "condition_type": "above", "threshold_indicator": "bbands_middle"},
            {"indicator": "close", "condition_type": "above", "threshold_indicator": "vwap"},
        ],
    },
    "breakout": {
        "description": "Enter on price breaking above resistance, exit on fall below",
        "entry_combos": [
            {"indicator": "close", "condition_type": "crosses_above", "threshold_indicator": "bbands_upper"},
            {"indicator": "close", "condition_type": "crosses_above", "threshold_indicator": "sma"},
        ],
        "exit_combos": [
            {"indicator": "close", "condition_type": "crosses_below", "threshold_indicator": "sma"},
            {"indicator": "close", "condition_type": "crosses_below", "threshold_indicator": "bbands_middle"},
        ],
    },
    "momentum_confirmation": {
        "description": "Enter when multiple indicators agree on direction",
        "requires_multi": True,
    },
}


class StrategyGenerator:
    """Generate CompositeStrategy candidates from indicator building blocks."""

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def generate_random(self, n: int = 200) -> list[CompositeStrategy]:
        """Generate n random candidate strategies."""
        candidates: list[CompositeStrategy] = []
        patterns = list(PATTERN_TEMPLATES.keys())

        for i in range(n):
            pattern = self.rng.choice(patterns)
            try:
                strategy = self._generate_from_pattern(pattern, i)
                if strategy is not None:
                    candidates.append(strategy)
            except Exception:
                logger.debug("Failed to generate candidate %d", i, exc_info=True)

        logger.info("Generated %d random candidates", len(candidates))
        return candidates

    def generate_exhaustive(self, max_indicators: int = 2) -> list[CompositeStrategy]:
        """Generate strategies by exhaustively combining patterns and parameters."""
        candidates: list[CompositeStrategy] = []
        idx = 0

        # Trend following: all pairs of fast/slow indicators
        for fast_ind, slow_ind in PATTERN_TEMPLATES["trend_following"]["indicator_pairs"]:
            fast_params_list = _param_combinations(INDICATOR_CATALOG[fast_ind])
            slow_params_list = _param_combinations(INDICATOR_CATALOG[slow_ind])

            for fast_params in fast_params_list:
                for slow_params in slow_params_list:
                    # Ensure fast < slow for MA strategies
                    if fast_ind in ("sma", "ema") and slow_ind in ("sma", "ema"):
                        if fast_params.get("length", 0) >= slow_params.get("length", 0):
                            continue

                    long_entry = IndicatorCondition(
                        indicator=fast_ind,
                        condition_type="crosses_above",
                        params=fast_params,
                        threshold=slow_ind,
                        threshold_params=slow_params,
                    )
                    long_exit = IndicatorCondition(
                        indicator=fast_ind,
                        condition_type="crosses_below",
                        params=fast_params,
                        threshold=slow_ind,
                        threshold_params=slow_params,
                    )
                    candidates.append(CompositeStrategy(
                        name=f"trend_{fast_ind}_{slow_ind}_{idx}",
                        long_entry=long_entry,
                        long_exit=long_exit,
                    ))
                    idx += 1

        # Mean reversion: RSI + Bollinger combinations
        for entry_combo in PATTERN_TEMPLATES["mean_reversion"]["entry_combos"]:
            for exit_combo in PATTERN_TEMPLATES["mean_reversion"]["exit_combos"]:
                for entry_cond in _expand_mean_reversion_combo(entry_combo):
                    for exit_cond in _expand_mean_reversion_combo(exit_combo):
                        candidates.append(CompositeStrategy(
                            name=f"meanrev_{idx}",
                            long_entry=entry_cond,
                            long_exit=exit_cond,
                        ))
                        idx += 1

        # Multi-indicator confirmation (2-indicator AND)
        if max_indicators >= 2:
            single_entries = candidates[:min(len(candidates), 30)]
            for a, b in itertools.combinations(range(len(single_entries)), 2):
                sa = single_entries[a]
                sb = single_entries[b]
                if sa._long_entry and sb._long_entry:
                    combined_entry = CompositeCondition(
                        operator="and",
                        conditions=[sa._long_entry, sb._long_entry],
                    )
                    combined_exit = CompositeCondition(
                        operator="or",
                        conditions=[c for c in [sa._long_exit, sb._long_exit] if c is not None],
                    )
                    candidates.append(CompositeStrategy(
                        name=f"multi_{idx}",
                        long_entry=combined_entry,
                        long_exit=combined_exit if combined_exit.conditions else sa._long_exit,
                    ))
                    idx += 1

        logger.info("Generated %d exhaustive candidates", len(candidates))
        return candidates

    def generate_mutations(
        self, winners: list[CompositeStrategy], mutations_per: int = 5,
    ) -> list[CompositeStrategy]:
        """Take winning strategies and mutate their parameters to explore nearby space."""
        candidates: list[CompositeStrategy] = []
        idx = 0

        for strategy in winners:
            for _ in range(mutations_per):
                try:
                    mutated = self._mutate_strategy(strategy, idx)
                    if mutated is not None:
                        candidates.append(mutated)
                        idx += 1
                except Exception:
                    logger.debug("Mutation failed", exc_info=True)

        logger.info("Generated %d mutations from %d winners", len(candidates), len(winners))
        return candidates

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_from_pattern(self, pattern: str, idx: int) -> CompositeStrategy | None:
        """Generate a single strategy from a pattern template."""
        if pattern == "trend_following":
            return self._gen_trend_following(idx)
        elif pattern == "mean_reversion":
            return self._gen_mean_reversion(idx)
        elif pattern == "breakout":
            return self._gen_breakout(idx)
        elif pattern == "momentum_confirmation":
            return self._gen_momentum_confirmation(idx)
        return None

    def _gen_trend_following(self, idx: int) -> CompositeStrategy:
        fast_ind, slow_ind = self.rng.choice(
            PATTERN_TEMPLATES["trend_following"]["indicator_pairs"]
        )
        fast_params = _random_params(INDICATOR_CATALOG[fast_ind], self.rng)
        slow_params = _random_params(INDICATOR_CATALOG[slow_ind], self.rng)

        # Ensure fast < slow for MA
        if fast_ind in ("sma", "ema") and slow_ind in ("sma", "ema"):
            fast_len = fast_params.get("length", 20)
            slow_len = slow_params.get("length", 50)
            if fast_len >= slow_len:
                fast_params["length"] = min(fast_len, slow_len) - 5
                slow_params["length"] = max(fast_len, slow_len) + 5

        long_entry = IndicatorCondition(
            indicator=fast_ind,
            condition_type="crosses_above",
            params=fast_params,
            threshold=slow_ind,
            threshold_params=slow_params,
        )
        long_exit = IndicatorCondition(
            indicator=fast_ind,
            condition_type="crosses_below",
            params=fast_params,
            threshold=slow_ind,
            threshold_params=slow_params,
        )
        return CompositeStrategy(
            name=f"trend_{fast_ind}_{slow_ind}_{idx}",
            long_entry=long_entry,
            long_exit=long_exit,
        )

    def _gen_mean_reversion(self, idx: int) -> CompositeStrategy:
        entry_combo = self.rng.choice(PATTERN_TEMPLATES["mean_reversion"]["entry_combos"])
        exit_combo = self.rng.choice(PATTERN_TEMPLATES["mean_reversion"]["exit_combos"])

        entry_conds = _expand_mean_reversion_combo(entry_combo)
        exit_conds = _expand_mean_reversion_combo(exit_combo)

        long_entry = self.rng.choice(entry_conds) if entry_conds else None
        long_exit = self.rng.choice(exit_conds) if exit_conds else None

        if long_entry is None:
            return None

        return CompositeStrategy(
            name=f"meanrev_{idx}",
            long_entry=long_entry,
            long_exit=long_exit,
        )

    def _gen_breakout(self, idx: int) -> CompositeStrategy:
        entry_combo = self.rng.choice(PATTERN_TEMPLATES["breakout"]["entry_combos"])
        exit_combo = self.rng.choice(PATTERN_TEMPLATES["breakout"]["exit_combos"])

        threshold_ind = entry_combo["threshold_indicator"]
        thr_params = _random_params(INDICATOR_CATALOG.get(threshold_ind, {}), self.rng)

        long_entry = IndicatorCondition(
            indicator=entry_combo["indicator"],
            condition_type=entry_combo["condition_type"],
            params={},
            threshold=threshold_ind,
            threshold_params=thr_params,
        )

        exit_thr_ind = exit_combo["threshold_indicator"]
        exit_thr_params = _random_params(INDICATOR_CATALOG.get(exit_thr_ind, {}), self.rng)
        long_exit = IndicatorCondition(
            indicator=exit_combo["indicator"],
            condition_type=exit_combo["condition_type"],
            params={},
            threshold=exit_thr_ind,
            threshold_params=exit_thr_params,
        )

        return CompositeStrategy(
            name=f"breakout_{idx}",
            long_entry=long_entry,
            long_exit=long_exit,
        )

    def _gen_momentum_confirmation(self, idx: int) -> CompositeStrategy:
        """Generate a multi-indicator confirmation strategy (AND of 2 conditions)."""
        cond1 = self._random_single_condition()
        cond2 = self._random_single_condition()

        long_entry = CompositeCondition(operator="and", conditions=[cond1, cond2])

        # Exit on either condition flipping
        exit1 = self._invert_condition(cond1)
        exit2 = self._invert_condition(cond2)
        long_exit = CompositeCondition(operator="or", conditions=[exit1, exit2])

        return CompositeStrategy(
            name=f"momentum_{idx}",
            long_entry=long_entry,
            long_exit=long_exit,
        )

    def _random_single_condition(self) -> IndicatorCondition:
        """Generate a random single indicator condition."""
        choice = self.rng.choice([
            ("rsi", "below", 30, {}),
            ("rsi", "above", 50, {}),
            ("close", "above", "sma", {"length": self.rng.choice([20, 50, 100, 200])}),
            ("close", "above", "ema", {"length": self.rng.choice([20, 50, 100])}),
            ("macd_histogram", "above", 0.0, {}),
            ("close", "above", "vwap", {"length": self.rng.choice([10, 20, 30])}),
        ])
        ind, cond_type, threshold, thr_params = choice
        ind_params = {}
        if ind == "rsi":
            ind_params = {"length": self.rng.choice([7, 14, 21])}

        return IndicatorCondition(
            indicator=ind,
            condition_type=cond_type,
            params=ind_params,
            threshold=threshold,
            threshold_params=thr_params,
        )

    def _invert_condition(self, cond: IndicatorCondition) -> IndicatorCondition:
        """Create the opposite condition for exit signals."""
        inversion_map = {
            "above": "below",
            "below": "above",
            "crosses_above": "crosses_below",
            "crosses_below": "crosses_above",
            "above_eq": "below_eq",
            "below_eq": "above_eq",
        }
        return IndicatorCondition(
            indicator=cond.indicator,
            condition_type=inversion_map.get(cond.condition_type, "below"),
            params=dict(cond.params),
            threshold=cond.threshold,
            threshold_params=dict(cond.threshold_params),
        )

    def _mutate_strategy(self, strategy: CompositeStrategy, idx: int) -> CompositeStrategy | None:
        """Mutate a single parameter of a strategy."""
        d = strategy.to_dict()
        d["name"] = f"mutant_{strategy.name}_{idx}"

        # Pick a random condition branch to mutate
        branches = ["long_entry", "long_exit", "short_entry", "short_exit"]
        self.rng.shuffle(branches)

        for branch in branches:
            if d.get(branch) is None:
                continue
            mutated = self._mutate_condition_dict(d[branch])
            if mutated:
                d[branch] = mutated
                return CompositeStrategy.from_dict(d)

        return None

    def _mutate_condition_dict(self, cond_dict: dict) -> dict | None:
        """Mutate a parameter in a condition dictionary."""
        if cond_dict.get("type") == "composite":
            if cond_dict.get("conditions"):
                target = self.rng.choice(cond_dict["conditions"])
                mutated = self._mutate_condition_dict(target)
                if mutated:
                    idx = cond_dict["conditions"].index(target)
                    result = dict(cond_dict)
                    result["conditions"] = list(cond_dict["conditions"])
                    result["conditions"][idx] = mutated
                    return result
            return None

        result = dict(cond_dict)
        params = dict(result.get("params", {}))

        # Mutate a numeric parameter by +/- 20-50%
        numeric_keys = [k for k, v in params.items() if isinstance(v, (int, float))]
        if numeric_keys:
            key = self.rng.choice(numeric_keys)
            factor = self.rng.uniform(0.5, 1.5)
            old_val = params[key]
            if isinstance(old_val, int):
                params[key] = max(2, int(old_val * factor))
            else:
                params[key] = round(old_val * factor, 4)
            result["params"] = params
            return result

        # Mutate threshold if numeric
        if isinstance(result.get("threshold"), (int, float)):
            factor = self.rng.uniform(0.7, 1.3)
            result["threshold"] = round(result["threshold"] * factor, 4)
            return result

        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _random_params(catalog: dict[str, list], rng: random.Random) -> dict[str, Any]:
    """Pick a random value for each parameter from the catalog."""
    return {k: rng.choice(v) for k, v in catalog.items()}


def _param_combinations(catalog: dict[str, list]) -> list[dict[str, Any]]:
    """Generate all combinations of parameter values."""
    if not catalog:
        return [{}]
    keys = list(catalog.keys())
    values = [catalog[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def _expand_mean_reversion_combo(combo: dict) -> list[IndicatorCondition]:
    """Expand a mean reversion combo template into concrete IndicatorConditions."""
    conditions = []
    indicator = combo["indicator"]
    condition_type = combo["condition_type"]
    ind_params = {}

    if indicator == "rsi":
        for length in INDICATOR_CATALOG["rsi"]["length"]:
            ind_params = {"length": length}
            for thr in combo.get("threshold", [30]):
                conditions.append(IndicatorCondition(
                    indicator=indicator,
                    condition_type=condition_type,
                    params=dict(ind_params),
                    threshold=thr,
                ))
    elif "threshold_indicator" in combo:
        thr_ind = combo["threshold_indicator"]
        for thr_params in _param_combinations(INDICATOR_CATALOG.get(thr_ind, {})):
            conditions.append(IndicatorCondition(
                indicator=indicator,
                condition_type=condition_type,
                params={},
                threshold=thr_ind,
                threshold_params=thr_params,
            ))
    return conditions
