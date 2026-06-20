"""Streamlit trading dashboard. Run: streamlit run bot/dashboard.py"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Anchor project root so imports work when launched from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bot.dashboard_data as dd  # noqa: E402

st.set_page_config(
    page_title="Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── load all data once per render ────────────────────────────────────
events  = dd.load_trades_jsonl()
daily   = dd.parse_today_daily_summary()
metrics = dd.load_backtest_metrics()
curves  = dd.load_equity_curves()
mode    = dd.detect_mode()
kill    = dd.get_kill_switch_status(events)

# ── sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Controls")
    mode_color = "green" if mode == "live" else "gray"
    st.markdown(f"Bot status: :{mode_color}[**{'LIVE' if mode == 'live' else 'STATIC'}**]")
    auto_refresh = st.toggle("Auto-refresh (30 s)", value=True)
    st.caption(f"Last loaded: {pd.Timestamp.now().strftime('%H:%M:%S')}")

# ── account overview ─────────────────────────────────────────────────
st.title("Trading Dashboard")

col1, col2, col3, col4, col5 = st.columns(5)
portfolio_value = daily.get("account_value")
cash            = daily.get("cash")
daily_pnl       = daily.get("daily_pnl")
open_count      = len(dd.get_open_positions(events))

col1.metric("Portfolio Value", f"${portfolio_value:,.2f}" if portfolio_value else "—")
col2.metric("Cash", f"${cash:,.2f}" if cash else "—")
col3.metric(
    "Daily P&L",
    f"${daily_pnl:,.2f}" if daily_pnl is not None else "—",
    delta=f"{daily_pnl:,.2f}" if daily_pnl else None,
)
col4.metric("Open Positions", open_count)
if kill["killed"]:
    col5.error("KILL SWITCH: ON")
    if kill["reason"]:
        st.error(f"Kill reason: {kill['reason']}")
else:
    col5.success("Kill Switch: OK")

st.divider()

# ── tabs ─────────────────────────────────────────────────────────────
tab_pos, tab_sig, tab_bt, tab_lvbt, tab_risk = st.tabs([
    "Live Positions", "Signal Feed", "Backtest Results",
    "Live vs Backtest", "Risk Status",
])

# ── Tab 1: Live Positions ─────────────────────────────────────────────
with tab_pos:
    st.subheader("Open Positions")
    positions_df = dd.get_open_positions(events)
    if positions_df.empty:
        st.info("No open positions. The bot may not have run yet, or all positions are closed.")
    else:
        st.caption("Current price and unrealized P&L are only available while the bot is running.")

        def _color_direction(val: str) -> str:
            color = "#1a7a4a" if str(val).lower() == "long" else "#a02020"
            return f"color: {color}; font-weight: bold"

        fmt: dict = {}
        for col in ["entry_price", "stop_loss", "take_profit"]:
            if col in positions_df.columns:
                fmt[col] = "${:.2f}"
        if "qty" in positions_df.columns:
            fmt["qty"] = "{:.0f}"

        styled = positions_df.style.format(fmt)
        if "direction" in positions_df.columns:
            styled = styled.applymap(_color_direction, subset=["direction"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

# ── Tab 2: Signal Feed ────────────────────────────────────────────────
with tab_sig:
    st.subheader("Recent Signals (last 50)")
    signals_df = dd.get_signals(events, n=50)
    if signals_df.empty:
        st.info("No signals recorded yet.")
    else:
        def _highlight_fired(row: pd.Series):
            bg = "#1a4a1a" if row.get("fired_trade") else ""
            return [f"background-color: {bg}"] * len(row)

        ts_fmt = {}
        if "timestamp" in signals_df.columns:
            ts_fmt["timestamp"] = lambda t: (
                t.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(t) else "—"
            )
        st.dataframe(
            signals_df.style.apply(_highlight_fired, axis=1).format(ts_fmt),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Green rows = signal triggered a position open.")

# ── Tab 3: Backtest Results ───────────────────────────────────────────
with tab_bt:
    st.subheader("Strategy Comparison")
    if metrics.empty:
        st.info("No backtest reports found. Run run_backtest.py first.")
    else:
        display_cols = [
            "strategy", "total_return", "annual_return", "sharpe_ratio",
            "sortino_ratio", "max_drawdown_percent", "win_rate",
            "profit_factor", "expectancy", "calmar_ratio",
            "total_trades", "trades_per_year",
        ]
        display_cols = [c for c in display_cols if c in metrics.columns]
        df_display = metrics[display_cols].copy()
        for col in ["total_return", "annual_return", "max_drawdown_percent", "win_rate"]:
            if col in df_display.columns:
                df_display[col] = df_display[col] * 100

        st.dataframe(
            df_display.style.format({
                "total_return":         "{:.2f}%",
                "annual_return":        "{:.3f}%",
                "sharpe_ratio":         "{:.3f}",
                "sortino_ratio":        "{:.3f}",
                "max_drawdown_percent": "{:.2f}%",
                "win_rate":             "{:.1f}%",
                "profit_factor":        "{:.2f}",
                "expectancy":           "${:.2f}",
                "calmar_ratio":         "{:.3f}",
                "total_trades":         "{:.0f}",
                "trades_per_year":      "{:.1f}",
            }),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Equity Curves")
    if curves.empty:
        st.info("No equity curve data found.")
    else:
        fig = go.Figure()
        for col in curves.columns:
            fig.add_trace(go.Scatter(
                x=curves.index, y=curves[col],
                mode="lines", name=col,
                hovertemplate="%{y:$,.0f}<extra>%{fullData.name}</extra>",
            ))
        fig.update_layout(
            title="Equity Curves — All Strategies",
            xaxis_title="Date", yaxis_title="Portfolio Value ($)",
            hovermode="x unified", height=500,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

# ── Tab 4: Live vs Backtest ───────────────────────────────────────────
with tab_lvbt:
    st.subheader("Live Performance vs Backtest Expectations")
    live_m = dd.compute_live_metrics(events)

    if live_m["total_trades"] == 0:
        st.info("No closed trades yet. Run the bot to generate live data.")

    if not metrics.empty:
        live_strategy = next(
            (e.get("strategy") for e in reversed(events) if e.get("strategy")), None
        )
        bt_row = None
        if live_strategy:
            matches = metrics[metrics["strategy"] == live_strategy]
            if not matches.empty:
                bt_row = matches.iloc[0]

        metric_map = {
            "Total Return":  ("total_return",  "total_return",          True),
            "Win Rate":      ("win_rate",       "win_rate",              True),
            "Total Trades":  ("total_trades",   "total_trades",          False),
            "Avg Trade P&L": ("average_pnl",    "average_trade_pnl",     False),
            "Max Drawdown":  ("max_drawdown",   "max_drawdown_percent",  True),
        }

        def _fmt(v, pct: bool) -> str:
            if v is None:
                return "—"
            if pct:
                return f"{float(v):.1%}"
            if isinstance(v, float):
                return f"${v:,.2f}"
            return str(v)

        rows = []
        for label, (lk, bk, is_pct) in metric_map.items():
            lv = live_m.get(lk)
            bv = bt_row[bk] if (bt_row is not None and bk in bt_row.index) else None
            diverged = False
            if lv is not None and bv is not None:
                if lk == "win_rate" and abs(float(lv) - float(bv)) > 0.15:
                    diverged = True
                elif lk == "max_drawdown" and abs(float(lv)) > abs(float(bv)) * 1.5:
                    diverged = True
            rows.append({
                "Metric": label,
                "Live": _fmt(lv, is_pct),
                "Backtest": _fmt(bv, is_pct),
                "Status": "DIVERGED" if diverged else "OK",
            })

        cdf = pd.DataFrame(rows)

        def _highlight_diverged(row: pd.Series):
            if row["Status"] == "DIVERGED":
                return ["background-color: #5c1a1a"] * len(row)
            return [""] * len(row)

        st.dataframe(
            cdf.style.apply(_highlight_diverged, axis=1),
            use_container_width=True, hide_index=True,
        )
        if live_strategy:
            st.caption(f"Comparing live results against backtest for: `{live_strategy}`")
        else:
            st.caption("No live strategy detected yet.")

# ── Tab 5: Risk Status ────────────────────────────────────────────────
with tab_risk:
    st.subheader("Risk Manager Status")
    if kill["killed"]:
        st.error(f"Kill switch ACTIVE — {kill['reason']}")
    else:
        st.success("Kill switch: Not triggered")

    initial_capital    = 100_000.0
    max_daily_loss_pct = 0.05
    daily_pnl_val      = daily.get("daily_pnl") or 0.0
    daily_loss_pct     = abs(min(daily_pnl_val, 0.0)) / initial_capital

    st.write("**Daily Loss Used vs 5% Limit**")
    st.progress(
        min(daily_loss_pct / max_daily_loss_pct, 1.0),
        text=f"{daily_loss_pct:.2%} of {max_daily_loss_pct:.0%} limit used",
    )

    c1, c2 = st.columns(2)
    c1.metric("Trades Opened Today", int(daily.get("trades_opened", 0)))
    c1.caption("Max allowed: 20")
    c2.metric(
        "Wins / Losses Today",
        f"{int(daily.get('wins', 0))} / {int(daily.get('losses', 0))}",
    )

    st.subheader("Kill Switch Event History")
    risk_df = dd.get_risk_events(events)
    if risk_df.empty:
        st.info("No risk events recorded.")
    else:
        st.dataframe(risk_df, use_container_width=True, hide_index=True)

# ── auto-refresh ──────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(30)
    st.rerun()
