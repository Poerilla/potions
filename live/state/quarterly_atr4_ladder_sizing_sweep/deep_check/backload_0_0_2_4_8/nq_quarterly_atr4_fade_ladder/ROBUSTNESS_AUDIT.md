# NQ quarterly ATR4 fade ladder 0/0/2/4/8 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 8 |
| Net | $517956.60 |
| Campaign closed DD | $-10752.70 |
| Win rate | 50.00% |
| Profit factor | 47.858 |
| Avg trade | $64744.57 |
| Median trade | $17577.73 |
| Max losing streak | 3 |
| Full initial SL losses | 4 (50.0%) |
| Hit TP (any) | 50.0% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2016: $-9756.74 net, -0.95 N/S.
- Full initial SL share is high (50.0%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $517956.60 |
| Top 10 share of net | 100.00% |
| Worst 10 losers net | $517956.60 |
| Worst 10 share of |net| | 100.00% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $3064.55 |
| Gap-through beyond 1 tick | $2704.55 |
| Filled stop count | 6 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 11838 |
| Max recovery calendar days | 2722 |
| Unresolved recovery days | 484 |
| Bars in close-equity DD | 81.73% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2013.00 |     1.00 |  35456.46 |       -33040.00 |              1.07 |         100.00 |          inf    |                     0.35 |
| 2014.00 |     1.00 |   -301.00 |        -1540.00 |             -0.20 |           0.00 |            0.00 |                    -0.00 |
| 2016.00 |     1.00 |  -9756.74 |       -10220.00 |             -0.95 |           0.00 |            0.00 |                    -0.07 |
| 2019.00 |     1.00 |   -694.96 |        -8750.00 |             -0.08 |           0.00 |            0.00 |                    -0.01 |
| 2020.00 |     1.00 | 374887.80 |      -125720.00 |              2.98 |         100.00 |          inf    |                     3.01 |
| 2025.00 |     2.00 |  76490.56 |      -349130.63 |              0.22 |          50.00 |          255.12 |                     0.15 |
| 2026.00 |     1.00 |  41874.48 |      -235040.00 |              0.18 |         100.00 |          inf    |                     0.07 |

## Rolling stability (50)

- Windows: 0
- Worst rolling PF: 0.000
- Worst rolling Net/closed-DD: 0.00
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |   net_usd |   avg_unit |
|:--------------|--------:|----------:|-----------:|
| flatten       |      16 | 315136.00 |   19696.00 |
| tp4           |      16 | 215739.00 |   13483.69 |
| tp3           |       8 |  78656.26 |    9832.03 |
| stop          |      72 | -91574.66 |   -1271.87 |

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
