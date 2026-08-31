# AUDJPY Yearly ORB limit_retest 4/1/1 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 146 |
| Net | $420146.78 |
| Campaign closed DD | $-7408.61 |
| Win rate | 90.41% |
| Profit factor | 12.445 |
| Avg trade | $2877.72 |
| Median trade | $1578.65 |
| Max losing streak | 2 |
| Full initial SL losses | 0 (0.0%) |
| Hit TP (any) | 0.0% |
| EOD / flatten | 0.0% |

## Fragility

- At least one calendar year is net-negative.
- Weakest year is 2006: $-2161.34 net, -0.48 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $131939.18 |
| Top 10 share of net | 31.40% |
| Worst 10 losers net | $-35262.64 |
| Worst 10 share of |net| | 8.39% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $42.73 |
| Gap-through beyond 1 tick | $0.00 |
| Filled stop count | 26 |

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
| 2004.00 |     6.00 |  12405.51 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.12 |
| 2005.00 |     3.00 |  22143.21 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.20 |
| 2006.00 |     3.00 |  -2161.34 |        -4527.72 |             -0.48 |          66.67 |            0.52 |                    -0.02 |
| 2007.00 |     7.00 |  55962.34 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.42 |
| 2008.00 |     7.00 |  50635.06 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.27 |
| 2009.00 |     3.00 |  10945.94 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.05 |
| 2010.00 |    11.00 |  51247.83 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.21 |
| 2011.00 |    12.00 |  26583.75 |         -311.35 |             85.38 |          91.67 |           86.38 |                     0.09 |
| 2012.00 |     5.00 |   7999.59 |         -709.54 |             11.27 |          80.00 |           12.27 |                     0.02 |
| 2013.00 |     6.00 |  18015.51 |        -1642.26 |             10.97 |          83.33 |           11.97 |                     0.05 |
| 2014.00 |    17.00 |  13042.43 |        -7408.61 |              1.76 |          76.47 |            2.19 |                     0.04 |
| 2015.00 |     1.00 |   1499.55 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.00 |
| 2016.00 |     9.00 |   5608.72 |         -540.89 |             10.37 |          66.67 |            4.03 |                     0.02 |
| 2017.00 |    11.00 |  26896.01 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.07 |
| 2018.00 |     5.00 |  14479.59 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.04 |
| 2019.00 |     2.00 |   1297.29 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.00 |
| 2020.00 |     8.00 |   8401.89 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.02 |
| 2021.00 |     4.00 |   8905.49 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.02 |
| 2022.00 |    10.00 |  17725.55 |        -4609.54 |              3.85 |          80.00 |            2.56 |                     0.04 |
| 2023.00 |     1.00 |   4699.55 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.01 |
| 2024.00 |    10.00 |  37445.55 |        -5313.17 |              7.05 |          90.00 |            8.05 |                     0.08 |
| 2025.00 |     5.00 |  26367.77 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.05 |

## Rolling stability (50)

- Windows: 97
- Worst rolling PF: 5.309
- Worst rolling Net/closed-DD: 8.98
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason                          |   units |   net_usd |   avg_unit |
|:-------------------------------------|--------:|----------:|-----------:|
| close,runner_entry                   |     113 | 228178.75 |    2019.28 |
| close,runner_entry,target            |      23 | 207477.03 |    9020.74 |
| runner_entry,runner_stop,target      |       1 |   8485.92 |    8485.92 |
| runner_entry,runner_stop,stop,target |       2 |   7606.38 |    3803.19 |
| runner_entry,runner_stop,stop        |       7 | -31601.30 |   -4514.47 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       34 |  44771.22 |          88.24 |            3.56 |     1316.80 |        -9220.85 |                 4.86 |
| Q2               |       33 |  97105.30 |          96.97 |           36.11 |     2942.58 |        -2765.90 |                35.11 |
| Q3               |       33 |  95594.39 |          87.88 |            8.94 |     2896.80 |        -7124.53 |                13.42 |
| Q4 high          |       33 | 163408.03 |         100.00 |          inf    |     4951.76 |            0.00 |                 0.00 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
