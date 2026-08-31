# NAS100 best-path first_lower — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 9 |
| Net | $33127.04 |
| Campaign closed DD | $-3805.87 |
| Win rate | 33.33% |
| Profit factor | 6.031 |
| Avg trade | $3680.78 |
| Median trade | $-357.37 |
| Max losing streak | 5 |
| Full initial SL losses | 3 (33.3%) |
| Hit TP (any) | 66.7% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2017: $-357.37 net, -1.00 N/S.
- Full initial SL share is high (33.3%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $33127.04 |
| Top 10 share of net | 100.00% |
| Worst 10 losers net | $33127.04 |
| Worst 10 share of |net| | 100.00% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $9.90 |
| Gap-through beyond 1 tick | $4.50 |
| Filled stop count | 6 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 7142 |
| Max recovery calendar days | 1682 |
| Unresolved recovery days | 92 |
| Bars in close-equity DD | 94.33% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2017.00 |     1.00 |   -357.37 |         -357.37 |             -1.00 |           0.00 |            0.00 |                    -0.00 |
| 2018.00 |     1.00 |   -236.83 |        -1516.00 |             -0.16 |           0.00 |            0.00 |                    -0.00 |
| 2021.00 |     1.00 |   -911.08 |        -1132.00 |             -0.80 |           0.00 |            0.00 |                    -0.01 |
| 2022.00 |     2.00 |  -2657.96 |        -3738.00 |             -0.71 |           0.00 |            0.00 |                    -0.03 |
| 2023.00 |     1.00 |   7714.85 |        -1164.40 |              6.63 |         100.00 |          inf    |                     0.08 |
| 2024.00 |     2.00 |   3790.00 |        -3488.00 |              1.09 |          50.00 |            2.57 |                     0.04 |
| 2025.00 |     1.00 |  25785.43 |        -5728.20 |              4.50 |         100.00 |          inf    |                     0.24 |

## Rolling stability (50)

- Windows: 0
- Worst rolling PF: 0.000
- Worst rolling Net/closed-DD: 0.00
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |   net_usd |   avg_unit |
|:--------------|--------:|----------:|-----------:|
| flatten       |       6 |  20777.30 |    3462.88 |
| tp4           |       6 |   7838.88 |    1306.48 |
| tp3           |       6 |   5768.74 |     961.46 |
| tp2           |       6 |   3698.60 |     616.43 |
| tp1           |      12 |   2335.14 |     194.60 |
| stop          |      54 |  -7291.56 |    -135.03 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |        3 |  -1505.28 |           0.00 |            0.00 |     -501.76 |        -1147.91 |                -1.31 |
| Q2               |        2 |  13926.55 |         100.00 |          inf    |     6963.27 |            0.00 |                 0.00 |
| Q3               |        2 |  -2657.96 |           0.00 |            0.00 |    -1328.98 |        -1130.14 |                -2.35 |
| Q4 high          |        2 |  23363.73 |          50.00 |           10.65 |    11681.87 |            0.00 |                 0.00 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
