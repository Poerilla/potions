# USDJPY FBO 1/1/3 atr80 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 156 |
| Net | $107890.36 |
| Campaign closed DD | $-19671.55 |
| Win rate | 50.64% |
| Profit factor | 1.529 |
| Avg trade | $691.60 |
| Median trade | $118.55 |
| Max losing streak | 6 |
| Full initial SL losses | 0 (0.0%) |
| Hit TP (any) | 81.4% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 4 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2019: $-5985.73 net, -0.83 N/S.
- Gap-through stop damage is more than 10% of |net|.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $98162.05 |
| Top 10 share of net | 90.98% |
| Worst 10 losers net | $-86362.27 |
| Worst 10 share of |net| | 80.05% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $19081.82 |
| Gap-through beyond 1 tick | $18372.73 |
| Filled stop count | 156 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 1411 |
| Max recovery calendar days | 1649 |
| Unresolved recovery days | 46 |
| Bars in close-equity DD | 96.67% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |     5.00 |  13008.86 |        -8313.64 |              1.56 |          80.00 |            7.46 |                     0.13 |
| 2004.00 |    10.00 |  -9435.23 |       -22725.77 |             -0.42 |          30.00 |            0.72 |                    -0.08 |
| 2005.00 |    10.00 |  13010.00 |       -14694.21 |              0.89 |          50.00 |            1.53 |                     0.13 |
| 2006.00 |     8.00 |   6472.91 |       -14903.64 |              0.43 |          62.50 |            1.40 |                     0.06 |
| 2007.00 |     6.00 |   8446.50 |        -8516.62 |              0.99 |          33.33 |            3.53 |                     0.07 |
| 2008.00 |     4.00 |   3018.05 |        -7390.38 |              0.41 |          50.00 |            1.71 |                     0.02 |
| 2009.00 |     7.00 | -10940.64 |       -21999.42 |             -0.50 |          42.86 |            0.24 |                    -0.08 |
| 2010.00 |     8.00 |  10631.77 |       -13876.18 |              0.77 |          62.50 |            1.97 |                     0.09 |
| 2011.00 |     8.00 |  -1057.77 |       -12538.69 |             -0.08 |          37.50 |            0.92 |                    -0.01 |
| 2012.00 |     7.00 |   7905.27 |        -7512.33 |              1.05 |          57.14 |            4.33 |                     0.06 |
| 2013.00 |     4.00 |  -2018.32 |        -9693.05 |             -0.21 |          25.00 |            0.12 |                    -0.01 |
| 2014.00 |     5.00 |  21286.36 |        -4343.83 |              4.90 |         100.00 |          inf    |                     0.15 |
| 2015.00 |    11.00 | -10205.09 |       -14066.36 |             -0.73 |          27.27 |            0.52 |                    -0.06 |
| 2016.00 |     4.00 |  -4098.55 |       -15231.82 |             -0.27 |          75.00 |            0.72 |                    -0.03 |
| 2017.00 |    11.00 |   5907.41 |       -10737.03 |              0.55 |          36.36 |            1.63 |                     0.04 |
| 2018.00 |     6.00 |   9234.68 |        -4206.62 |              2.20 |          50.00 |            8.11 |                     0.06 |
| 2019.00 |     3.00 |  -5985.73 |        -7244.50 |             -0.83 |          33.33 |            0.08 |                    -0.04 |
| 2020.00 |     8.00 |  -4386.41 |       -16334.37 |             -0.27 |          37.50 |            0.41 |                    -0.03 |
| 2021.00 |     9.00 |   1122.59 |        -8885.05 |              0.13 |          55.56 |            1.21 |                     0.01 |
| 2022.00 |     1.00 |  10209.00 |        -1045.45 |              9.77 |         100.00 |          inf    |                     0.07 |
| 2023.00 |     6.00 |  16155.14 |       -10654.86 |              1.52 |          66.67 |            5.95 |                     0.10 |
| 2024.00 |     4.00 |  14645.09 |        -8231.82 |              1.78 |         100.00 |          inf    |                     0.08 |
| 2025.00 |     7.00 |   7249.82 |       -15243.39 |              0.48 |          42.86 |            2.01 |                     0.04 |
| 2026.00 |     4.00 |   7714.64 |       -12409.09 |              0.62 |          75.00 |           17.05 |                     0.04 |

## Rolling stability (50)

- Windows: 107
- Worst rolling PF: 0.798
- Worst rolling Net/closed-DD: -0.79
- Rolling PF < 1.0 count: 4

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| tp1,tp2,tp3   |      26 |  163815.36 |    6300.59 |
| close,tp1,tp2 |      33 |   95060.64 |    2880.63 |
| close,tp1     |      68 |   -7149.14 |    -105.13 |
| close         |      29 | -143836.50 |   -4959.88 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       38 |  33014.95 |          60.53 |            2.16 |      868.81 |       -12326.91 |                 2.68 |
| Q2               |       37 |  -3151.09 |          35.14 |            0.93 |      -85.16 |       -11958.95 |                -0.26 |
| Q3               |       37 |  68988.45 |          56.76 |            2.08 |     1864.55 |       -16774.00 |                 4.11 |
| Q4 high          |       37 |  26460.50 |          56.76 |            1.58 |      715.15 |       -29070.77 |                 0.91 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
