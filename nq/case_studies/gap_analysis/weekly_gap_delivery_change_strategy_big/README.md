# NQ Big Weekly Gap Delivery-Change Strategy

Rules: big weekly gaps only; wait for a completed 1-hour delivery change before placing the pullback limit. Long pattern is swing high -> swing low -> higher high with a close above the prior swing high. Short pattern is swing low -> swing high -> lower low with a close below the prior swing low.

Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run. Size is 5 units: 1 off halfway, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1.

Point value used: $20.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 89 | $10,942.50 | $-92,717.50 | 29.2% | 1.03 | $122.95 | 62.28 | 119.92 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| EOW | 9 | $128,120.00 | $14,235.56 |
| Stop | 68 | $-334,257.50 | $-4,915.55 |
| TP2 | 12 | $217,080.00 | $18,090.00 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 36 | $-83,945.00 | $-2,331.81 |
| Short | 53 | $94,887.50 | $1,790.33 |

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
