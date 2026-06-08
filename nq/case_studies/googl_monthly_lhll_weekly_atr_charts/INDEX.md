# GOOGL Monthly LHLL + Weekly ATR Supertrend Charts

Yahoo adjusted OHLCV. Monthly candles are built from adjusted daily bars; the weekly ATR Supertrend is computed on Friday-anchored weekly candles and mapped causally onto the following trading week.

Signal overlay: confirmed monthly **low -> high -> lower low** using **2 bars left / 2 bars right**. The lower low is only marked once the right-side monthly confirmation is complete.

Window: **2004-08-19 through 2026-06-03** daily, **2004-08-31 through 2026-05-29** monthly.

ATR Supertrend: weekly **ATR(14) x 3.00**.

Counts: **262** monthly candles, **34** pivot lows, **31** pivot highs, **9** LHLL sequences.

Dropped partial final monthly candle: **2026-06-03**.

## Charts

| Chart | Window | Monthly Bars | Pivot Lows | Pivot Highs | LHLL Sequences |
|---|---:|---:|---:|---:|---:|
| [full_history.png](full_history.png) | 2004-08-11 to 2026-06-18 | 262 | 34 | 31 | 9 |
| [segments/2004_2008.png](segments/2004_2008.png) | 2003-11-17 to 2009-02-14 | 54 | 7 | 6 | 2 |
| [segments/2009_2013.png](segments/2009_2013.png) | 2008-11-17 to 2014-02-14 | 63 | 8 | 7 | 2 |
| [segments/2014_2018.png](segments/2014_2018.png) | 2013-11-17 to 2019-02-14 | 63 | 8 | 9 | 2 |
| [segments/2019_2023.png](segments/2019_2023.png) | 2018-11-17 to 2024-02-14 | 63 | 9 | 7 | 4 |
| [segments/2024_2026.png](segments/2024_2026.png) | 2023-11-17 to 2027-02-14 | 31 | 4 | 3 | 1 |

## LHLL Sequences

| # | Low 1 | High | Lower Low | Signal Known | L2 Below L1 |
|---:|---:|---:|---:|---:|---:|
| 1 | 2007-03-30 / 10.85 | 2007-11-30 / 18.55 | 2008-03-31 / 10.23 | 2008-05-30 | -5.70% |
| 2 | 2008-03-31 / 10.23 | 2008-05-30 / 14.95 | 2008-11-28 / 6.14 | 2009-01-30 | -39.99% |
| 3 | 2010-02-26 / 12.91 | 2010-04-30 / 14.84 | 2010-07-30 / 10.76 | 2010-09-30 | -16.61% |
| 4 | 2014-04-30 / 25.34 | 2014-07-31 / 30.20 | 2015-01-30 / 24.34 | 2015-03-31 | -3.93% |
| 5 | 2018-03-29 / 48.80 | 2018-07-31 / 64.04 | 2018-12-31 / 48.48 | 2019-02-28 | -0.64% |
| 6 | 2019-06-28 / 50.93 | 2020-02-28 / 75.91 | 2020-03-31 / 50.03 | 2020-05-29 | -1.77% |
| 7 | 2022-01-31 / 123.48 | 2022-02-28 / 150.30 | 2022-05-31 / 101.05 | 2022-07-29 | -18.17% |
| 8 | 2022-05-31 / 101.05 | 2022-08-31 / 121.43 | 2022-11-30 / 82.66 | 2023-01-31 | -18.20% |
| 9 | 2024-09-30 / 146.37 | 2025-02-28 / 206.10 | 2025-04-30 / 140.04 | 2025-06-30 | -4.32% |

## Files

- `monthly_bars.csv`
- `pivots.csv`
- `lhll_sequences.csv`
- `weekly_atr_stop_daily.csv`
