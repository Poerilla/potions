# QQQ Low-High-Lower-Low-Higher-High DCA Study

Data: Yahoo adjusted daily OHLCV for `QQQ`.
Window: **2000-01-03 through 2026-06-02**.

## Rule

- Confirmed pivots use `N` left bars and `N` right bars; the pivot is known only after the right-side bars complete.
- Bullish pattern: confirmed swing **low** -> confirmed swing **high** -> confirmed **lower low** -> first later **higher high** above that swing high.
- Higher high mode: **high**. The study buys on the next available daily open after the higher-high signal.
- Cashflow comparison: contribute **$1,000/month**. Monthly DCA buys each first trading day open. Signal variants hold cash and buy on pattern signals.
- `signal_expanding_prior_rate` is the causal backwards-trace sizing row: each signal uses only prior signal frequency to estimate `12 months of DCA / signals per year`.

## Leaderboard

| Rank | Pivot Bars | Variant | Signals | Signals / Yr | Buys | Avg Buy | Deployed | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | signal_expanding_prior_rate | 80 | 3.03 | 74 | $4,284 | 99.7% | $1,830,562 | $-2,180,998 | $-311,751 | 4.85 | 43.6% |
| 2 | 2 | signal_expanding_prior_rate | 56 | 2.12 | 56 | $5,661 | 99.7% | $1,721,792 | $-2,289,767 | $-291,805 | 4.81 | 41.6% |
| 3 | 3 | signal_expanding_prior_rate | 39 | 1.48 | 39 | $8,103 | 99.4% | $1,575,834 | $-2,435,725 | $-264,895 | 4.75 | 38.5% |
| 4 | 1 | signal_rolling_5y_rate | 80 | 3.03 | 80 | $3,405 | 85.7% | $1,544,936 | $-2,466,624 | $-252,331 | 4.86 | 39.5% |
| 5 | 2 | signal_rolling_5y_rate | 56 | 2.12 | 56 | $4,440 | 78.2% | $1,365,370 | $-2,646,190 | $-214,779 | 4.88 | 36.5% |
| 6 | 1 | signal_static_full_window | 80 | 3.03 | 80 | $3,900 | 98.1% | $1,317,105 | $-2,694,455 | $-209,163 | 4.78 | 34.7% |
| 7 | 3 | signal_static_full_window | 39 | 1.48 | 39 | $7,995 | 98.1% | $1,268,383 | $-2,743,176 | $-201,024 | 4.73 | 33.4% |
| 8 | 2 | signal_static_full_window | 56 | 2.12 | 56 | $5,511 | 97.1% | $1,234,976 | $-2,776,584 | $-191,535 | 4.79 | 33.3% |
| 9 | 3 | signal_rolling_5y_rate | 39 | 1.48 | 39 | $5,785 | 70.9% | $1,227,167 | $-2,784,393 | $-186,859 | 4.87 | 33.0% |
| 10 | 5 | signal_static_full_window | 24 | 0.91 | 24 | $12,000 | 90.6% | $1,139,009 | $-2,872,551 | $-172,139 | 4.77 | 28.2% |
| 11 | 5 | signal_expanding_prior_rate | 24 | 0.91 | 24 | $12,000 | 90.6% | $1,139,009 | $-2,872,551 | $-172,139 | 4.77 | 28.2% |
| 12 | 5 | signal_rolling_5y_rate | 24 | 0.91 | 24 | $8,201 | 61.9% | $974,926 | $-3,036,634 | $-132,962 | 4.94 | 24.8% |
| 13 | 8 | signal_static_full_window | 17 | 0.64 | 17 | $12,000 | 64.2% | $868,658 | $-3,142,901 | $-114,134 | 4.82 | 22.1% |
| 14 | 8 | signal_expanding_prior_rate | 17 | 0.64 | 17 | $12,000 | 64.2% | $868,658 | $-3,142,901 | $-114,134 | 4.82 | 22.1% |
| 15 | 8 | signal_rolling_5y_rate | 17 | 0.64 | 17 | $10,840 | 58.0% | $834,593 | $-3,176,967 | $-106,104 | 4.87 | 21.2% |

Monthly DCA baseline: **$4,011,560 ending equity**, **$3,693,560 net**, **$-714,352 max DD**, **5.17 Net/DD**.

## Causal Backwards-Trace Read

- Best causal expanding-frequency row: **1 pivot bars**, **signal_expanding_prior_rate**, **80 signals**, about **3.03/year**, median **7.0** signals/year.
- It ended at **$1,830,562**, which is **$-2,180,998** versus monthly DCA.
- Best any-mode row was **1 pivot bars / signal_expanding_prior_rate** at **$1,830,562** (**$-2,180,998** vs monthly).

## Sample Signals For Best Causal Row

| Buy Date | L1 | H1 | L2 | Buy Price | L2 vs L1 | Break vs H1 |
|---|---:|---:|---:|---:|---:|---:|
| 2024-01-19 | 397.79 | 407.90 | 390.53 | 410.17 | -1.82% | 0.16% |
| 2024-02-05 | 418.00 | 423.14 | 411.72 | 423.85 | -1.50% | 0.44% |
| 2024-02-26 | 420.15 | 429.70 | 416.50 | 432.27 | -0.87% | 1.29% |
| 2024-03-08 | 429.01 | 441.15 | 428.37 | 440.38 | -0.15% | 0.03% |
| 2024-03-21 | 430.14 | 438.62 | 427.47 | 444.00 | -0.62% | 0.15% |
| 2024-04-02 | 437.73 | 442.37 | 437.13 | 435.30 | -0.14% | 0.07% |
| 2024-05-15 | 431.54 | 441.48 | 408.58 | 443.56 | -5.32% | 0.03% |
| 2024-06-06 | 446.94 | 454.75 | 438.25 | 459.18 | -1.95% | 0.84% |
| 2024-10-30 | 486.17 | 496.36 | 419.52 | 495.45 | -13.71% | 0.21% |
| 2024-12-03 | 505.80 | 510.91 | 490.58 | 509.89 | -3.01% | 0.25% |
| 2025-02-18 | 515.06 | 534.89 | 496.55 | 536.33 | -3.59% | 0.10% |
| 2025-05-15 | 506.23 | 516.39 | 400.45 | 514.03 | -20.90% | 0.07% |
| 2025-06-26 | 526.34 | 534.19 | 521.71 | 541.34 | -0.88% | 1.33% |
| 2025-07-21 | 549.59 | 558.73 | 549.52 | 560.01 | -0.01% | 0.70% |
| 2025-08-11 | 556.54 | 572.50 | 549.64 | 572.56 | -1.24% | 0.02% |
| 2025-09-08 | 566.70 | 575.86 | 557.47 | 576.23 | -1.63% | 0.54% |
| 2025-10-21 | 601.50 | 610.19 | 587.55 | 610.08 | -2.32% | 0.17% |
| 2026-01-29 | 624.35 | 634.20 | 579.26 | 631.85 | -7.22% | 0.25% |
| 2026-04-16 | 617.49 | 629.19 | 555.60 | 639.21 | -10.02% | 1.37% |
| 2026-05-26 | 696.64 | 722.03 | 695.25 | 725.96 | -0.20% | 0.01% |

## Charts

- Best causal equity comparison: [`charts/best_causal_equity.png`](charts/best_causal_equity.png)
- Best causal signal counts by year: [`charts/best_causal_counts_by_year.png`](charts/best_causal_counts_by_year.png)

## Files

- `summary.csv`
- `signals.csv`
- `pivots.csv`
- `curves.csv`
- `counts_by_year.csv`
