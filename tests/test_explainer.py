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
