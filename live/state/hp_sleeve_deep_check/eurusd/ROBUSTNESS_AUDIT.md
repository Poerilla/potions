# EURUSD ST+PMC Thu @47.52× (~$200k stress) — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 865 |
| Net | $1693647.25 |
| Campaign closed DD | $-198579.85 |
| Win rate | 29.02% |
| Profit factor | 1.564 |
| Avg trade | $1957.97 |
| Median trade | $-502.50 |
| Max losing streak | 15 |
| Full initial SL losses | 614 (71.0%) |
| Hit TP (any) | 29.0% |
| EOD / flatten | 0.0% |

## Fragility

- 199 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2026: $-47262.59 net, -1.94 N/S.
- Full initial SL share is high (71.0%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $712064.65 |
| Top 10 share of net | 42.04% |
| Worst 10 losers net | $-291417.86 |
| Worst 10 share of |net| | 17.21% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $0.00 |
| Gap-through beyond 1 tick | $0.00 |
| Filled stop count | 0 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 0 |
| Max recovery calendar days | 0 |
| Unresolved recovery days | 0 |
| Bars in close-equity DD | 0.00% |

## Yearly stability

|    year |   trades |    net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|-----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |    22.00 |  -28710.78 |       -98097.83 |             -0.29 |          18.18 |            0.73 |                    -0.29 |
| 2004.00 |    43.00 |  -46843.02 |      -120844.83 |             -0.39 |          27.91 |            0.83 |                    -0.66 |
| 2005.00 |    39.00 |  -69749.14 |       -72737.14 |             -0.96 |          25.64 |            0.18 |                    -2.85 |
| 2006.00 |    37.00 |   92029.04 |       -54836.41 |              1.68 |          24.32 |            2.51 |                    -2.03 |
| 2007.00 |    29.00 |  -18384.49 |       -72145.63 |             -0.25 |          34.48 |            0.82 |                    -0.39 |
| 2008.00 |    45.00 |   45921.15 |       -72136.63 |              0.64 |          51.11 |            1.36 |                     1.62 |
| 2009.00 |    43.00 |  -89515.34 |      -100537.18 |             -0.89 |          30.23 |            0.50 |                    -1.21 |
| 2010.00 |    48.00 |   96140.18 |       -92048.68 |              1.04 |          29.17 |            1.72 |                    -6.30 |
| 2011.00 |    41.00 |  235071.61 |       -51794.09 |              4.54 |          29.27 |            2.79 |                     2.91 |
| 2012.00 |    47.00 |  350516.66 |       -26902.04 |             13.03 |          27.66 |            5.02 |                     1.11 |
| 2013.00 |    39.00 |  -64772.38 |      -137459.35 |             -0.47 |          33.33 |            0.58 |                    -0.10 |
| 2014.00 |    36.00 |  212626.23 |       -28409.54 |              7.48 |          30.56 |            3.57 |                     0.35 |
| 2015.00 |    57.00 |  358661.33 |       -52287.59 |              6.86 |          35.09 |            2.57 |                     0.44 |
| 2016.00 |    37.00 | -127884.89 |      -173696.81 |             -0.74 |          10.81 |            0.37 |                    -0.11 |
| 2017.00 |    36.00 |   41830.75 |       -50789.09 |              0.82 |          19.44 |            1.39 |                     0.04 |
| 2018.00 |    38.00 |   91578.84 |       -28912.04 |              3.17 |          23.68 |            2.49 |                     0.08 |
| 2019.00 |    25.00 |  -96478.34 |       -97531.18 |             -0.99 |          20.00 |            0.44 |                    -0.08 |
| 2020.00 |    32.00 |  127555.72 |       -92533.18 |              1.38 |          43.75 |            2.24 |                     0.12 |
| 2021.00 |    24.00 |  234027.77 |       -49272.59 |              4.75 |          29.17 |            5.23 |                     0.19 |
| 2022.00 |    44.00 |  163584.97 |       -47262.59 |              3.46 |          27.27 |            2.23 |                     0.11 |
| 2023.00 |    30.00 |   25472.21 |       -94543.18 |              0.27 |          30.00 |            1.20 |                     0.02 |
| 2024.00 |    27.00 |  137290.59 |       -49282.53 |              2.79 |          22.22 |            2.70 |                     0.08 |
| 2025.00 |    41.00 |   70941.19 |       -74974.08 |              0.95 |          31.71 |            1.45 |                     0.04 |
| 2026.00 |     5.00 |  -47262.59 |       -24380.54 |             -1.94 |          20.00 |            0.03 |                    -0.03 |

## Rolling stability (50)

- Windows: 816
- Worst rolling PF: 0.144
- Worst rolling Net/closed-DD: -1.22
- Rolling PF < 1.0 count: 199

## Exit dependency

| exit_reason   |   units |     net_usd |   avg_unit |
|:--------------|--------:|------------:|-----------:|
| tp_or_runner  |     251 |  4698017.32 |   18717.20 |
| stop          |     614 | -3004370.07 |   -4893.11 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      217 | 281910.78 |          26.73 |            1.40 |     1299.13 |      -121427.22 |                 2.32 |
| Q2               |      216 | 865958.40 |          28.24 |            2.26 |     4009.07 |      -150312.26 |                 5.76 |
| Q3               |      216 | 407138.51 |          29.17 |            1.61 |     1884.90 |      -165920.00 |                 2.45 |
| Q4 high          |      216 | 138639.57 |          31.94 |            1.15 |      641.85 |      -358019.68 |                 0.39 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
