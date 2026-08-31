# USDJPY London KZ sweep 1/1/1 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 1575 |
| Net | $2285.68 |
| Campaign closed DD | $-46831.59 |
| Win rate | 50.35% |
| Profit factor | 1.006 |
| Avg trade | $1.45 |
| Median trade | $16.17 |
| Max losing streak | 9 |
| Full initial SL losses | 629 (39.9%) |
| Hit TP (any) | 41.2% |
| EOD / flatten | 31.8% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 602 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2025: $-19578.45 net, -0.87 N/S.
- Full initial SL share is high (39.9%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $30648.09 |
| Top 10 share of net | 1340.87% |
| Worst 10 losers net | $-22861.91 |
| Worst 10 share of |net| | 1000.22% |

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

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2015.00 |   138.00 |   5207.29 |        -4513.19 |              1.15 |          52.17 |            1.17 |                     0.05 |
| 2016.00 |   129.00 |   9656.28 |        -5777.51 |              1.67 |          57.36 |            1.27 |                     0.09 |
| 2017.00 |   147.00 |  13683.75 |        -3827.51 |              3.58 |          59.86 |            1.52 |                     0.12 |
| 2018.00 |   144.00 |    282.51 |        -5321.88 |              0.05 |          51.39 |            1.01 |                     0.00 |
| 2019.00 |   134.00 |    825.33 |        -2234.83 |              0.37 |          48.51 |            1.04 |                     0.01 |
| 2020.00 |   140.00 |  -1234.91 |        -5180.69 |             -0.24 |          51.43 |            0.95 |                    -0.01 |
| 2021.00 |   153.00 |   1502.61 |        -3268.96 |              0.46 |          49.02 |            1.07 |                     0.01 |
| 2022.00 |   130.00 |   5331.55 |        -5699.42 |              0.94 |          47.69 |            1.12 |                     0.04 |
| 2023.00 |   155.00 |  -7811.41 |       -20731.43 |             -0.38 |          45.16 |            0.86 |                    -0.06 |
| 2024.00 |   142.00 |  -6089.84 |       -18586.17 |             -0.33 |          47.89 |            0.89 |                    -0.05 |
| 2025.00 |   130.00 | -19578.45 |       -22413.20 |             -0.87 |          42.31 |            0.66 |                    -0.16 |
| 2026.00 |    33.00 |    510.97 |        -3862.48 |              0.13 |          54.55 |            1.05 |                     0.01 |

## Rolling stability (50)

- Windows: 1526
- Worst rolling PF: 0.347
- Worst rolling Net/closed-DD: -1.16
- Rolling PF < 1.0 count: 602

## Exit dependency

| exit_reason     |   units |    net_usd |   avg_unit |
|:----------------|--------:|-----------:|-----------:|
| tp1+tp2+tp3     |     148 |  129844.47 |     877.33 |
| eod+tp1         |     125 |   97424.32 |     779.39 |
| eod+tp1+tp2     |      79 |   79512.19 |    1006.48 |
| be_stop+tp1     |     233 |   36662.79 |     157.35 |
| be_stop+tp1+tp2 |      64 |   27233.24 |     425.52 |
| eod             |     297 |   -5636.70 |     -18.98 |
| stop            |     629 | -362754.63 |    -576.72 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      394 |   6022.05 |          49.49 |            1.11 |       15.28 |        -3978.24 |                 1.51 |
| Q2               |      394 |   4377.51 |          52.28 |            1.06 |       11.11 |        -7910.65 |                 0.55 |
| Q3               |      393 |   4242.25 |          51.15 |            1.04 |       10.79 |       -25609.84 |                 0.17 |
| Q4 high          |      394 | -12356.13 |          48.48 |            0.93 |      -31.36 |       -21876.48 |                -0.56 |

### london_kz_width quartile

| range_width_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low                 |      396 |   6588.04 |          52.53 |            1.14 |       16.64 |        -3823.13 |                 1.72 |
| Q2                     |      392 |  14275.16 |          51.79 |            1.20 |       36.42 |        -4311.24 |                 3.31 |
| Q3                     |      393 |   4298.61 |          48.09 |            1.04 |       10.94 |       -24155.69 |                 0.18 |
| Q4 high                |      394 | -22876.13 |          48.98 |            0.88 |      -58.06 |       -30139.59 |                -0.76 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
