# NQ Big Weekly Gap Delivery-Change Strategy

Rules: big weekly gaps only; wait for completed 1-hour delivery structure before placing the pullback limit. `swing-sequence` mode places the order after swing high -> swing low for longs, or swing low -> swing high for shorts. `break-close` mode waits for the older higher-high/lower-low close-through trigger.

Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run. Size is 5 units: 1 off halfway, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1.

Variant settings: entry mode = `swing-sequence`; max attempts per day = `3`; max filled trades per week = `3`.

Point value used: $20.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 386 | $-1,873,592.50 | $-1,873,592.50 | 11.9% | 0.28 | $-4,853.87 | 80.88 | 53.19 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| EOW | 15 | $236,602.50 | $15,773.50 |
| Stop | 349 | $-2,538,865.00 | $-7,274.68 |
| TP2 | 22 | $428,670.00 | $19,485.00 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 130 | $-787,680.00 | $-6,059.08 |
| Short | 256 | $-1,085,912.50 | $-4,241.85 |

## Skips / No Trade Reasons

| Reason | Count |
|---|---:|
| gap_filled_before_delivery_change | 123 |
| max_week_trades_reached | 97 |
| gap_filled_before_limit | 5 |
| limit_not_filled | 3 |
| no_delivery_change | 2 |

## Files

- `gap_delivery_trades.csv`
- `gap_delivery_skips.csv`
- `charts/INDEX.md` when charts are enabled
