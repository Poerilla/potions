# XAUUSD quarterly ATR4 fade ladder 0/0/2/4/8 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 30 |
| Net | $592959.82 |
| Campaign closed DD | $-71774.36 |
| Win rate | 36.67% |
| Profit factor | 3.277 |
| Avg trade | $19765.33 |
| Median trade | $-4935.81 |
| Max losing streak | 8 |
| Full initial SL losses | 18 (60.0%) |
| Hit TP (any) | 40.0% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2013: $-29050.28 net, -0.62 N/S.
- Full initial SL share is high (60.0%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $848111.98 |
| Top 10 share of net | 143.03% |
| Worst 10 losers net | $-210734.16 |
| Worst 10 share of |net| | 35.54% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $40872.26 |
| Gap-through beyond 1 tick | $40592.26 |
| Filled stop count | 21 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 14595 |
| Max recovery calendar days | 3385 |
| Unresolved recovery days | 517 |
| Bars in close-equity DD | 98.42% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |     1.00 |  38409.00 |       -14004.80 |              2.74 |         100.00 |          inf    |                     0.38 |
| 2004.00 |     2.00 |  25918.22 |       -19002.40 |              1.36 |          50.00 |            8.75 |                     0.19 |
| 2005.00 |     3.00 | 102803.34 |       -36056.00 |              2.85 |          66.67 |           11.39 |                     0.63 |
| 2006.00 |     1.00 | -13548.50 |       -30018.80 |             -0.45 |           0.00 |            0.00 |                    -0.05 |
| 2007.00 |     1.00 |  65457.86 |       -42568.80 |              1.54 |         100.00 |          inf    |                     0.26 |
| 2008.00 |     1.00 |   5293.14 |       -64514.40 |              0.08 |         100.00 |          inf    |                     0.02 |
| 2009.00 |     3.00 |  39575.94 |       -63581.60 |              0.62 |          33.33 |            1.96 |                     0.12 |
| 2010.00 |     1.00 | -23882.88 |       -46725.00 |             -0.51 |           0.00 |            0.00 |                    -0.07 |
| 2011.00 |     1.00 |   -475.02 |       -18226.60 |             -0.03 |           0.00 |            0.00 |                    -0.00 |
| 2012.00 |     3.00 | 157192.32 |       -45673.20 |              3.44 |          33.33 |            5.01 |                     0.46 |
| 2013.00 |     3.00 | -29050.28 |       -46545.88 |             -0.62 |           0.00 |            0.00 |                    -0.06 |
| 2015.00 |     1.00 | -19901.42 |       -43639.40 |             -0.46 |           0.00 |            0.00 |                    -0.04 |
| 2016.00 |     1.00 |    -77.00 |       -14448.00 |             -0.01 |           0.00 |            0.00 |                    -0.00 |
| 2017.00 |     1.00 |  -8334.20 |       -24971.80 |             -0.33 |           0.00 |            0.00 |                    -0.02 |
| 2018.00 |     1.00 |  -6526.18 |       -41028.00 |             -0.16 |           0.00 |            0.00 |                    -0.01 |
| 2019.00 |     1.00 |  73007.50 |       -32673.20 |              2.23 |         100.00 |          inf    |                     0.17 |
| 2022.00 |     2.00 | -42350.70 |       -80620.36 |             -0.53 |           0.00 |            0.00 |                    -0.08 |
| 2023.00 |     1.00 | 228272.80 |       -80616.00 |              2.83 |         100.00 |          inf    |                     0.49 |
| 2024.00 |     2.00 |   1175.88 |      -165704.00 |              0.01 |          50.00 |            1.05 |                     0.00 |

## Rolling stability (50)

- Windows: 0
- Worst rolling PF: 0.000
- Worst rolling Net/closed-DD: 0.00
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| flatten       |      72 |  629845.60 |    8747.86 |
| tp4           |      44 |  190300.72 |    4325.02 |
| tp3           |      24 |   73571.58 |    3065.48 |
| stop          |     280 | -300758.08 |   -1074.14 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |        8 | 226062.24 |          62.50 |           12.43 |    28257.78 |        -9897.72 |                22.84 |
| Q2               |        7 | -71486.10 |           0.00 |            0.00 |   -10212.30 |       -57937.60 |                -1.23 |
| Q3               |        7 | 235316.24 |          42.86 |            4.30 |    33616.61 |       -71257.20 |                 3.30 |
| Q4 high          |        8 | 203067.44 |          37.50 |            3.07 |    25383.43 |       -66161.76 |                 3.07 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
