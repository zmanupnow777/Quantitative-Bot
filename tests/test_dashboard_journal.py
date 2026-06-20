# tests/test_dashboard_journal.py
from __future__ import annotations

import json
from pathlib import Path

import bot.dashboard_data as dd


def test_load_journal_returns_newest_first(tmp_path: Path, monkeypatch):
    jsonl = tmp_path / "journal.jsonl"
    rows = [
        {"timestamp": "2026-06-20T10:00:00", "kind": "entry", "symbol": "SPY", "narrative": "first", "terms": []},
        {"timestamp": "2026-06-20T11:00:00", "kind": "exit", "symbol": "SPY", "narrative": "second", "terms": []},
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(dd, "JOURNAL_JSONL", jsonl)

    out = dd.load_journal(limit=10)
    assert [r["narrative"] for r in out] == ["second", "first"]


def test_load_journal_missing_file_returns_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(dd, "JOURNAL_JSONL", tmp_path / "nope.jsonl")
    assert dd.load_journal() == []


def test_load_glossary_has_terms():
    assert "Bollinger band" in dd.load_glossary()
