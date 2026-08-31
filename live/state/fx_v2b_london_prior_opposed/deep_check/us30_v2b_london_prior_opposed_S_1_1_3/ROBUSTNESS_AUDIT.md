# US30 London prior-opposed S_1_1_3 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 300 |
| Net | $24369.95 |
| Campaign closed DD | $-3083.95 |
| Win rate | 61.33% |
| Profit factor | 1.835 |
| Avg trade | $81.23 |
| Median trade | $29.35 |
| Max losing streak | 4 |
| Full initial SL losses | 103 (34.3%) |
| Hit TP (any) | 63.7% |
| EOD / flatten | 23.7% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 20 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2025: $-700.85 net, -0.25 N/S.
- Gap-through stop damage is more than 10% of |net|.
- Full initial SL share is high (34.3%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $16038.95 |
| Top 10 share of net | 65.81% |
| Worst 10 losers net | $-6523.00 |
| Worst 10 share of |net| | 26.77% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $6558.55 |
| Gap-through beyond 1 tick | $6312.75 |
| Filled stop count | 529 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 88823 |
| Max recovery calendar days | 335 |
| Unresolved recovery days | 237 |
| Bars in close-equity DD | 99.70% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2021.00 |    97.00 |  12000.40 |        -1799.95 |              6.67 |          65.98 |            2.26 |                     0.12 |
| 2022.00 |    23.00 |   4554.65 |        -1956.90 |              2.33 |          65.22 |            2.67 |                     0.04 |
| 2023.00 |    59.00 |   -200.15 |        -3123.95 |             -0.06 |          57.63 |            0.97 |                    -0.00 |
| 2024.00 |    88.00 |   8715.90 |        -1917.95 |              4.54 |          60.23 |            2.35 |                     0.07 |
| 2025.00 |    33.00 |   -700.85 |        -2803.20 |             -0.25 |          54.55 |            0.82 |                    -0.01 |

## Rolling stability (50)

- Windows: 251
- Worst rolling PF: 0.656
- Worst rolling Net/closed-DD: -0.62
- Rolling PF < 1.0 count: 20

## Exit dependency

| exit_reason   |   units |   net_usd |   avg_unit |
|:--------------|--------:|----------:|-----------:|
| eod_close     |     228 |  36465.90 |     159.94 |
| tp2           |     123 |  10100.95 |      82.12 |
| tp1           |     191 |   7806.65 |      40.87 |
| runner_stop   |     443 |  -2178.55 |      -4.92 |
| wide_stop     |     515 | -27825.00 |     -54.03 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       76 |   9514.85 |          60.53 |            2.76 |      125.20 |        -1202.10 |                 7.92 |
| Q2               |       74 |   9516.05 |          67.57 |            3.02 |      128.60 |        -1030.45 |                 9.23 |
| Q3               |       75 |   2631.60 |          58.67 |            1.31 |       35.09 |        -2508.75 |                 1.05 |
| Q4 high          |       75 |   2707.45 |          58.67 |            1.26 |       36.10 |        -3083.35 |                 0.88 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
