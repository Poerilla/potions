# QQQ Sliding 2-Month-Low Limit DCA Study

Data: Yahoo adjusted daily OHLCV for `QQQ`.
Window: **2000-01-03 through 2026-06-03**.

## Rule

- Each trading day calculates the adjusted low of the **prior 2 calendar months**, excluding the current day.
- A buy limit is considered filled if the current daily low touches that trailing level. Fill price is the trailing low level, which is conservative on gap-down days for a buy limit.
- `all_touches` buys every daily touch; `new_touch_cluster` buys only the first touch after a non-touch day; `first_touch_per_month` buys the first touch per calendar month.
- Cashflow comparison: contribute **$1,000/month**. Monthly DCA buys first trading day open; signal variants hold cash and buy only on rolling-low signals.
- Matched-add sizing uses **12 months of DCA budget / expected fills per year**, capped by available cash. `static_full_window` is diagnostic; `expanding_prior_rate` uses only prior signal frequency.
- No year-end catch-up, no fees, taxes, slippage, or cash interest.

## Fill Frequency

| Event Mode | Definition | Signals | Signals / Yr | Static Matched Add | Zero-Fill Complete Years |
|---|---|---:|---:|---:|---:|
| all_touches | Every daily touch of the trailing low | 379 | 14.35 | $836 | 2 |
| new_touch_cluster | First touch after a non-touch day | 176 | 6.66 | $1,801 | 2 |
| first_touch_per_month | First touch per calendar month | 98 | 3.71 | $3,234 | 2 |

## Performance Leaderboard

| Rank | Event Mode | Sizing | Signals/Yr | Buys | Avg Buy | Deployed | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure | Ending Cash |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | first_touch_per_month | static_full_window | 3.71 | 98 | $2,783 | 85.8% | $3,656,047 | $-345,029 | $-639,673 | 5.22 | 93.0% | $45,277 |
| 2 | first_touch_per_month | rolling_5y_rate | 3.71 | 98 | $3,160 | 97.4% | $3,618,968 | $-382,108 | $-639,484 | 5.16 | 90.8% | $8,277 |
| 3 | new_touch_cluster | rolling_5y_rate | 6.66 | 154 | $1,995 | 96.6% | $3,578,122 | $-422,955 | $-627,700 | 5.19 | 90.1% | $10,743 |
| 4 | new_touch_cluster | static_full_window | 6.66 | 155 | $1,669 | 81.3% | $3,515,494 | $-485,583 | $-610,367 | 5.24 | 92.3% | $59,317 |
| 5 | all_touches | rolling_5y_rate | 14.35 | 308 | $974 | 94.3% | $3,495,457 | $-505,619 | $-611,294 | 5.20 | 89.4% | $18,005 |
| 6 | all_touches | static_full_window | 14.35 | 304 | $792 | 75.7% | $3,456,153 | $-544,923 | $-599,234 | 5.24 | 92.1% | $77,365 |
| 7 | first_touch_per_month | expanding_prior_rate | 3.71 | 98 | $2,466 | 76.0% | $3,055,060 | $-946,016 | $-522,492 | 5.24 | 85.4% | $76,334 |
| 8 | new_touch_cluster | expanding_prior_rate | 6.66 | 167 | $1,365 | 71.7% | $2,972,334 | $-1,028,742 | $-504,072 | 5.27 | 84.3% | $89,971 |
| 9 | all_touches | expanding_prior_rate | 14.35 | 348 | $589 | 64.4% | $2,859,134 | $-1,141,942 | $-482,348 | 5.27 | 82.8% | $113,184 |

Monthly DCA baseline: **$4,001,076 ending equity**, **$3,683,076 net**, **$-714,352 max DD**, **5.16 Net/DD**.

## Main Read

- Best tested row is **first_touch_per_month / static_full_window**, ending at **$3,656,047**, **$-345,029** versus monthly DCA, with **85.8%** deployed.
- The cleanest cadence is **new_touch_cluster**: **176** fills, **6.66/year**, static matched add **$1,801**.
- Static matched `new_touch_cluster` ends at **$3,515,494**, **$-485,583** versus monthly DCA, with **81.3%** deployed.
- Causal expanding-rate `new_touch_cluster` ends at **$2,972,334**, **$-1,028,742** versus monthly DCA, with **71.7%** deployed.

## Recent New-Touch Events

| Date | Buy Price | Rolling Low Date | Window Start | Daily Low | Daily Close |
|---|---:|---|---|---:|---:|
| 2022-10-10 | 261.41 | 2022-09-30 | 2022-08-10 | 258.03 | 260.74 |
| 2022-10-13 | 255.47 | 2022-10-11 | 2022-08-13 | 248.85 | 263.10 |
| 2023-08-18 | 351.84 | 2023-06-26 | 2023-06-18 | 349.01 | 352.37 |
| 2023-09-26 | 349.01 | 2023-08-18 | 2023-07-26 | 348.03 | 349.02 |
| 2023-10-23 | 346.21 | 2023-09-27 | 2023-08-23 | 345.97 | 350.46 |
| 2023-10-25 | 345.97 | 2023-10-23 | 2023-08-25 | 344.62 | 345.21 |
| 2024-04-19 | 416.50 | 2024-02-21 | 2024-02-19 | 408.58 | 410.15 |
| 2024-08-02 | 443.03 | 2024-06-03 | 2024-06-02 | 440.34 | 444.58 |
| 2025-02-28 | 496.55 | 2025-01-13 | 2024-12-28 | 493.80 | 504.97 |
| 2025-03-06 | 484.67 | 2025-03-04 | 2025-01-06 | 483.14 | 485.12 |
| 2025-03-13 | 464.07 | 2025-03-11 | 2025-01-13 | 463.49 | 465.39 |
| 2025-03-31 | 463.49 | 2025-03-13 | 2025-01-31 | 455.13 | 466.66 |
| 2025-04-03 | 455.13 | 2025-03-31 | 2025-02-03 | 447.97 | 448.49 |
| 2025-11-20 | 587.00 | 2025-09-25 | 2025-09-20 | 583.26 | 584.18 |
| 2026-02-05 | 598.75 | 2025-12-17 | 2025-12-05 | 594.01 | 596.28 |
| 2026-02-17 | 594.01 | 2026-02-05 | 2025-12-17 | 592.59 | 600.54 |
| 2026-03-03 | 592.59 | 2026-02-17 | 2026-01-03 | 591.12 | 600.82 |
| 2026-03-09 | 591.12 | 2026-03-03 | 2026-01-09 | 590.59 | 606.99 |
| 2026-03-19 | 590.59 | 2026-03-09 | 2026-01-19 | 586.34 | 592.27 |
| 2026-03-26 | 577.81 | 2026-03-20 | 2026-01-26 | 573.43 | 573.79 |

## Charts

- Equity comparison: [`charts/equity_vs_monthly.png`](charts/equity_vs_monthly.png)
- Signal counts by year: [`charts/signal_counts_by_year.png`](charts/signal_counts_by_year.png)
- Recent trailing-low levels: [`charts/recent_levels.png`](charts/recent_levels.png)
- 50/50 monthly DCA + sliding-low hybrid: [`HYBRID_50_50.md`](HYBRID_50_50.md)
- Regular DCA + extra `$500` sliding-low buys: [`EXTRA_500_OVERLAY.md`](EXTRA_500_OVERLAY.md)

## Files

- `summary.csv`
- `signals.csv`
- `levels.csv`
- `counts_by_year.csv`
- `curves.csv`
- `events.csv`
