# NQ OR-norm @40× — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are included.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 432 |
| Net | $24027067.50 |
| Campaign closed DD | $-804305.00 |
| Win rate | 65.97% |
| Profit factor | 3.458 |
| Avg trade | $55618.21 |
| Median trade | $2907.50 |
| Max losing streak | 5 |
| Full initial SL losses | 109 (25.2%) |
| Hit TP (any) | 55.6% |
| EOD / flatten | 54.2% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 9 rolling 50-campaign windows have PF < 1.0.
- Full initial SL share is high (25.2%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $10878800.00 |
| Top 10 share of net | 45.28% |
| Worst 10 losers net | $-3340000.00 |
| Worst 10 share of |net| | 13.90% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $0.00 |
| Gap-through beyond 1 tick | $0.00 |
| Filled stop count | 0 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 0 |
| Max recovery calendar days | 0 |
| Unresolved recovery days | 0 |
| Bars in close-equity DD | 0.00% |

## Yearly stability

|    year |   trades |     net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|------------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2021.00 |    91.00 |  2314645.00 |      -804305.00 |              2.88 |          62.64 |            1.94 |                    23.15 |
| 2022.00 |    18.00 |   788607.50 |      -385185.00 |              2.05 |          61.11 |            2.82 |                     0.33 |
| 2023.00 |    94.00 |  3377662.50 |      -760027.50 |              4.44 |          65.96 |            2.98 |                     1.05 |
| 2024.00 |   116.00 |  4605320.00 |      -724065.00 |              6.36 |          63.79 |            2.45 |                     0.70 |
| 2025.00 |    95.00 | 11505642.50 |      -370825.00 |             31.03 |          68.42 |            8.67 |                     1.03 |
| 2026.00 |    18.00 |  1435190.00 |      -498300.00 |              2.88 |          88.89 |            3.86 |                     0.06 |

## Rolling stability (50)

- Windows: 383
- Worst rolling PF: 0.583
- Worst rolling Net/closed-DD: -0.92
- Rolling PF < 1.0 count: 9

## Exit dependency

| exit_reason         |   units |     net_usd |   avg_unit |
|:--------------------|--------:|------------:|-----------:|
| eod_close,tp1,tp2   |      88 | 25447277.50 |  289173.61 |
| eod_close,tp1       |      63 |  5123402.50 |   81323.85 |
| runner_stop,tp1     |      71 |  1273067.50 |   17930.53 |
| runner_stop,tp1,tp2 |      18 |   997965.00 |   55442.50 |
| eod_close           |      83 |   472782.50 |    5696.17 |
| wide_stop           |     109 | -9287427.50 |  -85205.76 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |     net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|------------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      108 |  1614095.00 |          63.89 |            1.47 |    14945.32 |     -1005732.50 |                 1.60 |
| Q2               |      108 |  3940705.00 |          68.52 |            2.47 |    36488.01 |      -670072.50 |                 5.88 |
| Q3               |      108 | 11174967.50 |          67.59 |            9.77 |   103471.92 |      -498300.00 |                22.43 |
| Q4 high          |      108 |  7297300.00 |          63.89 |            4.03 |    67567.59 |      -468560.00 |                15.57 |

### OR width quartile

_(empty)_

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
