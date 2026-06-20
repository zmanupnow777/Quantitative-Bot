from __future__ import annotations

import numpy as np
import pandas as pd

from bot.reason_derivers import derive_reason


def _flat_then_drop() -> pd.DataFrame:
    # 30 bars flat at 100, then a sharp drop so the last close is far below the lower band
    close = np.concatenate([np.full(30, 100.0), [90.0]])
    return pd.DataFrame({"Close": close})


def _flat_then_spike() -> pd.DataFrame:
    close = np.concatenate([np.full(30, 100.0), [110.0]])
    return pd.DataFrame({"Close": close})


def test_bollinger_long_reason_is_cheap_zone():
    reason = derive_reason(
        "bollinger_band", _flat_then_drop(), "long",
        {"length": 20, "std_dev": 2.0, "band_buffer": 0.0},
    )
    assert reason["zone"] == "cheap"
    assert reason["band_name"] == "lower Bollinger band"
    assert reason["close"] == 90.0
    assert reason["band"] is not None


def test_bollinger_short_reason_is_expensive_zone():
    reason = derive_reason(
        "bollinger_band", _flat_then_spike(), "short",
        {"length": 20, "std_dev": 2.0, "band_buffer": 0.0},
    )
    assert reason["zone"] == "expensive"
    assert reason["band_name"] == "upper Bollinger band"
    assert reason["close"] == 110.0


def test_unknown_strategy_uses_generic_reason():
    reason = derive_reason("some_other_strategy", _flat_then_drop(), "long", {})
    assert reason["rule"] == "strategy_signal"
    assert reason["zone"] is None
    assert reason["close"] == 90.0
