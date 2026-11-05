# TOP3 x10 YTD cap 5% cap_fixed (joint 1m) — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 858 |
| Net | $181487.97 |
| Campaign closed DD | $-25577.60 |
| Win rate | 33.10% |
| Profit factor | 1.442 |
| Avg trade | $211.52 |
| Median trade | $-258.50 |
| Max losing streak | 14 |
| Full initial SL losses | 12 (1.4%) |
| Hit TP (any) | 13.5% |
| EOD / flatten | 13.2% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 119 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2003: $-3891.64 net, -0.49 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $86795.25 |
| Top 10 share of net | 47.82% |
| Worst 10 losers net | $-33543.40 |
| Worst 10 share of |net| | 18.48% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $0.00 |
| Gap-through beyond 1 tick | $0.00 |
| Filled stop count | 0 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 468 |
| Max recovery calendar days | 549 |
| Unresolved recovery days | 44 |
| Bars in close-equity DD | 25.86% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |    40.00 |  -3891.64 |        -7875.62 |             -0.49 |          30.00 |            0.85 |                    -0.04 |
| 2004.00 |    24.00 |   4987.42 |       -10045.51 |              0.50 |          29.17 |            1.39 |                     0.05 |
| 2005.00 |     2.00 |   5094.46 |         -545.45 |              9.34 |         100.00 |          inf    |                     0.05 |
| 2006.00 |     7.00 |   5387.70 |        -2668.60 |              2.02 |          42.86 |            3.19 |                     0.05 |
| 2007.00 |     6.00 |   5583.20 |        -1108.42 |              5.04 |          50.00 |            5.75 |                     0.05 |
| 2008.00 |    65.00 |   6039.44 |       -10084.26 |              0.60 |          33.85 |            1.12 |                     0.05 |
| 2009.00 |     8.00 |   6165.55 |        -4010.08 |              1.54 |          50.00 |            1.92 |                     0.05 |
| 2010.00 |    37.00 |   6494.73 |        -8806.70 |              0.74 |          27.03 |            1.34 |                     0.05 |
| 2011.00 |    28.00 |   6829.77 |        -9838.47 |              0.69 |          28.57 |            1.55 |                     0.05 |
| 2012.00 |    25.00 |   7153.88 |        -3225.65 |              2.22 |          52.00 |            2.14 |                     0.05 |
| 2013.00 |     4.00 |   7500.28 |        -2160.50 |              3.47 |          75.00 |            7.36 |                     0.05 |
| 2014.00 |    76.00 |   7871.90 |        -9093.49 |              0.87 |          38.16 |            1.28 |                     0.05 |
| 2015.00 |   149.00 |   8328.70 |       -16310.56 |              0.51 |          42.95 |            1.11 |                     0.05 |
| 2016.00 |    12.00 |   9651.47 |        -8471.14 |              1.14 |          25.00 |            2.23 |                     0.06 |
| 2017.00 |    28.00 |   9161.37 |        -2881.08 |              3.18 |          35.71 |            2.20 |                     0.05 |
| 2018.00 |    24.00 |   9726.20 |        -2373.19 |              4.10 |          41.67 |            3.02 |                     0.05 |
| 2019.00 |    57.00 |  10125.89 |        -4685.94 |              2.16 |          21.05 |            1.77 |                     0.05 |
| 2020.00 |    44.00 |  10608.28 |        -1995.39 |              5.32 |          25.00 |            2.46 |                     0.05 |
| 2021.00 |    37.00 |  11314.53 |        -4064.40 |              2.78 |          29.73 |            2.54 |                     0.05 |
| 2022.00 |    18.00 |  11995.30 |        -3571.22 |              3.36 |          22.22 |            3.05 |                     0.05 |
| 2023.00 |     8.00 |  12619.27 |        -2402.63 |              5.25 |          37.50 |            4.23 |                     0.05 |
| 2024.00 |    47.00 |  12929.19 |       -12046.89 |              1.07 |          25.53 |            1.66 |                     0.05 |
| 2025.00 |    76.00 |  13689.09 |       -25664.87 |              0.53 |          18.42 |            1.22 |                     0.05 |
| 2026.00 |    36.00 |  -3877.99 |        -8327.55 |             -0.47 |          38.89 |            0.87 |                    -0.01 |

## Rolling stability (50)

- Windows: 809
- Worst rolling PF: 0.565
- Worst rolling Net/closed-DD: -1.05
- Rolling PF < 1.0 count: 119

## Exit dependency

| exit_reason           |   units |    net_usd |   avg_unit |
|:----------------------|--------:|-----------:|-----------:|
| target                |     265 |  275735.73 |    1040.51 |
| week_end              |     363 |  167107.78 |     460.35 |
| ytd_cap_flatten       |      85 |   66368.60 |     780.81 |
| eod_close             |     713 |   37739.17 |      52.93 |
| tp1                   |      59 |   14229.88 |     241.18 |
| tp2                   |       7 |    3373.19 |     481.88 |
| runner_stop           |      20 |    -364.91 |     -18.25 |
| failed_clean_close    |      70 |   -9019.50 |    -128.85 |
| trail_stop            |      24 |   -9246.00 |    -385.25 |
| close_back_into_range |     114 |  -21858.50 |    -191.74 |
| wide_stop             |      84 |  -25447.16 |    -302.94 |
| dd30                  |     489 |  -97212.03 |    -198.80 |
| dd50                  |     674 | -219918.28 |    -326.29 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       85 |  27495.18 |          31.76 |            2.38 |      323.47 |        -2908.54 |                 9.45 |
| Q2               |       85 |  17055.02 |          23.53 |            1.95 |      200.65 |        -3918.39 |                 4.35 |
| Q3               |       85 |  24348.08 |          27.06 |            1.68 |      286.45 |       -10423.60 |                 2.34 |
| Q4 high          |       84 |  33270.83 |          20.24 |            1.57 |      396.08 |       -18588.75 |                 1.79 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
