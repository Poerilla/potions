# MYM Prior-Opposed v2b Robustness Audit

Purpose: aggressively poke holes in the confirmed broker-like MYM prior-opposed ST+PMC -> v2b `S_1_1_3` result.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 333 |
| Net | $26053.62 |
| Campaign closed DD | $-2482.12 |
| Win rate | 59.76% |
| Profit factor | 1.742 |
| Avg trade | $78.24 |
| Median trade | $47.38 |
| Skew | 0.409 |
| Max losing streak | 6 |
| Max winning streak | 12 |

## Main Ways This Could Be Fragile

- 27 rolling 50-campaign windows have PF < 1.0.
- Weakest year is 2024: $1789.38 net, 1.16 PF, 0.72 Net/closed-DD.
- Gap-through stop damage is more than 10% of net.
- Loss streak reaches 5+ campaigns; sizing must tolerate clustering.
- Opening-range-width fragility: Q3 has 0.81 Net/closed-DD and 1.24 PF.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $9812.12 |
| Top 10 winners share of total net | 37.66% |
| Worst 10 losers net | $-5692.50 |
| Worst 10 losers share of total net | 21.85% |
| Positive campaign share | 59.76% |

Top winner and loser tables are in `top_10_winners.csv` and `worst_10_losers.csv`.

## Execution Fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost vs stop price | $18241.12 |
| Gap-through cost beyond the baseline 1 tick | $17095.62 |
| Filled stop count | 475 |

Stop slippage includes the normal 1-tick adverse stop fill. Gap-through isolates the amount beyond that baseline.

## Recovery / Exposure

| Metric | Value |
|---|---:|
| Max recovery bars | 36140 |
| Max recovery calendar days | 305 |
| Unresolved recovery days at end | 3 |
| Bars in close-equity drawdown | 99.45% |

## Yearly Stability

|   year |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|-------:|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
|   2021 |       72 |   5028.25 |          61.11 |            1.77 |       69.84 |        -1840.75 |       -155.93 |         -563.12 |                 2.73 |
|   2022 |       21 |   4794.75 |          71.43 |            3.20 |      228.32 |        -1076.38 |       -208.27 |         -578.12 |                 4.45 |
|   2023 |       62 |   3435.00 |          58.06 |            1.62 |       55.40 |        -1355.62 |       -186.52 |         -763.12 |                 2.53 |
|   2024 |       86 |   1789.38 |          53.49 |            1.16 |       20.81 |        -2482.12 |       -208.23 |         -650.62 |                 0.72 |
|   2025 |       76 |   7898.88 |          63.16 |            1.97 |      103.93 |        -1282.50 |       -214.51 |         -662.50 |                 6.16 |
|   2026 |       16 |   3107.38 |          62.50 |            2.83 |      194.21 |        -1203.88 |       -213.32 |         -502.50 |                 2.58 |

## Rolling Stability

- Rolling windows: 284 using 50 campaigns.
- Worst rolling PF: 0.810
- Worst rolling Net/closed-DD: -0.62
- Rolling PF < 1.0 count: 27

Charts: [`charts/campaign_equity_dd.png`](charts/campaign_equity_dd.png), [`charts/rolling_50_metrics.png`](charts/rolling_50_metrics.png).

## Runner / Exit Dependency

| exit_reason   |   units |   net_usd |   avg_unit |
|:--------------|--------:|----------:|-----------:|
| eod_close     |     771 |  40329.22 |      52.31 |
| tp1           |     192 |   9444.92 |      49.19 |
| tp2           |      76 |   7339.32 |      96.57 |
| runner_stop   |     271 |  -4969.54 |     -18.34 |
| wide_stop     |     355 | -26085.80 |     -73.48 |

## Cross-Regime Quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low           |       84 |   -342.88 |          51.19 |            0.96 |       -4.08 |        -1870.38 |       -172.92 |         -555.00 |                -0.18 |
| Q2               |       83 |   7108.25 |          61.45 |            1.75 |       85.64 |        -2315.88 |       -192.92 |         -650.62 |                 3.07 |
| Q3               |       83 |   9934.38 |          62.65 |            2.35 |      119.69 |        -1091.38 |       -189.47 |         -763.12 |                 9.10 |
| Q4 high          |       83 |   9353.88 |          63.86 |            2.04 |      112.70 |        -1332.00 |       -223.19 |         -662.50 |                 7.02 |

### Opening gap quartile

| gap_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:---------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
|                |      333 |  26053.62 |          59.76 |            1.74 |       78.24 |        -2482.12 |       -194.56 |         -763.12 |                10.50 |

### Opening range width quartile

| or_width_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:--------------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low              |       86 |   5651.00 |          55.81 |            1.94 |       65.71 |         -759.88 |       -124.55 |         -342.50 |                 7.44 |
| Q2                  |       82 |   8566.00 |          69.51 |            2.56 |      104.46 |         -999.88 |       -156.69 |         -442.50 |                 8.57 |
| Q3                  |       82 |   2699.12 |          52.44 |            1.24 |       32.92 |        -3329.88 |       -225.78 |         -580.00 |                 0.81 |
| Q4 high             |       83 |   9137.50 |          61.45 |            1.74 |      110.09 |        -2331.88 |       -273.67 |         -763.12 |                 3.92 |

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