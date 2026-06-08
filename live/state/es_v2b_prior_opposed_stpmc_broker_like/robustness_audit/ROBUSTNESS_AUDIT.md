# ES Prior-Opposed v2b Robustness Audit

Purpose: aggressively poke holes in the confirmed broker-like ES prior-opposed ST+PMC -> v2b `S_1_1_3` result.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 245 |
| Net | $348687.50 |
| Campaign closed DD | $-27950.00 |
| Win rate | 63.67% |
| Profit factor | 2.180 |
| Avg trade | $1423.21 |
| Median trade | $592.50 |
| Skew | 0.587 |
| Max losing streak | 7 |
| Max winning streak | 12 |

## Main Ways This Could Be Fragile

- Weakest year is 2023: $22030.00 net, 1.27 PF, 0.79 Net/closed-DD.
- Gap-through stop damage is more than 10% of net.
- Loss streak reaches 5+ campaigns; sizing must tolerate clustering.
- Opening-range-width fragility: Q4 high has 3.48 Net/closed-DD and 1.79 PF.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $142375.00 |
| Top 10 winners share of total net | 40.83% |
| Worst 10 losers net | $-79800.00 |
| Worst 10 losers share of total net | 22.89% |
| Positive campaign share | 63.67% |

Top winner and loser tables are in `top_10_winners.csv` and `worst_10_losers.csv`.

## Execution Fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost vs stop price | $255325.00 |
| Gap-through cost beyond the baseline 1 tick | $233375.00 |
| Filled stop count | 372 |

Stop slippage includes the normal 1-tick adverse stop fill. Gap-through isolates the amount beyond that baseline.

## Recovery / Exposure

| Metric | Value |
|---|---:|
| Max recovery bars | 41055 |
| Max recovery calendar days | 327 |
| Unresolved recovery days at end | 21 |
| Bars in close-equity drawdown | 99.62% |

## Yearly Stability

|   year |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|-------:|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
|   2021 |       35 |  84937.50 |          71.43 |            4.21 |     2426.79 |        -9280.00 |      -1671.43 |        -5875.00 |                 9.15 |
|   2022 |       15 |  25287.50 |          53.33 |            1.78 |     1685.83 |       -12077.50 |      -3987.50 |        -8437.50 |                 2.09 |
|   2023 |       56 |  22030.00 |          55.36 |            1.27 |      393.39 |       -27950.00 |      -2354.91 |        -9375.00 |                 0.79 |
|   2024 |       66 |  83092.50 |          65.15 |            2.20 |     1258.98 |       -15455.00 |      -2236.74 |       -13437.50 |                 5.38 |
|   2025 |       54 | 108720.00 |          68.52 |            3.23 |     2013.33 |        -9765.00 |      -2476.85 |        -8312.50 |                11.13 |
|   2026 |       19 |  24620.00 |          63.16 |            1.65 |     1295.79 |       -18810.00 |      -3651.32 |        -9750.00 |                 1.31 |

## Rolling Stability

- Rolling windows: 196 using 50 campaigns.
- Worst rolling PF: 1.092
- Worst rolling Net/closed-DD: 0.25
- Rolling PF < 1.0 count: 0

Charts: [`charts/campaign_equity_dd.png`](charts/campaign_equity_dd.png), [`charts/rolling_50_metrics.png`](charts/rolling_50_metrics.png).

## Runner / Exit Dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| eod_close     |     412 |  444219.50 |    1078.20 |
| tp2           |     102 |  103597.00 |    1015.66 |
| tp1           |     180 |   96742.50 |     537.46 |
| runner_stop   |     291 |  -76574.00 |    -263.14 |
| wide_stop     |     240 | -219297.50 |    -913.74 |

## Cross-Regime Quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low           |       62 |  75872.50 |          64.52 |            2.52 |     1223.75 |       -11250.00 |      -1702.62 |        -6500.00 |                 6.74 |
| Q2               |       61 |  75355.00 |          59.02 |            2.11 |     1235.33 |       -13565.00 |      -2097.34 |        -7562.50 |                 5.56 |
| Q3               |       61 |  85917.50 |          65.57 |            2.01 |     1408.48 |       -28810.00 |      -2592.21 |       -13437.50 |                 2.98 |
| Q4 high          |       61 | 111542.50 |          65.57 |            2.21 |     1828.57 |       -18810.00 |      -3431.35 |       -10000.00 |                 5.93 |

### Opening gap quartile

| gap_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:---------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
|                |      245 | 348687.50 |          63.67 |            2.18 |     1423.21 |       -27950.00 |      -2452.81 |       -13437.50 |                12.48 |

### Opening range width quartile

| or_width_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:--------------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low              |       63 |  66377.50 |          68.25 |            3.03 |     1053.61 |        -7877.50 |      -1371.03 |        -4187.50 |                 8.43 |
| Q2                  |       60 |  70150.00 |          65.00 |            2.37 |     1169.17 |       -11842.50 |      -1698.96 |        -3937.50 |                 5.92 |
| Q3                  |       62 |  96535.00 |          62.90 |            2.46 |     1557.02 |       -11167.50 |      -2507.06 |        -6625.00 |                 8.64 |
| Q4 high             |       60 | 115625.00 |          58.33 |            1.79 |     1927.08 |       -33227.50 |      -4286.46 |       -13437.50 |                 3.48 |

## Known Gaps

- CPI/FOMC exclusion is not included yet because no local event calendar was found in the workspace. Add a dated event-calendar CSV and rerun this audit to quantify those exclusions.
- Replay/live parity still needs an online dry-run harness: restart mid-session, replay from persisted state, compare expected order book to broker-paper order book, and verify no duplicate re-arming.
- This audit estimates per-campaign intrabar heat from 1m bars; the headline replay `intrabar_stress_dd` remains the authoritative portfolio-level stress number.

## Files

- `campaigns_robustness.csv`
- `yearly_breakdown.csv`
- `rolling_50.csv`
- `exit_reason_contribution.csv`
- `stop_slippage_audit.csv`
- `top_10_winners.csv`
- `worst_10_losers.csv`