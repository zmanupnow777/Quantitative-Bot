# Dashboard Graphs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four visual charts (price+Bollinger bands+trade markers, account value curve, per-trade PnL bars, drawdown) to the Streamlit dashboard in a new "📈 Charts" tab.

**Architecture:** Follow the existing data-vs-UI split. Pure, file-only data-prep functions go in `bot/dashboard_data.py`; pure Plotly figure builders go in a new `bot/dashboard_charts.py`; `bot/dashboard.py` adds one `tab_charts` that wires them with empty-state guards. No trading/broker/strategy/Explainer code changes.

**Tech Stack:** Python 3.12, pandas, plotly.graph_objects, streamlit, existing `strategies.indicator_utils.bollinger_bands`, existing `config.settings`, pytest.

## Global Constraints

- Python 3.10+, `from __future__ import annotations` at top of new modules.
- Type hints + docstrings on all public functions.
- Library code uses `logging`, never `print`.
- Data-prep functions are file/event-only and MUST NOT raise on missing files or absent events — return an empty `pd.DataFrame` / `pd.Series` / `[]`. The UI guards emptiness before calling a figure builder, so builders may assume non-empty input.
- Cached price files live at `settings.DATA_DIR / <symbol> / <timeframe>.parquet` (note: `settings.DATA_DIR` already resolves to `.../data/cache`). Parquet has a `DatetimeIndex` named `Date` and columns `Open, High, Low, Close, Volume`.
- Bollinger bands use `strategies.indicator_utils.bollinger_bands(close, length=20, std_dev=2.0)` which returns `(lower, middle, upper)`.
- Event schema in `logs/trades.jsonl`: `position_opened` = `{event, timestamp, symbol, direction, qty, price, stop_loss, take_profit}`; `position_closed` = `{event, timestamp, symbol, side, qty, entry_price, exit_price, pnl, pnl_pct, exit_reason}`.
- Run tests with: `./.venv/Scripts/python.exe -m pytest <path> -v` (Windows bash).

---

### Task 1: Price-window + cached-symbol loaders

**Files:**
- Modify: `bot/dashboard_data.py`
- Test: `tests/test_dashboard_charts_data.py`

**Interfaces:**
- Consumes: `settings.DATA_DIR` (already imported in the module).
- Produces:
  - `list_cached_symbols() -> list[str]` — sorted symbol dir names under `settings.DATA_DIR` containing at least one `*.parquet`; `[]` if the dir is missing.
  - `load_price_window(symbol: str, timeframe: str = "1d", bars: int = 250) -> pd.DataFrame` — last `bars` rows of `settings.DATA_DIR/<symbol>/<timeframe>.parquet`; empty DataFrame if the file is missing or unreadable.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_charts_data.py
from __future__ import annotations

from pathlib import Path

import pandas as pd

import bot.dashboard_data as dd


def _make_cache(tmp_path: Path) -> Path:
    cache = tmp_path / "cache"
    (cache / "SPY").mkdir(parents=True)
    idx = pd.date_range("2024-01-01", periods=300, freq="D", name="Date")
    df = pd.DataFrame(
        {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": range(300), "Volume": 10},
        index=idx,
    )
    df.to_parquet(cache / "SPY" / "1d.parquet")
    return cache


def test_list_cached_symbols(tmp_path, monkeypatch):
    cache = _make_cache(tmp_path)
    monkeypatch.setattr(dd.settings, "DATA_DIR", cache)
    assert dd.list_cached_symbols() == ["SPY"]


def test_list_cached_symbols_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dd.settings, "DATA_DIR", tmp_path / "nope")
    assert dd.list_cached_symbols() == []


def test_load_price_window_returns_last_bars(tmp_path, monkeypatch):
    cache = _make_cache(tmp_path)
    monkeypatch.setattr(dd.settings, "DATA_DIR", cache)
    df = dd.load_price_window("SPY", "1d", bars=50)
    assert len(df) == 50
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df["Close"].iloc[-1] == 299


def test_load_price_window_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(dd.settings, "DATA_DIR", tmp_path)
    assert dd.load_price_window("NOPE", "1d").empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_charts_data.py -v`
Expected: FAIL with `AttributeError: module 'bot.dashboard_data' has no attribute 'list_cached_symbols'`

- [ ] **Step 3: Add the functions at the END of bot/dashboard_data.py**

```python
def list_cached_symbols() -> list[str]:
    """Return sorted symbol names that have cached price parquet files."""
    cache_dir = settings.DATA_DIR
    if not cache_dir.exists():
        return []
    symbols = [
        p.name for p in cache_dir.iterdir()
        if p.is_dir() and any(p.glob("*.parquet"))
    ]
    return sorted(symbols)


def load_price_window(symbol: str, timeframe: str = "1d", bars: int = 250) -> pd.DataFrame:
    """Return the last ``bars`` rows of cached OHLCV data for ``symbol``.

    Reads ``settings.DATA_DIR/<symbol>/<timeframe>.parquet``. Returns an empty
    DataFrame if the file is missing or cannot be read.
    """
    path = settings.DATA_DIR / symbol / f"{timeframe}.parquet"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001 - corrupt/unreadable cache is "no data"
        logger.warning("Could not read price cache %s", path)
        return pd.DataFrame()
    return df.tail(bars)
```

Also add a module logger if one is not already present near the top of the file (after the imports):

```python
import logging
logger = logging.getLogger(__name__)
```

(If `logging`/`logger` already exist in the file, do not duplicate them.)

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_charts_data.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/dashboard_data.py tests/test_dashboard_charts_data.py
git commit -m "feat: add cached price-window and symbol loaders for charts"
```

---

### Task 2: Trade-derived data prep (markers, equity, pnls, drawdown)

**Files:**
- Modify: `bot/dashboard_data.py`
- Test: `tests/test_dashboard_charts_data.py`

**Interfaces:**
- Produces:
  - `get_trade_markers(events: list[dict]) -> pd.DataFrame` — columns `timestamp` (datetime), `price` (float), `side` (`"buy"`/`"sell"`), `kind` (`"entry"`/`"exit"`). Entry: price=`price`, side=`"buy"` if `direction=="long"` else `"sell"`. Exit: price=`exit_price`, side=`"sell"` if `side=="long"` else `"buy"`. Empty DataFrame if no trade events.
  - `build_equity_series(events: list[dict], initial_capital: float = 100_000.0) -> pd.Series` — cumulative `initial_capital + cumsum(pnl)` over `position_closed` events in timestamp order, indexed by close timestamp. Empty Series if no closes.
  - `build_trade_pnls(events: list[dict]) -> pd.DataFrame` — one row per `position_closed`: `timestamp`, `symbol`, `pnl`, `won` (`pnl > 0`). Empty DataFrame if none.
  - `compute_drawdown(equity: pd.Series) -> pd.Series` — `(equity - equity.cummax()) / equity.cummax()`; empty Series if input empty.

- [ ] **Step 1: Write the failing test (append to tests/test_dashboard_charts_data.py)**

```python
def _trade_events():
    return [
        {"event": "position_opened", "timestamp": "2024-02-01T10:00:00", "symbol": "SPY",
         "direction": "long", "qty": 10, "price": 100.0},
        {"event": "position_closed", "timestamp": "2024-02-02T10:00:00", "symbol": "SPY",
         "side": "long", "qty": 10, "entry_price": 100.0, "exit_price": 110.0,
         "pnl": 100.0, "pnl_pct": 0.10, "exit_reason": "take_profit"},
        {"event": "position_closed", "timestamp": "2024-02-03T10:00:00", "symbol": "SPY",
         "side": "long", "qty": 10, "entry_price": 110.0, "exit_price": 106.0,
         "pnl": -40.0, "pnl_pct": -0.036, "exit_reason": "stop_loss"},
        {"event": "signal", "timestamp": "2024-02-04T10:00:00", "direction": "none"},
    ]


def test_get_trade_markers():
    m = dd.get_trade_markers(_trade_events())
    assert list(m["kind"]) == ["entry", "exit", "exit"]
    assert list(m["side"]) == ["buy", "sell", "sell"]
    assert list(m["price"]) == [100.0, 110.0, 106.0]


def test_get_trade_markers_empty():
    assert dd.get_trade_markers([{"event": "signal"}]).empty


def test_build_equity_series_accumulates():
    eq = dd.build_equity_series(_trade_events(), initial_capital=100_000.0)
    assert list(eq.values) == [100100.0, 100060.0]
    assert str(eq.index[0]) == "2024-02-02 10:00:00"


def test_build_equity_series_empty():
    assert dd.build_equity_series([]).empty


def test_build_trade_pnls_won_flag():
    p = dd.build_trade_pnls(_trade_events())
    assert list(p["pnl"]) == [100.0, -40.0]
    assert list(p["won"]) == [True, False]


def test_compute_drawdown():
    eq = dd.build_equity_series(_trade_events(), initial_capital=100_000.0)
    dd_series = dd.compute_drawdown(eq)
    # peak at first point -> 0; second point down 40 from peak 100100
    assert dd_series.iloc[0] == 0.0
    assert abs(dd_series.iloc[1] - (-40.0 / 100100.0)) < 1e-9


def test_compute_drawdown_empty():
    assert dd.compute_drawdown(pd.Series(dtype=float)).empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_charts_data.py -k "marker or equity or pnls or drawdown" -v`
Expected: FAIL with `AttributeError: module 'bot.dashboard_data' has no attribute 'get_trade_markers'`

- [ ] **Step 3: Add the functions at the END of bot/dashboard_data.py**

```python
def get_trade_markers(events: list[dict]) -> pd.DataFrame:
    """Return entry/exit markers (timestamp, price, side, kind) from trade events."""
    rows: list[dict] = []
    for e in events:
        ev = e.get("event")
        if ev == "position_opened":
            rows.append({
                "timestamp": pd.to_datetime(e.get("timestamp")),
                "price": float(e.get("price", 0.0)),
                "side": "buy" if e.get("direction") == "long" else "sell",
                "kind": "entry",
            })
        elif ev == "position_closed":
            rows.append({
                "timestamp": pd.to_datetime(e.get("timestamp")),
                "price": float(e.get("exit_price", 0.0)),
                "side": "sell" if e.get("side") == "long" else "buy",
                "kind": "exit",
            })
    return pd.DataFrame(rows)


def build_equity_series(events: list[dict], initial_capital: float = 100_000.0) -> pd.Series:
    """Return cumulative account value over closed-trade timestamps."""
    closes = [e for e in events if e.get("event") == "position_closed"]
    if not closes:
        return pd.Series(dtype=float)
    closes.sort(key=lambda e: e.get("timestamp", ""))
    times = [pd.to_datetime(e.get("timestamp")) for e in closes]
    pnls = [float(e.get("pnl", 0.0)) for e in closes]
    equity = initial_capital + pd.Series(pnls).cumsum()
    return pd.Series(equity.values, index=pd.DatetimeIndex(times))


def build_trade_pnls(events: list[dict]) -> pd.DataFrame:
    """Return one row per closed trade: timestamp, symbol, pnl, won."""
    rows = [
        {
            "timestamp": pd.to_datetime(e.get("timestamp")),
            "symbol": e.get("symbol", "?"),
            "pnl": float(e.get("pnl", 0.0)),
            "won": float(e.get("pnl", 0.0)) > 0,
        }
        for e in events if e.get("event") == "position_closed"
    ]
    return pd.DataFrame(rows)


def compute_drawdown(equity: pd.Series) -> pd.Series:
    """Return the underwater curve (<=0 fraction) of an equity series."""
    if equity.empty:
        return pd.Series(dtype=float)
    peak = equity.cummax()
    return (equity - peak) / peak
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_charts_data.py -v`
Expected: PASS (all data-prep tests pass)

- [ ] **Step 5: Commit**

```bash
git add bot/dashboard_data.py tests/test_dashboard_charts_data.py
git commit -m "feat: add trade markers, equity, pnl and drawdown data prep"
```

---

### Task 3: Figure builders

**Files:**
- Create: `bot/dashboard_charts.py`
- Test: `tests/test_dashboard_charts_figs.py`

**Interfaces:**
- Consumes: `strategies.indicator_utils.bollinger_bands`; output DataFrames/Series from Tasks 1–2.
- Produces (all return `plotly.graph_objects.Figure`):
  - `price_band_figure(price: pd.DataFrame, markers: pd.DataFrame, length: int = 20, std_dev: float = 2.0) -> go.Figure`
  - `equity_figure(equity: pd.Series) -> go.Figure`
  - `trade_pnl_figure(pnls: pd.DataFrame) -> go.Figure`
  - `drawdown_figure(drawdown: pd.Series) -> go.Figure`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_charts_figs.py
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import bot.dashboard_charts as dc


def _price():
    idx = pd.date_range("2024-01-01", periods=60, freq="D", name="Date")
    return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0,
                         "Close": range(60), "Volume": 10}, index=idx)


def _markers():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-10", "2024-02-01"]),
        "price": [9.0, 31.0], "side": ["buy", "sell"], "kind": ["entry", "exit"],
    })


def test_price_band_figure_returns_figure():
    fig = dc.price_band_figure(_price(), _markers())
    assert isinstance(fig, go.Figure)
    # close line + 3 bands + 2 marker groups (buy/sell) = at least 4 traces
    assert len(fig.data) >= 4


def test_equity_figure_returns_figure():
    eq = pd.Series([100100.0, 100060.0],
                   index=pd.to_datetime(["2024-02-02", "2024-02-03"]))
    assert isinstance(dc.equity_figure(eq), go.Figure)


def test_trade_pnl_figure_returns_figure():
    pnls = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-02-02", "2024-02-03"]),
        "symbol": ["SPY", "SPY"], "pnl": [100.0, -40.0], "won": [True, False],
    })
    assert isinstance(dc.trade_pnl_figure(pnls), go.Figure)


def test_drawdown_figure_returns_figure():
    dd_series = pd.Series([0.0, -0.004],
                          index=pd.to_datetime(["2024-02-02", "2024-02-03"]))
    assert isinstance(dc.drawdown_figure(dd_series), go.Figure)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_charts_figs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.dashboard_charts'`

- [ ] **Step 3: Create bot/dashboard_charts.py**

```python
"""Pure Plotly figure builders for the dashboard Charts tab.

Each builder assumes non-empty, well-formed input; the UI layer guards
emptiness before calling. Builders never read files or events themselves.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from strategies.indicator_utils import bollinger_bands


def price_band_figure(
    price: pd.DataFrame, markers: pd.DataFrame, length: int = 20, std_dev: float = 2.0
) -> go.Figure:
    """Price line with Bollinger bands and buy/sell trade markers."""
    close = price["Close"]
    lower, middle, upper = bollinger_bands(close, length, std_dev)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=price.index, y=upper, mode="lines",
                             line=dict(width=1, color="rgba(150,150,150,0.5)"), name="Upper band"))
    fig.add_trace(go.Scatter(x=price.index, y=middle, mode="lines",
                             line=dict(width=1, color="rgba(150,150,150,0.8)", dash="dot"), name="Mid"))
    fig.add_trace(go.Scatter(x=price.index, y=lower, mode="lines",
                             line=dict(width=1, color="rgba(150,150,150,0.5)"),
                             fill="tonexty", fillcolor="rgba(150,150,150,0.08)", name="Lower band"))
    fig.add_trace(go.Scatter(x=price.index, y=close, mode="lines",
                             line=dict(width=2, color="#2b8cbe"), name="Close"))

    if not markers.empty:
        lo, hi = price.index.min(), price.index.max()
        in_window = markers[(markers["timestamp"] >= lo) & (markers["timestamp"] <= hi)]
        buys = in_window[in_window["side"] == "buy"]
        sells = in_window[in_window["side"] == "sell"]
        if not buys.empty:
            fig.add_trace(go.Scatter(x=buys["timestamp"], y=buys["price"], mode="markers",
                                     marker=dict(symbol="triangle-up", size=12, color="#1a7a4a"),
                                     name="Buy"))
        if not sells.empty:
            fig.add_trace(go.Scatter(x=sells["timestamp"], y=sells["price"], mode="markers",
                                     marker=dict(symbol="triangle-down", size=12, color="#a02020"),
                                     name="Sell"))

    fig.update_layout(title="Price & Bollinger Bands", xaxis_title="Date",
                      yaxis_title="Price ($)", hovermode="x unified", height=480,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def equity_figure(equity: pd.Series) -> go.Figure:
    """Account value over time."""
    fig = go.Figure(go.Scatter(x=equity.index, y=equity.values, mode="lines",
                               line=dict(width=2, color="#1a7a4a"), name="Account value"))
    fig.update_layout(title="Account Value", xaxis_title="Date",
                      yaxis_title="Value ($)", hovermode="x unified", height=360)
    return fig


def trade_pnl_figure(pnls: pd.DataFrame) -> go.Figure:
    """Per-trade PnL bars, green for wins and red for losses."""
    colors = ["#1a7a4a" if w else "#a02020" for w in pnls["won"]]
    fig = go.Figure(go.Bar(x=pnls["timestamp"], y=pnls["pnl"], marker_color=colors,
                           name="Trade PnL"))
    fig.update_layout(title="Per-Trade PnL", xaxis_title="Trade time",
                      yaxis_title="PnL ($)", height=360)
    return fig


def drawdown_figure(drawdown: pd.Series) -> go.Figure:
    """Underwater curve of drawdown percentage."""
    fig = go.Figure(go.Scatter(x=drawdown.index, y=drawdown.values * 100.0, mode="lines",
                               fill="tozeroy", line=dict(width=1, color="#a02020"),
                               name="Drawdown"))
    fig.update_layout(title="Drawdown (Underwater)", xaxis_title="Date",
                      yaxis_title="Drawdown (%)", height=320)
    return fig
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_charts_figs.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/dashboard_charts.py tests/test_dashboard_charts_figs.py
git commit -m "feat: add plotly figure builders for the four charts"
```

---

### Task 4: Wire the Charts tab into the dashboard

**Files:**
- Modify: `bot/dashboard.py`

**Interfaces:**
- Consumes: `dd.list_cached_symbols`, `dd.load_price_window`, `dd.get_trade_markers`, `dd.build_equity_series`, `dd.build_trade_pnls`, `dd.compute_drawdown` (Tasks 1–2); `bot.dashboard_charts` builders (Task 3); the existing module-level `events` list.
- Produces: a new `tab_charts` rendered after the existing tabs. No new public Python interface.

- [ ] **Step 1: Add the charts import**

In `bot/dashboard.py`, after the line `import bot.dashboard_data as dd  # noqa: E402`, add:

```python
import bot.dashboard_charts as dc  # noqa: E402
```

- [ ] **Step 2: Add the tab to the tab row**

Replace:

```python
tab_pos, tab_sig, tab_bt, tab_lvbt, tab_risk = st.tabs([
    "Live Positions", "Signal Feed", "Backtest Results",
    "Live vs Backtest", "Risk Status",
])
```

with:

```python
tab_pos, tab_sig, tab_bt, tab_lvbt, tab_risk, tab_charts = st.tabs([
    "Live Positions", "Signal Feed", "Backtest Results",
    "Live vs Backtest", "Risk Status", "📈 Charts",
])
```

- [ ] **Step 3: Add the tab_charts render block**

Immediately BEFORE the line `st.markdown("---")` that precedes `st.subheader("\U0001F4D3 Journal")` (i.e. after the `with tab_risk:` block ends and before the Journal section), insert:

```python
# ── Tab 6: Charts ─────────────────────────────────────────────────────
with tab_charts:
    st.subheader("Price & Bollinger Bands")
    symbols = dd.list_cached_symbols()
    if not symbols:
        st.info("No cached price data found. Run a backtest or data fetch first.")
    else:
        default_idx = symbols.index("SPY") if "SPY" in symbols else 0
        sym = st.selectbox("Symbol", symbols, index=default_idx)
        price = dd.load_price_window(sym, "1d", bars=250)
        if price.empty:
            st.info(f"No cached price data for {sym}.")
        else:
            markers = dd.get_trade_markers(events)
            st.plotly_chart(dc.price_band_figure(price, markers), use_container_width=True)
            st.caption("Bands use length=20, std_dev=2.0 — the same as the deployed strategy. "
                       "Price is as fresh as the last data fetch.")

    equity = dd.build_equity_series(events)
    pnls = dd.build_trade_pnls(events)

    st.subheader("Account Value")
    if equity.empty:
        st.caption("No trades yet — this populates once the bot closes its first trade.")
    else:
        st.plotly_chart(dc.equity_figure(equity), use_container_width=True)

    st.subheader("Per-Trade PnL")
    if pnls.empty:
        st.caption("No trades yet — this populates once the bot closes its first trade.")
    else:
        st.plotly_chart(dc.trade_pnl_figure(pnls), use_container_width=True)

    st.subheader("Drawdown")
    if equity.empty:
        st.caption("No trades yet — this populates once the bot closes its first trade.")
    else:
        st.plotly_chart(dc.drawdown_figure(dd.compute_drawdown(equity)), use_container_width=True)
```

- [ ] **Step 4: Verify the dashboard imports and the data layer works headlessly**

Run:
```bash
./.venv/Scripts/python.exe -c "import bot.dashboard_charts as dc, bot.dashboard_data as dd; print('charts import OK'); print('symbols:', dd.list_cached_symbols())"
```
Expected: prints `charts import OK` and a symbols list (e.g. `['IVV', 'SPY']`) with no traceback.

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `./.venv/Scripts/python.exe -m pytest tests -q`
Expected: PASS (all prior tests + the new chart tests).

- [ ] **Step 6: Commit**

```bash
git add bot/dashboard.py
git commit -m "feat: add Charts tab with price/bands, equity, pnl and drawdown"
```

---

## Manual verification (after all tasks)

- [ ] Launch the dashboard and open the 📈 Charts tab:

```bash
./.venv/Scripts/python.exe -m streamlit run bot/dashboard.py
```
Confirm: the Price & Bollinger Bands chart renders for SPY (bands + price line); the other three show the "No trades yet" caption (or, if `logs/trades.jsonl` has closed trades, render the curves/bars).
