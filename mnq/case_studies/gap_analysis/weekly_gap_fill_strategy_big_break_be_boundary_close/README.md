# MNQ Big Weekly Gap-Fill Strategy

Rules: big weekly gaps only; 1-hour break-in close must be at least halfway to the prior weekly RTH close; then a limit at the break-in close is placed after that candle closes. Max two filled attempts per week. Size is 5 units: 1 off halfway to TP1, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1. Stop is the break-in candle low for longs or high for shorts.

Variant settings: stop mode = `break-candle`; move remaining stop to breakeven after TP1 = `True`; 1-hour close back outside gap boundary exit = `True`.

Point value used: $2.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 91 | $-50.75 | $-12,054.25 | 45.1% | 1.00 | $-0.56 | 61.96 | 109.05 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| BE Stop | 32 | $14,997.50 | $468.67 |
| BoundaryClose | 4 | $-5,235.00 | $-1,308.75 |
| EOW | 3 | $4,790.75 | $1,596.92 |
| Stop | 46 | $-28,210.00 | $-613.26 |
| TP2 | 6 | $13,606.00 | $2,267.67 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 46 | $8,132.75 | $176.80 |
| Short | 45 | $-8,183.50 | $-181.86 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| no_qualifying_break_in | 34 |
| gap_filled_before_break_in | 29 |
| gap_filled_before_limit | 1 |

## Files

- `gap_fill_trades.csv`
- `gap_fill_skips.csv`
- `charts/INDEX.md` when charts are enabled
