# Explainer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a plain-English narrator that turns each bot decision into a journal entry plus linked glossary terms, surfaced in the Streamlit dashboard, as an isolated module that can never break trading.

**Architecture:** A new self-contained `bot/explainer.py` consumes the structured event dicts already produced at each decision point and the current price window, derives a human-readable narrative via deterministic templates, links glossary terms, and appends to `logs/journal/YYYY-MM-DD.md` (human) + `logs/journal.jsonl` (dashboard). Strategies and `trade_logger.py` are untouched; `trading_bot.py` gets one small change to thread an exit reason and call the Explainer beside the existing logger. Every Explainer call swallows its own exceptions so the trading loop is never affected.

**Tech Stack:** Python 3.12, pandas, existing `strategies/indicator_utils.bollinger_bands`, existing `config.settings`, Streamlit (dashboard), pytest.

## Global Constraints

- Python 3.10+ syntax, `from __future__ import annotations` at top of every new module.
- Type hints and docstrings on all public functions/methods (project convention).
- Library code uses the `logging` module, never `print`.
- The Explainer is non-critical: no Explainer code path may raise into the trading loop.
- Journal files live under `logs/` (`config.settings.LOGS_DIR`): `logs/journal/<date>.md` and `logs/journal.jsonl`. No SQLite.
- Strategy display name used as the deriver key is the strategy's `.name` property, which returns `strategy_name` (e.g. `"bollinger_band"`).
- `bollinger_bands(series, length, std_dev)` returns `(lower, middle, upper)` as a 3-tuple of `pd.Series`.
- Tests go in `tests/`, run with `.\.venv\Scripts\python.exe -m pytest` (Windows) / `./.venv/Scripts/python.exe -m pytest` (bash).

---

### Task 1: Glossary module

**Files:**
- Create: `bot/glossary.py`
- Test: `tests/test_glossary.py`

**Interfaces:**
- Produces: `GLOSSARY: dict[str, str]` (canonical term -> beginner definition); `detect_terms(text: str) -> list[str]` (canonical terms present in `text`, case-insensitive whole-word, deduped, in order of first appearance).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_glossary.py
from __future__ import annotations

from bot.glossary import GLOSSARY, detect_terms


def test_glossary_has_core_terms():
    for term in ["Bollinger band", "Sharpe ratio", "stop-loss", "kill switch"]:
        assert term in GLOSSARY
        assert GLOSSARY[term].strip()


def test_detect_terms_finds_terms_case_insensitive_in_order():
    text = "Price hit the lower BOLLINGER BAND, so the stop-loss was set."
    assert detect_terms(text) == ["Bollinger band", "stop-loss"]


def test_detect_terms_whole_word_only_and_deduped():
    # "averages" must not match the term "average"; repeated term appears once
    text = "A moving average crossed; the moving average held."
    assert detect_terms(text) == ["moving average"]


def test_detect_terms_returns_empty_for_no_match():
    assert detect_terms("nothing relevant here") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_glossary.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.glossary'`

- [ ] **Step 3: Write minimal implementation**

```python
# bot/glossary.py
"""Beginner-friendly glossary of trading terms used in the journal."""
from __future__ import annotations

import re

GLOSSARY: dict[str, str] = {
    "Bollinger band": "A price envelope a set number of standard deviations above and below a moving average. Touching the lower band is often read as 'unusually cheap', the upper band as 'unusually expensive'.",
    "moving average": "The average closing price over the last N bars, used to smooth out noise and show the trend.",
    "standard deviation": "A measure of how spread out prices are. Bigger standard deviation means more volatile.",
    "Sharpe ratio": "Return earned per unit of risk. Higher is better; below 1 is weak, above 1 is decent for a simple strategy.",
    "drawdown": "How far the account has fallen from its previous peak. Max drawdown is the worst such drop.",
    "stop-loss": "A pre-set exit price that caps the loss on a trade if it moves against you.",
    "take-profit": "A pre-set exit price that locks in profit once a trade moves in your favour.",
    "trailing stop": "A stop-loss that ratchets up as the trade gains, protecting profit without capping upside.",
    "bracket order": "An order that ships with both a stop-loss and a take-profit attached, so the exit is automatic.",
    "position sizing": "Deciding how many shares to buy so a single trade only risks a small slice of the account.",
    "risk per trade": "The fraction of the account you allow yourself to lose on one trade (here, 2%).",
    "kill switch": "A hard stop that halts all trading, e.g. when the daily loss limit is breached.",
    "mean reversion": "The idea that price tends to snap back toward its average after stretching too far.",
    "slippage": "The difference between the price you expected and the price you actually got.",
    "commission": "The broker's fee per trade.",
    "paper trading": "Trading with fake money against live prices, to validate a strategy before risking real capital.",
    "equity curve": "A line chart of account value over time.",
    "long": "A bet that price will rise (you buy first, sell later).",
    "short": "A bet that price will fall (you sell first, buy back later).",
}


def detect_terms(text: str) -> list[str]:
    """Return canonical glossary terms appearing in ``text``.

    Matching is case-insensitive and whole-word. Terms are deduplicated and
    returned in order of first appearance.
    """
    found: list[tuple[int, str]] = []
    lowered = text.lower()
    for term in GLOSSARY:
        pattern = r"\b" + re.escape(term.lower()) + r"\b"
        match = re.search(pattern, lowered)
        if match:
            found.append((match.start(), term))
    found.sort(key=lambda pair: pair[0])
    return [term for _, term in found]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_glossary.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/glossary.py tests/test_glossary.py
git commit -m "feat: add glossary module with term detection"
```

---

### Task 2: Bollinger reason deriver + registry

**Files:**
- Create: `bot/reason_derivers.py`
- Test: `tests/test_reason_derivers.py`

**Interfaces:**
- Consumes: `strategies.indicator_utils.bollinger_bands`.
- Produces: `derive_reason(strategy_name: str, data: pd.DataFrame, direction: str, params: dict) -> dict`. Returned dict keys: `rule: str`, `zone: str | None` (`"cheap"`/`"expensive"`/`None`), `close: float | None`, `band: float | None`, `band_name: str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reason_derivers.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reason_derivers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.reason_derivers'`

- [ ] **Step 3: Write minimal implementation**

```python
# bot/reason_derivers.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_reason_derivers.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/reason_derivers.py tests/test_reason_derivers.py
git commit -m "feat: add bollinger reason deriver with generic fallback"
```

---

### Task 3: Explainer core — journal sink, error swallowing, explain_entry

**Files:**
- Create: `bot/explainer.py`
- Test: `tests/test_explainer.py`

**Interfaces:**
- Consumes: `bot.glossary.detect_terms`, `bot.reason_derivers.derive_reason`.
- Produces: class `Explainer(log_dir: str | Path = "logs")` with:
  - `explain_entry(event: dict, data: pd.DataFrame, strategy_name: str, params: dict) -> tuple[str, list[str]]`
  - `_emit(kind: str, symbol: str, narrative: str) -> list[str]` (internal: detect terms, append md + jsonl, return terms)
  - Entry `event` keys consumed: `symbol`, `direction`, `qty`, `price`, `stop_loss`, `take_profit`.
- Journal outputs: `<log_dir>/journal/<date>.md` and `<log_dir>/journal.jsonl` (one JSON object per line: `{timestamp, kind, symbol, narrative, terms}`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_explainer.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_explainer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.explainer'`

- [ ] **Step 3: Write minimal implementation**

```python
# bot/explainer.py
"""Plain-English narrator for bot decisions. Non-critical: never raises into the loop."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from bot.glossary import detect_terms
from bot.reason_derivers import derive_reason

logger = logging.getLogger(__name__)


class Explainer:
    """Writes a human journal (markdown) and a structured feed (jsonl)."""

    def __init__(self, log_dir: str | Path = "logs") -> None:
        self.log_dir = Path(log_dir)
        self.journal_dir = self.log_dir / "journal"
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.log_dir / "journal.jsonl"

    def explain_entry(
        self, event: dict, data: pd.DataFrame, strategy_name: str, params: dict
    ) -> tuple[str, list[str]]:
        """Narrate a position entry. Returns (narrative, glossary_terms)."""
        try:
            direction = event.get("direction", "long")
            qty = event.get("qty", 0)
            symbol = event.get("symbol", "?")
            price = float(event.get("price", 0.0))
            notional = qty * price
            reason = derive_reason(strategy_name, data, direction, params)

            if reason["zone"] == "cheap":
                why = f"price ${reason['close']:,.2f} dipped to the {reason['band_name']} (${reason['band']:,.2f}) — an unusually cheap zone"
            elif reason["zone"] == "expensive":
                why = f"price ${reason['close']:,.2f} stretched to the {reason['band_name']} (${reason['band']:,.2f}) — an unusually expensive zone"
            else:
                why = f"the {strategy_name} strategy signalled a {direction} entry"

            verb = "Bought" if direction == "long" else "Shorted"
            narrative = (
                f"{verb} {qty} {symbol} @ ${price:,.2f} (about ${notional:,.0f}); {why}. "
                f"Stop-loss ${event.get('stop_loss', 0):,.2f}, take-profit ${event.get('take_profit', 0):,.2f}. "
                f"This is a mean reversion bet sized by the risk per trade rule."
            )
            return narrative, self._emit("entry", symbol, narrative)
        except Exception:
            logger.exception("Explainer.explain_entry failed; trading continues")
            return "", []

    def _emit(self, kind: str, symbol: str, narrative: str) -> list[str]:
        """Detect glossary terms, append to md + jsonl. Best-effort."""
        terms = detect_terms(narrative)
        try:
            now = datetime.now()
            md_path = self.journal_dir / f"{now.date()}.md"
            with md_path.open("a", encoding="utf-8") as f:
                f.write(f"### {now.strftime('%H:%M:%S')} — {kind} {symbol}\n\n{narrative}\n\n")
            record = {
                "timestamp": now.isoformat(),
                "kind": kind,
                "symbol": symbol,
                "narrative": narrative,
                "terms": terms,
            }
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            logger.exception("Explainer._emit failed to write journal; trading continues")
        return terms
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_explainer.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/explainer.py tests/test_explainer.py
git commit -m "feat: add Explainer core with entry narration and journal sink"
```

---

### Task 4: Explainer exit, risk-event, and daily-digest narration

**Files:**
- Modify: `bot/explainer.py`
- Test: `tests/test_explainer.py`

**Interfaces:**
- Produces (added to `Explainer`):
  - `explain_exit(event: dict) -> tuple[str, list[str]]`. Consumes keys: `symbol`, `side`, `qty`, `entry_price`, `exit_price`, `pnl`, `pnl_pct`, `exit_reason`.
  - `explain_risk_event(event: dict) -> tuple[str, list[str]]`. Consumes key: `reason` (plus optional `symbol`).
  - `daily_digest(account_info: dict) -> tuple[str, list[str]]`. Consumes keys: `portfolio_value`, `cash`, `daily_pnl`, optional `trades_today`.
- `exit_reason` vocabulary: `"stop_loss"`, `"take_profit"`, `"strategy"`, `"kill_switch"`, or any other string (shown verbatim).

- [ ] **Step 1: Write the failing test (append to tests/test_explainer.py)**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_explainer.py -k "exit or risk or digest" -v`
Expected: FAIL with `AttributeError: 'Explainer' object has no attribute 'explain_exit'`

- [ ] **Step 3: Add the methods to bot/explainer.py**

Add these methods inside the `Explainer` class (after `explain_entry`):

```python
    _EXIT_PHRASES = {
        "stop_loss": "hit its stop-loss",
        "take_profit": "hit its take-profit target",
        "strategy": "the strategy signalled an exit",
        "kill_switch": "the kill switch fired",
    }

    def explain_exit(self, event: dict) -> tuple[str, list[str]]:
        """Narrate a position close. Returns (narrative, glossary_terms)."""
        try:
            symbol = event.get("symbol", "?")
            qty = event.get("qty", 0)
            exit_price = float(event.get("exit_price", 0.0))
            pnl = float(event.get("pnl", 0.0))
            pnl_pct = float(event.get("pnl_pct", 0.0))
            reason = event.get("exit_reason", "strategy")
            phrase = self._EXIT_PHRASES.get(reason, f"a risk rule fired ({reason})")
            outcome = "a profit" if pnl >= 0 else "a loss"
            side = event.get("side", "long")
            verb = "Sold" if side == "long" else "Covered"
            narrative = (
                f"{verb} {qty} {symbol} @ ${exit_price:,.2f} because it {phrase}. "
                f"Booked {outcome} of ${pnl:,.2f} ({pnl_pct:.2%})."
            )
            return narrative, self._emit("exit", symbol, narrative)
        except Exception:
            logger.exception("Explainer.explain_exit failed; trading continues")
            return "", []

    _RISK_PHRASES = {
        "daily_loss_limit": "Daily loss limit breached — the kill switch halted trading for the day.",
        "max_positions": "Max open positions reached — no new trade was opened.",
        "max_daily_trades": "Daily trade cap reached — no new trade was opened.",
        "position_size_zero": "Risk sizing came out to zero shares — trade skipped.",
    }

    def explain_risk_event(self, event: dict) -> tuple[str, list[str]]:
        """Narrate a risk veto / kill-switch / bracket trigger."""
        try:
            reason = event.get("reason", "unknown")
            symbol = event.get("symbol", "")
            narrative = self._RISK_PHRASES.get(reason, f"Risk manager event: {reason}.")
            return narrative, self._emit("risk", symbol or "-", narrative)
        except Exception:
            logger.exception("Explainer.explain_risk_event failed; trading continues")
            return "", []

    def daily_digest(self, account_info: dict) -> tuple[str, list[str]]:
        """Narrate an end-of-day summary."""
        try:
            value = float(account_info.get("portfolio_value", 0.0))
            cash = float(account_info.get("cash", 0.0))
            pnl = float(account_info.get("daily_pnl", 0.0))
            trades = int(account_info.get("trades_today", 0))
            head = "Held — no action today. " if trades == 0 else f"{trades} trade(s) today. "
            narrative = (
                f"{head}End of day: portfolio ${value:,.2f}, cash ${cash:,.2f}, "
                f"daily PnL ${pnl:,.2f}."
            )
            return narrative, self._emit("digest", "-", narrative)
        except Exception:
            logger.exception("Explainer.daily_digest failed; trading continues")
            return "", []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_explainer.py -v`
Expected: PASS (all explainer tests pass)

- [ ] **Step 5: Commit**

```bash
git add bot/explainer.py tests/test_explainer.py
git commit -m "feat: add exit, risk-event and daily-digest narration"
```

---

### Task 5: Wire Explainer into the trading loop + thread exit reason

**Files:**
- Modify: `bot/trading_bot.py`
- Test: `tests/test_bot_explainer_wiring.py`

**Interfaces:**
- Consumes: `bot.explainer.Explainer`.
- Changes to `TradingBot`:
  - `__init__`: add `self.explainer = Explainer(log_dir="logs")`.
  - `_open_position(self, direction, price, available_cash)` -> `_open_position(self, direction, price, available_cash, data)`; after `self.trade_logger.log_position_opened(payload)` call `self.explainer.explain_entry(payload, data, self.strategy.name, self.strategy.params)`.
  - `_close_position(self, position, price)` -> `_close_position(self, position, price, exit_reason)`; include `"exit_reason": exit_reason` in the close payload, and after `self.trade_logger.log_position_closed(payload)` call `self.explainer.explain_exit(payload)`.
  - Call sites in `_run_cycle`: risk exit passes `exit_reason="stop_loss"`/`"take_profit"`/`f"risk:{risk_reason}"` (see mapping below); strategy exit passes `exit_reason="strategy"`; entry passes `data`.
  - After each existing `self.trade_logger.log_risk_event({...})`, add `self.explainer.explain_risk_event({...})` with the same dict.
  - In `_on_stop`, after `write_daily_summary`, call `self.explainer.daily_digest(account)`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_bot_explainer_wiring.py -v`
Expected: FAIL with `TypeError: _close_position() got an unexpected keyword argument 'exit_reason'`

- [ ] **Step 3a: Add the Explainer import and instance**

In `bot/trading_bot.py`, add to the imports near the other `from bot.` lines:

```python
from bot.explainer import Explainer
```

In `TradingBot.__init__`, after `self.trade_logger = TradeLogger(log_dir="logs")`, add:

```python
        self.explainer = Explainer(log_dir="logs")
```

- [ ] **Step 3b: Thread exit_reason through the exit call sites in `_run_cycle`**

Replace the risk/strategy exit block (currently the `if risk_reason:` / `elif self.strategy.should_exit(...)` block) with:

```python
            # Check risk-based exit
            risk_reason = self.risk_manager.should_close_on_risk(pos)
            if risk_reason:
                logger.info("Risk exit: %s", risk_reason)
                self.trade_logger.log_risk_event({"reason": risk_reason, "symbol": pos.symbol})
                self.explainer.explain_risk_event({"reason": risk_reason, "symbol": pos.symbol})
                if "stop" in risk_reason.lower():
                    exit_reason = "stop_loss"
                elif "take" in risk_reason.lower() or "profit" in risk_reason.lower():
                    exit_reason = "take_profit"
                else:
                    exit_reason = f"risk:{risk_reason}"
                self._close_position(pos, current_price, exit_reason)
            elif self.strategy.should_exit(data, pos):
                logger.info("Strategy exit signal for %s", pos.symbol)
                self._close_position(pos, current_price, "strategy")
```

- [ ] **Step 3c: Pass `data` into entry and update the entry call**

In `_run_cycle`, change the entry execution line from `self._open_position(direction, current_price, account["cash"])` to:

```python
                self._open_position(direction, current_price, account["cash"], data)
```

- [ ] **Step 3d: Update `_open_position` signature and add the explainer call**

Change the signature to `def _open_position(self, direction: str, price: float, available_cash: float, data) -> None:` and, immediately after the existing `self.trade_logger.log_position_opened({...})` call, capture its payload in a variable and pass it to the explainer. Replace:

```python
            self.trade_logger.log_position_opened({
                "symbol": self.config.symbol,
                "direction": direction,
                "qty": qty,
                "price": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            })
```

with:

```python
            opened_payload = {
                "symbol": self.config.symbol,
                "direction": direction,
                "qty": qty,
                "price": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
            self.trade_logger.log_position_opened(opened_payload)
            self.explainer.explain_entry(opened_payload, data, self.strategy.name, self.strategy.params)
```

- [ ] **Step 3e: Update `_close_position` signature and payload**

Change the signature to `def _close_position(self, position, price: float, exit_reason: str = "strategy") -> None:` and replace the existing close payload + log call:

```python
        self.trade_logger.log_position_closed({
            "symbol": position.symbol,
            "side": position.side,
            "qty": position.qty,
            "entry_price": position.entry_price,
            "exit_price": price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        })
```

with:

```python
        closed_payload = {
            "symbol": position.symbol,
            "side": position.side,
            "qty": position.qty,
            "entry_price": position.entry_price,
            "exit_price": price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "exit_reason": exit_reason,
        }
        self.trade_logger.log_position_closed(closed_payload)
        self.explainer.explain_exit(closed_payload)
```

- [ ] **Step 3f: Add explainer call to the bracket-trigger risk events and daily digest**

For the two existing `self.trade_logger.log_risk_event({...})` bracket calls in `_run_cycle` (the `"bracket_order_triggered_by_monitor"` lambda and the `"bracket_order_triggered"` block) and the daily-loss-limit block, add a matching `self.explainer.explain_risk_event(<same dict>)` immediately after each. In `_on_stop`, after `self.trade_logger.write_daily_summary(account)`, add:

```python
        self.explainer.daily_digest(account)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_bot_explainer_wiring.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: PASS (all prior tests + new ones)

- [ ] **Step 6: Commit**

```bash
git add bot/trading_bot.py tests/test_bot_explainer_wiring.py
git commit -m "feat: wire Explainer into trading loop and thread exit reasons"
```

---

### Task 6: Dashboard Journal + Glossary panel

**Files:**
- Modify: `bot/dashboard_data.py`
- Modify: `bot/dashboard.py`
- Test: `tests/test_dashboard_journal.py`

**Interfaces:**
- Consumes: `bot.glossary.GLOSSARY`, `logs/journal.jsonl`.
- Produces (in `dashboard_data.py`): `load_journal(limit: int = 50) -> list[dict]` (most-recent-first journal records); `load_glossary() -> dict[str, str]`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_journal.py -v`
Expected: FAIL with `AttributeError: module 'bot.dashboard_data' has no attribute 'JOURNAL_JSONL'` (or `load_journal`)

- [ ] **Step 3a: Add the data functions to bot/dashboard_data.py**

Near the other path constants (after `TRADES_JSONL = LOGS_DIR / "trades.jsonl"`), add:

```python
JOURNAL_JSONL = LOGS_DIR / "journal.jsonl"
```

At the end of the file add:

```python
def load_journal(limit: int = 50) -> list[dict]:
    """Return the most recent journal records (newest first), or [] if missing."""
    if not JOURNAL_JSONL.exists():
        return []
    records: list[dict] = []
    with JOURNAL_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    records.reverse()
    return records[:limit]


def load_glossary() -> dict[str, str]:
    """Return the glossary term -> definition map."""
    from bot.glossary import GLOSSARY
    return dict(GLOSSARY)
```

- [ ] **Step 3b: Run the data-layer tests (UI not yet added)**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_journal.py -v`
Expected: PASS (3 passed)

- [ ] **Step 3c: Add the Journal + Glossary UI to bot/dashboard.py**

After the existing data-loading block (after `kill = dd.get_kill_switch_status(events)`), add:

```python
journal_entries = dd.load_journal(limit=50)
glossary = dd.load_glossary()
```

Near the bottom of the render (after the existing panels), add:

```python
st.markdown("---")
st.subheader("\U0001F4D3 Journal")
if not journal_entries:
    st.caption("No journal entries yet — the bot will explain each decision here.")
for entry in journal_entries:
    ts = entry.get("timestamp", "")[:19].replace("T", " ")
    st.markdown(f"**{ts} — {entry.get('kind','')} {entry.get('symbol','')}**")
    st.write(entry.get("narrative", ""))
    terms = entry.get("terms") or []
    if terms:
        st.caption("Terms: " + ", ".join(terms))

with st.expander("\U0001F4D6 Glossary"):
    for term, definition in glossary.items():
        st.markdown(f"**{term}** — {definition}")
```

- [ ] **Step 4: Verify the dashboard imports cleanly**

Run: `./.venv/Scripts/python.exe -c "import bot.dashboard_data as dd; print(len(dd.load_glossary()), 'terms'); print(dd.load_journal()[:1])"`
Expected: prints the glossary term count and `[]` (or recent entries) with no traceback.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add bot/dashboard_data.py bot/dashboard.py tests/test_dashboard_journal.py
git commit -m "feat: add Journal and Glossary panels to the dashboard"
```

---

## Manual verification (after all tasks)

- [ ] Run a sim session and confirm the journal is written and readable:

```bash
./.venv/Scripts/python.exe run_sim_bot.py --strategy bollinger --symbol SPY --cycles 5
cat logs/journal.jsonl
```

- [ ] Launch the dashboard and eyeball the Journal + Glossary:

```bash
./.venv/Scripts/python.exe -m streamlit run bot/dashboard.py
```
