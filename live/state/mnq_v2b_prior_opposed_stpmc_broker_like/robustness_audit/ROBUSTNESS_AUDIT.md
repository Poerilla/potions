# MNQ Prior-Opposed v2b Robustness Audit

Purpose: aggressively poke holes in the confirmed broker-like MNQ prior-opposed ST+PMC -> v2b `S_1_1_3` result.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 353 |
| Net | $113547.50 |
| Campaign closed DD | $-3493.50 |
| Win rate | 68.56% |
| Profit factor | 2.615 |
| Avg trade | $321.66 |
| Median trade | $199.00 |
| Skew | 1.097 |
| Max losing streak | 4 |
| Max winning streak | 11 |

## Main Ways This Could Be Fragile

- Weakest year is 2022: $874.50 net, 1.11 PF, 0.27 Net/closed-DD.
- Gap-through stop damage is more than 10% of net.
- Opening-range-width fragility: Q4 high has 1.44 Net/closed-DD and 1.48 PF.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $33166.00 |
| Top 10 winners share of total net | 29.21% |
| Worst 10 losers net | $-15875.00 |
| Worst 10 losers share of total net | 13.98% |
| Positive campaign share | 68.56% |

Top winner and loser tables are in `top_10_winners.csv` and `worst_10_losers.csv`.

## Execution Fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost vs stop price | $52673.00 |
| Gap-through cost beyond the baseline 1 tick | $51483.00 |
| Filled stop count | 495 |

Stop slippage includes the normal 1-tick adverse stop fill. Gap-through isolates the amount beyond that baseline.

## Recovery / Exposure

| Metric | Value |
|---|---:|
| Max recovery bars | 19343 |
| Max recovery calendar days | 407 |
| Unresolved recovery days at end | 1 |
| Bars in close-equity drawdown | 99.36% |

## Yearly Stability

|   year |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|-------:|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
|   2021 |       77 |  26560.00 |          72.73 |            3.63 |      344.94 |        -1097.50 |       -337.86 |        -1267.50 |                24.20 |
|   2022 |       16 |    874.50 |          56.25 |            1.11 |       54.66 |        -3196.50 |       -919.53 |        -1630.00 |                 0.27 |
|   2023 |       74 |  16291.00 |          67.57 |            2.34 |      220.15 |        -3493.50 |       -343.34 |        -1337.50 |                 4.66 |
|   2024 |       93 |  18747.00 |          63.44 |            1.81 |      201.58 |        -2535.00 |       -488.44 |        -2607.50 |                 7.40 |
|   2025 |       74 |  38097.00 |          70.27 |            3.71 |      514.82 |        -2300.00 |       -522.06 |        -2012.50 |                16.56 |
|   2026 |       19 |  12978.00 |          84.21 |            5.61 |      683.05 |        -1550.00 |       -775.00 |        -2050.00 |                 8.37 |

## Rolling Stability

- Rolling windows: 304 using 50 campaigns.
- Worst rolling PF: 1.143
- Worst rolling Net/closed-DD: 0.54
- Rolling PF < 1.0 count: 0

Charts: [`charts/campaign_equity_dd.png`](charts/campaign_equity_dd.png), [`charts/rolling_50_metrics.png`](charts/rolling_50_metrics.png).

## Runner / Exit Dependency

| exit_reason   |   units |   net_usd |   avg_unit |
|:--------------|--------:|----------:|-----------:|
| eod_close     |     800 | 119194.00 |     148.99 |
| tp1           |     235 |  27796.50 |     118.28 |
| tp2           |     115 |  25649.50 |     223.04 |
| runner_stop   |     300 |  -7267.50 |     -24.23 |
| wide_stop     |     315 | -51825.00 |    -164.52 |

## Cross-Regime Quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low           |       89 |  14322.50 |          64.04 |            2.04 |      160.93 |        -2809.50 |       -322.11 |        -1017.50 |                 5.10 |
| Q2               |       88 |  48899.00 |          76.14 |            5.15 |      555.67 |        -2337.50 |       -334.94 |        -1462.50 |                20.92 |
| Q3               |       88 |  20317.00 |          67.05 |            1.95 |      230.88 |        -2983.50 |       -516.11 |        -2607.50 |                 6.81 |
| Q4 high          |       88 |  30009.00 |          67.05 |            2.28 |      341.01 |        -3847.00 |       -697.24 |        -2520.00 |                 7.80 |

### Opening gap quartile

| gap_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:---------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
|                |      353 | 113547.50 |          68.56 |            2.61 |      321.66 |        -3493.50 |       -467.19 |        -2607.50 |                32.50 |

### Opening range width quartile

| or_width_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:--------------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low              |       89 |  18586.00 |          70.79 |            2.95 |      208.83 |        -1792.50 |       -266.57 |        -1100.00 |                10.37 |
| Q2                  |       88 |  22474.00 |          65.91 |            2.70 |      255.39 |        -2380.00 |       -321.34 |        -1047.50 |                 9.44 |
| Q3                  |       88 |  56706.00 |          75.00 |            4.81 |      644.39 |        -3077.00 |       -434.94 |        -1277.50 |                18.43 |
| Q4 high             |       88 |  15781.50 |          62.50 |            1.48 |      179.34 |       -10997.50 |       -848.18 |        -2607.50 |                 1.44 |

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