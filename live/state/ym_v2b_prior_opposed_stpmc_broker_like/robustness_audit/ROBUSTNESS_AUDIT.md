# YM Prior-Opposed v2b Robustness Audit

Purpose: aggressively poke holes in the confirmed broker-like YM prior-opposed ST+PMC -> v2b `S_1_1_3` result.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 347 |
| Net | $320190.00 |
| Campaign closed DD | $-24017.50 |
| Win rate | 59.65% |
| Profit factor | 1.887 |
| Avg trade | $922.74 |
| Median trade | $516.25 |
| Skew | 0.438 |
| Max losing streak | 6 |
| Max winning streak | 7 |

## Main Ways This Could Be Fragile

- 13 rolling 50-campaign windows have PF < 1.0.
- Gap-through stop damage is more than 10% of net.
- Loss streak reaches 5+ campaigns; sizing must tolerate clustering.
- Opening-range-width fragility: Q3 has 3.46 Net/closed-DD and 1.67 PF.

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $105390.00 |
| Top 10 winners share of total net | 32.91% |
| Worst 10 losers net | $-60181.25 |
| Worst 10 losers share of total net | 18.80% |
| Positive campaign share | 59.65% |

Top winner and loser tables are in `top_10_winners.csv` and `worst_10_losers.csv`.

## Execution Fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost vs stop price | $173440.00 |
| Gap-through cost beyond the baseline 1 tick | $161525.00 |
| Filled stop count | 493 |

Stop slippage includes the normal 1-tick adverse stop fill. Gap-through isolates the amount beyond that baseline.

## Recovery / Exposure

| Metric | Value |
|---|---:|
| Max recovery bars | 32376 |
| Max recovery calendar days | 305 |
| Unresolved recovery days at end | 10 |
| Bars in close-equity drawdown | 98.77% |

## Yearly Stability

|   year |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|-------:|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
|   2021 |       76 |  53243.75 |          60.53 |            1.77 |      700.58 |       -17668.75 |      -1581.83 |        -5581.25 |                 3.01 |
|   2022 |       21 |  49185.00 |          71.43 |            3.30 |     2342.14 |       -10461.25 |      -2108.93 |        -5856.25 |                 4.70 |
|   2023 |       64 |  40593.75 |          60.94 |            1.76 |      634.28 |       -12898.75 |      -1806.93 |        -7681.25 |                 3.15 |
|   2024 |       85 |  35215.00 |          52.94 |            1.35 |      414.29 |       -24017.50 |      -2018.46 |        -6431.25 |                 1.47 |
|   2025 |       79 |  95773.75 |          62.03 |            2.20 |     1212.33 |       -12621.25 |      -2117.33 |        -6600.00 |                 7.59 |
|   2026 |       22 |  46178.75 |          59.09 |            2.29 |     2099.03 |       -19366.25 |      -2759.38 |        -8431.25 |                 2.38 |

## Rolling Stability

- Rolling windows: 298 using 50 campaigns.
- Worst rolling PF: 0.859
- Worst rolling Net/closed-DD: -0.39
- Rolling PF < 1.0 count: 13

Charts: [`charts/campaign_equity_dd.png`](charts/campaign_equity_dd.png), [`charts/rolling_50_metrics.png`](charts/rolling_50_metrics.png).

## Runner / Exit Dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| eod_close     |     811 |  455159.75 |     561.23 |
| tp1           |     198 |  103215.50 |     521.29 |
| tp2           |      78 |   80501.75 |    1032.07 |
| runner_stop   |     273 |  -42537.00 |    -155.81 |
| wide_stop     |     375 | -276150.00 |    -736.40 |

## Cross-Regime Quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low           |       87 |  -1547.50 |          49.43 |            0.98 |      -17.79 |       -18772.50 |      -1755.32 |        -5581.25 |                -0.08 |
| Q2               |       87 | 105048.75 |          66.67 |            2.31 |     1207.46 |       -22565.00 |      -1792.10 |        -6431.25 |                 4.66 |
| Q3               |       86 |  99198.75 |          61.63 |            2.24 |     1153.47 |       -11420.00 |      -1969.26 |        -7681.25 |                 8.69 |
| Q4 high          |       87 | 117490.00 |          60.92 |            2.14 |     1350.46 |       -19366.25 |      -2318.53 |        -8431.25 |                 6.07 |

### Opening gap quartile

| gap_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:---------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
|                |      347 | 320190.00 |          59.65 |            1.89 |      922.74 |       -24017.50 |      -1958.77 |        -8431.25 |                13.33 |

### Opening range width quartile

| or_width_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:--------------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low              |       87 |  59978.75 |          55.17 |            2.01 |      689.41 |        -9060.00 |      -1242.17 |        -2756.25 |                 6.62 |
| Q2                  |       89 |  82006.25 |          67.42 |            2.42 |      921.42 |       -13113.75 |      -1559.97 |        -4625.00 |                 6.25 |
| Q3                  |       84 |  71666.25 |          55.95 |            1.67 |      853.17 |       -20701.25 |      -2224.03 |        -5825.00 |                 3.46 |
| Q4 high             |       87 | 106538.75 |          59.77 |            1.78 |     1224.58 |       -19366.25 |      -2827.23 |        -8431.25 |                 5.50 |

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