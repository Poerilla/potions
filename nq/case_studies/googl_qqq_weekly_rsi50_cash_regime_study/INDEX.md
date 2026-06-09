# GOOGL vs QQQ Weekly RSI50 Cash / Weighted-Spend Study

Data: Yahoo adjusted daily OHLCV on the common GOOGL/QQQ window.

Window: **2004-08-19 through 2026-06-05**.

Rules:

- Basic benchmark: buy **$1,000/month** on the first trading-day open.
- Combined static benchmark: 2-month-low **first touch per month** plus confirmed monthly **low -> high -> lower low** with **2/2** monthly pivots.
- Combined add size is static full-window matched: `12 months of DCA budget / expected combined signals per year`.
- Weekly RSI cash regime uses prior completed weekly RSI(14) smoothed with EMA(14), mapped causally with no same-bar access.
- If weekly RSI EMA is **below 50**, sell existing shares at the next daily open and keep monthly contributions/signals in cash.
- Redeploy all cash at the first monthly buy date where the prior completed weekly RSI EMA is back **>= 50**.
- Weighted-spend variant: keep existing shares, spend **25%** of the normal target when weekly RSI EMA is **>= 50**, and **75%** when it is **< 50**.
- 70/30 hybrid: spend **70%** as plain monthly DCA and reserve **30%** for equal-sized bulk buys on confirmed monthly LHLL signals where causal buy-date weekly RSI EMA is **< 50**.
- The 70/30 hybrid is cashflow-real: early bulk signals can only spend reserve cash accumulated so far, and unused reserve after the final signal stays in cash.
- ATR Supertrend DCA variant: monthly cash still arrives, but buys can occur on any day where the **prior completed daily ATR(14) x 3.0 Supertrend** is bullish. It liquidates at the next open after the prior completed state turns bearish, and its per-buy amount is matched to the full-window bullish-day rate.

## Leaderboard

| Ticker | Strategy | Touch | Sizing | Signals | Matched Add | Buys | Sells | Ending Equity | vs Basic DCA | Max DD | Avg Exposure | Deployed | Ending Cash | Net/DD |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | basic_dca_open | - | - | 0 | $1,000 | 263 | 0 | $4,930,166 | $0 | $-934,019 | 100.0% | 100.0% | $0 | 5.00 |
| GOOGL | monthly_dca_rsi50_cash | - | - | 0 | $1,000 | 208 | 14 | $2,170,790 | $-2,759,376 | $-410,280 | 76.6% | 100.0% | $0 | 4.65 |
| GOOGL | monthly_dca_rsi50_weighted_spend | - | - | 0 | $1,000 | 263 | 0 | $1,944,314 | $-2,985,853 | $-335,632 | 60.2% | 35.5% | $169,750 | 5.01 |
| GOOGL | monthly_dca70_lhll_rsi50_bulk30 | monthly_lhll_weekly_rsi_lt50 | 70pct_monthly_dca_30pct_static_bulk | 7 | $11,271 | 263 | 0 | $4,326,579 | $-603,587 | $-817,532 | 93.8% | 95.7% | $11,314 | 4.97 |
| GOOGL | daily_atr_supertrend_matched_dca | daily_atr_supertrend_bullish_days | static_full_window | 3136 | $83 | 1565 | 84 | $1,663,369 | $-3,266,798 | $-298,294 | 56.9% | - | $1,663,369 | 4.69 |
| GOOGL | combined_first_month_lhll_static | first_touch_per_month | static_full_window | 86 | $3,041 | 86 | 0 | $4,283,863 | $-646,304 | $-808,577 | 90.5% | 93.9% | $15,954 | 4.97 |
| GOOGL | combined_first_month_lhll_static_rsi50_cash | first_touch_per_month | static_full_window | 86 | $3,041 | 67 | 14 | $2,007,236 | $-2,922,930 | $-378,172 | 69.6% | 97.4% | $6,959 | 4.61 |
| GOOGL | combined_first_month_lhll_static_rsi50_weighted_spend | first_touch_per_month | static_full_window | 86 | $3,041 | 86 | 0 | $2,235,364 | $-2,694,802 | $-394,595 | 61.8% | 42.8% | $150,486 | 5.00 |
| QQQ | basic_dca_open | - | - | 0 | $1,000 | 263 | 0 | $2,585,017 | $0 | $-478,448 | 100.0% | 100.0% | $0 | 4.85 |
| QQQ | monthly_dca_rsi50_cash | - | - | 0 | $1,000 | 222 | 9 | $1,844,429 | $-740,588 | $-422,466 | 83.0% | 100.0% | $0 | 3.74 |
| QQQ | monthly_dca_rsi50_weighted_spend | - | - | 0 | $1,000 | 263 | 0 | $1,076,541 | $-1,508,476 | $-159,057 | 54.3% | 32.8% | $176,750 | 5.11 |
| QQQ | monthly_dca70_lhll_rsi50_bulk30 | monthly_lhll_weekly_rsi_lt50 | 70pct_monthly_dca_30pct_static_bulk | 4 | $19,725 | 263 | 0 | $2,335,841 | $-249,176 | $-412,939 | 91.9% | 91.3% | $22,950 | 5.02 |
| QQQ | daily_atr_supertrend_matched_dca | daily_atr_supertrend_bullish_days | static_full_window | 3434 | $76 | 1934 | 86 | $849,435 | $-1,735,582 | $-100,560 | 62.2% | 99.8% | $619 | 5.83 |
| QQQ | combined_first_month_lhll_static | first_touch_per_month | static_full_window | 77 | $3,396 | 76 | 0 | $2,311,629 | $-273,388 | $-414,072 | 91.8% | 92.3% | $20,200 | 4.95 |
| QQQ | combined_first_month_lhll_static_rsi50_cash | first_touch_per_month | static_full_window | 77 | $3,396 | 65 | 9 | $1,790,957 | $-794,060 | $-408,792 | 77.8% | 98.9% | $3,000 | 3.74 |
| QQQ | combined_first_month_lhll_static_rsi50_weighted_spend | first_touch_per_month | static_full_window | 77 | $3,396 | 77 | 0 | $1,283,926 | $-1,301,090 | $-197,469 | 60.6% | 37.1% | $165,355 | 5.17 |

## Read

- **GOOGL:** basic DCA ends at **$4,930,166**. The 70/30 monthly DCA + monthly-LHLL-RSI<50 bulk row ends at **$4,326,579** (**$-603,587** vs basic). Daily ATR Supertrend matched DCA ends at **$1,663,369** (**$-3,266,798** vs basic). The first/month + LHLL static row is **$4,283,863** (**$-646,304** vs basic). The weekly RSI50 cash regime ends at **$2,007,236** (**$-2,922,930** vs basic, **$-2,276,627** vs unfiltered combined). The 25/75 weighted combined row ends at **$2,235,364** (**$-2,694,802** vs basic, **$-2,048,498** vs unfiltered combined). Plain monthly DCA with 25/75 weighting ends at **$1,944,314** (**$-2,985,853** vs basic).
- **QQQ:** basic DCA ends at **$2,585,017**. The 70/30 monthly DCA + monthly-LHLL-RSI<50 bulk row ends at **$2,335,841** (**$-249,176** vs basic). Daily ATR Supertrend matched DCA ends at **$849,435** (**$-1,735,582** vs basic). The first/month + LHLL static row is **$2,311,629** (**$-273,388** vs basic). The weekly RSI50 cash regime ends at **$1,790,957** (**$-794,060** vs basic, **$-520,672** vs unfiltered combined). The 25/75 weighted combined row ends at **$1,283,926** (**$-1,301,090** vs basic, **$-1,027,702** vs unfiltered combined). Plain monthly DCA with 25/75 weighting ends at **$1,076,541** (**$-1,508,476** vs basic).

## Charts

- Google vs QQQ basic monthly DCA: [`charts/google_vs_qqq_basic_dca_equity.png`](charts/google_vs_qqq_basic_dca_equity.png)
- Strategy comparison by ticker: [`charts/google_qqq_strategy_equity.png`](charts/google_qqq_strategy_equity.png)

## Files

- `summary.csv`
- `curves.csv`
- `events.csv`
- `signals.csv`
- `weekly_rsi_state.csv`
- `daily_atr_state.csv`
