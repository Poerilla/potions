# MNQ Big Weekly Gap-Fill Strategy

Rules: big weekly gaps only; 1-hour break-in close must be at least halfway to the prior weekly RTH close; then a limit at the break-in close is placed after that candle closes. Max two filled attempts per week. Size is 5 units: 1 off halfway to TP1, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1. Stop is the break-in candle low for longs or high for shorts.

Variant settings: stop mode = `swing`; move remaining stop to breakeven after TP1 = `True`; 1-hour close back outside gap boundary exit = `True`.

Point value used: $2.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 60 | $-6,829.25 | $-12,886.75 | 56.7% | 0.79 | $-113.82 | 96.82 | 127.45 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| BE Stop | 25 | $12,330.00 | $493.20 |
| BoundaryClose | 11 | $-14,642.50 | $-1,331.14 |
| EOW | 4 | $4,198.50 | $1,049.62 |
| Stop | 14 | $-17,748.00 | $-1,267.71 |
| TP2 | 6 | $9,032.75 | $1,505.46 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 30 | $631.25 | $21.04 |
| Short | 30 | $-7,460.50 | $-248.68 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| no_confirmed_swing_stop | 49 |
| gap_filled_before_break_in | 41 |
| no_qualifying_break_in | 34 |
| no_valid_or_filled_candidate | 3 |
| limit_not_filled | 1 |
| gap_filled_before_limit | 1 |

## Files

- `gap_fill_trades.csv`
- `gap_fill_skips.csv`
- `charts/INDEX.md` when charts are enabled
