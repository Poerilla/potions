# US30 London 4h OR S_1_1_1 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 1355 |
| Net | $22708.25 |
| Campaign closed DD | $-13790.65 |
| Win rate | 52.77% |
| Profit factor | 1.128 |
| Avg trade | $16.76 |
| Median trade | $30.30 |
| Max losing streak | 10 |
| Full initial SL losses | 442 (32.6%) |
| Hit TP (any) | 42.4% |
| EOD / flatten | 48.8% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- 575 rolling 50-campaign windows have PF < 1.0.
- At least one calendar year is net-negative.
- Weakest year is 2023: $-6374.55 net, -0.65 N/S.
- Gap-through stop damage is more than 10% of |net|.
- Full initial SL share is high (32.6%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $12514.15 |
| Top 10 share of net | 55.11% |
| Worst 10 losers net | $-9769.95 |
| Worst 10 share of |net| | 43.02% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $15600.10 |
| Gap-through beyond 1 tick | $15016.60 |
| Filled stop count | 2039 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 273410 |
| Max recovery calendar days | 914 |
| Unresolved recovery days | 914 |
| Bars in close-equity DD | 99.66% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2021.00 |   370.00 |  16649.35 |        -3158.55 |              5.27 |          56.76 |            1.38 |                     0.17 |
| 2022.00 |    83.00 |   8262.65 |        -3758.95 |              2.20 |          63.86 |            1.65 |                     0.07 |
| 2023.00 |   319.00 |  -6374.55 |        -9838.75 |             -0.65 |          48.28 |            0.86 |                    -0.05 |
| 2024.00 |   468.00 |   5403.00 |        -7097.40 |              0.76 |          51.28 |            1.10 |                     0.05 |
| 2025.00 |   115.00 |  -1232.20 |        -7690.65 |             -0.16 |          50.43 |            0.94 |                    -0.01 |

## Rolling stability (50)

- Windows: 1306
- Worst rolling PF: 0.396
- Worst rolling Net/closed-DD: -1.13
- Rolling PF < 1.0 count: 575

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| eod_close     |    1513 |   73576.75 |      48.63 |
| tp1           |     574 |   59310.00 |     103.33 |
| tp2           |     208 |   36972.65 |     177.75 |
| runner_stop   |     444 |   -3787.15 |      -8.53 |
| wide_stop     |    1326 | -143364.00 |    -108.12 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |      340 |   -825.50 |          49.71 |            0.98 |       -2.43 |        -8152.65 |                -0.10 |
| Q2               |      339 |  -1316.55 |          51.92 |            0.97 |       -3.88 |        -5644.10 |                -0.23 |
| Q3               |      337 |   7346.15 |          54.01 |            1.17 |       21.80 |        -6853.95 |                 1.07 |
| Q4 high          |      339 |  17504.15 |          55.46 |            1.35 |       51.63 |        -7010.20 |                 2.50 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
