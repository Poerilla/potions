# EURUSD ST+PMC 50/150 fair 3R — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 865 |
| Net | $59962.07 |
| Campaign closed DD | $-21126.00 |
| Win rate | 29.02% |
| Profit factor | 1.190 |
| Avg trade | $69.32 |
| Median trade | $-508.00 |
| Max losing streak | 15 |
| Full initial SL losses | 614 (71.0%) |
| Hit TP (any) | 0.0% |
| EOD / flatten | 0.0% |

## Fragility

- 209 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2003: $-3572.32 net, -1.11 N/S.
- Full initial SL share is high (71.0%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $14930.00 |
| Top 10 share of net | 24.90% |
| Worst 10 losers net | $-7781.67 |
| Worst 10 share of |net| | 12.98% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $3482.93 |
| Gap-through beyond 1 tick | $2868.93 |
| Filled stop count | 614 |

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
| 2003.00 |    22.00 |  -3572.32 |        -3229.40 |             -1.11 |          18.18 |            0.63 |                    -0.04 |
| 2004.00 |    43.00 |   1936.57 |        -3810.32 |              0.51 |          27.91 |            1.12 |                     0.02 |
| 2005.00 |    39.00 |    162.99 |        -4726.04 |              0.03 |          25.64 |            1.01 |                     0.00 |
| 2006.00 |    37.00 |   -839.30 |        -8217.33 |             -0.10 |          24.32 |            0.94 |                    -0.01 |
| 2007.00 |    29.00 |   5250.22 |        -2543.23 |              2.06 |          34.48 |            1.54 |                     0.05 |
| 2008.00 |    45.00 |  23135.44 |        -2032.00 |             11.39 |          51.11 |            3.07 |                     0.22 |
| 2009.00 |    43.00 |   4169.00 |        -7112.00 |              0.59 |          30.23 |            1.27 |                     0.03 |
| 2010.00 |    48.00 |   3630.00 |        -3110.00 |              1.17 |          29.17 |            1.21 |                     0.03 |
| 2011.00 |    41.00 |   3184.00 |        -5235.00 |              0.61 |          29.27 |            1.22 |                     0.02 |
| 2012.00 |    47.00 |   2137.00 |        -3587.00 |              0.60 |          27.66 |            1.12 |                     0.02 |
| 2013.00 |    39.00 |   5558.42 |        -4198.58 |              1.32 |          33.33 |            1.40 |                     0.04 |
| 2014.00 |    36.00 |   3723.00 |        -5111.00 |              0.73 |          30.56 |            1.29 |                     0.03 |
| 2015.00 |    57.00 |  11064.00 |        -6282.00 |              1.76 |          35.09 |            1.59 |                     0.07 |
| 2016.00 |    37.00 | -10792.00 |       -10284.00 |             -1.05 |          10.81 |            0.36 |                    -0.07 |
| 2017.00 |    36.00 |  -4281.00 |        -6697.00 |             -0.64 |          19.44 |            0.71 |                    -0.03 |
| 2018.00 |    38.00 |  -1295.00 |        -7682.00 |             -0.17 |          23.68 |            0.91 |                    -0.01 |
| 2019.00 |    25.00 |  -2695.00 |        -4095.00 |             -0.66 |          20.00 |            0.73 |                    -0.02 |
| 2020.00 |    32.00 |  11758.00 |        -3048.00 |              3.86 |          43.75 |            2.29 |                     0.08 |
| 2021.00 |    24.00 |   1815.00 |        -2571.00 |              0.71 |          29.17 |            1.21 |                     0.01 |
| 2022.00 |    44.00 |   1388.83 |        -5619.00 |              0.25 |          27.27 |            1.08 |                     0.01 |
| 2023.00 |    30.00 |   2769.00 |        -4095.00 |              0.68 |          30.00 |            1.26 |                     0.02 |
| 2024.00 |    27.00 |  -1836.63 |        -4314.63 |             -0.43 |          22.22 |            0.83 |                    -0.01 |
| 2025.00 |    41.00 |   4130.86 |        -4603.00 |              0.90 |          31.71 |            1.27 |                     0.03 |
| 2026.00 |     5.00 |   -539.00 |        -1016.00 |             -0.53 |          20.00 |            0.73 |                    -0.00 |

## Rolling stability (50)

- Windows: 816
- Worst rolling PF: 0.478
- Worst rolling Net/closed-DD: -1.07
- Rolling PF < 1.0 count: 209

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| target        |     251 |  374743.00 |    1493.00 |
| stop          |     614 | -314780.93 |    -512.67 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      217 |   5653.42 |          26.73 |            1.07 |       26.05 |        -8688.23 |                 0.65 |
| Q2               |      216 |  10971.62 |          28.24 |            1.14 |       50.79 |       -13456.00 |                 0.82 |
| Q3               |      216 |  15310.09 |          29.17 |            1.19 |       70.88 |        -9217.33 |                 1.66 |
| Q4 high          |      216 |  28026.95 |          31.94 |            1.37 |      129.75 |        -7744.00 |                 3.62 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
