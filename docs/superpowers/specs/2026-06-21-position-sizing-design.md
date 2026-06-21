# Position-Sizing Rework — Design Spec

> Status: Approved 2026-06-21.
> Goal: one shared, risk-based, ATR-driven sizing model used identically by the backtester and the
> live bot, plus ATR stop/take-profit enforcement in the backtester, so backtest ≈ paper ≈ live.

## Problem

Two incompatible sizing models exist today:
- Backtester (`backtester/engine.py:206`): `notional = equity × risk_per_trade` → ~2% of capital per
  trade. This is why SPY backtest returns are ~1%.
- Live bot (`bot/risk_manager.py:64`): risk-based `shares = (risk_per_trade × capital) / |entry − stop|`,
  capped at 25% of capital. With its 2% fixed stop, the cap binds → ~25% of capital per trade.

They size ~12× differently, so paper-vs-backtest comparison (the whole point of the 30-day gate) is
currently meaningless. This spec unifies them.

## Decisions locked during brainstorming

- **Full fidelity**: unify sizing AND model stops/take-profits in the backtester (not sizing-only).
- **ATR-based stops** (volatility-adaptive), in BOTH backtester and live bot, so the risk knob is
  meaningful and the two match.
- Defaults: `atr_period=14`, `atr_stop_mult=2.0`, `take_profit_r=2.0` (2:1), `risk_per_trade=0.02`,
  `max_position_pct=0.25`.
- **Trailing stops stay OUT of the backtest** for this spec (live keeps its existing trailing). The
  backtest models a fixed ATR stop, making it slightly conservative on big winners vs live — an
  accepted, documented divergence.

## The sizing math (one formula, everywhere)

```
atr        = ATR(atr_period) of recent bars
stop_dist  = atr_stop_mult × atr
stop_price = entry − stop_dist   (long)   /   entry + stop_dist   (short)
tp_price   = entry + take_profit_r × stop_dist   (long)   /   entry − take_profit_r × stop_dist (short)
risk_$     = risk_per_trade × equity
shares     = risk_$ / stop_dist
shares     = min(shares, max_position_pct × equity / entry)        # cap
```

## Components

### `strategies/indicator_utils.py` — add `atr`
`atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series`. Use
`pandas-ta` when available with a pandas-native fallback (true range = max(high−low, |high−prev_close|,
|low−prev_close|); Wilder/EMA smoothing), matching the module's existing try/fallback pattern.

### New `position_sizing.py` (project root — neutral, so neither `backtester/` nor `bot/` depends on the other)
`position_size(equity: float, entry_price: float, stop_price: float, risk_per_trade: float, max_position_pct: float) -> float`
returns share count. Pure, fully unit-testable. Returns `0.0` if `stop_dist <= 0`, `entry_price <= 0`,
or `equity <= 0`. Applies the cap.

### `backtester/engine.py`
- Add constructor knobs: `atr_period=14, atr_stop_mult=2.0, take_profit_r=2.0, max_position_pct=0.25`.
- Compute `atr` once from the prepared OHLC data.
- On entry: compute `stop_dist` from ATR at the entry bar, size via `position_size`, record
  `stop_price` and `tp_price` on the active trade.
- Each subsequent bar, BEFORE signal handling, enforce the bracket intrabar using High/Low:
  - Long: if `Low ≤ stop_price` → exit at `stop_price`; elif `High ≥ tp_price` → exit at `tp_price`.
  - Short: if `High ≥ stop_price` → exit at `stop_price`; elif `Low ≤ tp_price` → exit at `tp_price`.
  - Stop checked before TP (conservative). Commission + slippage apply to bracket fills.
- Signal-based exits still apply when neither bracket level is hit.
- If ATR is NaN at the entry bar (warmup), skip the entry (no position) rather than divide by zero.

### `bot/risk_manager.py`
- `calculate_stop_loss(entry_price, side, atr)` and `calculate_take_profit(entry_price, side, atr)`
  become ATR-based using `atr_stop_mult` / `take_profit_r` from config.
- `calculate_position_size` delegates to the shared `position_sizing.position_size`, using
  `config.max_position_pct` (replaces the hard-coded `0.25`).

### `bot/trading_bot.py`
- Compute ATR from the bars it already fetches each cycle; pass `atr` into the stop/TP/size calls.
- If ATR is unavailable (insufficient bars), skip entry that cycle (logged), do not crash.

### `config/settings.py` + `bot/brokers/base.py` (`BotConfig`)
- Add `atr_period=14, atr_stop_mult=2.0, take_profit_r=2.0, max_position_pct=0.25`.

## Out of scope (deliberate)

- Trailing stops in the backtest (live keeps existing trailing).
- Per-strategy custom stops, multi-position backtests (engine is single-position), short-side changes
  beyond mirroring the long math.

## Error handling

- `position_size` and the ATR warmup paths never divide by zero — guard and return 0 / skip entry.
- ATR helper returns NaN during warmup; callers treat NaN as "cannot size → no trade".

## Testing

- `position_size`: risk-dollar math; cap binding vs not binding; zero/negative stop distance,
  zero equity, zero price → 0.
- `atr`: known small OHLC series → expected values; pandas fallback path (pandas-ta absent).
- Engine: long stopped out exits at `stop_price` (not the later signal); long hitting TP exits at
  `tp_price`; wider ATR → fewer shares; a stop-out loses ≈ `risk_per_trade × equity` (within
  commission/slippage); NaN-ATR warmup bar opens no position.
- `risk_manager`: ATR stop/TP prices and share count match the shared formula and the cap.
- Regression: SPY 2020–2025 before/after; record the new return AND drawdown (bigger positions cut
  both ways — expected, not a bug).

## Expected outcome

Returns and drawdowns both grow substantially vs the 2%-notional baseline; the optimizer/stress-test
layer judges whether the new risk profile is *good*. This spec makes backtest, paper, and live size
trades the same way — the precondition for a meaningful 30-day paper validation.
