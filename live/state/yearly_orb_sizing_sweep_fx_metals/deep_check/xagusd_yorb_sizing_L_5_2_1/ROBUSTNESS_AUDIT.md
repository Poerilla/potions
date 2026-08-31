# XAGUSD Yearly ORB limit_retest 5/2/1 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 89 |
| Net | $296836.75 |
| Campaign closed DD | $-5407.00 |
| Win rate | 86.52% |
| Profit factor | 25.597 |
| Avg trade | $3335.24 |
| Median trade | $1321.00 |
| Max losing streak | 3 |
| Full initial SL losses | 0 (0.0%) |
| Hit TP (any) | 0.0% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2004: $-457.00 net, -0.13 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $172199.50 |
| Top 10 share of net | 58.01% |
| Worst 10 losers net | $-11990.00 |
| Worst 10 share of |net| | 4.04% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $36.00 |
| Gap-through beyond 1 tick | $0.00 |
| Filled stop count | 15 |

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
| 2004.00 |     7.00 |   -457.00 |        -3566.00 |             -0.13 |          57.14 |            0.88 |                    -0.00 |
| 2005.00 |     5.00 |   6549.50 |           -0.00 |              0.00 |          80.00 |           40.22 |                     0.07 |
| 2006.00 |     9.00 |  39266.25 |         -503.00 |             78.06 |          88.89 |           79.06 |                     0.37 |
| 2007.00 |     4.00 |   8254.50 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.06 |
| 2008.00 |     1.00 |    697.00 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.00 |
| 2009.00 |     4.00 |  17241.50 |        -5407.00 |              3.19 |          75.00 |            4.19 |                     0.11 |
| 2010.00 |     4.00 |  28833.50 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.17 |
| 2011.00 |     4.00 |  62380.00 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.31 |
| 2012.00 |     8.00 |  14288.00 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.05 |
| 2013.00 |     1.00 |   5489.00 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.02 |
| 2014.00 |     1.00 |   1417.00 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.01 |
| 2015.00 |     5.00 |  12783.25 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.05 |
| 2016.00 |     3.00 |   8421.00 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.03 |
| 2017.00 |     4.00 |   7093.50 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.02 |
| 2018.00 |     1.00 |   5726.75 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.02 |
| 2019.00 |     7.00 |   2918.50 |         -934.00 |              3.12 |          57.14 |            2.60 |                     0.01 |
| 2020.00 |     1.00 |  31375.50 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.10 |
| 2021.00 |     8.00 |   4856.00 |         -110.00 |             44.15 |          75.00 |           45.15 |                     0.01 |
| 2022.00 |     4.00 |  16512.50 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.05 |
| 2023.00 |     6.00 |  21732.50 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.06 |
| 2025.00 |     2.00 |   1458.00 |         -151.00 |              9.66 |          50.00 |           10.66 |                     0.00 |

## Rolling stability (50)

- Windows: 40
- Worst rolling PF: 19.908
- Worst rolling Net/closed-DD: 34.54
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason                          |   units |   net_usd |   avg_unit |
|:-------------------------------------|--------:|----------:|-----------:|
| close,runner_entry,target            |      23 | 200251.75 |    8706.60 |
| close,runner_entry                   |      60 |  68564.00 |    1142.73 |
| runner_entry,runner_stop,target      |       1 |  37577.50 |   37577.50 |
| runner_entry,runner_stop,stop,target |       1 |   1167.50 |    1167.50 |
| runner_entry,runner_stop,stop        |       4 | -10724.00 |   -2681.00 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       21 |  33737.00 |          76.19 |            7.11 |     1606.52 |         -934.00 |                36.12 |
| Q2               |       21 |  69546.50 |          90.48 |          186.95 |     3311.74 |         -335.00 |               207.60 |
| Q3               |       20 |  59743.00 |          85.00 |          229.90 |     2987.15 |         -151.00 |               395.65 |
| Q4 high          |       21 |  92646.50 |          90.48 |           16.68 |     4411.74 |        -5407.00 |                17.13 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
