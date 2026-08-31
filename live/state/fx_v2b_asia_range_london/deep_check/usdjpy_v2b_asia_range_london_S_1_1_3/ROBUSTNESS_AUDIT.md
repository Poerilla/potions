# USDJPY Asia-range London v2b S_1_1_3 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 1673 |
| Net | $104653.14 |
| Campaign closed DD | $-49133.77 |
| Win rate | 49.07% |
| Profit factor | 1.135 |
| Avg trade | $62.55 |
| Median trade | $-18.50 |
| Max losing streak | 11 |
| Full initial SL losses | 213 (12.7%) |
| Hit TP (any) | 17.8% |
| EOD / flatten | 84.2% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 697 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2019: $-8559.05 net, -0.75 N/S.
- Gap-through stop damage is more than 10% of |net|.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $78444.09 |
| Top 10 share of net | 74.96% |
| Worst 10 losers net | $-51075.91 |
| Worst 10 share of |net| | 48.80% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $106431.82 |
| Gap-through beyond 1 tick | $97672.73 |
| Filled stop count | 1938 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 465636 |
| Max recovery calendar days | 2122 |
| Unresolved recovery days | 98 |
| Bars in close-equity DD | 99.86% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2015.00 |   216.00 |  34340.36 |        -6568.71 |              5.23 |          53.70 |            1.43 |                     0.34 |
| 2016.00 |    36.00 |   4934.00 |       -10648.57 |              0.46 |          63.89 |            1.27 |                     0.04 |
| 2017.00 |   114.00 |  -9779.00 |       -22991.18 |             -0.43 |          50.88 |            0.81 |                    -0.07 |
| 2018.00 |   157.00 | -21875.41 |       -32625.73 |             -0.67 |          38.22 |            0.65 |                    -0.17 |
| 2019.00 |    77.00 |  -8559.05 |       -11460.48 |             -0.75 |          40.26 |            0.59 |                    -0.08 |
| 2020.00 |    47.00 |  11589.59 |        -6145.77 |              1.89 |          44.68 |            1.90 |                     0.12 |
| 2021.00 |   233.00 |  -9136.86 |       -16425.18 |             -0.56 |          46.35 |            0.87 |                    -0.08 |
| 2022.00 |   256.00 |  56195.82 |       -17495.36 |              3.21 |          51.17 |            1.36 |                     0.55 |
| 2023.00 |   167.00 |   9850.50 |       -19879.18 |              0.50 |          47.31 |            1.12 |                     0.06 |
| 2024.00 |   148.00 |  32832.00 |       -15608.48 |              2.10 |          47.97 |            1.38 |                     0.20 |
| 2025.00 |   156.00 |  14514.91 |       -20314.48 |              0.71 |          56.41 |            1.17 |                     0.07 |
| 2026.00 |    66.00 | -10253.73 |       -15797.05 |             -0.65 |          53.03 |            0.74 |                    -0.05 |

## Rolling stability (50)

- Windows: 1624
- Worst rolling PF: 0.246
- Worst rolling Net/closed-DD: -1.14
- Rolling PF < 1.0 count: 697

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| eod_close     |    6731 |  341094.39 |      50.68 |
| tp1           |     298 |   98943.76 |     332.03 |
| tp2           |      66 |   38133.07 |     577.77 |
| runner_stop   |     205 |   -5982.14 |     -29.18 |
| wide_stop     |    1065 | -367535.95 |    -345.10 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      420 | -24161.82 |          43.10 |            0.81 |      -57.53 |       -34312.82 |                -0.70 |
| Q2               |      418 |    762.45 |          45.69 |            1.00 |        1.82 |       -22434.18 |                 0.03 |
| Q3               |      418 |  42584.27 |          53.11 |            1.22 |      101.88 |       -17411.32 |                 2.45 |
| Q4 high          |      417 |  85468.23 |          54.44 |            1.30 |      204.96 |       -14828.82 |                 5.76 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
