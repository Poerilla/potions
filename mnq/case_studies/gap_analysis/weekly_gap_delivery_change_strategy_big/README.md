# MNQ Big Weekly Gap Delivery-Change Strategy

Rules: big weekly gaps only; wait for a completed 1-hour delivery change before placing the pullback limit. Long pattern is swing high -> swing low -> higher high with a close above the prior swing high. Short pattern is swing low -> swing high -> lower low with a close below the prior swing low.

Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run. Size is 5 units: 1 off halfway, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1.

Point value used: $2.00/pt.

## Summary

| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 60 | $192.75 | $-9,003.75 | 28.3% | 1.01 | $3.21 | 75.98 | 154.73 |

## By Exit Reason

| Exit | Trades | Net | Avg |
|---|---:|---:|---:|
| EOW | 8 | $12,243.25 | $1,530.41 |
| Stop | 45 | $-28,245.75 | $-627.68 |
| TP2 | 7 | $16,195.25 | $2,313.61 |

## By Side

| Side | Trades | Net | Avg |
|---|---:|---:|---:|
| Long | 27 | $-9,917.00 | $-367.30 |
| Short | 33 | $10,109.75 | $306.36 |

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
