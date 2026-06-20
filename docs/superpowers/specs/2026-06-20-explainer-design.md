# Explainer — Design Spec

> Status: Approved 2026-06-20. First spec in the "Quant Analysis Bot" tailoring.
> Scope: the **Explainer** pillar only (plain-English journal + glossary, surfaced in the dashboard).
> Companion strategy decision (separate): deploy `bollinger_band` (length=20, std_dev=2.0) for the
> 30-day paper run — chosen for walk-forward robustness (OOS Sharpe 0.93 > IS 0.89, the only
> non-overfit-flagged candidate) and smoothest parameter surface.

## One-line purpose

A plain-English narrator that turns every bot decision into a journal entry plus linked glossary
terms, surfaced in the dashboard — built as one isolated module that can never break trading.

## Context

The project already has the brokers (sim/paper/alpaca), risk manager, backtester, strategies, and a
Streamlit dashboard. The Explainer is the "make it understandable" pillar from the design and is 0%
built. This spec covers only the Explainer; SQLite migration, structured strategy reasons, the
autoresearch loop, the Claude-polish job, and position-sizing rework are each their own later spec.

### Decisions locked during brainstorming

- **Source of the "why":** Phase 1 — the Explainer **re-derives** the reason from the price window +
  which strategy fired (only `bollinger_band` matters for the upcoming paper run). Phase 2 (later
  spec) — strategies emit their own structured reasons. Strategies stay untouched in this spec.
- **Prose engine:** deterministic **templates in-loop now**; a non-blocking **Claude-polish
  background job is a later add-on** (this spec stubs its interface only).
- **Journaling scope:** actionable events only (entries, exits with reason, risk vetoes, kill-switch)
  — not every "no signal" cycle.
- **Storage:** flat files (`logs/journal/*.md` + `logs/journal.jsonl`). No SQLite in this spec.

## Architecture

A new self-contained `bot/explainer.py`. It consumes the **same structured event dicts already
flowing through the trading loop** (the dicts passed to `TradeLogger.log_signal`,
`log_position_opened`, `log_position_closed`, `log_risk_event`) plus the current price window
(`pandas.DataFrame`). It writes two outputs:

1. `logs/journal/YYYY-MM-DD.md` — human-readable daily journal.
2. `logs/journal.jsonl` — one structured entry per line, for the dashboard.

`bot/trade_logger.py` and all nine strategy files remain **unmodified**. The Explainer is called at
the same decision points the trade logger is already called.

## Components

### 1. `bot/explainer.py` — `Explainer`

Methods (each takes the event dict + optional price window, returns `(narrative: str, terms:
list[str])`, and appends to the journal sink). There is deliberately **no** `explain_signal`: an
actionable signal is already covered by `explain_entry` (it led to a trade) or `explain_risk_event`
(it was vetoed), so a separate signal method would double-journal. Routine `direction="none"` bars
are not journaled at all.

- `explain_entry(position_event, data)` — narrates entry: derived reason + risk-managed sizing
  ("risk manager approved N shares, ~X% of capital, stop at $S, target $T").
- `explain_exit(position_event)` — narrates exit using the **exit reason** (stop / take-profit /
  strategy / kill) and realized PnL.
- `explain_risk_event(risk_event)` — narrates vetoes and kill-switch (daily-loss limit, max
  positions, size=0, bracket triggers).
- `daily_digest(account_info)` — once-per-day wrap-up; notes "held, no action" days.

All public methods are wrapped so **any exception is caught, logged, and swallowed** — explanation
failure must never propagate to the trading loop.

### 2. Reason derivers (Phase 1)

A registry `REASON_DERIVERS: dict[str, Callable]` keyed by strategy short name.

- `bollinger` deriver: computes the lower/upper Bollinger band and close from the price window using
  the **same indicator util the strategy uses** (`strategies/indicator_utils.py`) so numbers match
  the strategy exactly, and returns a structured reason (rule fired, close, band value).
- Fallback: unknown strategies return a generic reason ("the strategy signalled a {direction}").

### 3. `bot/glossary.py`

- `GLOSSARY: dict[str, str]` — ~15–20 beginner-friendly terms: Bollinger band, moving average,
  standard deviation, Sharpe ratio, drawdown, stop-loss, take-profit, trailing stop, bracket order,
  position sizing, risk per trade, kill switch, mean reversion, long/short, slippage, commission,
  paper trading, equity curve.
- `detect_terms(text: str) -> list[str]` — case-insensitive whole-word match of glossary keys in a
  narrative, returning the terms present (deduped, in order of appearance).

### 4. Journal sink

- Markdown: append a dated, timestamped section per entry to `logs/journal/YYYY-MM-DD.md`.
- JSONL: append `{timestamp, kind, symbol, narrative, terms, raw_event}` to `logs/journal.jsonl`.
- Append-only, best-effort; a failed write is logged and swallowed.

### 5. Dashboard panel

Extend the existing Streamlit app:

- `bot/dashboard_data.py` — add `load_journal()` (reads `logs/journal.jsonl`) and `load_glossary()`
  (imports `bot.glossary.GLOSSARY`).
- `bot/dashboard.py` — add a **Journal** feed (most-recent-first narratives with their glossary
  terms) and a **Glossary** view (term → definition).

### 6. Targeted bot change

`bot/trading_bot.py` currently knows the exit reason (`risk_reason` vs strategy exit, lines ~228–235)
but drops it before `log_position_closed`. Change:

- Thread an `exit_reason` string ("stop_loss" / "take_profit" / "strategy" / "kill_switch" /
  "risk:<detail>") into `_close_position` and include it in the close event dict.
- Instantiate one `Explainer` in `TradingBot.__init__` and call the matching `explain_*` method
  immediately after each existing `trade_logger.log_*` call in `_run_cycle` / `_open_position` /
  `_close_position`.

No other behavior changes.

## Data flow

```
_run_cycle decision
  -> trade_logger.log_*(event)              # unchanged
  -> explainer.explain_*(event, price_window)
        -> reason deriver (bollinger) + template -> narrative
        -> glossary.detect_terms(narrative)
        -> append logs/journal/YYYY-MM-DD.md + logs/journal.jsonl
  -> dashboard renders Journal + Glossary
```

## What gets journaled

| Event | Journaled? |
|-------|-----------|
| Entry (long/short) | Yes — reason + sizing |
| Exit | Yes — reason (stop/take-profit/strategy/kill) + PnL |
| Risk veto (size=0, max positions, daily-loss limit) | Yes |
| Kill-switch / bracket trigger | Yes |
| Signal with `direction="none"` (routine wait) | No — dashboard shows live "waiting"; daily digest notes "held" |

## Error handling

The Explainer is non-critical infrastructure. Every public method runs inside a try/except that logs
the failure and returns without raising. Journal writes are best-effort and append-only. The trading
loop's correctness must not depend on the Explainer in any way.

## Testing

- Per-template unit tests: event dict + synthetic price window -> asserted phrases/numbers in the
  narrative.
- `bollinger` reason deriver: synthetic data with close at/below the lower band -> correct band value
  and "cheap zone" classification; close at/above upper band -> "expensive zone".
- `glossary.detect_terms`: text containing known terms returns them; unrelated text returns `[]`.
- **Isolation test:** a deriver/template that raises does not propagate out of the `Explainer` call
  (loop continues).
- Journal sink: entries land in both `.md` and `.jsonl`; malformed write is swallowed.

## Out of scope (each its own later spec)

- SQLite single-source-of-truth migration.
- Strategies emitting structured reasons (Phase 2 of the "why").
- Autoresearch (Karpathy) loop.
- Claude-polish background job (this spec defines the stub interface only).
- Position-sizing rework. Note: the project's ~1% backtest returns are mostly a sizing artifact
  (2%-risk cap -> small exposure), not a broken strategy. Recommended as the **next** spec.
