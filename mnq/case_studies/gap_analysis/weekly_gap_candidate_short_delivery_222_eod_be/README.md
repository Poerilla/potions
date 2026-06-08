# MNQ Big Weekly Gap Delivery-Change Strategy

Rules: big weekly gaps only; wait for completed 1-hour delivery structure before placing the pullback limit. `swing-sequence` mode places the order after swing high -> swing low for longs, or swing low -> swing high for shorts. `break-close` mode waits for the older higher-high/lower-low close-through trigger.

Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run.

Variant settings: entry mode = `break-close`; scaleout mode = `two_two_two_eod_be`; max attempts per day = `2`; max filled trades per week = `99`.

Point value used: $2.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 37 | $4,568.50 | $-2,946.00 | 40.5% | 1.42 | $123.47 | 43.28 | 101.02 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| BE Stop | 1 | $1,146.00 | $1,146.00 |
| EOD | 16 | $12,323.00 | $770.19 |
| Stop | 20 | $-8,900.50 | $-445.02 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Short | 37 | $4,568.50 | $123.47 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| gap_filled_before_delivery_change | 47 |
| no_delivery_change | 37 |
| gap_filled_before_limit | 22 |
| limit_not_filled | 7 |

## Files

- `gap_delivery_trades.csv`
- `gap_delivery_skips.csv`
- `charts/INDEX.md` when charts are enabled
