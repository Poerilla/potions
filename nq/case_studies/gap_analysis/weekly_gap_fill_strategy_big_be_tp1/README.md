# NQ Big Weekly Gap-Fill Strategy

Rules: big weekly gaps only; 1-hour break-in close must be at least halfway to the prior weekly RTH close; then a limit at the break-in close is placed after that candle closes. Max two filled attempts per week. Size is 5 units: 1 off halfway to TP1, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1. Stop is the break-in candle low for longs or high for shorts.

Variant settings: stop mode = `break-candle`; move remaining stop to breakeven after TP1 = `True`; 1-hour close back outside gap boundary exit = `False`.

Point value used: $20.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 143 | $9,472.50 | $-106,880.00 | 51.7% | 1.02 | $66.24 | 48.53 | 80.38 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| BE Stop | 55 | $164,325.00 | $2,987.73 |
| EOW | 6 | $36,590.00 | $6,098.33 |
| Stop | 68 | $-364,080.00 | $-5,354.12 |
| TP2 | 14 | $172,637.50 | $12,331.25 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 79 | $89,392.50 | $1,131.55 |
| Short | 64 | $-79,920.00 | $-1,248.75 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| gap_filled_before_break_in | 103 |
| no_qualifying_break_in | 72 |
| gap_filled_before_limit | 1 |

## Files

- `gap_fill_trades.csv`
- `gap_fill_skips.csv`
- `charts/INDEX.md` when charts are enabled
