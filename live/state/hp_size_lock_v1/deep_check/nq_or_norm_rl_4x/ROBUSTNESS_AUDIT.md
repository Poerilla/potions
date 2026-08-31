# NQ OR-norm HP sleeve @4x (resting limit, or_norm only) — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are included.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 129 |
| Net | $581952.50 |
| Campaign closed DD | $-19855.00 |
| Win rate | 70.54% |
| Profit factor | 3.585 |
| Avg trade | $4511.26 |
| Median trade | $2482.50 |
| Max losing streak | 4 |
| Full initial SL losses | 32 (24.8%) |
| Hit TP (any) | 64.3% |
| EOD / flatten | 53.5% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- Weakest year is 2022: $19677.50 net, 0.00 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $271970.00 |
| Top 10 share of net | 46.73% |
| Worst 10 losers net | $-83500.00 |
| Worst 10 share of |net| | 14.35% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $16657.50 |
| Gap-through beyond 1 tick | $12102.50 |
| Filled stop count | 189 |

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
| 2021.00 |    31.00 |  54497.50 |       -19855.00 |              2.74 |          61.29 |            1.94 |                     0.54 |
| 2022.00 |     3.00 |  19677.50 |           -0.00 |              0.00 |          66.67 |            3.20 |                     0.13 |
| 2023.00 |    25.00 |  81602.50 |       -18612.50 |              4.38 |          68.00 |            3.06 |                     0.47 |
| 2024.00 |    36.00 | 109865.00 |       -19082.50 |              5.76 |          69.44 |            2.47 |                     0.43 |
| 2025.00 |    28.00 | 283980.00 |        -9165.00 |             30.99 |          82.14 |            9.95 |                     0.78 |
| 2026.00 |     6.00 |  32330.00 |       -12457.50 |              2.60 |          83.33 |            3.60 |                     0.05 |

## Rolling stability (50)

- Windows: 80
- Worst rolling PF: 2.179
- Worst rolling Net/closed-DD: 6.17
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| eod_close     |     251 |  556803.50 |    2218.34 |
| tp2           |      45 |  126992.50 |    2822.06 |
| tp1           |      83 |  115695.50 |    1393.92 |
| runner_stop   |     106 |   -1749.00 |     -16.50 |
| wide_stop     |     160 | -215790.00 |   -1348.69 |

## Cross-regime quartiles

### ATR14 quartile

_(empty)_

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
