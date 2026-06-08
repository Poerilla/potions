# MNQ Big Weekly Gap Delivery-Change Strategy

Rules: big weekly gaps only; wait for completed 1-hour delivery structure before placing the pullback limit. `swing-sequence` mode places the order after swing high -> swing low for longs, or swing low -> swing high for shorts. `break-close` mode waits for the older higher-high/lower-low close-through trigger.

Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run. Size is 5 units: 1 off halfway, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1.

Variant settings: entry mode = `swing-sequence`; max attempts per day = `3`; max filled trades per week = `3`.

Point value used: $2.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 187 | $-110,960.50 | $-121,620.00 | 12.3% | 0.34 | $-593.37 | 112.20 | 86.04 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| EOW | 12 | $29,003.00 | $2,416.92 |
| Stop | 166 | $-164,978.00 | $-993.84 |
| TP2 | 9 | $25,014.50 | $2,779.39 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 66 | $-54,234.50 | $-821.73 |
| Short | 121 | $-56,726.00 | $-468.81 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| gap_filled_before_delivery_change | 48 |
| max_week_trades_reached | 47 |
| no_delivery_change | 2 |
| gap_filled_before_limit | 2 |
| limit_not_filled | 1 |

## Files

- `gap_delivery_trades.csv`
- `gap_delivery_skips.csv`
- `charts/INDEX.md` when charts are enabled
