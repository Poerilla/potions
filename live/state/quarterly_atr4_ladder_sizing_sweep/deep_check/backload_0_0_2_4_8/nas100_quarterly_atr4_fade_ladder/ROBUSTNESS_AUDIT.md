# NAS100 quarterly ATR4 fade ladder 0/0/2/4/8 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 9 |
| Net | $93496.68 |
| Campaign closed DD | $-7004.90 |
| Win rate | 33.33% |
| Profit factor | 9.454 |
| Avg trade | $10388.52 |
| Median trade | $-909.02 |
| Max losing streak | 5 |
| Full initial SL losses | 6 (66.7%) |
| Hit TP (any) | 33.3% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2017: $-663.74 net, -1.00 N/S.
- Full initial SL share is high (66.7%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $93496.68 |
| Top 10 share of net | 100.00% |
| Worst 10 losers net | $93496.68 |
| Worst 10 share of |net| | 100.00% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $15.40 |
| Gap-through beyond 1 tick | $7.00 |
| Filled stop count | 6 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 7129 |
| Max recovery calendar days | 1680 |
| Unresolved recovery days | 92 |
| Bars in close-equity DD | 94.27% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2017.00 |     1.00 |   -663.74 |         -663.77 |             -1.00 |           0.00 |            0.00 |                    -0.01 |
| 2018.00 |     1.00 |   -909.02 |        -2653.00 |             -0.34 |           0.00 |            0.00 |                    -0.01 |
| 2021.00 |     1.00 |  -1275.54 |        -1584.80 |             -0.80 |           0.00 |            0.00 |                    -0.01 |
| 2022.00 |     2.00 |  -4820.34 |        -5619.35 |             -0.86 |           0.00 |            0.00 |                    -0.05 |
| 2023.00 |     1.00 |  22233.90 |        -3958.40 |              5.62 |         100.00 |          inf    |                     0.24 |
| 2024.00 |     2.00 |  15629.66 |        -5136.00 |              3.04 |          50.00 |            5.61 |                     0.14 |
| 2025.00 |     1.00 |  63301.76 |       -16957.20 |              3.73 |         100.00 |          inf    |                     0.49 |

## Rolling stability (50)

- Windows: 0
- Worst rolling PF: 0.000
- Worst rolling Net/closed-DD: 0.00
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |   net_usd |   avg_unit |
|:--------------|--------:|----------:|-----------:|
| flatten       |      24 |  83109.20 |    3462.88 |
| tp4           |      12 |  15677.76 |    1306.48 |
| tp3           |       6 |   5768.74 |     961.46 |
| stop          |      84 | -11059.02 |    -131.66 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |        3 |  -2848.30 |           0.00 |            0.00 |     -949.43 |        -2184.56 |                -1.30 |
| Q2               |        2 |  41253.94 |         100.00 |          inf    |    20626.97 |            0.00 |                 0.00 |
| Q3               |        2 |  -4820.34 |           0.00 |            0.00 |    -2410.17 |        -2681.42 |                -1.80 |
| Q4 high          |        2 |  59911.38 |          50.00 |           18.67 |    29955.69 |            0.00 |                 0.00 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
