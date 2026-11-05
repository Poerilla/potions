# NAS100 clean-break ma_aligned arm-asof HP ×4 (research unit; demo 10× ≈ $408k/−$53k N/S 7.64) — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 1166 |
| Net | $40778.60 |
| Campaign closed DD | $-4941.25 |
| Win rate | 12.86% |
| Profit factor | 1.573 |
| Avg trade | $34.97 |
| Median trade | $-17.80 |
| Max losing streak | 27 |
| Full initial SL losses | 0 (0.0%) |
| Hit TP (any) | 8.8% |
| EOD / flatten | 4.4% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 275 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2016: $-707.25 net, -0.90 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $25336.40 |
| Top 10 share of net | 62.13% |
| Worst 10 losers net | $-9092.40 |
| Worst 10 share of |net| | 22.30% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $0.00 |
| Gap-through beyond 1 tick | $0.00 |
| Filled stop count | 0 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 169071 |
| Max recovery calendar days | 636 |
| Unresolved recovery days | 1 |
| Bars in close-equity DD | 99.65% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2016.00 |    19.00 |   -707.25 |         -786.65 |             -0.90 |           5.26 |            0.11 |                    -0.01 |
| 2017.00 |   125.00 |   -586.15 |        -1295.45 |             -0.45 |           8.00 |            0.79 |                    -0.01 |
| 2018.00 |   134.00 |   -637.15 |        -2036.20 |             -0.31 |          10.45 |            0.87 |                    -0.01 |
| 2019.00 |   131.00 |   4623.95 |        -1231.35 |              3.76 |          14.50 |            2.17 |                     0.05 |
| 2020.00 |   135.00 |   5095.90 |        -3674.70 |              1.39 |          12.59 |            1.63 |                     0.05 |
| 2021.00 |   146.00 |   9761.35 |        -2831.15 |              3.45 |          16.44 |            2.09 |                     0.09 |
| 2022.00 |   121.00 |   9758.30 |        -4200.60 |              2.32 |          11.57 |            2.01 |                     0.08 |
| 2023.00 |   140.00 |    468.00 |        -3420.00 |              0.14 |          11.43 |            1.04 |                     0.00 |
| 2024.00 |   123.00 |   4461.00 |        -3769.10 |              1.18 |          14.63 |            1.47 |                     0.03 |
| 2025.00 |    92.00 |   8540.65 |        -4919.35 |              1.74 |          18.48 |            1.79 |                     0.06 |

## Rolling stability (50)

- Windows: 1117
- Worst rolling PF: 0.211
- Worst rolling Net/closed-DD: -1.28
- Rolling PF < 1.0 count: 275

## Exit dependency

| exit_reason           |   units |   net_usd |   avg_unit |
|:----------------------|--------:|----------:|-----------:|
| target                |     386 |  80795.45 |     209.31 |
| eod_close             |     201 |  30218.50 |     150.34 |
| ambiguous_break_close |       7 |   -498.10 |     -71.16 |
| trail_stop            |     185 | -12998.95 |     -70.26 |
| failed_clean_close    |     517 | -16424.30 |     -31.77 |
| close_back_into_range |     774 | -40314.00 |     -52.09 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      290 |   2378.20 |          10.34 |            1.29 |        8.20 |        -1187.85 |                 2.00 |
| Q2               |      290 |   9184.45 |          12.76 |            1.71 |       31.67 |        -1363.45 |                 6.74 |
| Q3               |      289 |   9547.30 |          15.22 |            1.44 |       33.04 |        -4906.80 |                 1.95 |
| Q4 high          |      290 |  20006.05 |          13.45 |            1.71 |       68.99 |        -4939.65 |                 4.05 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
