# MNQ Big Weekly Gap-Fill Strategy

Rules: big weekly gaps only; 1-hour break-in close must be at least halfway to the prior weekly RTH close; then a limit at the break-in close is placed after that candle closes. Max two filled attempts per week. Size is 5 units: 1 off halfway to TP1, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1. Stop is the break-in candle low for longs or high for shorts.

Point value used: $2.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 91 | $2,047.25 | $-11,180.25 | 39.6% | 1.06 | $22.50 | 82.98 | 132.03 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| EOW | 7 | $8,059.00 | $1,151.29 |
| Stop | 69 | $-32,945.50 | $-477.47 |
| TP2 | 15 | $26,933.75 | $1,795.58 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 46 | $9,854.25 | $214.22 |
| Short | 45 | $-7,807.00 | $-173.49 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| no_qualifying_break_in | 34 |
| gap_filled_before_break_in | 29 |
| gap_filled_before_limit | 1 |

## Files

- `gap_fill_trades.csv`
- `gap_fill_skips.csv`
- `charts/INDEX.md`
