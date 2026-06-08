# QQQ Weekly-Pivot Market-Structure DCA Study

Data: Yahoo adjusted daily OHLCV for `QQQ`; weekly candles are resampled from the same adjusted daily bars.
Window: **2000-01-03 through 2026-06-02** (1379 completed/partial weekly bars).

## Rule

- Weekly pivots use `N` completed weekly bars on the left and `N` completed weekly bars on the right.
- Pattern 1: **L-H-LL** = confirmed weekly low -> confirmed weekly high -> confirmed lower weekly low.
- Pattern 2: **L-H-LL-HH** = L-H-LL, then first later completed weekly bar that breaks above the prior weekly high.
- Signal buys happen at the **next available daily open** after the weekly signal is known.
- Year-end catch-up: if signal buys have not spent the accumulated annual budget, remaining cash is invested on the final December weekly bar at that week's **high**.
- Cashflow comparison: contribute **$1,000/month**. Monthly DCA buys the first trading day open; signal variants hold cash and buy on weekly-swing signals.
- `signal_expanding_prior_rate` is the causal backwards-trace sizing row: each signal uses only prior signal frequency to estimate `12 months of DCA / signals per year`.
- `signal_all_cash_lump` buys all accumulated cash at each signal; it is a timing diagnostic, not the causal frequency-matched row.

## Leaderboard

| Rank | Pattern | Weekly Pivot Bars | Variant | Signals | Signals / Yr | Signal Buys | Dec Sweeps | Avg Buy | Deployed | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure |
|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | L-H-LL | 3 | signal_static_full_window | 31 | 1.17 | 31 | 25 | $5,643 | 99.4% | $3,986,240 | $-25,320 | $-709,101 | 5.17 | 94.7% |
| 2 | L-H-LL | 3 | signal_all_cash_lump | 31 | 1.17 | 31 | 24 | $5,745 | 99.4% | $3,985,998 | $-25,562 | $-709,056 | 5.17 | 94.7% |
| 3 | L-H-LL | 3 | signal_rolling_5y_rate | 31 | 1.17 | 31 | 24 | $5,745 | 99.4% | $3,984,069 | $-27,491 | $-708,748 | 5.17 | 94.7% |
| 4 | L-H-LL | 3 | signal_expanding_prior_rate | 31 | 1.17 | 31 | 26 | $5,544 | 99.4% | $3,982,032 | $-29,527 | $-708,323 | 5.17 | 94.7% |
| 5 | L-H-LL | 5 | signal_all_cash_lump | 19 | 0.72 | 18 | 26 | $7,205 | 99.7% | $3,980,302 | $-31,258 | $-709,414 | 5.16 | 92.5% |
| 6 | L-H-LL | 5 | signal_rolling_5y_rate | 19 | 0.72 | 18 | 26 | $7,205 | 99.7% | $3,980,302 | $-31,258 | $-709,414 | 5.16 | 92.5% |
| 7 | L-H-LL | 5 | signal_expanding_prior_rate | 19 | 0.72 | 18 | 26 | $7,205 | 99.7% | $3,980,302 | $-31,258 | $-709,414 | 5.16 | 92.5% |
| 8 | L-H-LL | 5 | signal_static_full_window | 19 | 0.72 | 18 | 26 | $7,205 | 99.7% | $3,980,302 | $-31,258 | $-709,414 | 5.16 | 92.5% |
| 9 | L-H-LL | 1 | signal_all_cash_lump | 97 | 3.67 | 89 | 21 | $2,873 | 99.4% | $3,966,638 | $-44,922 | $-706,037 | 5.17 | 97.0% |
| 10 | L-H-LL | 1 | signal_static_full_window | 97 | 3.67 | 91 | 22 | $2,796 | 99.4% | $3,958,985 | $-52,575 | $-704,853 | 5.17 | 96.6% |
| 11 | L-H-LL | 1 | signal_rolling_5y_rate | 97 | 3.67 | 91 | 22 | $2,796 | 99.4% | $3,957,466 | $-54,093 | $-704,474 | 5.17 | 96.7% |
| 12 | L-H-LL | 2 | signal_all_cash_lump | 50 | 1.89 | 49 | 23 | $4,389 | 99.4% | $3,955,733 | $-55,826 | $-704,400 | 5.16 | 95.7% |
| 13 | L-H-LL | 2 | signal_expanding_prior_rate | 50 | 1.89 | 49 | 24 | $4,329 | 99.4% | $3,954,285 | $-57,275 | $-704,179 | 5.16 | 95.5% |
| 14 | L-H-LL | 2 | signal_static_full_window | 50 | 1.89 | 49 | 23 | $4,389 | 99.4% | $3,950,210 | $-61,350 | $-703,426 | 5.16 | 95.6% |
| 15 | L-H-LL | 1 | signal_expanding_prior_rate | 97 | 3.67 | 93 | 24 | $2,701 | 99.4% | $3,948,494 | $-63,066 | $-702,918 | 5.16 | 96.6% |
| 16 | L-H-LL | 2 | signal_rolling_5y_rate | 50 | 1.89 | 49 | 23 | $4,389 | 99.4% | $3,942,029 | $-69,531 | $-701,900 | 5.16 | 95.6% |
| 17 | L-H-LL-HH | 1 | signal_all_cash_lump | 18 | 0.68 | 18 | 23 | $7,707 | 99.4% | $3,869,433 | $-142,126 | $-686,820 | 5.17 | 90.5% |
| 18 | L-H-LL-HH | 1 | signal_expanding_prior_rate | 18 | 0.68 | 18 | 23 | $7,707 | 99.4% | $3,869,433 | $-142,126 | $-686,820 | 5.17 | 90.5% |
| 19 | L-H-LL-HH | 1 | signal_static_full_window | 18 | 0.68 | 18 | 23 | $7,707 | 99.4% | $3,869,433 | $-142,126 | $-686,820 | 5.17 | 90.5% |
| 20 | L-H-LL-HH | 1 | signal_rolling_5y_rate | 18 | 0.68 | 18 | 24 | $7,524 | 99.4% | $3,869,313 | $-142,246 | $-686,820 | 5.17 | 90.5% |
| 21 | L-H-LL-HH | 3 | signal_expanding_prior_rate | 10 | 0.38 | 10 | 26 | $8,806 | 99.7% | $3,864,473 | $-147,086 | $-685,773 | 5.17 | 90.4% |
| 22 | L-H-LL-HH | 3 | signal_static_full_window | 10 | 0.38 | 10 | 26 | $8,806 | 99.7% | $3,864,473 | $-147,086 | $-685,773 | 5.17 | 90.4% |
| 23 | L-H-LL-HH | 3 | signal_rolling_5y_rate | 10 | 0.38 | 10 | 26 | $8,806 | 99.7% | $3,864,473 | $-147,086 | $-685,773 | 5.17 | 90.4% |
| 24 | L-H-LL-HH | 3 | signal_all_cash_lump | 10 | 0.38 | 10 | 26 | $8,806 | 99.7% | $3,864,473 | $-147,086 | $-685,773 | 5.17 | 90.4% |
| 25 | L-H-LL-HH | 2 | signal_static_full_window | 12 | 0.45 | 12 | 24 | $8,778 | 99.4% | $3,864,290 | $-147,269 | $-685,804 | 5.17 | 90.4% |
| 26 | L-H-LL-HH | 2 | signal_expanding_prior_rate | 12 | 0.45 | 12 | 24 | $8,778 | 99.4% | $3,864,290 | $-147,269 | $-685,804 | 5.17 | 90.4% |
| 27 | L-H-LL-HH | 2 | signal_rolling_5y_rate | 12 | 0.45 | 12 | 24 | $8,778 | 99.4% | $3,864,290 | $-147,269 | $-685,804 | 5.17 | 90.4% |
| 28 | L-H-LL-HH | 2 | signal_all_cash_lump | 12 | 0.45 | 12 | 24 | $8,778 | 99.4% | $3,864,290 | $-147,269 | $-685,804 | 5.17 | 90.4% |
| 29 | L-H-LL-HH | 5 | signal_all_cash_lump | 7 | 0.27 | 7 | 25 | $9,906 | 99.7% | $3,863,946 | $-147,614 | $-686,054 | 5.17 | 90.4% |
| 30 | L-H-LL-HH | 5 | signal_static_full_window | 7 | 0.27 | 7 | 25 | $9,906 | 99.7% | $3,863,946 | $-147,614 | $-686,054 | 5.17 | 90.4% |
| 31 | L-H-LL-HH | 5 | signal_expanding_prior_rate | 7 | 0.27 | 7 | 25 | $9,906 | 99.7% | $3,863,946 | $-147,614 | $-686,054 | 5.17 | 90.4% |
| 32 | L-H-LL-HH | 5 | signal_rolling_5y_rate | 7 | 0.27 | 7 | 25 | $9,906 | 99.7% | $3,863,946 | $-147,614 | $-686,054 | 5.17 | 90.4% |
| 33 | L-H-LL-HH | 8 | signal_rolling_5y_rate | 6 | 0.23 | 6 | 25 | $10,065 | 98.1% | $3,863,702 | $-147,857 | $-686,054 | 5.17 | 90.4% |
| 34 | L-H-LL-HH | 8 | signal_expanding_prior_rate | 6 | 0.23 | 6 | 25 | $10,065 | 98.1% | $3,863,702 | $-147,857 | $-686,054 | 5.17 | 90.4% |
| 35 | L-H-LL-HH | 8 | signal_static_full_window | 6 | 0.23 | 6 | 25 | $10,065 | 98.1% | $3,863,702 | $-147,857 | $-686,054 | 5.17 | 90.4% |
| 36 | L-H-LL-HH | 8 | signal_all_cash_lump | 6 | 0.23 | 6 | 25 | $10,065 | 98.1% | $3,863,702 | $-147,857 | $-686,054 | 5.17 | 90.4% |
| 37 | L-H-LL | 8 | signal_rolling_5y_rate | 14 | 0.53 | 14 | 24 | $8,368 | 100.0% | $3,836,699 | $-174,861 | $-683,613 | 5.15 | 91.7% |
| 38 | L-H-LL | 8 | signal_static_full_window | 14 | 0.53 | 14 | 24 | $8,368 | 100.0% | $3,836,699 | $-174,861 | $-683,613 | 5.15 | 91.7% |
| 39 | L-H-LL | 8 | signal_expanding_prior_rate | 14 | 0.53 | 14 | 24 | $8,368 | 100.0% | $3,836,699 | $-174,861 | $-683,613 | 5.15 | 91.7% |
| 40 | L-H-LL | 8 | signal_all_cash_lump | 14 | 0.53 | 14 | 24 | $8,368 | 100.0% | $3,836,699 | $-174,861 | $-683,613 | 5.15 | 91.7% |

Monthly DCA baseline: **$4,011,560 ending equity**, **$3,693,560 net**, **$-714,352 max DD**, **5.17 Net/DD**.

## Read

- Best causal weekly-swing row: **L-H-LL / 3-week pivots / signal_expanding_prior_rate**, with **31 signals** (1.17/year), **31 signal buys** and **26 December sweeps**, ending at **$3,982,032** (**$-29,527** vs monthly DCA).
- Best any-mode row: **L-H-LL / 3-week pivots / signal_static_full_window**, with **31 signal buys** and **25 December sweeps**, ending at **$3,986,240** (**$-25,320** vs monthly DCA).
- The December sweep removes the worst idle-cash drag, but it also means some performance is fallback deployment rather than signal timing.

## Best Causal By Pattern

| Pattern | Weekly Pivot Bars | Signals | Signals / Yr | Signal Buys | Dec Sweeps | End Equity | Vs Monthly | Deployed | Max DD | Net/DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| L-H-LL | 3 | 31 | 1.17 | 31 | 26 | $3,982,032 | $-29,527 | 99.4% | $-708,323 | 5.17 |
| L-H-LL-HH | 1 | 18 | 0.68 | 18 | 23 | $3,869,433 | $-142,126 | 99.4% | $-686,820 | 5.17 |

## Recent Signals

| Pattern | Pivot Bars | Buy Date | L1 | H1 | L2 | Buy Price | L2 vs L1 |
|---|---:|---|---:|---:|---:|---:|---:|
| L-H-LL | 3 | 2011-09-06 | 47.04 | 52.60 | 43.90 | 45.75 | -6.67% |
| L-H-LL | 3 | 2015-09-21 | 97.77 | 105.68 | 78.29 | 98.10 | -19.93% |
| L-H-LL | 3 | 2016-03-07 | 101.39 | 107.20 | 88.10 | 97.66 | -13.11% |
| L-H-LL | 3 | 2016-07-25 | 97.27 | 103.18 | 95.05 | 106.08 | -2.28% |
| L-H-LL | 3 | 2018-12-17 | 165.80 | 178.74 | 149.76 | 152.87 | -9.67% |
| L-H-LL | 3 | 2019-01-22 | 149.76 | 165.18 | 137.13 | 156.82 | -8.44% |
| L-H-LL | 3 | 2020-04-20 | 174.84 | 228.85 | 159.28 | 206.06 | -8.90% |
| L-H-LL | 3 | 2022-02-22 | 340.73 | 397.52 | 325.42 | 329.65 | -4.49% |
| L-H-LL | 3 | 2022-06-13 | 309.16 | 362.56 | 273.23 | 272.78 | -11.62% |
| L-H-LL | 3 | 2022-07-11 | 273.23 | 306.72 | 262.57 | 286.13 | -3.90% |
| L-H-LL | 3 | 2022-11-07 | 262.57 | 326.71 | 248.85 | 260.09 | -5.23% |
| L-H-LL | 3 | 2023-10-23 | 349.01 | 374.71 | 346.21 | 348.08 | -0.80% |
| L-H-LL | 3 | 2023-11-20 | 346.21 | 368.26 | 337.33 | 380.39 | -2.56% |
| L-H-LL | 3 | 2025-05-05 | 496.55 | 537.40 | 400.45 | 482.27 | -19.35% |
| L-H-LL | 3 | 2026-04-27 | 579.26 | 635.80 | 555.60 | 663.40 | -4.08% |

## Charts

- Top causal rows vs monthly DCA: [`charts/top_causal_vs_monthly.png`](charts/top_causal_vs_monthly.png)
- Best weekly row yearly chart pack: [`charts/yearly_lhll_3w/INDEX.md`](charts/yearly_lhll_3w/INDEX.md)
- Best L-H-LL equity comparison: [`charts/best_lhll_equity.png`](charts/best_lhll_equity.png)
- Best L-H-LL signal counts: [`charts/best_lhll_counts_by_year.png`](charts/best_lhll_counts_by_year.png)
- Best L-H-LL-HH equity comparison: [`charts/best_lhllhh_equity.png`](charts/best_lhllhh_equity.png)
- Best L-H-LL-HH signal counts: [`charts/best_lhllhh_counts_by_year.png`](charts/best_lhllhh_counts_by_year.png)

## Files

- `summary.csv`
- `signals.csv`
- `pivots.csv`
- `weekly_bars.csv`
- `curves.csv`
- `counts_by_year.csv`
