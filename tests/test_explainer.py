from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from bot.explainer import Explainer


def _data() -> pd.DataFrame:
    close = np.concatenate([np.full(30, 100.0), [90.0]])
    return pd.DataFrame({"Close": close})


def _entry_event() -> dict:
    return {
        "symbol": "SPY", "direction": "long", "qty": 10, "price": 90.0,
        "stop_loss": 88.0, "take_profit": 94.0,
    }


def test_explain_entry_writes_both_journal_files(tmp_path: Path):
    ex = Explainer(log_dir=tmp_path)
    narrative, terms = ex.explain_entry(
        _entry_event(), _data(), "bollinger_band",
        {"length": 20, "std_dev": 2.0, "band_buffer": 0.0},
    )
    assert "SPY" in narrative
    assert "Bollinger band" in terms

    jsonl = tmp_path / "journal.jsonl"
    assert jsonl.exists()
    record = json.loads(jsonl.read_text().strip().splitlines()[-1])
    assert record["kind"] == "entry"
    assert record["symbol"] == "SPY"
    assert record["terms"] == terms

    md_files = list((tmp_path / "journal").glob("*.md"))
    assert md_files and "SPY" in md_files[0].read_text()


def test_explain_entry_swallows_errors(tmp_path: Path, monkeypatch):
    ex = Explainer(log_dir=tmp_path)
    # Force the reason deriver to blow up; the call must NOT raise.
    import bot.explainer as mod
    monkeypatch.setattr(mod, "derive_reason", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    narrative, terms = ex.explain_entry(_entry_event(), _data(), "bollinger_band", {})
    assert narrative == ""
    assert terms == []


def test_explain_exit_uses_reason_and_pnl(tmp_path: Path):
    ex = Explainer(log_dir=tmp_path)
    event = {
        "symbol": "SPY", "side": "long", "qty": 10, "entry_price": 90.0,
        "exit_price": 94.0, "pnl": 40.0, "pnl_pct": 0.044, "exit_reason": "take_profit",
    }
    narrative, _terms = ex.explain_exit(event)
    assert "take-profit" in narrative
    assert "profit" in narrative.lower()
    assert "$40" in narrative


def test_explain_exit_loss_wording(tmp_path: Path):
    ex = Explainer(log_dir=tmp_path)
    event = {
        "symbol": "SPY", "side": "long", "qty": 10, "entry_price": 90.0,
        "exit_price": 88.0, "pnl": -20.0, "pnl_pct": -0.022, "exit_reason": "stop_loss",
    }
    narrative, _terms = ex.explain_exit(event)
    assert "stop-loss" in narrative
    assert "loss" in narrative.lower()


def test_explain_risk_event_kill_switch(tmp_path: Path):
    ex = Explainer(log_dir=tmp_path)
    narrative, terms = ex.explain_risk_event({"reason": "daily_loss_limit"})
    assert "kill switch" in narrative.lower() or "halt" in narrative.lower()
    assert narrative


def test_daily_digest_no_trades_says_held(tmp_path: Path):
    ex = Explainer(log_dir=tmp_path)
    narrative, _terms = ex.daily_digest(
        {"portfolio_value": 100000.0, "cash": 100000.0, "daily_pnl": 0.0, "trades_today": 0}
    )
    assert "Held" in narrative or "no action" in narrative.lower()
