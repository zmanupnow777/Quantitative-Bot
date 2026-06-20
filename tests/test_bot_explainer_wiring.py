# tests/test_bot_explainer_wiring.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from bot.brokers.base import BotConfig
from bot.live_strategy import get_live_strategy
from bot.trading_bot import TradingBot


class _Pos:
    symbol = "SPY"
    side = "long"
    qty = 10
    entry_price = 90.0
    unrealized_pnl = 40.0


class _FakeBroker:
    def submit_order(self, order):
        class _R:
            status = "filled"
        return _R()


def test_close_position_threads_exit_reason_and_journals(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # logs/ written under the temp dir
    config = BotConfig(symbol="SPY", mode="sim", timeframe="1d")
    bot = TradingBot(config, get_live_strategy("bollinger"))
    bot.broker = _FakeBroker()

    captured = {}
    real_log = bot.trade_logger.log_position_closed
    monkeypatch.setattr(
        bot.trade_logger, "log_position_closed",
        lambda payload: captured.update(payload) or real_log(payload),
    )

    bot._close_position(_Pos(), price=94.0, exit_reason="take_profit")

    assert captured["exit_reason"] == "take_profit"
    journal = Path(tmp_path) / "logs" / "journal.jsonl"
    assert journal.exists()
    assert "take-profit" in journal.read_text()
