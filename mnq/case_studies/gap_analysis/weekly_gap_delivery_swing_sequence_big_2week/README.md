# MNQ Big Weekly Gap Delivery-Change Strategy

Rules: big weekly gaps only; wait for completed 1-hour delivery structure before placing the pullback limit. `swing-sequence` mode places the order after swing high -> swing low for longs, or swing low -> swing high for shorts. `break-close` mode waits for the older higher-high/lower-low close-through trigger.

Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run. Size is 5 units: 1 off halfway, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1.

Variant settings: entry mode = `swing-sequence`; max attempts per day = `3`; max filled trades per week = `2`.

Point value used: $2.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 140 | $-75,791.00 | $-81,789.25 | 13.6% | 0.36 | $-541.36 | 107.26 | 86.62 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| EOW | 8 | $15,683.75 | $1,960.47 |
| Stop | 123 | $-116,489.25 | $-947.07 |
| TP2 | 9 | $25,014.50 | $2,779.39 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 51 | $-43,108.75 | $-845.27 |
| Short | 89 | $-32,682.25 | $-367.22 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| max_week_trades_reached | 63 |
| gap_filled_before_delivery_change | 43 |
| gap_filled_before_limit | 2 |

## Files

- `gap_delivery_trades.csv`
- `gap_delivery_skips.csv`
- `charts/INDEX.md` when charts are enabled
