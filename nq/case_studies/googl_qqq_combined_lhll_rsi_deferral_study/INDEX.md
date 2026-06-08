# GOOGL / QQQ RSI Overbought Deferral Sweep

Data: Yahoo adjusted daily OHLCV on the common comparison window.

Window: **2004-08-19 through 2026-06-03**.

Rule tested:

- Keep `$1,000/month` cashflow.
- If the selected RSI cadence is overbought, skip the scheduled buy/add and leave cash idle.
- Later allowed buys can spend up to **2.0x** the normal target, so skipped cash is redeployed gradually.
- RSI is Wilder RSI(14) smoothed with EMA(14), mapped causally from the prior completed daily/weekly/monthly bar.
- Thresholds swept: **60, 65, 70, 75, 80** across **daily, weekly, monthly**.
- Rows with **0 blocked events** did not actually use the overbought filter; any improvement there comes from the 2x redeployment cap, not RSI timing.

Strategies tested:

- **basic_dca_deferral:** first-trading-day monthly DCA with the same overbought skip/redeploy rule.
- **combined_signal_deferral:** combined 2-month-low touch + monthly LHLL signal buys with the same overbought skip/redeploy rule.

## Unfiltered Baselines

| Ticker | Baseline | Touch Mode | Sizing | Ending Equity | vs Basic DCA | Max DD | Net/DD |
|---|---|---|---|---:|---:|---:|---:|
| GOOGL | basic_dca_open | - | - | $4,802,541 | $0 | $-934,019 | 4.86 |
| GOOGL | combined_signal_unfiltered | first_touch_per_month | rolling_5y_rate | $4,462,508 | $-340,033 | $-866,343 | 4.85 |
| QQQ | basic_dca_open | - | - | $2,728,556 | $0 | $-478,448 | 5.15 |
| QQQ | combined_signal_unfiltered | first_touch_per_month | rolling_5y_rate | $2,481,256 | $-247,300 | $-430,165 | 5.16 |

## Best Filtered Rows

| Ticker | Strategy | Touch | Sizing | Threshold | RSI TF | Ending Equity | vs Basic DCA | Blocked Events | Buys | Ending Cash | Deployed | Max DD | Matched Add | Net/DD |
|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | basic_dca_deferral | - | - | 70 | monthly | $4,944,145 | $141,604 | 46 | 217 | $5,000 | 98.1% | $-961,379 | - | 4.87 |
| GOOGL | combined_signal_deferral | new_touch_cluster | rolling_5y_rate | 70 | monthly | $4,645,297 | $-157,244 | 27 | 88 | $11,000 | 95.8% | $-901,980 | $1,816 | 4.86 |
| QQQ | basic_dca_deferral | - | - | 70 | daily | $2,729,320 | $764 | 13 | 250 | $1,000 | 99.6% | $-478,602 | - | 5.15 |
| QQQ | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 70 | daily | $2,656,804 | $-71,751 | 0 | 74 | $3,000 | 98.9% | $-464,765 | $3,440 | 5.15 |

## Combined-Signal Top 15

| Ticker | Strategy | Touch | Sizing | Threshold | RSI TF | Ending Equity | vs Basic DCA | Blocked Events | Buys | Ending Cash | Deployed | Max DD | Matched Add | Net/DD |
|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | combined_signal_deferral | new_touch_cluster | rolling_5y_rate | 70 | monthly | $4,645,297 | $-157,244 | 27 | 88 | $11,000 | 95.8% | $-901,980 | $1,816 | 4.86 |
| GOOGL | combined_signal_deferral | new_touch_cluster | expanding_prior_rate | 70 | monthly | $4,630,938 | $-171,603 | 27 | 90 | $11,000 | 95.8% | $-899,183 | $1,816 | 4.86 |
| GOOGL | combined_signal_deferral | all_touches | rolling_5y_rate | 70 | monthly | $4,614,044 | $-188,496 | 55 | 131 | $12,261 | 95.3% | $-895,645 | $968 | 4.86 |
| GOOGL | combined_signal_deferral | all_touches | expanding_prior_rate | 70 | monthly | $4,585,219 | $-217,322 | 55 | 136 | $12,089 | 95.4% | $-890,062 | $968 | 4.86 |
| GOOGL | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 70 | monthly | $4,584,827 | $-217,714 | 15 | 71 | $11,000 | 95.8% | $-890,198 | $3,040 | 4.85 |
| GOOGL | combined_signal_deferral | first_touch_per_month | expanding_prior_rate | 70 | monthly | $4,577,130 | $-225,411 | 15 | 71 | $11,000 | 95.8% | $-888,698 | $3,040 | 4.85 |
| GOOGL | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 65 | weekly | $4,571,087 | $-231,454 | 15 | 69 | $11,000 | 95.8% | $-887,521 | $3,040 | 4.85 |
| GOOGL | combined_signal_deferral | first_touch_per_month | expanding_prior_rate | 65 | weekly | $4,570,743 | $-231,797 | 15 | 69 | $11,000 | 95.8% | $-887,454 | $3,040 | 4.85 |
| GOOGL | combined_signal_deferral | first_touch_per_month | expanding_prior_rate | 70 | weekly | $4,567,712 | $-234,828 | 6 | 78 | $11,000 | 95.8% | $-886,863 | $3,040 | 4.85 |
| GOOGL | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 70 | weekly | $4,564,547 | $-237,993 | 6 | 78 | $11,000 | 95.8% | $-886,247 | $3,040 | 4.85 |
| GOOGL | combined_signal_deferral | first_touch_per_month | expanding_prior_rate | 75 | weekly | $4,560,591 | $-241,950 | 1 | 83 | $4,917 | 98.1% | $-885,687 | $3,040 | 4.85 |
| GOOGL | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 75 | weekly | $4,557,610 | $-244,931 | 1 | 83 | $5,000 | 98.1% | $-885,103 | $3,040 | 4.85 |
| GOOGL | combined_signal_deferral | first_touch_per_month | expanding_prior_rate | 70 | daily | $4,557,167 | $-245,374 | 0 | 84 | $4,917 | 98.1% | $-885,020 | $3,040 | 4.85 |
| GOOGL | combined_signal_deferral | first_touch_per_month | expanding_prior_rate | 75 | daily | $4,557,167 | $-245,374 | 0 | 84 | $4,917 | 98.1% | $-885,020 | $3,040 | 4.85 |
| GOOGL | combined_signal_deferral | first_touch_per_month | expanding_prior_rate | 80 | daily | $4,557,167 | $-245,374 | 0 | 84 | $4,917 | 98.1% | $-885,020 | $3,040 | 4.85 |
| QQQ | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 70 | daily | $2,656,804 | $-71,751 | 0 | 74 | $3,000 | 98.9% | $-464,765 | $3,440 | 5.15 |
| QQQ | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 75 | daily | $2,656,804 | $-71,751 | 0 | 74 | $3,000 | 98.9% | $-464,765 | $3,440 | 5.15 |
| QQQ | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 80 | daily | $2,656,804 | $-71,751 | 0 | 74 | $3,000 | 98.9% | $-464,765 | $3,440 | 5.15 |
| QQQ | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 75 | weekly | $2,656,804 | $-71,751 | 0 | 74 | $3,000 | 98.9% | $-464,765 | $3,440 | 5.15 |
| QQQ | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 80 | weekly | $2,656,804 | $-71,751 | 0 | 74 | $3,000 | 98.9% | $-464,765 | $3,440 | 5.15 |
| QQQ | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 80 | monthly | $2,656,804 | $-71,751 | 0 | 74 | $3,000 | 98.9% | $-464,765 | $3,440 | 5.15 |
| QQQ | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 65 | daily | $2,654,344 | $-74,212 | 3 | 71 | $3,000 | 98.9% | $-464,367 | $3,440 | 5.15 |
| QQQ | combined_signal_deferral | new_touch_cluster | static_full_window | 70 | daily | $2,652,554 | $-76,002 | 0 | 86 | $3,000 | 98.9% | $-462,269 | $2,059 | 5.17 |
| QQQ | combined_signal_deferral | new_touch_cluster | static_full_window | 75 | daily | $2,652,554 | $-76,002 | 0 | 86 | $3,000 | 98.9% | $-462,269 | $2,059 | 5.17 |
| QQQ | combined_signal_deferral | new_touch_cluster | static_full_window | 80 | daily | $2,652,554 | $-76,002 | 0 | 86 | $3,000 | 98.9% | $-462,269 | $2,059 | 5.17 |
| QQQ | combined_signal_deferral | new_touch_cluster | static_full_window | 75 | weekly | $2,652,554 | $-76,002 | 0 | 86 | $3,000 | 98.9% | $-462,269 | $2,059 | 5.17 |
| QQQ | combined_signal_deferral | new_touch_cluster | static_full_window | 80 | weekly | $2,652,554 | $-76,002 | 0 | 86 | $3,000 | 98.9% | $-462,269 | $2,059 | 5.17 |
| QQQ | combined_signal_deferral | new_touch_cluster | static_full_window | 80 | monthly | $2,652,554 | $-76,002 | 0 | 86 | $3,000 | 98.9% | $-462,269 | $2,059 | 5.17 |
| QQQ | combined_signal_deferral | first_touch_per_month | rolling_5y_rate | 60 | daily | $2,652,488 | $-76,068 | 4 | 70 | $3,000 | 98.9% | $-464,024 | $3,440 | 5.15 |
| QQQ | combined_signal_deferral | first_touch_per_month | expanding_prior_rate | 70 | daily | $2,651,700 | $-76,855 | 0 | 74 | $3,000 | 98.9% | $-463,824 | $3,440 | 5.15 |

## Read

- **GOOGL:** basic DCA is **$4,802,541**. Best RSI-deferred basic DCA is **monthly / 70 threshold** at **$4,944,145** (**$141,604** vs basic). Best RSI-deferred combined signal is **new_touch_cluster / monthly / 70 threshold** at **$4,645,297** (**$-157,244** vs basic).
- **QQQ:** basic DCA is **$2,728,556**. Best RSI-deferred basic DCA is **daily / 70 threshold** at **$2,729,320** (**$764** vs basic). Best RSI-deferred combined signal is **first_touch_per_month / daily / 70 threshold** at **$2,656,804** (**$-71,751** vs basic).

## Charts

- GOOGL selected equity curves: [`charts/googl_selected_equity.png`](charts/googl_selected_equity.png)
- QQQ selected equity curves: [`charts/qqq_selected_equity.png`](charts/qqq_selected_equity.png)

## Files

- `summary.csv`
- `baselines.csv`
- `selected_curves.csv`
- `events.csv`
