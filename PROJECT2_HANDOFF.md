# Project 2 Handoff

Last updated: 2026-03-28

## Scope Completed

Project 2 is implemented for the existing Python project `quant-trading-system`.

Built:

- Reusable strategy base class with JSON serialization
- Ten independently testable strategy modules
- Backtest engine with trade tracking, equity curve generation, and metrics
- Comparator and ranking utilities
- Text and HTML reporting
- CLI runner for multi-symbol backtests
- Strategy test suite

## Key Files

Core implementation:

- `strategies/base.py`
- `strategies/indicator_utils.py`
- `strategies/ma_crossover.py`
- `strategies/rsi_mean_reversion.py`
- `strategies/bollinger_band.py`
- `strategies/donchian_breakout.py`
- `strategies/macd_trend.py`
- `strategies/trend_delta.py`
- `strategies/momentum.py`
- `strategies/vwap_reversion.py`
- `strategies/engulfing.py`
- `strategies/pairs_mean_reversion.py`
- `backtester/engine.py`
- `backtester/comparator.py`
- `run_backtest.py`
- `tests/test_strategies.py`

Exports:

- `strategies/__init__.py`
- `backtester/__init__.py`

## Design Notes

- Existing Project 1 data pipeline is reused through `data.storage.DataStore`.
- Library code uses `logging`, not `print`.
- `pandas-ta` is used when available, with pandas-based fallbacks in `strategies/indicator_utils.py`.
- Strategies emit action signals:
  - `1` = buy / enter long / cover short
  - `-1` = sell / exit long / enter short
  - `0` = hold
- Engine behavior:
  - Opposite signal closes an existing position.
  - New entries are only opened from flat.
  - In long-only mode, short-entry signals are ignored.
- `risk_per_trade` is implemented as position sizing based on current equity, not stop-distance risk.
- The pairs strategy uses a synthetic ratio series via `Close / PairClose`; it is not a full dollar-neutral two-leg portfolio model.

## Default Strategy Suite

Configured in `run_backtest.py`:

1. `MACrossoverStrategy`
2. `RSIMeanReversionStrategy`
3. `BollingerBandStrategy`
4. `DonchianBreakoutStrategy`
5. `MACDTrendStrategy`
6. `TrendDeltaStrategy`
7. `MomentumStrategy`
8. `VWAPReversionStrategy`
9. `EngulfingStrategy`
10. `PairsMeanReversionStrategy`

Default pair mapping currently includes:

- `SPY -> IVV`
- `IVV -> SPY`
- `VOO -> SPY`
- `QQQ -> QQQM`
- `QQQM -> QQQ`
- `IWM -> VTWO`
- `VTWO -> IWM`
- `GLD -> IAU`
- `TLT -> IEF`

## Test Status

Executed on 2026-03-28:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

Result:

- `19 passed`

Notes:

- Third-party deprecation warning observed from `pandas_ta`
- No failing tests

## Full SPY Backtest Run

Executed on 2026-03-28:

```powershell
.\.venv\Scripts\python.exe run_backtest.py --symbols SPY --start 2020-01-01 --end 2025-12-31
```

Run settings:

- Initial capital: `100000`
- Commission: `0.001`
- Slippage: `0.0005`
- Risk per trade: `0.02`
- Mode: long-only

## SPY Comparison Summary

| Strategy | Total Return | Annual Return | Sharpe | Max DD | Trades | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `rsi_mean_reversion` | 1.0139% | 0.1685% | 0.5478 | 0.5765% | 15 | Best ranked overall |
| `vwap_reversion` | 1.0188% | 0.1693% | 0.5195 | 0.5331% | 35 | Best raw return |
| `ma_crossover` | 0.9314% | 0.1548% | 0.5970 | 0.7484% | 13 | Best Sharpe |
| `bollinger_band` | 0.8819% | 0.1466% | 0.4706 | 0.5765% | 35 | Solid mean-reversion |
| `momentum` | 0.7653% | 0.1273% | 0.5615 | 0.5603% | 24 | Reasonable balance |
| `donchian_breakout` | 0.7427% | 0.1235% | 0.4834 | 0.3800% | 34 | Lowest drawdown among profitable set |
| `trend_delta` | 0.6141% | 0.1022% | 0.3940 | 0.4147% | 53 | Works but weak edge |
| `macd_trend` | 0.2159% | 0.0360% | 0.1864 | 0.4167% | 66 | Weak |
| `engulfing` | 0.1938% | 0.0323% | 0.1409 | 0.7368% | 66 | Weak |
| `pairs_mean_reversion` | -0.0541% | -0.0090% | -0.6814 | 0.0541% | 16 | Weakest |

## Weak Strategies / Assumptions / Issues

Weakest strategies from the SPY run:

- `pairs_mean_reversion`
- `macd_trend`
- `engulfing`

Assumptions worth remembering:

- Pairs strategy is a simplified synthetic-ratio backtest.
- Long-only was used for the SPY run.
- Strategy defaults have not been optimized.
- Returns are modest because exposure per trade is capped at 2% of equity.

Observed warnings:

- `yfinance` emitted a Pandas deprecation warning internally.
- `pandas_ta` emitted a Pandas copy-on-write deprecation warning internally.

No internal code failures were encountered during the full run.

## Saved Output Files

Generated on 2026-03-28:

- `reports/backtest_SPY_2020-01-01_2025-12-31_20260328_225533_comparison.csv`
- `reports/backtest_SPY_2020-01-01_2025-12-31_20260328_225533_metrics.json`
- `reports/backtest_SPY_2020-01-01_2025-12-31_20260328_225533_equity_curves.csv`
- `reports/backtest_SPY_2020-01-01_2025-12-31_20260328_225533_report.txt`
- `reports/backtest_SPY_2020-01-01_2025-12-31_20260328_225533_report.html`

## Quick Resume Prompts

Good follow-up instructions after clearing context:

- "Optimize the best 3 strategies on SPY and update the reports."
- "Add portfolio-level backtesting across multiple symbols."
- "Upgrade the pairs strategy to model both legs explicitly."
- "Add stop-loss, take-profit, and ATR position sizing."
- "Run the suite in long-short mode and compare against long-only."
