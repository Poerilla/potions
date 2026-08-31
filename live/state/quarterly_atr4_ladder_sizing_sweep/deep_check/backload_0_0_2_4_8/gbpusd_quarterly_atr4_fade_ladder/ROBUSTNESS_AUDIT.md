# GBPUSD quarterly ATR4 fade ladder 0/0/2/4/8 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 51 |
| Net | $676997.96 |
| Campaign closed DD | $-61699.30 |
| Win rate | 43.14% |
| Profit factor | 3.053 |
| Avg trade | $13274.47 |
| Median trade | $-5261.48 |
| Max losing streak | 4 |
| Full initial SL losses | 27 (52.9%) |
| Hit TP (any) | 45.1% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2022: $-30306.92 net, -0.64 N/S.
- Full initial SL share is high (52.9%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $833769.88 |
| Top 10 share of net | 123.16% |
| Worst 10 losers net | $-178715.04 |
| Worst 10 share of |net| | 26.40% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $2384.86 |
| Gap-through beyond 1 tick | $1910.86 |
| Filled stop count | 38 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 7699 |
| Max recovery calendar days | 1738 |
| Unresolved recovery days | 63 |
| Bars in close-equity DD | 98.32% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |     1.00 |   -154.00 |        -1806.00 |             -0.09 |           0.00 |            0.00 |                    -0.00 |
| 2004.00 |     2.00 | 115331.46 |       -62325.33 |              1.85 |          50.00 |            8.42 |                     1.16 |
| 2005.00 |     3.00 | -22620.68 |       -47096.00 |             -0.48 |          33.33 |            0.38 |                    -0.11 |
| 2006.00 |     1.00 |  67545.00 |       -38144.00 |              1.77 |         100.00 |          inf    |                     0.35 |
| 2007.00 |     1.00 |  11384.90 |       -49600.00 |              0.23 |         100.00 |          inf    |                     0.04 |
| 2008.00 |     4.00 | -44857.58 |       -76008.19 |             -0.59 |          25.00 |            0.21 |                    -0.17 |
| 2009.00 |     1.00 | -16841.72 |       -38150.00 |             -0.44 |           0.00 |            0.00 |                    -0.07 |
| 2010.00 |     1.00 |   8173.86 |       -43680.00 |              0.19 |         100.00 |          inf    |                     0.04 |
| 2011.00 |     2.00 |  61700.28 |       -67208.00 |              0.92 |         100.00 |          inf    |                     0.28 |
| 2012.00 |     3.00 |  52799.16 |       -32774.28 |              1.61 |          33.33 |            3.61 |                     0.19 |
| 2013.00 |     3.00 | 107805.94 |       -37184.76 |              2.90 |          33.33 |            6.69 |                     0.32 |
| 2014.00 |     3.00 |  24976.86 |       -44744.00 |              0.56 |          33.33 |            2.38 |                     0.06 |
| 2015.00 |     3.00 |  90871.18 |       -47864.00 |              1.90 |          33.33 |            6.04 |                     0.20 |
| 2016.00 |     4.00 |   7642.32 |      -118896.00 |              0.06 |          50.00 |            1.43 |                     0.01 |
| 2017.00 |     4.00 |  57906.48 |       -42007.57 |              1.38 |          50.00 |            4.54 |                     0.10 |
| 2019.00 |     2.00 | -12118.70 |       -47885.67 |             -0.25 |           0.00 |            0.00 |                    -0.02 |
| 2020.00 |     1.00 | -14715.40 |       -33838.00 |             -0.43 |           0.00 |            0.00 |                    -0.02 |
| 2021.00 |     2.00 |  28867.44 |       -42904.00 |              0.67 |          50.00 |            3.81 |                     0.05 |
| 2022.00 |     2.00 | -30306.92 |       -47422.43 |             -0.64 |           0.00 |            0.00 |                    -0.05 |
| 2023.00 |     2.00 |  71846.54 |       -54747.83 |              1.31 |         100.00 |          inf    |                     0.12 |
| 2024.00 |     2.00 |  11351.64 |       -30876.00 |              0.37 |          50.00 |            2.11 |                     0.02 |
| 2025.00 |     3.00 |  92936.26 |       -23200.00 |              4.01 |          33.33 |            6.45 |                     0.14 |
| 2026.00 |     1.00 |   7473.64 |       -42416.00 |              0.18 |         100.00 |          inf    |                     0.01 |

## Rolling stability (50)

- Windows: 2
- Worst rolling PF: 3.030
- Worst rolling Net/closed-DD: 10.85
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| flatten       |     110 |  648710.00 |    5897.36 |
| tp4           |      84 |  307026.36 |    3655.08 |
| tp3           |      46 |  128017.44 |    2782.99 |
| stop          |     474 | -406755.84 |    -858.13 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       13 |  26179.54 |          30.77 |            1.34 |     2013.81 |       -53102.78 |                 0.49 |
| Q2               |       13 | 164106.28 |          30.77 |            2.76 |    12623.56 |       -25943.68 |                 6.33 |
| Q3               |       12 | 411432.00 |          66.67 |           12.76 |    34286.00 |       -34842.36 |                11.81 |
| Q4 high          |       13 |  75280.14 |          46.15 |            1.60 |     5790.78 |       -96102.04 |                 0.78 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
