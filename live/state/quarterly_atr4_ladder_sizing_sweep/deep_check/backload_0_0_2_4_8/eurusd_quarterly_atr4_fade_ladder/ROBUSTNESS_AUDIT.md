# EURUSD quarterly ATR4 fade ladder 0/0/2/4/8 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 16 |
| Net | $210299.42 |
| Campaign closed DD | $-48878.76 |
| Win rate | 31.25% |
| Profit factor | 3.569 |
| Avg trade | $13143.71 |
| Median trade | $-5017.74 |
| Max losing streak | 6 |
| Full initial SL losses | 11 (68.8%) |
| Hit TP (any) | 31.2% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2010: $-9531.06 net, -1.00 N/S.
- Full initial SL share is high (68.8%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $267762.14 |
| Top 10 share of net | 127.32% |
| Worst 10 losers net | $-77263.90 |
| Worst 10 share of |net| | 36.74% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $296.00 |
| Gap-through beyond 1 tick | $134.00 |
| Filled stop count | 12 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 33762 |
| Max recovery calendar days | 7642 |
| Unresolved recovery days | 378 |
| Bars in close-equity DD | 97.55% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |     1.00 | 113195.56 |       -15408.00 |              7.35 |         100.00 |          inf    |                     1.13 |
| 2004.00 |     2.00 |   5009.86 |       -58474.21 |              0.09 |          50.00 |            1.49 |                     0.02 |
| 2008.00 |     3.00 |  24795.76 |       -57240.00 |              0.43 |          33.33 |            2.14 |                     0.11 |
| 2010.00 |     1.00 |  -9531.06 |        -9534.00 |             -1.00 |           0.00 |            0.00 |                    -0.04 |
| 2012.00 |     1.00 |  -7555.66 |       -13314.00 |             -0.57 |           0.00 |            0.00 |                    -0.03 |
| 2015.00 |     1.00 |  -4614.12 |       -22456.00 |             -0.21 |           0.00 |            0.00 |                    -0.02 |
| 2019.00 |     2.00 | -12983.46 |       -28728.54 |             -0.45 |           0.00 |            0.00 |                    -0.06 |
| 2020.00 |     1.00 |  57270.16 |       -13580.00 |              4.22 |         100.00 |          inf    |                     0.27 |
| 2021.00 |     1.00 |  -4934.44 |        -6314.00 |             -0.78 |           0.00 |            0.00 |                    -0.02 |
| 2022.00 |     1.00 |  -5151.58 |        -7504.00 |             -0.69 |           0.00 |            0.00 |                    -0.02 |
| 2024.00 |     1.00 |  -5101.04 |        -6944.00 |             -0.73 |           0.00 |            0.00 |                    -0.02 |
| 2025.00 |     1.00 |  59899.44 |       -23528.00 |              2.55 |         100.00 |          inf    |                     0.24 |

## Rolling stability (50)

- Windows: 0
- Worst rolling PF: 0.000
- Worst rolling Net/closed-DD: 0.00
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |   net_usd |   avg_unit |
|:--------------|--------:|----------:|-----------:|
| flatten       |      36 | 227118.00 |    6308.83 |
| tp4           |      16 |  46287.24 |    2892.95 |
| tp3           |      10 |  24229.22 |    2422.92 |
| stop          |     162 | -87335.04 |    -539.11 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |        4 | -23236.08 |           0.00 |            0.00 |    -5809.02 |       -14849.52 |                -1.56 |
| Q2               |        4 | 104679.50 |          50.00 |            9.38 |    26169.88 |        -4934.44 |                21.21 |
| Q3               |        4 |  84101.18 |          25.00 |            3.89 |    21025.29 |       -29094.38 |                 2.89 |
| Q4 high          |        4 |  44754.82 |          50.00 |            3.63 |    11188.71 |        -9531.06 |                 4.70 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
