# NQ Big Weekly Gap-Fill Strategy

Rules: big weekly gaps only; 1-hour break-in close must be at least halfway to the prior weekly RTH close; then a limit at the break-in close is placed after that candle closes. Max two filled attempts per week. Size is 5 units: 1 off halfway to TP1, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1. Stop is the break-in candle low for longs or high for shorts.

Variant settings: stop mode = `break-candle`; move remaining stop to breakeven after TP1 = `True`; 1-hour close back outside gap boundary exit = `True`.

Point value used: $20.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 145 | $120.00 | $-109,932.50 | 48.3% | 1.00 | $0.83 | 45.21 | 78.04 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| BE Stop | 53 | $162,162.50 | $3,059.67 |
| BoundaryClose | 9 | $-78,220.00 | $-8,691.11 |
| EOW | 4 | $51,105.00 | $12,776.25 |
| Stop | 66 | $-299,120.00 | $-4,532.12 |
| TP2 | 13 | $164,192.50 | $12,630.19 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 81 | $87,750.00 | $1,083.33 |
| Short | 64 | $-87,630.00 | $-1,369.22 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| gap_filled_before_break_in | 105 |
| no_qualifying_break_in | 73 |
| gap_filled_before_limit | 1 |

## Files

- `gap_fill_trades.csv`
- `gap_fill_skips.csv`
- `charts/INDEX.md` when charts are enabled
