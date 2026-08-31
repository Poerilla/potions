# NQ best-path second_after_upper (corrected) — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 8 |
| Net | $306961.76 |
| Campaign closed DD | $-7680.50 |
| Win rate | 50.00% |
| Profit factor | 39.878 |
| Avg trade | $38370.22 |
| Median trade | $7506.49 |
| Max losing streak | 3 |
| Full initial SL losses | 4 (50.0%) |
| Hit TP (any) | 50.0% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2016: $-6969.10 net, -0.95 N/S.
- Full initial SL share is high (50.0%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $306961.76 |
| Top 10 share of net | 100.00% |
| Worst 10 losers net | $306961.76 |
| Worst 10 share of |net| | 100.00% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $2123.96 |
| Gap-through beyond 1 tick | $1903.96 |
| Filled stop count | 6 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 11831 |
| Max recovery calendar days | 2721 |
| Unresolved recovery days | 139 |
| Bars in close-equity DD | 81.67% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2013.00 |     1.00 |  15227.98 |        -8260.00 |              1.84 |         100.00 |          inf    |                     0.15 |
| 2014.00 |     1.00 |   -215.00 |        -1100.00 |             -0.20 |           0.00 |            0.00 |                    -0.00 |
| 2016.00 |     1.00 |  -6969.10 |        -7300.00 |             -0.95 |           0.00 |            0.00 |                    -0.06 |
| 2019.00 |     1.00 |   -496.40 |        -6250.00 |             -0.08 |           0.00 |            0.00 |                    -0.00 |
| 2020.00 |     1.00 | 145574.52 |       -31430.00 |              4.63 |         100.00 |          inf    |                     1.35 |
| 2025.00 |     2.00 |  94307.82 |      -119067.65 |              0.79 |          50.00 |          439.64 |                     0.37 |
| 2026.00 |     1.00 |  59531.94 |       -58760.00 |              1.01 |         100.00 |          inf    |                     0.17 |

## Rolling stability (50)

- Windows: 0
- Worst rolling PF: 0.000
- Worst rolling Net/closed-DD: 0.00
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |   net_usd |   avg_unit |
|:--------------|--------:|----------:|-----------:|
| tp4           |       8 | 107869.50 |   13483.69 |
| flatten       |       4 |  78784.00 |   19696.00 |
| tp3           |       8 |  78656.26 |    9832.03 |
| tp2           |       8 |  49443.00 |    6180.38 |
| tp1           |       8 |  20234.74 |    2529.34 |
| stop          |      44 | -28025.74 |    -636.95 |

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
