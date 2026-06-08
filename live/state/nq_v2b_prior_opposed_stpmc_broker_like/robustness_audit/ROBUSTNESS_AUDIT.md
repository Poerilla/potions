# NQ Prior-Opposed v2b Robustness Audit

Purpose: aggressively poke holes in the confirmed broker-like NQ prior-opposed ST+PMC -> v2b `S_1_1_3` result.

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 352 |
| Net | $1184585.00 |
| Campaign closed DD | $-34652.50 |
| Win rate | 69.32% |
| Profit factor | 2.747 |
| Avg trade | $3365.30 |
| Median trade | $2072.50 |
| Skew | 1.093 |
| Max losing streak | 4 |
| Max winning streak | 11 |

## Main Ways This Could Be Fragile

- Weakest year is 2022: $13425.00 net, 1.17 PF, 0.43 Net/closed-DD.
- Gap-through stop damage is more than 10% of net.
- Opening-gap fragility: Q3 has 2.94 Net/closed-DD and 3.27 PF.
- Opening-range-width fragility: Q4 high has 1.52 Net/closed-DD and 1.50 PF.

Follow-up tests:

- Filter/reduced-size scenario matrix: [`FILTER_STUDY.md`](FILTER_STUDY.md).
- CPI/FOMC event-date audit: [`EVENT_CALENDAR_AUDIT.md`](EVENT_CALENDAR_AUDIT.md).
- 2022 forensic chart index: [`../charts/prior_opposed_15m/INDEX_2022.md`](../charts/prior_opposed_15m/INDEX_2022.md).

## Concentration

| Metric | Value |
|---|---:|
| Top 10 winners net | $332350.00 |
| Top 10 winners share of total net | 28.06% |
| Worst 10 losers net | $-157950.00 |
| Worst 10 losers share of total net | 13.33% |
| Positive campaign share | 69.32% |

Top winner and loser tables are in `top_10_winners.csv` and `worst_10_losers.csv`.

## Execution Fragility

| Metric | Value |
|---|---:|
| Stop adverse fill cost vs stop price | $528170.00 |
| Gap-through cost beyond the baseline 1 tick | $516365.00 |
| Filled stop count | 491 |

Stop slippage includes the normal 1-tick adverse stop fill. Gap-through isolates the amount beyond that baseline.

## Recovery / Exposure

| Metric | Value |
|---|---:|
| Max recovery bars | 18523 |
| Max recovery calendar days | 400 |
| Unresolved recovery days at end | 1 |
| Bars in close-equity drawdown | 99.33% |

## Yearly Stability

|   year |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|-------:|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
|   2021 |       77 | 273142.50 |          72.73 |            3.74 |     3547.31 |       -10815.00 |      -3332.14 |       -12675.00 |                25.26 |
|   2022 |       16 |  13425.00 |          56.25 |            1.17 |      839.06 |       -31382.50 |      -9175.00 |       -16150.00 |                 0.43 |
|   2023 |       73 | 168292.50 |          68.49 |            2.43 |     2305.38 |       -34652.50 |      -3445.55 |       -13350.00 |                 4.86 |
|   2024 |       93 | 199522.50 |          64.52 |            1.89 |     2145.40 |       -24945.00 |      -4790.32 |       -26100.00 |                 8.00 |
|   2025 |       74 | 399000.00 |          71.62 |            4.09 |     5391.89 |       -22815.00 |      -5068.58 |       -20225.00 |                17.49 |
|   2026 |       19 | 131202.50 |          84.21 |            5.70 |     6905.39 |       -15465.00 |      -7750.00 |       -20575.00 |                 8.48 |

## Rolling Stability

- Rolling windows: 303 using 50 campaigns.
- Worst rolling PF: 1.236
- Worst rolling Net/closed-DD: 1.06
- Rolling PF < 1.0 count: 0

Charts: [`charts/campaign_equity_dd.png`](charts/campaign_equity_dd.png), [`charts/rolling_50_metrics.png`](charts/rolling_50_metrics.png).

## Runner / Exit Dependency

| exit_reason   |   units |    net_usd |   avg_unit |
|:--------------|--------:|-----------:|-----------:|
| eod_close     |     806 | 1206666.00 |    1497.10 |
| tp1           |     237 |  281949.50 |    1189.66 |
| tp2           |     116 |  259191.00 |    2234.41 |
| runner_stop   |     301 |  -67971.50 |    -225.82 |
| wide_stop     |     300 | -495250.00 |   -1650.83 |

## Cross-Regime Quartiles

### ATR14 quartile

| atr14_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:-----------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low           |       88 | 152180.00 |          64.77 |            2.15 |     1729.32 |       -27497.50 |      -3208.81 |       -10100.00 |                 5.53 |
| Q2               |       88 | 453285.00 |          75.00 |            4.61 |     5150.97 |       -23340.00 |      -3414.77 |       -14750.00 |                19.42 |
| Q3               |       88 | 268185.00 |          70.45 |            2.43 |     3047.56 |       -23397.50 |      -4873.30 |       -26100.00 |                11.46 |
| Q4 high          |       88 | 310935.00 |          67.05 |            2.34 |     3533.35 |       -38182.50 |      -6943.18 |       -25075.00 |                 8.14 |

### Opening gap quartile

| gap_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:---------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low         |      165 | 630172.50 |          72.12 |            3.47 |     3819.23 |       -27140.00 |      -3798.64 |       -25075.00 |                23.22 |
| Q2             |       70 | 240380.00 |          72.86 |            3.21 |     3434.00 |       -18630.00 |      -4157.86 |       -14750.00 |                12.90 |
| Q3             |       45 | 168462.50 |          68.89 |            3.27 |     3743.61 |       -57212.50 |      -4557.22 |       -17575.00 |                 2.94 |
| Q4 high        |       72 | 145570.00 |          59.72 |            1.61 |     2021.81 |       -48045.00 |      -6942.01 |       -26100.00 |                 3.03 |

### Opening range width quartile

| or_width_quartile   |   trades |   net_usd |   win_rate_pct |   profit_factor |   avg_trade |   closed_dd_usd |   avg_mae_usd |   worst_mae_usd |   net_over_closed_dd |
|:--------------------|---------:|----------:|---------------:|----------------:|------------:|----------------:|--------------:|----------------:|---------------------:|
| Q1 low              |       88 | 191040.00 |          71.59 |            3.10 |     2170.91 |       -22842.50 |      -2621.31 |       -11000.00 |                 8.36 |
| Q2                  |       89 | 248617.50 |          67.42 |            3.00 |     2793.46 |       -25437.50 |      -3108.99 |       -10500.00 |                 9.77 |
| Q3                  |       87 | 581517.50 |          75.86 |            5.21 |     6684.11 |       -30202.50 |      -4282.47 |       -12775.00 |                19.25 |
| Q4 high             |       88 | 163410.00 |          62.50 |            1.50 |     1856.93 |      -107315.00 |      -8440.62 |       -26100.00 |                 1.52 |

## Known Gaps

- CPI/FOMC exclusion now has a first-pass official-date audit in [`EVENT_CALENDAR_AUDIT.md`](EVENT_CALENDAR_AUDIT.md), but it does not include surprise magnitude, other macro releases, or exact press-conference risk windows.
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
