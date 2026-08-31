# EURUSD best-path second_after_upper — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 16 |
| Net | $83746.68 |
| Campaign closed DD | $-22278.84 |
| Win rate | 37.50% |
| Profit factor | 2.802 |
| Avg trade | $5234.17 |
| Median trade | $-3344.66 |
| Max losing streak | 4 |
| Full initial SL losses | 8 (50.0%) |
| Hit TP (any) | 50.0% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2010: $-6862.90 net, -1.01 N/S.
- Full initial SL share is high (50.0%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $117070.54 |
| Top 10 share of net | 139.79% |
| Worst 10 losers net | $-46464.48 |
| Worst 10 share of |net| | 55.48% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $189.00 |
| Gap-through beyond 1 tick | $85.00 |
| Filled stop count | 12 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 26587 |
| Max recovery calendar days | 6021 |
| Unresolved recovery days | 378 |
| Bars in close-equity DD | 97.54% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |     1.00 |  43104.62 |       -10560.00 |              4.08 |         100.00 |          inf    |                     0.43 |
| 2004.00 |     2.00 |  10577.79 |       -20286.55 |              0.52 |          50.00 |            2.43 |                     0.07 |
| 2008.00 |     3.00 |  14600.33 |       -19080.00 |              0.77 |          33.33 |            2.26 |                     0.10 |
| 2010.00 |     1.00 |  -6862.90 |        -6810.00 |             -1.01 |           0.00 |            0.00 |                    -0.04 |
| 2012.00 |     1.00 |  -2871.68 |        -7608.00 |             -0.38 |           0.00 |            0.00 |                    -0.02 |
| 2015.00 |     1.00 |  -3350.82 |       -16040.00 |             -0.21 |           0.00 |            0.00 |                    -0.02 |
| 2019.00 |     2.00 |  -2986.44 |       -13610.23 |             -0.22 |          50.00 |            0.11 |                    -0.02 |
| 2020.00 |     1.00 |  20570.07 |        -5586.00 |              3.68 |         100.00 |          inf    |                     0.14 |
| 2021.00 |     1.00 |  -3579.60 |        -4510.00 |             -0.79 |           0.00 |            0.00 |                    -0.02 |
| 2022.00 |     1.00 |  -3734.65 |        -5360.00 |             -0.70 |           0.00 |            0.00 |                    -0.02 |
| 2024.00 |     1.00 |  -3698.62 |        -4960.00 |             -0.75 |           0.00 |            0.00 |                    -0.02 |
| 2025.00 |     1.00 |  21978.58 |        -5882.00 |              3.74 |         100.00 |          inf    |                     0.14 |

## Rolling stability (50)

- Windows: 0
- Worst rolling PF: 0.000
- Worst rolling Net/closed-DD: 0.00
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |   net_usd |   avg_unit |
|:--------------|--------:|----------:|-----------:|
| flatten       |      10 |  60089.00 |    6008.90 |
| tp3           |      10 |  24229.22 |    2422.92 |
| tp4           |       8 |  23143.62 |    2892.95 |
| tp2           |      12 |  18729.00 |    1560.75 |
| tp1           |      16 |  12773.04 |     798.32 |
| stop          |     104 | -54337.24 |    -522.47 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |        4 | -10419.71 |          25.00 |            0.03 |    -2604.93 |       -10771.78 |                -0.97 |
| Q2               |        4 |  36097.36 |          50.00 |            6.60 |     9024.34 |        -3579.60 |                10.08 |
| Q3               |        4 |  26144.77 |          25.00 |            2.54 |     6536.19 |       -16959.85 |                 1.54 |
| Q4 high          |        4 |  31924.25 |          50.00 |            3.60 |     7981.06 |        -6862.90 |                 4.65 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
