# QQQ Low-High-Lower-Low DCA Study

Data: Yahoo adjusted daily OHLCV for `QQQ`.
Window: **2000-01-03 through 2026-06-02**.

## Rule

- Confirmed pivots use `N` left bars and `N` right bars; the pivot is known only after the right-side bars complete.
- Bullish dip pattern: confirmed swing **low** -> confirmed swing **high** -> confirmed **lower low**.
- Buy timing: next available daily open after the lower-low pivot confirmation.
- Cashflow comparison: contribute **$1,000/month**. Monthly DCA buys each first trading day open. Signal variants hold cash and buy on pattern signals.
- `signal_expanding_prior_rate` is the causal backwards-trace sizing row: each signal uses only prior signal frequency to estimate `12 months of DCA / signals per year`.
- `signal_all_cash_lump` buys all accumulated cash at each signal; it is included as a more aggressive timing diagnostic.

## Leaderboard

| Rank | Pivot Bars | Variant | Signals | Signals / Yr | Buys | Avg Buy | Deployed | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2 | signal_all_cash_lump | 289 | 10.94 | 205 | $1,541 | 99.4% | $4,005,807 | $-5,753 | $-713,401 | 5.17 | 98.6% |
| 2 | 1 | signal_all_cash_lump | 484 | 18.32 | 262 | $1,210 | 99.7% | $4,003,915 | $-7,644 | $-713,123 | 5.17 | 99.0% |
| 3 | 3 | signal_all_cash_lump | 207 | 7.84 | 161 | $1,957 | 99.1% | $4,003,078 | $-8,481 | $-712,492 | 5.17 | 97.5% |
| 4 | 5 | signal_all_cash_lump | 128 | 4.85 | 112 | $2,821 | 99.4% | $3,994,507 | $-17,053 | $-710,547 | 5.17 | 97.2% |
| 5 | 8 | signal_all_cash_lump | 78 | 2.95 | 74 | $4,270 | 99.4% | $3,966,986 | $-44,574 | $-706,108 | 5.17 | 96.3% |
| 6 | 3 | signal_static_full_window | 207 | 7.84 | 203 | $1,473 | 94.0% | $3,902,126 | $-109,433 | $-689,133 | 5.20 | 95.5% |
| 7 | 5 | signal_rolling_5y_rate | 128 | 4.85 | 125 | $2,508 | 98.6% | $3,899,677 | $-111,883 | $-690,860 | 5.18 | 95.4% |
| 8 | 3 | signal_rolling_5y_rate | 207 | 7.84 | 198 | $1,561 | 97.2% | $3,889,184 | $-122,376 | $-688,069 | 5.19 | 95.7% |
| 9 | 2 | signal_static_full_window | 289 | 10.94 | 273 | $1,076 | 92.4% | $3,869,141 | $-142,418 | $-682,731 | 5.20 | 96.4% |
| 10 | 5 | signal_static_full_window | 128 | 4.85 | 126 | $2,355 | 93.3% | $3,853,518 | $-158,042 | $-677,126 | 5.22 | 94.9% |
| 11 | 2 | signal_rolling_5y_rate | 289 | 10.94 | 269 | $1,164 | 98.5% | $3,850,034 | $-161,525 | $-679,914 | 5.19 | 96.0% |
| 12 | 1 | signal_rolling_5y_rate | 484 | 18.32 | 447 | $694 | 97.5% | $3,849,581 | $-161,979 | $-682,693 | 5.17 | 96.8% |
| 13 | 1 | signal_static_full_window | 484 | 18.32 | 473 | $638 | 95.0% | $3,843,250 | $-168,310 | $-680,157 | 5.18 | 96.0% |
| 14 | 8 | signal_rolling_5y_rate | 78 | 2.95 | 77 | $4,023 | 97.4% | $3,775,011 | $-236,548 | $-667,759 | 5.18 | 93.8% |
| 15 | 8 | signal_static_full_window | 78 | 2.95 | 78 | $3,596 | 88.2% | $3,719,169 | $-292,391 | $-652,952 | 5.21 | 93.7% |
| 16 | 3 | signal_expanding_prior_rate | 207 | 7.84 | 204 | $1,401 | 89.9% | $3,679,852 | $-331,708 | $-645,778 | 5.21 | 93.3% |
| 17 | 1 | signal_expanding_prior_rate | 484 | 18.32 | 475 | $615 | 91.9% | $3,660,128 | $-351,432 | $-644,588 | 5.18 | 94.6% |
| 18 | 5 | signal_expanding_prior_rate | 128 | 4.85 | 125 | $2,278 | 89.6% | $3,578,220 | $-433,339 | $-623,712 | 5.23 | 91.9% |
| 19 | 2 | signal_expanding_prior_rate | 289 | 10.94 | 285 | $959 | 86.0% | $3,532,962 | $-478,598 | $-616,838 | 5.21 | 91.9% |
| 20 | 8 | signal_expanding_prior_rate | 78 | 2.95 | 78 | $3,361 | 82.4% | $3,439,056 | $-572,504 | $-597,897 | 5.22 | 87.4% |

Monthly DCA baseline: **$4,011,560 ending equity**, **$3,693,560 net**, **$-714,352 max DD**, **5.17 Net/DD**.

## Read

- Best causal expanding-frequency row: **3 pivot bars**, **signal_expanding_prior_rate**, **207 signals**, about **7.84/year**, median **8.0** signals/year.
- It ended at **$3,679,852**, which is **$-331,708** versus monthly DCA.
- Best any-mode row was **2 pivot bars / signal_all_cash_lump** at **$4,005,807** (**$-5,753** vs monthly).
- This earlier lower-low entry improved on the higher-high-confirmed version, but still did not beat monthly DCA as tested.

## Sample Signals For Best Causal Row

| Buy Date | L1 | H1 | L2 | Buy Price | L2 vs L1 |
|---|---:|---:|---:|---:|---:|
| 2023-03-17 | 282.91 | 298.24 | 279.79 | 300.91 | -1.10% |
| 2023-05-01 | 307.12 | 315.82 | 304.49 | 316.48 | -0.86% |
| 2023-08-24 | 368.32 | 378.69 | 349.01 | 366.65 | -5.24% |
| 2023-10-03 | 363.21 | 372.19 | 346.21 | 353.52 | -4.68% |
| 2023-11-01 | 346.21 | 368.26 | 337.33 | 346.56 | -2.56% |
| 2024-03-11 | 429.01 | 441.15 | 428.37 | 432.19 | -0.15% |
| 2024-04-25 | 430.38 | 441.48 | 408.58 | 414.69 | -5.07% |
| 2024-08-09 | 486.17 | 471.13 | 419.52 | 442.59 | -13.71% |
| 2024-11-06 | 481.22 | 497.39 | 479.93 | 496.61 | -0.27% |
| 2025-01-08 | 505.27 | 527.89 | 502.52 | 511.84 | -0.54% |
| 2025-01-17 | 502.52 | 524.59 | 496.55 | 519.56 | -1.19% |
| 2025-03-19 | 518.66 | 537.40 | 463.49 | 473.81 | -10.64% |
| 2025-04-11 | 463.49 | 491.24 | 400.45 | 442.51 | -13.60% |
| 2025-11-28 | 597.15 | 623.27 | 579.26 | 614.54 | -2.99% |
| 2026-01-26 | 609.38 | 629.21 | 606.29 | 622.43 | -0.51% |
| 2026-02-11 | 606.29 | 635.80 | 594.01 | 615.60 | -2.02% |
| 2026-02-23 | 594.01 | 616.74 | 592.59 | 605.85 | -0.24% |
| 2026-03-09 | 592.59 | 616.05 | 591.12 | 593.48 | -0.25% |
| 2026-03-13 | 591.12 | 612.11 | 590.59 | 598.97 | -0.09% |
| 2026-03-26 | 591.82 | 605.14 | 577.81 | 582.60 | -2.37% |

## Charts

- Best causal equity comparison: [`charts/best_causal_equity.png`](charts/best_causal_equity.png)
- Best causal signal counts by year: [`charts/best_causal_counts_by_year.png`](charts/best_causal_counts_by_year.png)
- 2-bar yearly signal chart pack: [`charts/yearly_2bar/INDEX.md`](charts/yearly_2bar/INDEX.md)

## Files

- `summary.csv`
- `signals.csv`
- `pivots.csv`
- `curves.csv`
- `counts_by_year.csv`
