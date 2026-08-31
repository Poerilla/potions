# GBPUSD quarterly ATR4 fade ladder 1m broker (4h N/S 7.99 → 1m 5.36 · 33k · 46t) — instrument deep-check / robustness

Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are **not applicable** — skipped.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 46 |
| Net | $332917.96 |
| Campaign closed DD | $-37016.36 |
| Win rate | 47.83% |
| Profit factor | 3.010 |
| Avg trade | $7237.35 |
| Median trade | $-419.77 |
| Max losing streak | 3 |
| Full initial SL losses | 16 (34.8%) |
| Hit TP (any) | 65.2% |
| EOD / flatten | 0.0% |

## Fragility

- Top-10 winners contribute more than 45% of total net.
- At least one calendar year is net-negative.
- Weakest year is 2003: $-672.40 net, -1.00 N/S.
- Full initial SL share is high (34.8%).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $360157.98 |
| Top 10 share of net | 108.18% |
| Worst 10 losers net | $-103312.48 |
| Worst 10 share of |net| | 31.03% |

## Execution fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost | $449.00 |
| Gap-through beyond 1 tick | $193.00 |
| Filled stop count | 35 |

## Recovery

| Metric | Value |
|---|---:|
| Max recovery bars | 7234 |
| Max recovery calendar days | 1642 |
| Unresolved recovery days | 63 |
| Bars in close-equity DD | 98.21% |

## Yearly stability

|    year |   trades |   net_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   return_on_start_equity |
|--------:|---------:|----------:|----------------:|------------------:|---------------:|----------------:|-------------------------:|
| 2003.00 |     1.00 |   -672.40 |         -672.42 |             -1.00 |           0.00 |            0.00 |                    -0.01 |
| 2004.00 |     2.00 |  49331.90 |       -30474.93 |              1.62 |         100.00 |          inf    |                     0.50 |
| 2005.00 |     3.00 |  -1374.84 |       -21775.01 |             -0.06 |          33.33 |            0.92 |                    -0.01 |
| 2006.00 |     1.00 |  36817.74 |        -9536.00 |              3.86 |         100.00 |          inf    |                     0.25 |
| 2007.00 |     1.00 |  20627.44 |       -12400.00 |              1.66 |         100.00 |          inf    |                     0.11 |
| 2008.00 |     4.00 | -27427.42 |       -48998.77 |             -0.56 |          25.00 |            0.29 |                    -0.13 |
| 2009.00 |     1.00 |  -5934.56 |       -18506.12 |             -0.32 |           0.00 |            0.00 |                    -0.03 |
| 2010.00 |     1.00 |  13594.82 |       -10920.00 |              1.24 |         100.00 |          inf    |                     0.08 |
| 2011.00 |     2.00 |  51519.04 |       -16802.00 |              3.07 |         100.00 |          inf    |                     0.28 |
| 2012.00 |     1.00 |   -167.14 |       -13926.00 |             -0.01 |           0.00 |            0.00 |                    -0.00 |
| 2013.00 |     3.00 |  37253.76 |       -21088.01 |              1.77 |          33.33 |            4.44 |                     0.16 |
| 2014.00 |     3.00 |  19409.52 |       -19176.00 |              1.01 |          66.67 |            5.70 |                     0.07 |
| 2015.00 |     3.00 |  30861.40 |       -14069.18 |              2.19 |          33.33 |            3.16 |                     0.11 |
| 2016.00 |     4.00 |  23651.80 |       -36437.00 |              0.65 |          50.00 |            2.49 |                     0.07 |
| 2017.00 |     3.00 |  15566.26 |        -8820.00 |              1.76 |          33.33 |            2.08 |                     0.04 |
| 2019.00 |     2.00 |   1851.92 |       -19249.27 |              0.10 |          50.00 |            1.39 |                     0.01 |
| 2020.00 |     1.00 |   2877.60 |       -15642.00 |              0.18 |         100.00 |          inf    |                     0.01 |
| 2021.00 |     2.00 |  17687.98 |       -16990.00 |              1.04 |          50.00 |            3.20 |                     0.05 |
| 2022.00 |     2.00 | -11482.56 |       -21649.78 |             -0.53 |           0.00 |            0.00 |                    -0.03 |
| 2024.00 |     2.00 |   9124.48 |       -14534.00 |              0.63 |          50.00 |            2.06 |                     0.02 |
| 2025.00 |     3.00 |  39673.90 |       -14446.14 |              2.75 |          33.33 |            5.01 |                     0.10 |
| 2026.00 |     1.00 |  10127.32 |       -10604.00 |              0.96 |         100.00 |          inf    |                     0.02 |

## Rolling stability (50)

- Windows: 0
- Worst rolling PF: 0.000
- Worst rolling Net/closed-DD: 0.00
- Rolling PF < 1.0 count: 0

## Exit dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| flatten       |      26 |  142692.00 |    5488.15 |
| tp4           |      32 |  128163.08 |    4005.10 |
| tp3           |      36 |  110545.74 |    3070.72 |
| tp2           |      50 |  104503.00 |    2090.06 |
| tp1           |      60 |   62738.66 |    1045.64 |
| stop          |     256 | -215724.52 |    -842.67 |

## Cross-regime quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|---------------------:|
| Q1 low           |       12 | -17725.58 |          25.00 |            0.66 |    -1477.13 |       -41408.64 |                -0.43 |
| Q2               |       11 |  38930.74 |          36.36 |            1.91 |     3539.16 |       -17242.50 |                 2.26 |
| Q3               |       11 | 221272.36 |          72.73 |           14.93 |    20115.67 |        -7721.62 |                28.66 |
| Q4 high          |       12 |  90440.44 |          58.33 |            2.65 |     7536.70 |       -29531.26 |                 3.06 |

## Files

- `yearly_breakdown.csv`
- `campaigns_robustness.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `entry_hour_dist.csv` / `exit_hour_dist.csv`
- `charts/`
