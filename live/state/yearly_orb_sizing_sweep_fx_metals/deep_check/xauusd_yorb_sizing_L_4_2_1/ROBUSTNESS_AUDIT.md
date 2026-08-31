# XAUUSD Yearly ORB limit_retest 4/2/1 — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 91 |
| Net | $1033570.30 |
| Campaign closed DD | $-36001.00 |
| Win rate | 94.51% |
| Profit factor | 12.630 |
| Avg trade | $11357.92 |
| Median trade | $4050.90 |
| Max losing streak | 2 |
| Full initial SL losses | 0 (0.0%) |
| Hit TP (any) | 0.0% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2012: $-4543.70 net, -0.16 N/S.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $696218.00 |
| Top 10 share of net | 67.36% |
| Worst 10 losers net | $-87774.40 |
| Worst 10 share of |net| | 8.49% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $35.00 |
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
| 2004.00 |     8.00 |  19025.20 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.19 |
| 2005.00 |     1.00 |   1047.90 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.01 |
| 2006.00 |     8.00 |  46030.60 |        -8895.60 |              5.17 |          87.50 |            6.17 |                     0.38 |
| 2007.00 |     3.00 |   2341.50 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.01 |
| 2008.00 |     6.00 |  74079.60 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.44 |
| 2009.00 |     4.00 |   7781.90 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.03 |
| 2010.00 |     2.00 |  63338.80 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.25 |
| 2011.00 |     1.00 |  53922.90 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.17 |
| 2012.00 |     5.00 |  -4543.70 |       -28241.50 |             -0.16 |          60.00 |            0.84 |                    -0.01 |
| 2013.00 |     1.00 |   1614.20 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.00 |
| 2014.00 |     5.00 |  70271.40 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.19 |
| 2015.00 |     5.00 |  72634.70 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.17 |
| 2016.00 |     6.00 |  34546.40 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.07 |
| 2017.00 |     8.00 |  70157.20 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.13 |
| 2018.00 |     3.00 |   7043.40 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.01 |
| 2019.00 |     4.00 |   7588.70 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.01 |
| 2020.00 |     7.00 |  47586.70 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.08 |
| 2022.00 |     6.00 |  40929.20 |       -15736.00 |              2.60 |          83.33 |            3.60 |                     0.06 |
| 2023.00 |     5.00 |  63927.00 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.09 |
| 2024.00 |     1.00 | 116679.40 |           -0.00 |              0.00 |         100.00 |          inf    |                     0.15 |
| 2025.00 |     2.00 | 237567.30 |           -0.00 |              0.00 |          50.00 |            7.60 |                     0.27 |

## Rolling stability (50)

- Windows: 42
- Worst rolling PF: 8.713
- Worst rolling Net/closed-DD: 12.01
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason                   |   units |   net_usd |   avg_unit |
|:------------------------------|--------:|----------:|-----------:|
| close,runner_entry,target     |      17 | 792808.10 |   46635.77 |
| close,runner_entry            |      69 | 329636.30 |    4777.34 |
| runner_entry,runner_stop,stop |       5 | -88874.10 |  -17774.82 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       21 |  92703.40 |         100.00 |          inf    |     4414.45 |            0.00 |                 0.00 |
| Q2               |       21 | 241381.10 |          95.24 |           28.13 |    11494.34 |        -8895.60 |                27.13 |
| Q3               |       21 | 176371.20 |          85.71 |            5.01 |     8398.63 |       -28241.50 |                 6.25 |
| Q4 high          |       21 | 479780.60 |          95.24 |           14.33 |    22846.70 |       -36001.00 |                13.33 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
