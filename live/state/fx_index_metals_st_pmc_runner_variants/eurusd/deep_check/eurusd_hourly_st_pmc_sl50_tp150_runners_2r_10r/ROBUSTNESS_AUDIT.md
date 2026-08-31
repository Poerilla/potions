# EURUSD ST+PMC 50/150 2R→10R — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 285 |
| Net | $104545.35 |
| Campaign closed DD | $-64558.00 |
| Win rate | 31.93% |
| Profit factor | 1.350 |
| Avg trade | $366.83 |
| Median trade | $-1538.00 |
| Max losing streak | 13 |
| Full initial SL losses | 0 (0.0%) |
| Hit TP (any) | 0.0% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 77 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2016: $-24983.00 net, -1.07 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $179657.00 |
| Top 10 share of net | 171.85% |
| Worst 10 losers net | $-15573.53 |
| Worst 10 share of |net| | 14.90% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $986.65 |
| Gap-through beyond 1 tick | $277.65 |
| Filled stop count | 709 |

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
| 2003.00 |    11.00 |   1071.68 |        -9244.32 |              0.12 |          27.27 |            1.09 |                     0.01 |
| 2004.00 |    18.00 |   -802.73 |        -6458.89 |             -0.12 |          38.89 |            0.95 |                    -0.01 |
| 2005.00 |    19.00 | -14322.18 |       -14172.18 |             -1.01 |          21.05 |            0.38 |                    -0.14 |
| 2006.00 |     4.00 |  20853.00 |        -1538.00 |             13.56 |          75.00 |           14.56 |                     0.24 |
| 2007.00 |    10.00 |   2602.33 |        -3151.00 |              0.83 |          50.00 |            1.34 |                     0.02 |
| 2008.00 |    23.00 |  72646.44 |        -3076.00 |             23.62 |          60.87 |            6.25 |                     0.66 |
| 2009.00 |    27.00 |  30490.00 |       -21682.00 |              1.41 |          33.33 |            2.10 |                     0.17 |
| 2010.00 |    21.00 |   9712.00 |        -7915.00 |              1.23 |          28.57 |            1.42 |                     0.05 |
| 2011.00 |    16.00 |   8399.00 |       -13992.00 |              0.60 |          18.75 |            1.42 |                     0.04 |
| 2012.00 |     6.00 |   2776.00 |        -3076.00 |              0.90 |          33.33 |            1.45 |                     0.01 |
| 2014.00 |     4.00 |  14851.00 |        -3076.00 |              4.83 |          25.00 |            4.22 |                     0.06 |
| 2015.00 |    30.00 |  -7127.00 |       -20369.00 |             -0.35 |          30.00 |            0.78 |                    -0.03 |
| 2016.00 |    26.00 | -24983.00 |       -23445.00 |             -1.07 |          15.38 |            0.26 |                    -0.10 |
| 2017.00 |    15.00 | -14067.00 |       -16993.00 |             -0.83 |          13.33 |            0.30 |                    -0.07 |
| 2018.00 |     7.00 |  -4764.00 |        -7690.00 |             -0.62 |          14.29 |            0.48 |                    -0.02 |
| 2019.00 |     9.00 |  -4839.00 |        -7765.00 |             -0.62 |          22.22 |            0.55 |                    -0.02 |
| 2020.00 |     4.00 |   2851.00 |        -1538.00 |              1.85 |          50.00 |            1.93 |                     0.01 |
| 2022.00 |    11.00 |  -1913.00 |        -4764.00 |             -0.40 |          36.36 |            0.82 |                    -0.01 |
| 2023.00 |    11.00 |  10091.00 |        -1613.00 |              6.26 |          54.55 |            2.31 |                     0.05 |
| 2024.00 |    10.00 |   -376.20 |        -7691.20 |             -0.05 |          30.00 |            0.97 |                    -0.00 |
| 2025.00 |     3.00 |   1396.00 |        -1538.00 |              0.91 |          33.33 |            1.45 |                     0.01 |

## Rolling stability (50)

- Windows: 236
- Worst rolling PF: 0.291
- Worst rolling Net/closed-DD: -1.04
- Rolling PF < 1.0 count: 77

## Exit dependency

| exit_reason                                    |   units |    net_usd |   avg_unit |
|:-----------------------------------------------|--------:|-----------:|-----------:|
| runner_entry,runner_entry_2,runner_stop,target |      81 |  223453.88 |    2758.69 |
| runner_entry,runner_entry_2,target             |      10 |  179657.00 |   17965.70 |
| runner_entry,runner_entry_2,runner_stop,stop   |     194 | -298565.53 |   -1539.00 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       72 |  -2719.67 |          27.78 |            0.97 |      -37.77 |       -46740.00 |                -0.06 |
| Q2               |       71 |  28688.87 |          35.21 |            1.41 |      404.07 |       -15992.27 |                 1.79 |
| Q3               |       71 |   4751.51 |          30.99 |            1.06 |       66.92 |       -15830.00 |                 0.30 |
| Q4 high          |       71 |  73824.64 |          33.80 |            2.02 |     1039.78 |       -19994.00 |                 3.69 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
