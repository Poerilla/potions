# NAS100 trail06_m4_e2_out_be 1mfill (brl_21741b260a28) — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 1166 |
| Net | $12252.95 |
| Campaign closed DD | $-1865.80 |
| Win rate | 12.86% |
| Profit factor | 1.432 |
| Avg trade | $10.51 |
| Median trade | $-8.65 |
| Max losing streak | 27 |
| Full initial SL losses | 0 (0.0%) |
| Hit TP (any) | 8.8% |
| EOD / flatten | 4.4% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 250 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2016: $-140.55 net, -0.84 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $7318.20 |
| Top 10 share of net | 59.73% |
| Worst 10 losers net | $-2962.90 |
| Worst 10 share of |net| | 24.18% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $184.15 |
| Gap-through beyond 1 tick | $49.05 |
| Filled stop count | 1214 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 110096 |
| Max recovery calendar days | 414 |
| Unresolved recovery days | 1 |
| Bars in close-equity DD | 99.70% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2016.00 |    19.00 |   -140.55 |         -166.55 |             -0.84 |           5.26 |            0.38 |                    -0.00 |
| 2017.00 |   125.00 |    -90.70 |         -444.45 |             -0.20 |           8.00 |            0.91 |                    -0.00 |
| 2018.00 |   134.00 |   -234.10 |         -755.50 |             -0.31 |          10.45 |            0.89 |                    -0.00 |
| 2019.00 |   131.00 |   1060.25 |         -360.45 |              2.94 |          14.50 |            1.72 |                     0.01 |
| 2020.00 |   135.00 |   1393.30 |        -1116.30 |              1.25 |          12.59 |            1.42 |                     0.01 |
| 2021.00 |   146.00 |   2539.90 |         -983.80 |              2.58 |          16.44 |            1.66 |                     0.02 |
| 2022.00 |   121.00 |   2496.80 |        -1322.45 |              1.89 |          11.57 |            1.60 |                     0.02 |
| 2023.00 |   140.00 |   1274.70 |        -1503.60 |              0.85 |          11.43 |            1.29 |                     0.01 |
| 2024.00 |   123.00 |   1642.05 |        -1462.55 |              1.12 |          14.63 |            1.49 |                     0.02 |
| 2025.00 |    92.00 |   2311.30 |        -1890.75 |              1.22 |          18.48 |            1.52 |                     0.02 |

## Rolling stability (50)

- Windows: 1117
- Worst rolling PF: 0.268
- Worst rolling Net/closed-DD: -1.61
- Rolling PF < 1.0 count: 250

## Exit dependency

| exit_reason           |   units |   net_usd |   avg_unit |
|:----------------------|--------:|----------:|-----------:|
| target                |     386 |  30149.30 |      78.11 |
| eod_close             |     201 |  10230.70 |      50.90 |
| ambiguous_break_close |       7 |   -162.55 |     -23.22 |
| trail_stop            |     185 |  -5678.95 |     -30.70 |
| failed_clean_close    |     517 |  -6000.80 |     -11.61 |
| close_back_into_range |     774 | -16284.75 |     -21.04 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      290 |    710.50 |          10.34 |            1.23 |        2.45 |         -450.35 |                 1.58 |
| Q2               |      290 |   2896.60 |          12.76 |            1.55 |        9.99 |         -744.75 |                 3.89 |
| Q3               |      289 |   4611.70 |          15.22 |            1.58 |       15.96 |        -1037.55 |                 4.44 |
| Q4 high          |      290 |   4127.50 |          13.45 |            1.35 |       14.23 |        -1927.15 |                 2.14 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
