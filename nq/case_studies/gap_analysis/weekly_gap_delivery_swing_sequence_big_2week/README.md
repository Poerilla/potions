# NQ Big Weekly Gap Delivery-Change Strategy

Rules: big weekly gaps only; wait for completed 1-hour delivery structure before placing the pullback limit. `swing-sequence` mode places the order after swing high -> swing low for longs, or swing low -> swing high for shorts. `break-close` mode waits for the older higher-high/lower-low close-through trigger.

Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run. Size is 5 units: 1 off halfway, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1.

Variant settings: entry mode = `swing-sequence`; max attempts per day = `3`; max filled trades per week = `2`.

Point value used: $20.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 289 | $-1,282,322.50 | $-1,282,322.50 | 12.8% | 0.32 | $-4,437.10 | 79.09 | 55.17 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| EOW | 9 | $159,992.50 | $17,776.94 |
| Stop | 261 | $-1,836,837.50 | $-7,037.69 |
| TP2 | 19 | $394,522.50 | $20,764.34 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 100 | $-604,632.50 | $-6,046.32 |
| Short | 189 | $-677,690.00 | $-3,585.66 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| max_week_trades_reached | 130 |
| gap_filled_before_delivery_change | 113 |
| gap_filled_before_limit | 2 |

## Files

- `gap_delivery_trades.csv`
- `gap_delivery_skips.csv`
- `charts/INDEX.md` when charts are enabled
