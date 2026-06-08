# QQQ Sliding 2-Month Low 50/50 Hybrid

Hybrid rule: allocate half of each monthly contribution to blind QQQ monthly DCA and half to the selected sliding-low timing variant.

- Total contribution remains **$1,000/month**.
- Monthly leg contributes **$500/month** and buys the first trading day open.
- Timing leg contributes **$500/month**, holds cash, and buys only on its sliding-low signal.
- Static full-window sizing is diagnostic because it knows the full-window signal frequency; rolling/expanding rows are causal sizing approximations.

Monthly DCA baseline: **$4,001,076 ending equity**, **$3,683,076 net**, **$-714,352 max DD**, **5.16 Net/DD**.

## Leaderboard

| Rank | Timing Leg | Sizing | Signals/Yr | End Equity | Vs Monthly | Max DD | Net/DD | Deployed | Avg Exposure | Ending Cash |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | first_touch_per_month | static_full_window | 3.71 | $3,828,562 | $-172,514 | $-677,013 | 5.19 | 92.9% | 96.5% | $22,638 |
| 2 | first_touch_per_month | rolling_5y_rate | 3.71 | $3,810,022 | $-191,054 | $-676,918 | 5.16 | 98.7% | 95.5% | $4,139 |
| 3 | new_touch_cluster | rolling_5y_rate | 6.66 | $3,789,599 | $-211,477 | $-671,026 | 5.17 | 98.3% | 95.1% | $5,372 |
| 4 | new_touch_cluster | static_full_window | 6.66 | $3,758,285 | $-242,791 | $-662,360 | 5.19 | 90.7% | 96.2% | $29,659 |
| 5 | all_touches | rolling_5y_rate | 14.35 | $3,748,267 | $-252,809 | $-662,823 | 5.18 | 97.2% | 94.8% | $9,003 |
| 6 | all_touches | static_full_window | 14.35 | $3,728,615 | $-272,462 | $-656,793 | 5.19 | 87.8% | 96.1% | $38,683 |
| 7 | first_touch_per_month | expanding_prior_rate | 3.71 | $3,528,068 | $-473,008 | $-618,402 | 5.19 | 88.0% | 92.9% | $38,167 |
| 8 | new_touch_cluster | expanding_prior_rate | 6.66 | $3,486,705 | $-514,371 | $-609,177 | 5.20 | 85.9% | 92.4% | $44,985 |
| 9 | all_touches | expanding_prior_rate | 14.35 | $3,430,105 | $-570,971 | $-598,294 | 5.20 | 82.2% | 91.8% | $56,592 |

## Read

- Best 50/50 row is **first_touch_per_month / static_full_window**, ending at **$3,828,562**, **$-172,514** versus monthly DCA.
- The requested diagnostic **first-touch-per-month / static-full-window** hybrid ends at **$3,828,562**, **$-172,514** versus monthly DCA.
- The more defensible **first-touch-per-month / rolling-5y-rate** hybrid ends at **$3,810,022**, **$-191,054** versus monthly DCA.

## Charts

- Hybrid equity comparison: [`charts/hybrid_equity_vs_monthly.png`](charts/hybrid_equity_vs_monthly.png)

## Files

- `hybrid_50_50_summary.csv`
- `hybrid_50_50_curves.csv`
