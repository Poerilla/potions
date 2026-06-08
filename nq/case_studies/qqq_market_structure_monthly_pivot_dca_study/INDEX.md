# QQQ Monthly-Pivot Market-Structure DCA Study

Data: Yahoo adjusted daily OHLCV for `QQQ`; monthly candles are resampled from adjusted daily bars.
Window: **2000-01-03 through 2026-06-02** (317 monthly bars).
Final partial monthly bar ending **2026-06-02** was dropped before pivot detection.

## Rule

- Monthly pivots use `N` completed monthly bars on the left and `N` completed monthly bars on the right.
- Pattern 1: **L-H-LL** = confirmed monthly low -> confirmed monthly high -> confirmed lower monthly low.
- Pattern 2: **L-H-LL-HH** = L-H-LL, then first later completed monthly bar that breaks above the prior monthly high.
- Signal buys happen at the **next available daily open** after the monthly signal is known.
- Year-end catch-up: if signal buys have not spent the accumulated annual budget, remaining cash is invested on the final December weekly bar at that week's **high**.
- Cashflow comparison: contribute **$1,000/month**. Monthly DCA buys the first trading day open; signal variants hold cash and buy on monthly-swing signals.

## Leaderboard

| Rank | Pattern | Monthly Pivot Bars | Variant | Signals | Signals / Yr | Signal Buys | Dec Sweeps | Avg Buy | Deployed | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure |
|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | L-H-LL | 2 | signal_static_full_window | 11 | 0.42 | 11 | 25 | $8,667 | 98.1% | $3,915,450 | $-96,110 | $-697,021 | 5.16 | 91.6% |
| 2 | L-H-LL | 2 | signal_expanding_prior_rate | 11 | 0.42 | 11 | 25 | $8,667 | 98.1% | $3,915,450 | $-96,110 | $-697,021 | 5.16 | 91.6% |
| 3 | L-H-LL | 2 | signal_rolling_5y_rate | 11 | 0.42 | 11 | 25 | $8,667 | 98.1% | $3,915,450 | $-96,110 | $-697,021 | 5.16 | 91.6% |
| 4 | L-H-LL | 2 | signal_all_cash_lump | 11 | 0.42 | 11 | 25 | $8,667 | 98.1% | $3,915,450 | $-96,110 | $-697,021 | 5.16 | 91.6% |
| 5 | L-H-LL | 3 | signal_expanding_prior_rate | 4 | 0.15 | 4 | 25 | $10,759 | 98.1% | $3,913,259 | $-98,301 | $-695,484 | 5.17 | 91.4% |
| 6 | L-H-LL | 3 | signal_rolling_5y_rate | 4 | 0.15 | 4 | 25 | $10,759 | 98.1% | $3,913,259 | $-98,301 | $-695,484 | 5.17 | 91.4% |
| 7 | L-H-LL | 3 | signal_all_cash_lump | 4 | 0.15 | 4 | 25 | $10,759 | 98.1% | $3,913,259 | $-98,301 | $-695,484 | 5.17 | 91.4% |
| 8 | L-H-LL | 3 | signal_static_full_window | 4 | 0.15 | 4 | 25 | $10,759 | 98.1% | $3,913,259 | $-98,301 | $-695,484 | 5.17 | 91.4% |
| 9 | L-H-LL | 1 | signal_expanding_prior_rate | 16 | 0.61 | 16 | 24 | $7,925 | 99.7% | $3,907,911 | $-103,649 | $-696,238 | 5.16 | 91.9% |
| 10 | L-H-LL | 1 | signal_static_full_window | 16 | 0.61 | 16 | 24 | $7,925 | 99.7% | $3,907,911 | $-103,649 | $-696,238 | 5.16 | 91.9% |
| 11 | L-H-LL | 1 | signal_all_cash_lump | 16 | 0.61 | 16 | 24 | $7,925 | 99.7% | $3,907,911 | $-103,649 | $-696,238 | 5.16 | 91.9% |
| 12 | L-H-LL | 1 | signal_rolling_5y_rate | 16 | 0.61 | 16 | 24 | $7,925 | 99.7% | $3,907,911 | $-103,649 | $-696,238 | 5.16 | 91.9% |
| 13 | L-H-LL | 8 | signal_all_cash_lump | 1 | 0.04 | 1 | 26 | $11,556 | 98.1% | $3,873,551 | $-138,008 | $-688,140 | 5.17 | 90.4% |
| 14 | L-H-LL | 8 | signal_static_full_window | 1 | 0.04 | 1 | 26 | $11,556 | 98.1% | $3,873,551 | $-138,008 | $-688,140 | 5.17 | 90.4% |
| 15 | L-H-LL | 8 | signal_expanding_prior_rate | 1 | 0.04 | 1 | 26 | $11,556 | 98.1% | $3,873,551 | $-138,008 | $-688,140 | 5.17 | 90.4% |
| 16 | L-H-LL | 8 | signal_rolling_5y_rate | 1 | 0.04 | 1 | 26 | $11,556 | 98.1% | $3,873,551 | $-138,008 | $-688,140 | 5.17 | 90.4% |
| 17 | L-H-LL-HH | 1 | signal_all_cash_lump | 7 | 0.27 | 7 | 25 | $9,938 | 100.0% | $3,865,411 | $-146,149 | $-686,321 | 5.17 | 90.4% |
| 18 | L-H-LL-HH | 1 | signal_rolling_5y_rate | 7 | 0.27 | 7 | 25 | $9,938 | 100.0% | $3,865,411 | $-146,149 | $-686,321 | 5.17 | 90.4% |
| 19 | L-H-LL-HH | 1 | signal_expanding_prior_rate | 7 | 0.27 | 7 | 25 | $9,938 | 100.0% | $3,865,411 | $-146,149 | $-686,321 | 5.17 | 90.4% |
| 20 | L-H-LL-HH | 1 | signal_static_full_window | 7 | 0.27 | 7 | 25 | $9,938 | 100.0% | $3,865,411 | $-146,149 | $-686,321 | 5.17 | 90.4% |
| 21 | L-H-LL-HH | 2 | signal_static_full_window | 6 | 0.23 | 6 | 25 | $10,065 | 98.1% | $3,865,327 | $-146,232 | $-686,321 | 5.17 | 90.4% |
| 22 | L-H-LL-HH | 2 | signal_expanding_prior_rate | 6 | 0.23 | 6 | 25 | $10,065 | 98.1% | $3,865,327 | $-146,232 | $-686,321 | 5.17 | 90.4% |
| 23 | L-H-LL-HH | 2 | signal_rolling_5y_rate | 6 | 0.23 | 6 | 25 | $10,065 | 98.1% | $3,865,327 | $-146,232 | $-686,321 | 5.17 | 90.4% |
| 24 | L-H-LL-HH | 2 | signal_all_cash_lump | 6 | 0.23 | 6 | 25 | $10,065 | 98.1% | $3,865,327 | $-146,232 | $-686,321 | 5.17 | 90.4% |
| 25 | L-H-LL-HH | 3 | signal_rolling_5y_rate | 4 | 0.15 | 4 | 26 | $10,400 | 98.1% | $3,859,978 | $-151,582 | $-685,547 | 5.17 | 90.4% |
| 26 | L-H-LL-HH | 3 | signal_all_cash_lump | 4 | 0.15 | 4 | 26 | $10,400 | 98.1% | $3,859,978 | $-151,582 | $-685,547 | 5.17 | 90.4% |
| 27 | L-H-LL-HH | 3 | signal_static_full_window | 4 | 0.15 | 4 | 26 | $10,400 | 98.1% | $3,859,978 | $-151,582 | $-685,547 | 5.17 | 90.4% |
| 28 | L-H-LL-HH | 3 | signal_expanding_prior_rate | 4 | 0.15 | 4 | 26 | $10,400 | 98.1% | $3,859,978 | $-151,582 | $-685,547 | 5.17 | 90.4% |
| 29 | L-H-LL-HH | 8 | signal_rolling_5y_rate | 1 | 0.04 | 1 | 26 | $11,556 | 98.1% | $3,849,679 | $-161,880 | $-683,725 | 5.17 | 90.4% |
| 30 | L-H-LL-HH | 8 | signal_expanding_prior_rate | 1 | 0.04 | 1 | 26 | $11,556 | 98.1% | $3,849,679 | $-161,880 | $-683,725 | 5.17 | 90.4% |
| 31 | L-H-LL-HH | 8 | signal_static_full_window | 1 | 0.04 | 1 | 26 | $11,556 | 98.1% | $3,849,679 | $-161,880 | $-683,725 | 5.17 | 90.4% |
| 32 | L-H-LL-HH | 8 | signal_all_cash_lump | 1 | 0.04 | 1 | 26 | $11,556 | 98.1% | $3,849,679 | $-161,880 | $-683,725 | 5.17 | 90.4% |
| 33 | L-H-LL-HH | 5 | signal_static_full_window | 0 | 0.00 | 0 | 26 | $12,000 | 98.1% | $3,849,141 | $-162,419 | $-683,626 | 5.17 | 90.3% |
| 34 | L-H-LL-HH | 5 | signal_expanding_prior_rate | 0 | 0.00 | 0 | 26 | $12,000 | 98.1% | $3,849,141 | $-162,419 | $-683,626 | 5.17 | 90.3% |
| 35 | L-H-LL-HH | 5 | signal_rolling_5y_rate | 0 | 0.00 | 0 | 26 | $12,000 | 98.1% | $3,849,141 | $-162,419 | $-683,626 | 5.17 | 90.3% |
| 36 | L-H-LL-HH | 5 | signal_all_cash_lump | 0 | 0.00 | 0 | 26 | $12,000 | 98.1% | $3,849,141 | $-162,419 | $-683,626 | 5.17 | 90.3% |
| 37 | L-H-LL | 5 | signal_rolling_5y_rate | 0 | 0.00 | 0 | 26 | $12,000 | 98.1% | $3,849,141 | $-162,419 | $-683,626 | 5.17 | 90.3% |
| 38 | L-H-LL | 5 | signal_static_full_window | 0 | 0.00 | 0 | 26 | $12,000 | 98.1% | $3,849,141 | $-162,419 | $-683,626 | 5.17 | 90.3% |
| 39 | L-H-LL | 5 | signal_expanding_prior_rate | 0 | 0.00 | 0 | 26 | $12,000 | 98.1% | $3,849,141 | $-162,419 | $-683,626 | 5.17 | 90.3% |
| 40 | L-H-LL | 5 | signal_all_cash_lump | 0 | 0.00 | 0 | 26 | $12,000 | 98.1% | $3,849,141 | $-162,419 | $-683,626 | 5.17 | 90.3% |

Monthly DCA baseline: **$4,011,560 ending equity**, **$3,693,560 net**, **$-714,352 max DD**, **5.17 Net/DD**.

## Read

- Best causal monthly-swing row: **L-H-LL / 2-month pivots / signal_expanding_prior_rate**, with **11 signals** (0.42/year), **11 signal buys** and **25 December sweeps**, ending at **$3,915,450** (**$-96,110** vs monthly DCA).
- Best any-mode row: **L-H-LL / 2-month pivots / signal_static_full_window**, with **11 signal buys** and **25 December sweeps**, ending at **$3,915,450** (**$-96,110** vs monthly DCA).
- Monthly pivots are far sparser than weekly pivots; the December catch-up keeps exposure high but also makes much of the result fallback deployment rather than signal timing.

## Best Causal By Pattern

| Pattern | Monthly Pivot Bars | Signals | Signals / Yr | Signal Buys | Dec Sweeps | End Equity | Vs Monthly | Deployed | Max DD | Net/DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| L-H-LL | 2 | 11 | 0.42 | 11 | 25 | $3,915,450 | $-96,110 | 98.1% | $-697,021 | 5.16 |
| L-H-LL-HH | 1 | 7 | 0.27 | 7 | 25 | $3,865,411 | $-146,149 | 100.0% | $-686,321 | 5.17 |

## Recent Signals

| Pattern | Pivot Bars | Buy Date | L1 | H1 | L2 | Buy Price | L2 vs L1 |
|---|---:|---|---:|---:|---:|---:|---:|
| L-H-LL | 2 | 2001-07-02 | 60.95 | 87.32 | 28.34 | 38.51 | -53.49% |
| L-H-LL | 2 | 2001-12-03 | 28.34 | 43.82 | 22.94 | 33.14 | -19.05% |
| L-H-LL | 2 | 2003-01-02 | 22.94 | 36.48 | 16.67 | 20.85 | -27.35% |
| L-H-LL | 2 | 2004-11-01 | 28.70 | 31.98 | 27.30 | 31.21 | -4.88% |
| L-H-LL | 2 | 2006-10-02 | 31.83 | 37.02 | 30.42 | 34.77 | -4.43% |
| L-H-LL | 2 | 2009-02-02 | 35.31 | 43.56 | 21.59 | 24.84 | -38.85% |
| L-H-LL | 2 | 2015-11-02 | 91.37 | 105.68 | 78.29 | 105.23 | -14.32% |
| L-H-LL | 2 | 2020-06-01 | 162.09 | 228.85 | 159.28 | 224.50 | -1.73% |
| L-H-LL | 2 | 2022-09-01 | 288.29 | 397.52 | 262.57 | 289.88 | -8.92% |
| L-H-LL | 2 | 2023-01-03 | 262.57 | 326.71 | 248.85 | 263.56 | -5.23% |
| L-H-LL | 2 | 2025-07-01 | 419.52 | 537.40 | 400.45 | 547.70 | -4.54% |

## Charts

- Top causal rows vs monthly DCA: [`charts/top_causal_vs_monthly.png`](charts/top_causal_vs_monthly.png)
- Best monthly row yearly chart pack: [`charts/yearly_lhll_2m/INDEX.md`](charts/yearly_lhll_2m/INDEX.md)
- Best L-H-LL equity comparison: [`charts/best_lhll_equity.png`](charts/best_lhll_equity.png)
- Best L-H-LL-HH equity comparison: [`charts/best_lhllhh_equity.png`](charts/best_lhllhh_equity.png)

## Files

- `summary.csv`
- `signals.csv`
- `pivots.csv`
- `monthly_bars.csv`
- `weekly_bars.csv`
- `curves.csv`
- `counts_by_year.csv`
