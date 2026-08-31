# EURUSD Monday OR M1_S2_R2 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 2946 |
| Net | $77675.90 |
| Campaign closed DD | $-87822.30 |
| Win rate | 28.68% |
| Profit factor | 1.049 |
| Avg trade | $26.37 |
| Median trade | $-494.80 |
| Max losing streak | 17 |
| Full initial SL losses | 0 (0.0%) |
| Hit TP (any) | 0.0% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 1430 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2021: $-14657.10 net, -1.02 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $109839.00 |
| Top 10 share of net | 141.41% |
| Worst 10 losers net | $-37543.30 |
| Worst 10 share of |net| | 48.33% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $6657.10 |
| Gap-through beyond 1 tick | $795.10 |
| Filled stop count | 4057 |

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
| 2003.00 |    66.00 |    641.90 |       -10392.40 |              0.06 |          37.88 |            1.02 |                     0.01 |
| 2004.00 |   139.00 |  -1224.10 |       -11108.00 |             -0.11 |          25.90 |            0.99 |                    -0.01 |
| 2005.00 |   119.00 |    532.90 |       -13968.20 |              0.04 |          29.41 |            1.01 |                     0.01 |
| 2006.00 |   134.00 |  19726.40 |        -9952.60 |              1.98 |          32.84 |            1.31 |                     0.20 |
| 2007.00 |   142.00 |   9854.40 |       -12575.20 |              0.78 |          28.17 |            1.16 |                     0.08 |
| 2008.00 |   108.00 |  28684.20 |       -24504.60 |              1.17 |          36.11 |            1.27 |                     0.22 |
| 2009.00 |   118.00 |  -4646.60 |       -35767.00 |             -0.13 |          30.51 |            0.96 |                    -0.03 |
| 2010.00 |   128.00 |  26670.60 |       -19812.80 |              1.35 |          28.91 |            1.26 |                     0.17 |
| 2011.00 |   121.00 |   5349.40 |       -26740.50 |              0.20 |          31.40 |            1.05 |                     0.03 |
| 2012.00 |   125.00 |  19043.70 |       -12695.10 |              1.50 |          32.00 |            1.27 |                     0.10 |
| 2013.00 |   146.00 | -12446.90 |       -23692.80 |             -0.53 |          25.34 |            0.83 |                    -0.06 |
| 2014.00 |   142.00 |   6080.00 |       -11161.80 |              0.54 |          28.87 |            1.11 |                     0.03 |
| 2015.00 |   134.00 |  33859.30 |       -19754.10 |              1.71 |          32.09 |            1.44 |                     0.17 |
| 2016.00 |   148.00 | -14087.20 |       -15372.90 |             -0.92 |          25.68 |            0.81 |                    -0.06 |
| 2017.00 |   125.00 |  -2004.00 |        -6975.60 |             -0.29 |          24.00 |            0.96 |                    -0.01 |
| 2018.00 |   128.00 | -16685.40 |       -20060.30 |             -0.83 |          26.56 |            0.76 |                    -0.08 |
| 2019.00 |   139.00 |   2118.90 |        -8976.50 |              0.24 |          27.34 |            1.05 |                     0.01 |
| 2020.00 |   124.00 |  16151.50 |       -17345.70 |              0.93 |          31.45 |            1.29 |                     0.08 |
| 2021.00 |   130.00 | -14657.10 |       -14312.60 |             -1.02 |          27.69 |            0.70 |                    -0.07 |
| 2022.00 |   126.00 | -11153.00 |       -27652.40 |             -0.40 |          26.19 |            0.86 |                    -0.05 |
| 2023.00 |   137.00 | -17513.50 |       -31635.10 |             -0.55 |          24.09 |            0.71 |                    -0.09 |
| 2024.00 |   135.00 |  -9186.90 |       -13654.90 |             -0.67 |          25.93 |            0.81 |                    -0.05 |
| 2025.00 |   112.00 |   8321.90 |        -9267.20 |              0.90 |          26.79 |            1.16 |                     0.05 |
| 2026.00 |    20.00 |   4245.50 |        -3269.50 |              1.30 |          40.00 |            1.46 |                     0.02 |

## Rolling stability (50)

- Windows: 2897
- Worst rolling PF: 0.320
- Worst rolling Net/closed-DD: -1.19
- Rolling PF < 1.0 count: 1430

## Exit dependency

| exit_reason   |   units |     net_usd |   avg_unit |
|:--------------|--------:|------------:|-----------:|
| target        |     235 |   819610.00 |    3487.70 |
| week_end      |     501 |   719569.00 |    1436.27 |
| dd30,target   |      91 |    83537.10 |     917.99 |
| dd30,week_end |     272 |   -70268.60 |    -258.34 |
| dd30,dd50     |    1847 | -1474771.60 |    -798.47 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      737 |  30111.80 |          28.49 |            1.12 |       40.86 |       -28265.10 |                 1.07 |
| Q2               |      735 |  -3079.10 |          27.21 |            0.99 |       -4.19 |       -56249.90 |                -0.05 |
| Q3               |      736 | -25848.50 |          27.85 |            0.94 |      -35.12 |       -63256.10 |                -0.41 |
| Q4 high          |      736 |  78663.90 |          31.25 |            1.13 |      106.88 |       -45886.30 |                 1.71 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
