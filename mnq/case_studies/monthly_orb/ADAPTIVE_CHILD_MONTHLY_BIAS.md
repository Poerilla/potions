# Adaptive child vs monthly ORB bias

Bias rule used here is causal: after the first 3 daily bars of a month, the next RTH session uses the prior daily close versus that monthly opening range.

- Prior close above monthly OR high: bullish bias, keep Long v2b trades.
- Prior close below monthly OR low: bearish bias, keep Short v2b trades.
- Prior close inside the monthly OR, or while the range is still building: skip v2b trades.
- v2d rows are left unchanged in the full-adaptive comparison; the filter is only applied to v2b rows.

## Headline

- v2b-only filter kept 416 of 1,437 trades and removed 1,021.
- Dropped v2b trades had combined net $11,695.00.
- v2b-only net changed by $-11,695.00.
- Full adaptive net changed by $-11,695.00 because v2d trades were retained.
- Opposed-only v2b trades were stronger than aligned-only in this sample: $12,414.00 vs $7,368.00.
- The cleaner variant was not directional alignment; it was skipping v2b while the prior close was still inside the monthly range. That full-adaptive outside-only version changed net by $719.00.

## Metrics

| Segment | Trades | Days | Net | Trade DD | Daily DD | Win rate | PF | Avg/trade | Median |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full adaptive baseline | 1920 | 1284 | $22,020.00 | $-5,411.50 | $-5,379.50 | 49.69% | 1.14 | $11.47 | $-1.75 |
| full adaptive, v2b monthly aligned only | 899 | 739 | $10,325.00 | $-4,063.00 | $-4,063.00 | 51.17% | 1.14 | $11.48 | $12.00 |
| full adaptive, v2b monthly opposed only | 911 | 751 | $15,371.00 | $-3,720.50 | $-3,720.50 | 51.37% | 1.21 | $16.87 | $22.00 |
| full adaptive, v2b monthly outside only | 1327 | 893 | $22,739.00 | $-4,053.00 | $-4,053.00 | 51.24% | 1.22 | $17.14 | $14.00 |
| v2b only baseline | 1437 | 961 | $19,063.00 | $-5,442.00 | $-5,410.00 | 49.13% | 1.16 | $13.27 | $-6.50 |
| v2b aligned only | 416 | 416 | $7,368.00 | $-3,158.00 | $-3,158.00 | 50.96% | 1.23 | $17.71 | $9.25 |
| v2b opposed only | 428 | 428 | $12,414.00 | $-2,537.00 | $-2,537.00 | 51.40% | 1.40 | $29.00 | $18.50 |
| v2b monthly outside only | 844 | 570 | $19,782.00 | $-2,297.50 | $-1,963.50 | 51.18% | 1.31 | $23.44 | $10.00 |
| v2b dropped by monthly filter | 1021 | 819 | $11,695.00 | $-6,312.50 | $-6,312.50 | 48.38% | 1.13 | $11.45 | $-8.50 |
| v2d retained unchanged | 483 | 323 | $2,957.00 | $-4,763.50 | $-4,763.50 | 51.35% | 1.07 | $6.12 | $26.50 |

## Kept v2b trades by direction and bias

| Trade_Direction | monthly_bias | trades | days | net_usd | win_rate | avg_trade_usd |
| --- | --- | --- | --- | --- | --- | --- |
| Long | bullish | 297 | 297 | $4,990.50 | 51.85% | $16.80 |
| Short | bearish | 119 | 119 | $2,377.50 | 48.74% | $19.98 |

## Dropped v2b trades by filter state

| bias_alignment | monthly_bias | Trade_Direction | trades | days | net_usd | win_rate | avg_trade_usd |
| --- | --- | --- | --- | --- | --- | --- | --- |
| opposed | bullish | Short | 294 | 294 | $9,833.50 | 53.74% | $33.45 |
| opposed | bearish | Long | 134 | 134 | $2,580.50 | 46.27% | $19.26 |
| neutral | neutral | Short | 215 | 215 | $868.00 | 46.51% | $4.04 |
| neutral | neutral | Long | 218 | 218 | $812.00 | 45.41% | $3.72 |
| building_range | building_range | Short | 76 | 76 | $-1,133.50 | 46.05% | $-14.91 |
| building_range | building_range | Long | 84 | 84 | $-1,265.50 | 47.62% | $-15.07 |

## All adaptive rows by monthly bias

| Regime | bias_alignment | monthly_bias | trades | days | net_usd | win_rate | avg_trade_usd |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2b | opposed | bullish | 294 | 294 | $9,833.50 | 53.74% | $33.45 |
| v2b | aligned | bullish | 297 | 297 | $4,990.50 | 51.85% | $16.80 |
| v2b | opposed | bearish | 134 | 134 | $2,580.50 | 46.27% | $19.26 |
| v2b | aligned | bearish | 119 | 119 | $2,377.50 | 48.74% | $19.98 |
| v2d | building_range | building_range | 58 | 36 | $1,700.00 | 58.62% | $29.31 |
| v2b | neutral | neutral | 433 | 287 | $1,680.00 | 45.96% | $3.88 |
| v2d | neutral | neutral | 141 | 94 | $1,365.00 | 50.35% | $9.68 |
| v2d | aligned | bullish | 67 | 67 | $1,194.00 | 55.22% | $17.82 |
| v2d | aligned | bearish | 66 | 66 | $361.00 | 56.06% | $5.47 |
| v2d | opposed | bearish | 73 | 73 | $-157.50 | 49.32% | $-2.16 |
| v2d | opposed | bullish | 78 | 78 | $-1,505.50 | 42.31% | $-19.30 |
| v2b | building_range | building_range | 160 | 104 | $-2,399.00 | 46.88% | $-14.99 |

## Outputs

- Annotated trades: [adaptive_child_monthly_bias_annotated.csv](adaptive_child_monthly_bias_annotated.csv)
- Daily monthly-bias table: [monthly_bias_by_day.csv](monthly_bias_by_day.csv)
