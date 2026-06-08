# MNQ Big Weekly Gap Delivery-Change Strategy

Rules: big weekly gaps only; wait for completed 1-hour delivery structure before placing the pullback limit. `swing-sequence` mode places the order after swing high -> swing low for longs, or swing low -> swing high for shorts. `break-close` mode waits for the older higher-high/lower-low close-through trigger.

Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run.

Variant settings: entry mode = `break-close`; scaleout mode = `half3_tp1_2`; max attempts per day = `2`; max filled trades per week = `99`.

Point value used: $2.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 60 | $3,521.25 | $-8,457.50 | 43.3% | 1.13 | $58.69 | 73.92 | 130.46 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| EOW | 3 | $2,453.25 | $817.75 |
| Stop | 43 | $-21,403.75 | $-497.76 |
| TP1 | 14 | $22,471.75 | $1,605.12 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 27 | $-4,862.00 | $-180.07 |
| Short | 33 | $8,383.25 | $254.04 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| gap_filled_before_delivery_change | 45 |
| no_delivery_change | 35 |
| gap_filled_before_limit | 18 |
| limit_not_filled | 6 |

## Files

- `gap_delivery_trades.csv`
- `gap_delivery_skips.csv`
- `charts/INDEX.md` when charts are enabled
