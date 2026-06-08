# NQ Big Weekly Gap Delivery-Change Strategy

Rules: big weekly gaps only; wait for completed 1-hour delivery structure before placing the pullback limit. `swing-sequence` mode places the order after swing high -> swing low for longs, or swing low -> swing high for shorts. `break-close` mode waits for the older higher-high/lower-low close-through trigger.

Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run.

Variant settings: entry mode = `break-close`; scaleout mode = `half3_tp1_2`; max attempts per day = `2`; max filled trades per week = `99`.

Point value used: $20.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 53 | $69,242.50 | $-44,047.50 | 39.6% | 1.46 | $1,306.46 | 45.67 | 93.39 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| EOW | 3 | $24,732.50 | $8,244.17 |
| Stop | 37 | $-123,210.00 | $-3,330.00 |
| TP1 | 13 | $167,720.00 | $12,901.54 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Short | 53 | $69,242.50 | $1,306.46 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| gap_filled_before_delivery_change | 123 |
| no_delivery_change | 72 |
| gap_filled_before_limit | 39 |
| limit_not_filled | 9 |

## Files

- `gap_delivery_trades.csv`
- `gap_delivery_skips.csv`
- `charts/INDEX.md` when charts are enabled
