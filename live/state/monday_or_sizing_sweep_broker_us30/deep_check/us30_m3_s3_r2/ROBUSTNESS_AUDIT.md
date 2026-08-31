# US30 Monday OR M3_S3_R2 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 1121 |
| Net | $31329.53 |
| Campaign closed DD | $-15981.05 |
| Win rate | 29.17% |
| Profit factor | 1.141 |
| Avg trade | $27.95 |
| Median trade | $-141.12 |
| Max losing streak | 18 |
| Full initial SL losses | 0 (0.0%) |
| Hit TP (any) | 0.0% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 415 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2023: $-6549.10 net, -0.94 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $45684.20 |
| Top 10 share of net | 145.82% |
| Worst 10 losers net | $-13567.00 |
| Worst 10 share of |net| | 43.30% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $1044.48 |
| Gap-through beyond 1 tick | $860.38 |
| Filled stop count | 1576 |

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
| 2016.00 |    21.00 |   2251.30 |         -656.00 |              3.43 |          42.86 |            3.20 |                     0.02 |
| 2017.00 |   126.00 |   2499.40 |        -1175.50 |              2.13 |          30.16 |            1.34 |                     0.02 |
| 2018.00 |   114.00 |   9668.60 |        -2699.50 |              3.58 |          32.46 |            1.52 |                     0.09 |
| 2019.00 |   144.00 |   1803.80 |        -3998.50 |              0.45 |          27.08 |            1.09 |                     0.02 |
| 2020.00 |   120.00 |   1677.60 |        -9450.50 |              0.18 |          25.83 |            1.04 |                     0.01 |
| 2021.00 |   125.00 |   6360.20 |        -5711.00 |              1.11 |          29.60 |            1.29 |                     0.05 |
| 2022.00 |   148.00 |  -5329.80 |       -12807.60 |             -0.42 |          25.00 |            0.89 |                    -0.04 |
| 2023.00 |   139.00 |  -6549.10 |        -6933.40 |             -0.94 |          28.78 |            0.75 |                    -0.06 |
| 2024.00 |   127.00 |   9026.60 |        -3358.75 |              2.69 |          33.86 |            1.41 |                     0.08 |
| 2025.00 |    57.00 |   9920.93 |        -6598.91 |              1.50 |          28.07 |            1.55 |                     0.08 |

## Rolling stability (50)

- Windows: 1072
- Worst rolling PF: 0.339
- Worst rolling Net/closed-DD: -1.16
- Rolling PF < 1.0 count: 415

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| target        |      86 |  117575.20 |    1367.15 |
| week_end      |     182 |  107550.80 |     590.94 |
| dd30,target   |      34 |   14183.97 |     417.18 |
| dd30,week_end |      96 |    1138.10 |      11.86 |
| dd30,dd50     |     723 | -209118.54 |    -289.24 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      279 |   -382.46 |          27.60 |            0.98 |       -1.37 |        -6925.50 |                -0.06 |
| Q2               |      278 |  12984.66 |          29.86 |            1.32 |       46.71 |        -6423.79 |                 2.02 |
| Q3               |      278 |  14737.47 |          31.29 |            1.24 |       53.01 |        -8060.08 |                 1.83 |
| Q4 high          |      278 |   2844.66 |          27.70 |            1.03 |       10.23 |       -14845.40 |                 0.19 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
