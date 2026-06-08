# QQQ Sliding 3-Month-Low Limit DCA Study

Data: Yahoo adjusted daily OHLCV for `QQQ`.
Window: **2000-01-03 through 2026-06-03**.

## Rule

- Each trading day calculates the adjusted low of the **prior 3 calendar months**, excluding the current day.
- A buy limit is considered filled if the current daily low touches that trailing level. Fill price is the trailing low level, which is conservative on gap-down days for a buy limit.
- `all_touches` buys every daily touch; `new_touch_cluster` buys only the first touch after a non-touch day; `first_touch_per_month` buys the first touch per calendar month.
- Cashflow comparison: contribute **$1,000/month**. Monthly DCA buys first trading day open; signal variants hold cash and buy only on rolling-low signals.
- Matched-add sizing uses **12 months of DCA budget / expected fills per year**, capped by available cash. `static_full_window` is diagnostic; `expanding_prior_rate` uses only prior signal frequency.
- No year-end catch-up, no fees, taxes, slippage, or cash interest.

## Fill Frequency

| Event Mode | Definition | Signals | Signals / Yr | Static Matched Add | Zero-Fill Complete Years |
|---|---|---:|---:|---:|---:|
| all_touches | Every daily touch of the trailing low | 291 | 11.02 | $1,089 | 3 |
| new_touch_cluster | First touch after a non-touch day | 136 | 5.15 | $2,331 | 3 |
| first_touch_per_month | First touch per calendar month | 76 | 2.88 | $4,171 | 3 |

## Performance Leaderboard

| Rank | Event Mode | Sizing | Signals/Yr | Buys | Avg Buy | Deployed | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure | Ending Cash |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | first_touch_per_month | rolling_5y_rate | 2.88 | 76 | $4,017 | 96.0% | $3,525,582 | $-475,494 | $-622,233 | 5.15 | 89.1% | $12,685 |
| 2 | first_touch_per_month | static_full_window | 2.88 | 76 | $3,436 | 82.1% | $3,503,338 | $-497,738 | $-606,913 | 5.25 | 91.4% | $56,853 |
| 3 | new_touch_cluster | rolling_5y_rate | 5.15 | 115 | $2,660 | 96.2% | $3,503,221 | $-497,856 | $-617,235 | 5.16 | 87.9% | $12,146 |
| 4 | all_touches | rolling_5y_rate | 11.02 | 227 | $1,348 | 96.2% | $3,419,997 | $-581,080 | $-594,977 | 5.21 | 87.4% | $12,051 |
| 5 | new_touch_cluster | static_full_window | 5.15 | 117 | $2,104 | 77.4% | $3,335,964 | $-665,112 | $-572,501 | 5.27 | 89.6% | $71,818 |
| 6 | all_touches | static_full_window | 11.02 | 207 | $1,068 | 69.5% | $3,242,979 | $-758,097 | $-554,302 | 5.28 | 89.7% | $96,984 |
| 7 | first_touch_per_month | expanding_prior_rate | 2.88 | 76 | $3,017 | 72.1% | $2,864,408 | $-1,136,668 | $-482,635 | 5.28 | 82.8% | $88,694 |
| 8 | new_touch_cluster | expanding_prior_rate | 5.15 | 128 | $1,693 | 68.1% | $2,764,796 | $-1,236,280 | $-461,225 | 5.30 | 81.1% | $101,310 |
| 9 | all_touches | expanding_prior_rate | 11.02 | 261 | $712 | 58.4% | $2,613,231 | $-1,387,845 | $-431,497 | 5.32 | 79.4% | $132,154 |

Monthly DCA baseline: **$4,001,076 ending equity**, **$3,683,076 net**, **$-714,352 max DD**, **5.16 Net/DD**.

## Main Read

- Best tested row is **first_touch_per_month / rolling_5y_rate**, ending at **$3,525,582**, **$-475,494** versus monthly DCA, with **96.0%** deployed.
- The cleanest cadence is **new_touch_cluster**: **136** fills, **5.15/year**, static matched add **$2,331**.
- Static matched `new_touch_cluster` ends at **$3,335,964**, **$-665,112** versus monthly DCA, with **77.4%** deployed.
- Causal expanding-rate `new_touch_cluster` ends at **$2,764,796**, **$-1,236,280** versus monthly DCA, with **68.1%** deployed.

## Recent New-Touch Events

| Date | Buy Price | Rolling Low Date | Window Start | Daily Low | Daily Close |
|---|---:|---|---|---:|---:|
| 2022-06-13 | 273.23 | 2022-05-20 | 2022-03-13 | 267.69 | 268.55 |
| 2022-06-16 | 266.53 | 2022-06-14 | 2022-03-16 | 262.57 | 264.63 |
| 2022-09-23 | 269.42 | 2022-06-30 | 2022-06-23 | 266.23 | 269.64 |
| 2022-09-29 | 266.23 | 2022-09-23 | 2022-06-29 | 263.12 | 266.08 |
| 2022-10-10 | 261.41 | 2022-09-30 | 2022-07-10 | 258.03 | 260.74 |
| 2022-10-13 | 255.47 | 2022-10-11 | 2022-07-13 | 248.85 | 263.10 |
| 2023-09-26 | 349.01 | 2023-08-18 | 2023-06-26 | 348.03 | 349.02 |
| 2023-10-23 | 346.21 | 2023-09-27 | 2023-07-23 | 345.97 | 350.46 |
| 2023-10-25 | 345.97 | 2023-10-23 | 2023-07-25 | 344.62 | 345.21 |
| 2024-04-19 | 409.58 | 2024-01-19 | 2024-01-19 | 408.58 | 410.15 |
| 2024-08-05 | 431.78 | 2024-05-06 | 2024-05-05 | 419.52 | 431.33 |
| 2025-02-28 | 496.55 | 2025-01-13 | 2024-11-28 | 493.80 | 504.97 |
| 2025-03-06 | 484.67 | 2025-03-04 | 2024-12-06 | 483.14 | 485.12 |
| 2025-03-13 | 464.07 | 2025-03-11 | 2024-12-13 | 463.49 | 465.39 |
| 2025-03-31 | 463.49 | 2025-03-13 | 2024-12-31 | 455.13 | 466.66 |
| 2025-04-03 | 455.13 | 2025-03-31 | 2025-01-03 | 447.97 | 448.49 |
| 2026-03-03 | 592.59 | 2026-02-17 | 2025-12-03 | 591.12 | 600.82 |
| 2026-03-09 | 591.12 | 2026-03-03 | 2025-12-09 | 590.59 | 606.99 |
| 2026-03-19 | 590.59 | 2026-03-09 | 2025-12-19 | 586.34 | 592.27 |
| 2026-03-26 | 577.81 | 2026-03-20 | 2025-12-26 | 573.43 | 573.79 |

## Charts

- Equity comparison: [`charts/equity_vs_monthly.png`](charts/equity_vs_monthly.png)
- Signal counts by year: [`charts/signal_counts_by_year.png`](charts/signal_counts_by_year.png)
- Recent trailing-low levels: [`charts/recent_levels.png`](charts/recent_levels.png)

## Files

- `summary.csv`
- `signals.csv`
- `levels.csv`
- `counts_by_year.csv`
- `curves.csv`
- `events.csv`
