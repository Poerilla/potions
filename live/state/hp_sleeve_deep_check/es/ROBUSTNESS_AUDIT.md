# ES ST-age>180m @40× — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are included.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 245 |
| Net | $6517610.00 |
| Campaign closed DD | $-275870.00 |
| Win rate | 63.67% |
| Profit factor | 5.189 |
| Avg trade | $26602.49 |
| Median trade | $1255.00 |
| Max losing streak | 7 |
| Full initial SL losses | 48 (19.6%) |
| Hit TP (any) | 73.5% |
| EOD / flatten | 48.2% |

## Fragility

- Top-10 winners contribute more than 45% of total net.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $4264000.00 |
| Top 10 share of net | 65.42% |
| Worst 10 losers net | $-1164000.00 |
| Worst 10 share of |net| | 17.86% |

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

|    year |   trades |    net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|-----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2021.00 |    35.00 | 1701390.00 |      -181800.00 |              9.36 |          71.43 |            7.36 |                    17.01 |
| 2022.00 |    15.00 | 1057715.00 |      -275300.00 |              3.84 |          53.33 |            4.52 |                     0.59 |
| 2023.00 |    56.00 | 1074737.50 |      -223570.00 |              4.81 |          55.36 |            3.57 |                     0.38 |
| 2024.00 |    66.00 |  974340.00 |      -102595.00 |              9.50 |          65.15 |            5.82 |                     0.25 |
| 2025.00 |    54.00 | 1335855.00 |      -115800.00 |             11.54 |          68.52 |            5.07 |                     0.27 |
| 2026.00 |    19.00 |  373572.50 |       -18810.00 |             19.86 |          63.16 |           10.83 |                     0.06 |

## Rolling stability (50)

- Windows: 196
- Worst rolling PF: 3.135
- Worst rolling Net/closed-DD: 3.95
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason         |   units |    net_usd |   avg_unit |
|:--------------------|--------:|-----------:|-----------:|
| eod_close,tp1,tp2   |      71 | 4889670.00 |   68868.59 |
| eod_close,tp1       |      30 | 1974207.50 |   65806.92 |
| eod_close           |      17 |  397675.00 |   23392.65 |
| runner_stop,tp1,tp2 |      25 |  256792.50 |   10271.70 |
| runner_stop,tp1     |      54 | -217205.00 |   -4022.31 |
| wide_stop           |      48 | -783530.00 |  -16323.54 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |    net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|-----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       62 | 1233100.00 |          64.52 |            5.69 |    19888.71 |      -147407.50 |                 8.37 |
| Q2               |       61 | 1223612.50 |          59.02 |            2.67 |    20059.22 |      -275870.00 |                 4.44 |
| Q3               |       61 | 2213562.50 |          65.57 |            7.41 |    36287.91 |      -209140.00 |                10.58 |
| Q4 high          |       61 | 1847335.00 |          65.57 |            9.57 |    30284.18 |      -115800.00 |                15.95 |

### ST age bucket

| st_age_bucket   |   trades |    net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:----------------|---------:|-----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| st_age_30_90m   |       71 |  127980.00 |          60.56 |            2.27 |     1802.54 |       -16132.50 |                 7.93 |
| st_age_90_180m  |       46 |   33242.50 |          56.52 |            1.57 |      722.66 |       -14117.50 |                 2.35 |
| st_age_gt180m   |       68 | 6327100.00 |          72.06 |            5.89 |    93045.59 |      -275300.00 |                22.98 |
| st_age_lt30m    |       60 |   29287.50 |          63.33 |            1.28 |      488.12 |       -29102.50 |                 1.01 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
