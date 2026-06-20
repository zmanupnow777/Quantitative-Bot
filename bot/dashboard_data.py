"""
dashboard_data.py — all file I/O for the trading dashboard.
The UI layer (dashboard.py) never opens file handles directly.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

REPORTS_DIR  = settings.REPORTS_DIR
LOGS_DIR     = settings.LOGS_DIR
DAILY_DIR    = LOGS_DIR / "daily"
TRADES_JSONL = LOGS_DIR / "trades.jsonl"
JOURNAL_JSONL = LOGS_DIR / "journal.jsonl"
BOT_LOG      = LOGS_DIR / "trading_bot.log"


def load_trades_jsonl() -> list[dict]:
    """Return all events from trades.jsonl, or [] if file missing."""
    if not TRADES_JSONL.exists():
        return []
    events: list[dict] = []
    with TRADES_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def get_open_positions(events: list[dict]) -> pd.DataFrame:
    """Reconstruct open positions from event stream."""
    opened: dict[str, dict] = {}
    for e in events:
        symbol = e.get("symbol", "?")
        if e.get("event") == "position_opened":
            opened[symbol] = e
        elif e.get("event") == "position_closed":
            opened.pop(symbol, None)

    if not opened:
        return pd.DataFrame(columns=[
            "symbol", "direction", "qty",
            "entry_price", "stop_loss", "take_profit", "timestamp",
        ])
    df = pd.DataFrame(list(opened.values()))
    keep = [c for c in ["symbol", "direction", "qty", "entry_price",
                         "stop_loss", "take_profit", "timestamp"] if c in df.columns]
    return df[keep].copy()


def get_signals(events: list[dict], n: int = 50) -> pd.DataFrame:
    """Return the most recent N signal events, annotated with whether each fired a trade."""
    for i, e in enumerate(events):
        if e.get("event") != "signal":
            continue
        fired = False
        for j in range(i + 1, min(i + 4, len(events))):
            if (events[j].get("event") == "position_opened"
                    and events[j].get("strategy", "") == e.get("strategy", "NONE")):
                fired = True
                break
        e["_fired_trade"] = fired

    signal_events = [e for e in events if e.get("event") == "signal"]
    if not signal_events:
        return pd.DataFrame()

    df = pd.DataFrame(signal_events)
    cols = [c for c in ["timestamp", "strategy", "direction", "_fired_trade"] if c in df.columns]
    df = df[cols].rename(columns={"_fired_trade": "fired_trade"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp", ascending=False).head(n).reset_index(drop=True)


def get_risk_events(events: list[dict]) -> pd.DataFrame:
    """Return all risk_event entries sorted newest first."""
    risk = [e for e in events if e.get("event") == "risk_event"]
    if not risk:
        return pd.DataFrame()
    df = pd.DataFrame(risk)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp", ascending=False).reset_index(drop=True)


def get_kill_switch_status(events: list[dict]) -> dict:
    risk_events = [e for e in events if e.get("event") == "risk_event"]
    killed = len(risk_events) > 0
    reason = risk_events[-1].get("reason", "") if risk_events else ""
    return {"killed": killed, "reason": reason, "event_count": len(risk_events)}


def parse_today_daily_summary() -> dict:
    """Parse most recent daily summary text file. Returns {} if none found."""
    if not DAILY_DIR.exists():
        return {}
    candidates = sorted(DAILY_DIR.glob("*.txt"), reverse=True)
    if not candidates:
        return {}
    today = date.today().isoformat()
    target = DAILY_DIR / f"{today}.txt"
    path = target if target.exists() else candidates[0]

    patterns = {
        "account_value": r"Account Value:\s+\$([\d,\.]+)",
        "cash":          r"Cash:\s+\$([\d,\.]+)",
        "daily_pnl":     r"Daily PnL:\s+\$([\-\d,\.]+)",
        "trades_opened": r"Trades Opened:\s+(\d+)",
        "trades_closed": r"Trades Closed:\s+(\d+)",
        "wins":          r"Wins / Losses:\s+(\d+)",
        "losses":        r"Wins / Losses:\s+\d+ / (\d+)",
        "total_pnl":     r"Total PnL:\s+\$([\-\d,\.]+)",
    }
    text = path.read_text(encoding="utf-8")
    result: dict = {"date": path.stem}
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                result[key] = float(raw)
            except ValueError:
                result[key] = raw
    return result


def load_backtest_metrics() -> pd.DataFrame:
    """Load newest *_metrics.json and flatten metrics sub-dict into columns."""
    files = sorted(REPORTS_DIR.glob("*_metrics.json"), reverse=True)
    if not files:
        return pd.DataFrame()
    with files[0].open(encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for entry in data:
        row: dict = {"symbol": entry.get("symbol"), "strategy": entry.get("strategy")}
        row.update(entry.get("metrics", {}))
        rows.append(row)
    return pd.DataFrame(rows)


def load_equity_curves() -> pd.DataFrame:
    """Load newest *_equity_curves.csv."""
    files = sorted(REPORTS_DIR.glob("*_equity_curves.csv"), reverse=True)
    if not files:
        return pd.DataFrame()
    df = pd.read_csv(files[0], index_col=0, parse_dates=True)
    # strip "SYMBOL|" prefix from column names for cleaner legend labels
    df.columns = [c.split("|")[-1] if "|" in c else c for c in df.columns]
    return df


def compute_live_metrics(events: list[dict], initial_capital: float = 100_000.0) -> dict:
    """Compute performance metrics from closed-position events."""
    closed = [e for e in events if e.get("event") == "position_closed"]
    if not closed:
        return {
            "total_return": None, "win_rate": None,
            "total_trades": 0, "average_pnl": None,
            "total_pnl": 0.0, "max_drawdown": None,
        }
    pnls = [t.get("pnl", 0.0) for t in closed]
    equity = initial_capital + np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    wins = sum(1 for p in pnls if p > 0)
    return {
        "total_return": float(equity[-1] / initial_capital - 1),
        "win_rate":     wins / len(pnls),
        "total_trades": len(pnls),
        "average_pnl":  float(np.mean(pnls)),
        "total_pnl":    float(sum(pnls)),
        "max_drawdown": float(drawdown.min()),
    }


def detect_mode() -> str:
    """Return 'live' if bot log was written within last 120 seconds, else 'static'."""
    if BOT_LOG.exists():
        if time.time() - BOT_LOG.stat().st_mtime < 120:
            return "live"
    return "static"


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


def get_trade_markers(events: list[dict]) -> pd.DataFrame:
    """Return entry/exit markers (timestamp, price, side, kind) from trade events.

    Extracts position_opened and position_closed events from the event stream,
    converting them to chart markers. Returns empty DataFrame if no trade events.

    Args:
        events: List of event dicts, each with "event" key and trade data.

    Returns:
        DataFrame with columns: timestamp (datetime), price (float), side (str),
        kind (str). Empty DataFrame if no trade events.
    """
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
    return pd.DataFrame(rows, columns=["timestamp", "price", "side", "kind"])


def build_equity_series(events: list[dict], initial_capital: float = 100_000.0) -> pd.Series:
    """Return cumulative account value over closed-trade timestamps.

    Extracts position_closed events, sorts by timestamp, and computes cumulative
    equity as initial_capital + cumsum(pnl). Returns empty Series if no closes.

    Args:
        events: List of event dicts containing position_closed events.
        initial_capital: Starting account value.

    Returns:
        Series indexed by close timestamp with cumulative equity values.
        Empty Series if no position_closed events.
    """
    closes = [e for e in events if e.get("event") == "position_closed"]
    if not closes:
        return pd.Series(dtype=float)
    closes.sort(key=lambda e: pd.to_datetime(e.get("timestamp")))
    times = [pd.to_datetime(e.get("timestamp")) for e in closes]
    pnls = [float(e.get("pnl", 0.0)) for e in closes]
    equity = initial_capital + pd.Series(pnls).cumsum()
    return pd.Series(equity.values, index=pd.DatetimeIndex(times))


def build_trade_pnls(events: list[dict]) -> pd.DataFrame:
    """Return one row per closed trade: timestamp, symbol, pnl, won.

    Extracts position_closed events and adds a "won" column (bool) indicating
    whether pnl > 0. Returns empty DataFrame if no closes.

    Args:
        events: List of event dicts containing position_closed events.

    Returns:
        DataFrame with columns: timestamp (datetime), symbol (str), pnl (float), won (bool).
        Empty DataFrame if no position_closed events.
    """
    rows = []
    for e in events:
        if e.get("event") != "position_closed":
            continue
        pnl = float(e.get("pnl", 0.0))
        rows.append({
            "timestamp": pd.to_datetime(e.get("timestamp")),
            "symbol": e.get("symbol", "?"),
            "pnl": pnl,
            "won": pnl > 0,
        })
    return pd.DataFrame(rows, columns=["timestamp", "symbol", "pnl", "won"])


def compute_drawdown(equity: pd.Series) -> pd.Series:
    """Return the underwater curve (<=0 fraction) of an equity series.

    Computes (equity - equity.cummax()) / equity.cummax(), yielding 0 at peaks
    and negative values during drawdowns. Returns empty Series if input is empty.

    Args:
        equity: Series of equity values, typically from build_equity_series.

    Returns:
        Series with same index as input, containing drawdown fractions.
        Empty Series if input is empty.
    """
    if equity.empty:
        return pd.Series(dtype=float)
    peak = equity.cummax()
    return (equity - peak) / peak
