# Dashboard Graphs — Design Spec

> Status: Approved 2026-06-20. Adds four visual charts to the Streamlit dashboard.
> Builds on the existing dashboard (`bot/dashboard.py` UI + `bot/dashboard_data.py` data layer)
> and the Explainer feature already merged.

## Purpose

Give the operator a visual read on what the bot is seeing and doing: the market and the
strategy's bands, where it traded, how the account is tracking, per-trade outcomes, and drawdown.

## Decisions locked during brainstorming

- **Location:** one new **"📈 Charts"** tab in the existing tab row, all four charts stacked.
- **Price source:** read from the **cached parquet** under `data/cache/<symbol>/<timeframe>.parquet`
  (offline, fast, no network). Trade-off accepted: the price chart is only as fresh as the last
  data fetch. A future "refresh data" control is out of scope here.
- **Bands:** computed with the same `strategies.indicator_utils.bollinger_bands(close, length=20,
  std_dev=2.0)` the chosen strategy uses, so the chart matches the journal narrative exactly.
- **Empty states:** charts 2–4 depend on real closed trades (none exist yet); each renders a clear
  "No trades yet — populates once the bot trades" message instead of an empty axis. Chart 1 renders
  immediately from cached price data.

## Architecture (follows the existing data-vs-UI split)

- **New `bot/dashboard_charts.py`** — pure figure builders: take already-prepared data, return a
  Plotly `go.Figure`. Keeps `dashboard.py` from bloating and keeps figure construction in one place.
- **`bot/dashboard_data.py`** — add small, pure, file-only data-prep functions (testable).
- **`bot/dashboard.py`** — add one `tab_charts` that calls the data-prep functions, passes results to
  the figure builders, and renders with `st.plotly_chart`, with the empty-state guards.

No changes to trading code, brokers, strategies, or the Explainer.

## Components

### `bot/dashboard_data.py` — new functions

- `list_cached_symbols() -> list[str]` — directory names under `data/cache/` that contain at least
  one `.parquet`. Returns `[]` if the cache dir is missing.
- `load_price_window(symbol: str, timeframe: str = "1d", bars: int = 250) -> pd.DataFrame` — read
  `data/cache/<symbol>/<timeframe>.parquet`, return the last `bars` rows with a DatetimeIndex and at
  least a `Close` column (and OHLC if present). Returns an empty DataFrame if the file is missing.
- `get_trade_markers(events: list[dict]) -> pd.DataFrame` — from `position_opened` / `position_closed`
  events, return columns `timestamp` (datetime), `price` (float), `side` (`"buy"`/`"sell"`),
  `kind` (`"entry"`/`"exit"`). Empty DataFrame if none.
- `build_equity_series(events: list[dict], initial_capital: float = 100_000.0) -> pd.Series` —
  cumulative account value: start at `initial_capital`, add each `position_closed` event's `pnl` in
  timestamp order; index = close timestamps. Empty Series if no closes.
- `build_trade_pnls(events: list[dict]) -> pd.DataFrame` — one row per `position_closed`: columns
  `timestamp`, `symbol`, `pnl`, `won` (bool, `pnl > 0`). Empty DataFrame if none.
- `compute_drawdown(equity: pd.Series) -> pd.Series` — `(equity - equity.cummax()) / equity.cummax()`
  (≤ 0 values, fraction). Empty Series if input empty.

### `bot/dashboard_charts.py` — figure builders

- `price_band_figure(price: pd.DataFrame, markers: pd.DataFrame, length: int = 20, std_dev: float = 2.0) -> go.Figure`
  — line of `Close`; lower/mid/upper Bollinger bands via `bollinger_bands`; ▲ green buy / ▼ red sell
  markers from `markers` (only those whose timestamp falls within the price window's date range).
- `equity_figure(equity: pd.Series) -> go.Figure` — line of account value over time.
- `trade_pnl_figure(pnls: pd.DataFrame) -> go.Figure` — bar per trade, green if `won` else red.
- `drawdown_figure(drawdown: pd.Series) -> go.Figure` — filled area (underwater) of drawdown %.

Each builder assumes non-empty input (the UI guards emptiness before calling).

### `bot/dashboard.py` — new tab

Add `"📈 Charts"` to the tab list. In `tab_charts`:
1. Symbol selectbox from `list_cached_symbols()` (default first, prefer `"SPY"` if present).
2. Chart 1: load price + markers; if price empty → info message; else render `price_band_figure`.
3. Build `equity = build_equity_series(events)`. Charts 2 and 4 guard on `equity.empty`; chart 3
   guards on `build_trade_pnls(events).empty`; each shows the "No trades yet" caption when empty.

## Data flow

```
trades.jsonl (events) ─┬─ get_trade_markers ─┐
                       ├─ build_equity_series ─┬─ compute_drawdown ─ drawdown_figure
                       └─ build_trade_pnls ── trade_pnl_figure
data/cache/<sym>.parquet ─ load_price_window ─┴─ price_band_figure (+ markers)
                                              └─ equity_figure
            tab_charts renders all four with empty-state guards
```

## Error handling

Data-prep functions return empty `DataFrame`/`Series` for missing files or absent events — never
raise. The UI checks emptiness and shows a caption before calling a figure builder, so a builder is
never handed empty input. A malformed parquet read is caught and treated as "no data".

## Testing

Pure data-prep functions get unit tests (`tests/test_dashboard_charts_data.py`):
- `build_equity_series`: two closes of +100 and −40 on $100k → series `[100100, 100060]` in time order.
- `compute_drawdown`: known equity series → expected underwater values; peak point → 0.
- `get_trade_markers`: mixed events → correct rows/sides; no trade events → empty.
- `build_trade_pnls`: `won` flag keys off `pnl > 0`; empty input → empty.
- `load_price_window` / `list_cached_symbols`: against a tmp cache dir → correct rows / symbol list;
  missing path → empty / `[]`.

Figure builders get a smoke test (`tests/test_dashboard_charts_figs.py`): synthetic non-empty input →
each returns a `plotly.graph_objects.Figure` without raising.

## Out of scope

Live (network) price refresh, candlestick OHLC styling toggles, multi-symbol overlays, indicators
beyond Bollinger bands, and any change to trading/broker/strategy code.
