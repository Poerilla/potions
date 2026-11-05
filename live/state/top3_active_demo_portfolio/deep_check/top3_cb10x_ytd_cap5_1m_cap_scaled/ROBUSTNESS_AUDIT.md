# TOP3 x10 YTD cap 5% cap_scaled (joint 1m) — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 640 |
| Net | $208355.81 |
| Campaign closed DD | $-71479.40 |
| Win rate | 34.69% |
| Profit factor | 1.357 |
| Avg trade | $325.56 |
| Median trade | $-537.75 |
| Max losing streak | 14 |
| Full initial SL losses | 11 (1.7%) |
| Hit TP (any) | 14.4% |
| EOD / flatten | 14.4% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 121 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2003: $-3891.64 net, -0.49 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $193968.03 |
| Top 10 share of net | 93.09% |
| Worst 10 losers net | $-75646.97 |
| Worst 10 share of |net| | 36.31% |

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
| Unresolved recovery days | 0 |
| Bars in close-equity DD | 21.30% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |    40.00 |  -3891.64 |        -7875.62 |             -0.49 |          30.00 |            0.85 |                    -0.04 |
| 2004.00 |    24.00 |   4830.02 |        -9654.58 |              0.50 |          29.17 |            1.39 |                     0.05 |
| 2005.00 |     2.00 |   5065.19 |         -550.57 |              9.20 |         100.00 |          inf    |                     0.05 |
| 2006.00 |     7.00 |   5333.40 |        -2828.81 |              1.89 |          42.86 |            3.05 |                     0.05 |
| 2007.00 |     4.00 |   5644.59 |         -792.61 |              7.12 |          50.00 |           10.43 |                     0.05 |
| 2008.00 |    57.00 |   5919.01 |       -11796.73 |              0.50 |          35.09 |            1.12 |                     0.05 |
| 2009.00 |     7.00 |   7128.96 |        -4928.41 |              1.45 |          42.86 |            1.87 |                     0.06 |
| 2010.00 |    36.00 |   6498.81 |       -11451.31 |              0.57 |          25.00 |            1.26 |                     0.05 |
| 2011.00 |    28.00 |   6945.26 |       -13432.30 |              0.52 |          28.57 |            1.41 |                     0.05 |
| 2012.00 |    15.00 |   7174.03 |        -2483.40 |              2.89 |          46.67 |            2.91 |                     0.05 |
| 2013.00 |     3.00 |   7625.99 |        -3254.73 |              2.34 |          66.67 |            5.29 |                     0.05 |
| 2014.00 |    75.00 |   7976.46 |       -14392.59 |              0.55 |          37.33 |            1.18 |                     0.05 |
| 2015.00 |   149.00 |   8326.97 |       -27116.32 |              0.31 |          42.95 |            1.07 |                     0.05 |
| 2016.00 |    12.00 |   9098.03 |       -14788.66 |              0.62 |          25.00 |            1.66 |                     0.05 |
| 2017.00 |    19.00 |   9235.64 |        -5291.83 |              1.75 |          36.84 |            1.88 |                     0.05 |
| 2018.00 |     9.00 |  10098.10 |        -1346.77 |              7.50 |          44.44 |            5.26 |                     0.05 |
| 2019.00 |     2.00 |  15035.03 |          -49.83 |            301.73 |         100.00 |          inf    |                     0.07 |
| 2020.00 |    25.00 |  11423.86 |        -3795.86 |              3.01 |          24.00 |            2.08 |                     0.05 |
| 2021.00 |     6.00 |  11432.71 |        -2126.15 |              5.38 |          50.00 |            4.15 |                     0.05 |
| 2022.00 |    18.00 |  12557.64 |        -8603.09 |              1.46 |          22.22 |            1.89 |                     0.05 |
| 2023.00 |     4.00 |  12634.88 |        -6089.65 |              2.07 |          50.00 |            3.42 |                     0.05 |
| 2024.00 |     8.00 |  13368.06 |        -2151.36 |              6.21 |          37.50 |            2.92 |                     0.05 |
| 2025.00 |    73.00 |  14134.63 |       -71723.29 |              0.20 |          16.44 |            1.08 |                     0.05 |
| 2026.00 |    17.00 |  14760.20 |       -24449.32 |              0.60 |          52.94 |            1.47 |                     0.05 |

## Rolling stability (50)

- Windows: 591
- Worst rolling PF: 0.584
- Worst rolling Net/closed-DD: -1.05
- Rolling PF < 1.0 count: 121

## Exit dependency

| exit_reason           |   units |    net_usd |   avg_unit |
|:----------------------|--------:|-----------:|-----------:|
| target                |     196 |  378950.56 |    1933.42 |
| week_end              |     277 |  196828.53 |     710.57 |
| ytd_cap_flatten       |      85 |  102561.16 |    1206.60 |
| eod_close             |     580 |   50108.09 |      86.39 |
| tp1                   |      52 |   20329.47 |     390.95 |
| tp2                   |       6 |    4763.19 |     793.86 |
| runner_stop           |      16 |    -473.24 |     -29.58 |
| failed_clean_close    |      33 |  -14239.12 |    -431.49 |
| trail_stop            |      16 |  -21990.97 |   -1374.44 |
| close_back_into_range |      50 |  -37205.83 |    -744.12 |
| wide_stop             |      77 |  -37732.14 |    -490.03 |
| dd30                  |     394 | -127616.36 |    -323.90 |
| dd50                  |     550 | -305927.55 |    -556.23 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       41 |  28875.77 |          34.15 |            2.52 |      704.29 |        -4168.75 |                 6.93 |
| Q2               |       41 |  38752.33 |          34.15 |            1.94 |      945.18 |       -16125.91 |                 2.40 |
| Q3               |       41 | -31221.36 |           9.76 |            0.66 |     -761.50 |       -70519.28 |                -0.44 |
| Q4 high          |       41 |  73513.82 |          26.83 |            1.99 |     1793.02 |       -39804.61 |                 1.85 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
