# GOOGL vs QQQ Combined 2-Month-Low + LHLL DCA Study

Data: Yahoo adjusted daily OHLCV. Primary comparison uses the common GOOGL/QQQ window.

Window: **GOOGL 2004-08-19 to 2026-06-03 / QQQ 2004-08-19 to 2026-06-03**.

Monthly cashflow: **$1,000/month**. Basic DCA buys the first trading-day open.

Combined signal rule:

- 2-month-low touch: daily low touches the prior **2 calendar months** adjusted low, excluding the current day.
- Monthly LHLL: confirmed monthly **low -> high -> lower low** with **2 left / 2 right** pivot confirmation; buy on the next available daily open.
- Every occurrence from either family counts as one expected signal. Same-day overlaps count twice.
- Matched add size = `12 months of DCA budget / expected combined signals per year`, capped by available cash.
- No year-end catch-up, fees, taxes, slippage, or cash interest.

## Basic DCA Baselines

| Ticker | Total Contributed | Ending Equity | Net | Max DD | Net/DD |
|---|---:|---:|---:|---:|---:|
| GOOGL | $263,000 | $4,802,541 | $4,539,541 | $-934,019 | 4.86 |
| QQQ | $263,000 | $2,728,556 | $2,465,556 | $-478,448 | 5.15 |

## Best Combined Rows Per Ticker

| Ticker | Touch Mode | Sizing | Total Signals | 2m Touches | LHLL | Signals/Yr | Static Matched Add | Buys | Ending Equity | Deployed | vs Basic DCA | Max DD | Net/DD |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | first_touch_per_month | rolling_5y_rate | 86 | 77 | 9 | 3.95 | $3,040 | 85 | $4,462,508 | 96.7% | $-340,033 | $-866,343 | 4.85 |
| QQQ | first_touch_per_month | rolling_5y_rate | 76 | 70 | 6 | 3.49 | $3,440 | 74 | $2,481,256 | 97.6% | $-247,300 | $-430,165 | 5.16 |

## Literal Every-Touch + LHLL Rows

These are the rows closest to the phrase "each occurrence" for the 2-month-low side: every daily touch plus every LHLL signal.

| Ticker | Touch Mode | Sizing | Total Signals | 2m Touches | LHLL | Signals/Yr | Static Matched Add | Buys | Ending Equity | Deployed | vs Basic DCA | Max DD | Net/DD |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | all_touches | static_full_window | 270 | 261 | 9 | 12.39 | $968 | 257 | $3,948,028 | 93.4% | $-854,512 | $-763,582 | 4.83 |
| QQQ | all_touches | static_full_window | 254 | 248 | 6 | 11.66 | $1,029 | 216 | $2,333,213 | 83.9% | $-395,343 | $-392,859 | 5.27 |

## Operational First-Touch-Per-Month Rows

These keep the 2-month-low side from firing repeatedly during the same drawdown month.

| Ticker | Touch Mode | Sizing | Total Signals | 2m Touches | LHLL | Signals/Yr | Static Matched Add | Buys | Ending Equity | Deployed | vs Basic DCA | Max DD | Net/DD |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | first_touch_per_month | expanding_prior_rate | 86 | 77 | 9 | 3.95 | $3,040 | 85 | $4,440,603 | 93.1% | $-361,938 | $-860,217 | 4.86 |
| GOOGL | first_touch_per_month | static_full_window | 86 | 77 | 9 | 3.95 | $3,040 | 86 | $4,173,109 | 93.9% | $-629,432 | $-808,516 | 4.84 |
| QQQ | first_touch_per_month | expanding_prior_rate | 76 | 70 | 6 | 3.49 | $3,440 | 76 | $2,382,222 | 92.8% | $-346,334 | $-402,671 | 5.26 |
| QQQ | first_touch_per_month | static_full_window | 76 | 70 | 6 | 3.49 | $3,440 | 75 | $2,443,447 | 91.9% | $-285,109 | $-414,425 | 5.26 |

## Full Leaderboard

| Ticker | Touch Mode | Sizing | Total Signals | 2m Touches | LHLL | Signals/Yr | Static Matched Add | Buys | Ending Equity | Deployed | vs Basic DCA | Max DD | Net/DD |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | first_touch_per_month | rolling_5y_rate | 86 | 77 | 9 | 3.95 | $3,040 | 85 | $4,462,508 | 96.7% | $-340,033 | $-866,343 | 4.85 |
| GOOGL | new_touch_cluster | expanding_prior_rate | 144 | 135 | 9 | 6.61 | $1,816 | 131 | $4,453,875 | 95.1% | $-348,666 | $-863,706 | 4.85 |
| GOOGL | first_touch_per_month | expanding_prior_rate | 86 | 77 | 9 | 3.95 | $3,040 | 85 | $4,440,603 | 93.1% | $-361,938 | $-860,217 | 4.86 |
| GOOGL | new_touch_cluster | rolling_5y_rate | 144 | 135 | 9 | 6.61 | $1,816 | 129 | $4,436,175 | 94.8% | $-366,366 | $-860,138 | 4.85 |
| GOOGL | all_touches | expanding_prior_rate | 270 | 261 | 9 | 12.39 | $968 | 231 | $4,302,089 | 93.1% | $-500,452 | $-832,415 | 4.85 |
| GOOGL | all_touches | rolling_5y_rate | 270 | 261 | 9 | 12.39 | $968 | 226 | $4,255,563 | 96.7% | $-546,978 | $-825,313 | 4.84 |
| GOOGL | first_touch_per_month | static_full_window | 86 | 77 | 9 | 3.95 | $3,040 | 86 | $4,173,109 | 93.9% | $-629,432 | $-808,516 | 4.84 |
| GOOGL | new_touch_cluster | static_full_window | 144 | 135 | 9 | 6.61 | $1,816 | 142 | $4,170,406 | 95.1% | $-632,134 | $-808,510 | 4.83 |
| GOOGL | all_touches | static_full_window | 270 | 261 | 9 | 12.39 | $968 | 257 | $3,948,028 | 93.4% | $-854,512 | $-763,582 | 4.83 |
| QQQ | first_touch_per_month | rolling_5y_rate | 76 | 70 | 6 | 3.49 | $3,440 | 74 | $2,481,256 | 97.6% | $-247,300 | $-430,165 | 5.16 |
| QQQ | first_touch_per_month | static_full_window | 76 | 70 | 6 | 3.49 | $3,440 | 75 | $2,443,447 | 91.9% | $-285,109 | $-414,425 | 5.26 |
| QQQ | new_touch_cluster | rolling_5y_rate | 127 | 121 | 6 | 5.83 | $2,059 | 109 | $2,415,502 | 97.1% | $-313,054 | $-414,613 | 5.19 |
| QQQ | first_touch_per_month | expanding_prior_rate | 76 | 70 | 6 | 3.49 | $3,440 | 76 | $2,382,222 | 92.8% | $-346,334 | $-402,671 | 5.26 |
| QQQ | new_touch_cluster | static_full_window | 127 | 121 | 6 | 5.83 | $2,059 | 117 | $2,353,177 | 88.6% | $-375,378 | $-395,430 | 5.29 |
| QQQ | all_touches | static_full_window | 254 | 248 | 6 | 11.66 | $1,029 | 216 | $2,333,213 | 83.9% | $-395,343 | $-392,859 | 5.27 |
| QQQ | all_touches | rolling_5y_rate | 254 | 248 | 6 | 11.66 | $1,029 | 202 | $2,331,549 | 96.2% | $-397,007 | $-396,505 | 5.22 |
| QQQ | new_touch_cluster | expanding_prior_rate | 127 | 121 | 6 | 5.83 | $2,059 | 119 | $2,279,805 | 88.7% | $-448,750 | $-381,062 | 5.29 |
| QQQ | all_touches | expanding_prior_rate | 254 | 248 | 6 | 11.66 | $1,029 | 226 | $2,183,002 | 79.8% | $-545,554 | $-362,891 | 5.29 |

## Read

- **GOOGL:** basic DCA ends at **$4,802,541**. Best combined row is **first_touch_per_month / rolling_5y_rate** at **$4,462,508**, which is **$-340,033** versus basic DCA.
- **QQQ:** basic DCA ends at **$2,728,556**. Best combined row is **first_touch_per_month / rolling_5y_rate** at **$2,481,256**, which is **$-247,300** versus basic DCA.

## Charts

- GOOGL equity comparison: [`charts/googl_equity.png`](charts/googl_equity.png)
- QQQ equity comparison: [`charts/qqq_equity.png`](charts/qqq_equity.png)

## Files

- `summary.csv`
- `curves.csv`
- `events.csv`
- `signals_and_diagnostics.csv`
