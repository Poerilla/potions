# GBPUSD best-path first_lower — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 51 |
| Net | $404130.30 |
| Campaign closed DD | $-30569.16 |
| Win rate | 50.98% |
| Profit factor | 3.501 |
| Avg trade | $7924.12 |
| Median trade | $1337.11 |
| Max losing streak | 3 |
| Full initial SL losses | 16 (31.4%) |
| Hit TP (any) | 68.6% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2022: $-11821.12 net, -0.54 N/S.
- Full initial SL share is high (31.4%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $355561.76 |
| Top 10 share of net | 87.98% |
| Worst 10 losers net | $-105256.73 |
| Worst 10 share of |net| | 26.05% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $1563.75 |
| Gap-through beyond 1 tick | $1301.75 |
| Filled stop count | 38 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 4844 |
| Max recovery calendar days | 1093 |
| Unresolved recovery days | 63 |
| Bars in close-equity DD | 97.94% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |     1.00 |   -110.00 |        -1290.00 |             -0.09 |           0.00 |            0.00 |                    -0.00 |
| 2004.00 |     2.00 |  49628.20 |       -29986.86 |              1.65 |         100.00 |          inf    |                     0.50 |
| 2005.00 |     3.00 |  -6760.56 |       -26046.99 |             -0.26 |          33.33 |            0.74 |                    -0.05 |
| 2006.00 |     1.00 |  35493.41 |        -9536.00 |              3.72 |         100.00 |          inf    |                     0.25 |
| 2007.00 |     1.00 |  15886.70 |       -12400.00 |              1.28 |         100.00 |          inf    |                     0.09 |
| 2008.00 |     4.00 |   1184.93 |       -32118.96 |              0.04 |          50.00 |            1.05 |                     0.01 |
| 2009.00 |     1.00 |  -6741.20 |       -21800.00 |             -0.31 |           0.00 |            0.00 |                    -0.03 |
| 2010.00 |     1.00 |  12633.27 |       -10920.00 |              1.16 |         100.00 |          inf    |                     0.07 |
| 2011.00 |     2.00 |  50217.46 |       -17580.95 |              2.86 |         100.00 |          inf    |                     0.25 |
| 2012.00 |     3.00 |  22027.48 |       -17150.20 |              1.28 |          33.33 |            3.70 |                     0.09 |
| 2013.00 |     3.00 |  36369.31 |       -22456.43 |              1.62 |          33.33 |            4.59 |                     0.13 |
| 2014.00 |     3.00 |  18638.80 |       -19176.00 |              0.97 |          66.67 |            5.68 |                     0.06 |
| 2015.00 |     3.00 |  30753.14 |       -13572.09 |              2.27 |          33.33 |            3.39 |                     0.09 |
| 2016.00 |     4.00 |  24441.60 |       -38836.04 |              0.63 |          50.00 |            2.92 |                     0.07 |
| 2017.00 |     4.00 |  27187.65 |       -14691.15 |              1.85 |          50.00 |            3.33 |                     0.07 |
| 2019.00 |     2.00 |   1677.37 |       -19305.89 |              0.09 |          50.00 |            1.39 |                     0.00 |
| 2020.00 |     1.00 |  -3362.65 |       -14502.00 |             -0.23 |           0.00 |            0.00 |                    -0.01 |
| 2021.00 |     2.00 |  13681.02 |       -17070.00 |              0.80 |          50.00 |            2.86 |                     0.03 |
| 2022.00 |     2.00 | -11821.12 |       -21859.88 |             -0.54 |           0.00 |            0.00 |                    -0.03 |
| 2023.00 |     2.00 |  36743.02 |       -16686.71 |              2.20 |         100.00 |          inf    |                     0.09 |
| 2024.00 |     2.00 |   7970.14 |       -14206.00 |              0.56 |          50.00 |            2.09 |                     0.02 |
| 2025.00 |     3.00 |  38499.24 |       -13938.99 |              2.76 |          33.33 |            4.99 |                     0.08 |
| 2026.00 |     1.00 |   9893.08 |       -10604.00 |              0.93 |         100.00 |          inf    |                     0.02 |

## Rolling stability (50)

- Windows: 2
- Worst rolling PF: 3.439
- Worst rolling Net/closed-DD: 12.90
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| flatten       |      30 |  162835.00 |    5427.83 |
| tp4           |      42 |  153513.18 |    3655.08 |
| tp3           |      46 |  128017.44 |    2782.99 |
| tp2           |      60 |  113964.00 |    1899.40 |
| tp1           |      70 |   64539.08 |     921.99 |
| stop          |     262 | -218738.08 |    -834.88 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       13 |  31165.46 |          38.46 |            1.86 |     2397.34 |       -17062.41 |                 1.83 |
| Q2               |       13 |  63884.80 |          30.77 |            2.19 |     4914.22 |       -18531.26 |                 3.45 |
| Q3               |       12 | 210867.96 |          75.00 |           16.05 |    17572.33 |       -13903.19 |                15.17 |
| Q4 high          |       13 |  98212.07 |          61.54 |            2.69 |     7554.77 |       -30569.16 |                 3.21 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
