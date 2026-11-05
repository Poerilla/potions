# TOP3 Asia+MondayOR+CleanBreak (one book) — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 3934 |
| Net | $483665.23 |
| Campaign closed DD | $-25794.15 |
| Win rate | 30.30% |
| Profit factor | 1.280 |
| Avg trade | $122.94 |
| Median trade | $-25.90 |
| Max losing streak | 21 |
| Full initial SL losses | 54 (1.4%) |
| Hit TP (any) | 7.9% |
| EOD / flatten | 9.6% |

## Fragility

- 1112 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2003: $-3906.07 net, -0.36 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $118483.66 |
| Top 10 share of net | 24.50% |
| Worst 10 losers net | $-67541.73 |
| Worst 10 share of |net| | 13.96% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $0.00 |
| Gap-through beyond 1 tick | $0.00 |
| Filled stop count | 0 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 235 |
| Max recovery calendar days | 403 |
| Unresolved recovery days | 44 |
| Bars in close-equity DD | 91.62% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |    40.00 |  -3906.07 |       -10795.98 |             -0.36 |          30.00 |            0.85 |                    -0.04 |
| 2004.00 |    87.00 |  20386.91 |       -13539.47 |              1.51 |          31.03 |            1.40 |                     0.21 |
| 2005.00 |    70.00 |   6900.20 |       -25180.84 |              0.27 |          30.00 |            1.17 |                     0.06 |
| 2006.00 |    84.00 |  -2685.24 |       -27409.54 |             -0.10 |          30.95 |            0.95 |                    -0.02 |
| 2007.00 |    82.00 |  26098.85 |        -6993.17 |              3.73 |          36.59 |            1.71 |                     0.22 |
| 2008.00 |    75.00 |  26541.40 |       -13669.91 |              1.94 |          37.33 |            1.50 |                     0.18 |
| 2009.00 |    78.00 |  11727.60 |       -17318.81 |              0.68 |          29.49 |            1.20 |                     0.07 |
| 2010.00 |    93.00 |  10276.35 |       -10724.11 |              0.96 |          30.11 |            1.21 |                     0.06 |
| 2011.00 |    81.00 |   5393.36 |       -13411.73 |              0.40 |          25.93 |            1.17 |                     0.03 |
| 2012.00 |    91.00 |  10187.38 |        -9900.17 |              1.03 |          34.07 |            1.31 |                     0.05 |
| 2013.00 |    85.00 |  21289.71 |       -17805.30 |              1.20 |          30.59 |            1.38 |                     0.10 |
| 2014.00 |    82.00 |  13816.00 |       -12476.47 |              1.11 |          39.02 |            1.44 |                     0.06 |
| 2015.00 |   279.00 |  42268.14 |       -21925.36 |              1.93 |          45.88 |            1.30 |                     0.17 |
| 2016.00 |   128.00 |  43882.64 |       -13921.61 |              3.15 |          37.50 |            1.61 |                     0.15 |
| 2017.00 |   216.00 |  30092.34 |        -8416.86 |              3.58 |          22.22 |            1.70 |                     0.09 |
| 2018.00 |   242.00 |   3015.19 |       -17921.23 |              0.17 |          20.25 |            1.05 |                     0.01 |
| 2019.00 |   243.00 |     58.04 |       -14260.31 |              0.00 |          20.99 |            1.00 |                     0.00 |
| 2020.00 |   223.00 |  24308.76 |       -15041.84 |              1.62 |          20.18 |            1.53 |                     0.07 |
| 2021.00 |   303.00 |  -3385.66 |       -29897.02 |             -0.11 |          27.06 |            0.95 |                    -0.01 |
| 2022.00 |   375.00 |  76584.97 |       -27343.60 |              2.80 |          35.20 |            1.32 |                     0.20 |
| 2023.00 |   336.00 |  29699.29 |       -31597.48 |              0.94 |          27.68 |            1.20 |                     0.06 |
| 2024.00 |   348.00 |  46570.33 |       -17715.15 |              2.63 |          29.89 |            1.25 |                     0.09 |
| 2025.00 |   257.00 |  48429.88 |       -18745.57 |              2.58 |          36.19 |            1.36 |                     0.09 |
| 2026.00 |    36.00 |  -3885.15 |       -15159.24 |             -0.26 |          38.89 |            0.87 |                    -0.01 |

## Rolling stability (50)

- Windows: 3885
- Worst rolling PF: 0.180
- Worst rolling Net/closed-DD: -1.46
- Rolling PF < 1.0 count: 1112

## Exit dependency

| exit_reason           |   units |    net_usd |   avg_unit |
|:----------------------|--------:|-----------:|-----------:|
| target                |     181 |  310518.79 |    1715.57 |
| week_end              |     178 |  308348.65 |    1732.30 |
| eod_close,tp1         |      60 |  177762.36 |    2962.71 |
| entry                 |    1312 |  151499.74 |     115.47 |
| dd30,target           |      41 |   79562.35 |    1940.55 |
| eod_close,tp1,tp2     |      17 |   74658.79 |    4391.69 |
| dd30,week_end         |      99 |   52378.42 |     529.07 |
| eod_close             |     376 |   23920.47 |      63.62 |
| runner_stop,tp1       |      10 |    1651.00 |     165.10 |
| ambiguous_break_close |       7 |    -162.55 |     -23.22 |
| trail_stop            |      48 |   -5678.95 |    -118.31 |
| failed_clean_close    |     517 |   -6000.80 |     -11.61 |
| close_back_into_range |     440 |  -16284.75 |     -37.01 |
| wide_stop             |      54 | -143816.78 |   -2663.27 |
| dd30,dd50             |     594 | -524691.51 |    -883.32 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      625 |  41264.60 |          22.24 |            1.33 |       66.02 |       -20308.47 |                 2.03 |
| Q2               |      624 |   9518.22 |          24.68 |            1.05 |       15.25 |       -34212.58 |                 0.28 |
| Q3               |      624 |  61512.22 |          29.33 |            1.24 |       98.58 |       -20451.99 |                 3.01 |
| Q4 high          |      625 | 142197.71 |          31.52 |            1.43 |      227.52 |       -21007.51 |                 6.77 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
