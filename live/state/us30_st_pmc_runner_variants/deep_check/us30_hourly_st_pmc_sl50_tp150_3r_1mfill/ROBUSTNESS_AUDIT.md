# US30 ST+PMC 3R (1m fill broker) — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 578 |
| Net | $19027.57 |
| Campaign closed DD | $-430.52 |
| Win rate | 42.56% |
| Profit factor | 2.087 |
| Avg trade | $32.92 |
| Median trade | $-51.60 |
| Max losing streak | 8 |
| Full initial SL losses | 332 (57.4%) |
| Hit TP (any) | 0.0% |
| EOD / flatten | 0.0% |

## Fragility

- Weakest year is 2016: $445.50 net, 0.00 N/S.
- Full initial SL share is high (57.4%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $1485.00 |
| Top 10 share of net | 7.80% |
| Worst 10 losers net | $-880.99 |
| Worst 10 share of |net| | 4.63% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $405.43 |
| Gap-through beyond 1 tick | $372.23 |
| Filled stop count | 332 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 0 |
| Max recovery calendar days | 0 |
| Unresolved recovery days | 0 |
| Bars in close-equity DD | 0.00% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2016.00 |     3.00 |    445.50 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.00 |
| 2017.00 |    45.00 |   1060.81 |         -329.35 |              3.22 |          37.78 |            1.72 |                     0.01 |
| 2018.00 |    47.00 |   1165.13 |         -258.00 |              4.52 |          38.30 |            1.77 |                     0.01 |
| 2019.00 |    60.00 |   2467.11 |         -430.52 |              5.73 |          46.67 |            2.46 |                     0.02 |
| 2020.00 |    65.00 |    676.14 |         -412.80 |              1.64 |          32.31 |            1.28 |                     0.01 |
| 2021.00 |    82.00 |   2768.68 |         -415.75 |              6.66 |          42.68 |            2.14 |                     0.03 |
| 2022.00 |    64.00 |   2375.31 |         -315.18 |              7.54 |          45.31 |            2.23 |                     0.02 |
| 2023.00 |    78.00 |   3377.98 |         -258.00 |             13.09 |          47.44 |            2.60 |                     0.03 |
| 2024.00 |    80.00 |   2875.03 |         -412.80 |              6.96 |          43.75 |            2.24 |                     0.03 |
| 2025.00 |    54.00 |   1815.90 |         -361.20 |              5.03 |          42.59 |            2.14 |                     0.02 |

## Rolling stability (50)

- Windows: 529
- Worst rolling PF: 1.233
- Worst rolling Net/closed-DD: 1.45
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |   net_usd |   avg_unit |
|:--------------|--------:|----------:|-----------:|
| target        |     246 |  36531.00 |     148.50 |
| stop          |     332 | -17503.43 |     -52.72 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      145 |   3532.29 |          38.62 |            1.74 |       24.36 |         -482.12 |                 7.33 |
| Q2               |      144 |   5938.50 |          46.53 |            2.48 |       41.24 |         -367.50 |                16.16 |
| Q3               |      147 |   5419.90 |          44.22 |            2.28 |       36.87 |         -425.40 |                12.74 |
| Q4 high          |      142 |   4136.88 |          40.85 |            1.92 |       29.13 |         -361.20 |                11.45 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
