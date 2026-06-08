# NQ Big Weekly Gap-Fill Strategy

Rules: big weekly gaps only; 1-hour break-in close must be at least halfway to the prior weekly RTH close; then a limit at the break-in close is placed after that candle closes. Max two filled attempts per week. Size is 5 units: 1 off halfway to TP1, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1. Stop is the break-in candle low for longs or high for shorts.

Variant settings: stop mode = `swing`; move remaining stop to breakeven after TP1 = `True`; 1-hour close back outside gap boundary exit = `True`.

Point value used: $20.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 99 | $-33,297.50 | $-133,290.00 | 60.6% | 0.91 | $-336.34 | 67.11 | 92.33 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| BE Stop | 42 | $139,962.50 | $3,332.44 |
| BoundaryClose | 17 | $-175,595.00 | $-10,329.12 |
| EOW | 6 | $47,662.50 | $7,943.75 |
| Stop | 21 | $-182,975.00 | $-8,713.10 |
| TP2 | 13 | $137,647.50 | $10,588.27 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 54 | $30,835.00 | $571.02 |
| Short | 45 | $-64,132.50 | $-1,425.17 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| gap_filled_before_break_in | 124 |
| no_confirmed_swing_stop | 72 |
| no_qualifying_break_in | 71 |
| no_valid_or_filled_candidate | 4 |
| limit_not_filled | 1 |
| gap_filled_before_limit | 1 |

## Files

- `gap_fill_trades.csv`
- `gap_fill_skips.csv`
- `charts/INDEX.md` when charts are enabled
