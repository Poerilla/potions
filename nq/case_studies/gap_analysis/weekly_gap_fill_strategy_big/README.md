# NQ Big Weekly Gap-Fill Strategy

Rules: big weekly gaps only; 1-hour break-in close must be at least halfway to the prior weekly RTH close; then a limit at the break-in close is placed after that candle closes. Max two filled attempts per week. Size is 5 units: 1 off halfway to TP1, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1. Stop is the break-in candle low for longs or high for shorts.

Point value used: $20.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 143 | $43,622.50 | $-97,110.00 | 39.9% | 1.11 | $305.05 | 64.45 | 98.41 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| EOW | 10 | $69,077.50 | $6,907.75 |
| Stop | 103 | $-364,015.00 | $-3,534.13 |
| TP2 | 30 | $338,560.00 | $11,285.33 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 79 | $123,712.50 | $1,565.98 |
| Short | 64 | $-80,090.00 | $-1,251.41 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| gap_filled_before_break_in | 103 |
| no_qualifying_break_in | 72 |
| gap_filled_before_limit | 1 |

## Files

- `gap_fill_trades.csv`
- `gap_fill_skips.csv`
- `charts/INDEX.md`
