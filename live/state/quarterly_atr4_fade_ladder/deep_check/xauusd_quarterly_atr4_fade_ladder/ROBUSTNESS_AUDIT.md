# XAUUSD family first_only_lower — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 30 |
| Net | $249404.42 |
| Campaign closed DD | $-45950.50 |
| Win rate | 46.67% |
| Profit factor | 2.829 |
| Avg trade | $8313.48 |
| Median trade | $-110.00 |
| Max losing streak | 7 |
| Full initial SL losses | 13 (43.3%) |
| Hit TP (any) | 56.7% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2013: $-20915.20 net, -0.63 N/S.
- Gap-through stop damage is more than 10% of |net|.
- Full initial SL share is high (43.3%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $362671.91 |
| Top 10 share of net | 145.42% |
| Worst 10 losers net | $-122693.35 |
| Worst 10 share of |net| | 49.19% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $29140.47 |
| Gap-through beyond 1 tick | $28968.47 |
| Filled stop count | 21 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 14522 |
| Max recovery calendar days | 3367 |
| Unresolved recovery days | 517 |
| Bars in close-equity DD | 98.32% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |     1.00 |  13194.83 |        -4044.00 |              3.26 |         100.00 |          inf    |                     0.13 |
| 2004.00 |     2.00 |   9727.96 |        -4953.00 |              1.96 |          50.00 |            4.98 |                     0.09 |
| 2005.00 |     3.00 |  37607.28 |       -10150.81 |              3.70 |          66.67 |            6.28 |                     0.31 |
| 2006.00 |     1.00 |  -9732.54 |       -21442.00 |             -0.45 |           0.00 |            0.00 |                    -0.06 |
| 2007.00 |     1.00 |  28025.15 |       -10642.20 |              2.63 |         100.00 |          inf    |                     0.19 |
| 2008.00 |     1.00 |  11974.31 |       -16128.60 |              0.74 |         100.00 |          inf    |                     0.07 |
| 2009.00 |     3.00 |  21192.47 |       -32744.59 |              0.65 |          33.33 |            1.88 |                     0.11 |
| 2010.00 |     1.00 | -11577.34 |       -26700.00 |             -0.43 |           0.00 |            0.00 |                    -0.05 |
| 2011.00 |     1.00 |   -394.27 |       -13019.00 |             -0.03 |           0.00 |            0.00 |                    -0.00 |
| 2012.00 |     3.00 |  43963.12 |       -27317.50 |              1.61 |          33.33 |            2.56 |                     0.22 |
| 2013.00 |     3.00 | -20915.20 |       -33247.07 |             -0.63 |           0.00 |            0.00 |                    -0.09 |
| 2015.00 |     1.00 |  -5224.67 |       -18702.60 |             -0.28 |           0.00 |            0.00 |                    -0.02 |
| 2016.00 |     1.00 |   -110.00 |       -10320.00 |             -0.01 |           0.00 |            0.00 |                    -0.00 |
| 2017.00 |     1.00 |  -6007.98 |       -17837.00 |             -0.34 |           0.00 |            0.00 |                    -0.03 |
| 2018.00 |     1.00 |   4201.64 |       -13676.00 |              0.31 |         100.00 |          inf    |                     0.02 |
| 2019.00 |     1.00 |  35670.75 |       -20318.00 |              1.76 |         100.00 |          inf    |                     0.17 |
| 2022.00 |     2.00 | -18553.51 |       -46733.18 |             -0.40 |          50.00 |            0.10 |                    -0.07 |
| 2023.00 |     1.00 |  76502.20 |       -20154.00 |              3.80 |         100.00 |          inf    |                     0.33 |
| 2024.00 |     2.00 |  39860.23 |       -49990.67 |              0.80 |         100.00 |          inf    |                     0.13 |

## Rolling stability (50)

- Windows: 0
- Worst rolling PF: 0.000
- Worst rolling Net/closed-DD: 0.00
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| flatten       |      18 |  157461.40 |    8747.86 |
| tp4           |      22 |   95150.36 |    4325.02 |
| tp3           |      24 |   73571.58 |    3065.48 |
| tp2           |      30 |   63590.80 |    2119.69 |
| tp1           |      34 |   32188.02 |     946.71 |
| stop          |     172 | -170907.70 |    -993.65 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |        8 |  92756.86 |          75.00 |           10.69 |    11594.61 |        -7124.81 |                13.02 |
| Q2               |        7 | -30593.83 |          14.29 |            0.06 |    -4370.55 |       -22967.31 |                -1.33 |
| Q3               |        7 |  84135.11 |          42.86 |            3.10 |    12019.30 |       -40012.14 |                 2.10 |
| Q4 high          |        8 | 103106.29 |          50.00 |            2.91 |    12888.29 |       -31340.67 |                 3.29 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
