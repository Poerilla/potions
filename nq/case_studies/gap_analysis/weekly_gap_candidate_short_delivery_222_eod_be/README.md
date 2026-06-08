# NQ Big Weekly Gap Delivery-Change Strategy

Rules: big weekly gaps only; wait for completed 1-hour delivery structure before placing the pullback limit. `swing-sequence` mode places the order after swing high -> swing low for longs, or swing low -> swing high for shorts. `break-close` mode waits for the older higher-high/lower-low close-through trigger.

Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run.

Variant settings: entry mode = `break-close`; scaleout mode = `two_two_two_eod_be`; max attempts per day = `2`; max filled trades per week = `99`.

Point value used: $20.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 58 | $34,570.00 | $-51,945.00 | 37.9% | 1.21 | $596.03 | 37.87 | 82.91 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| BE Stop | 2 | $19,320.00 | $9,660.00 |
| EOD | 23 | $160,685.00 | $6,986.30 |
| Stop | 33 | $-145,435.00 | $-4,407.12 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Short | 58 | $34,570.00 | $596.03 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| gap_filled_before_delivery_change | 124 |
| no_delivery_change | 74 |
| gap_filled_before_limit | 45 |
| limit_not_filled | 10 |

## Files

- `gap_delivery_trades.csv`
- `gap_delivery_skips.csv`
- `charts/INDEX.md` when charts are enabled
