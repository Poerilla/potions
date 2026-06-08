# QQQ Yearly ORB Study

Data: Yahoo daily QQQ adjusted OHLCV.
Window: **2000-01-03 through 2026-06-01**. Starting capital: **$10,000**.

Rules:

- Jan-Mar defines the yearly opening range.
- Apr-Dec is the trade window.
- Core QQQ variants are long-only; inverse rows buy PSQ as a 1x inverse ETF proxy. No leverage, no fees, no cash interest.
- `stop_breakout_range_close`: resting buy stop at the OR high from Apr 1; exit next open after a daily close back below/at the OR high, or year-end close.
- `close_breakout_next_open`: wait for a fresh daily close above the OR high, enter next open; same range-close/year-end exit.
- `limit_retest_after_close`: after a fresh daily close above the OR high, rest a buy limit at the OR high; same range-close/year-end exit.
- `50/50 stop_breakout + monthly DCA`: half the account follows `stop_breakout_range_close`; half follows cash-funded monthly DCA.
- `hybrid_stop_breakout_plus_monthly_dca`: permanent monthly DCA core plus a tactical sweep of not-yet-DCA cash during `stop_breakout_range_close` risk-on windows; range-close only liquidates the tactical sleeve.
- `PSQ inverse close-breakdown next-open`: buy PSQ at the next open after QQQ closes below the yearly OR low; exit next open after QQQ closes back above/at the OR low, or year-end close.
- `QQQ/PSQ dual close-confirmed ORB`: buy QQQ after a close above the OR high, or PSQ after a close below the OR low; one side at a time, next-open fills only.

Exposure is average invested market value divided by account equity, so monthly DCA reflects gradual capital deployment instead of a simple in/out flag.
PSQ inverse rows can only trade after local PSQ data begins: **2006-06-21**.

## Equity Ranking

| Rank | Variant | End Capital | Net | Return | CAGR | Max DD | Max DD % | Net/DD | Exposure |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | close_breakout_next_open | $72,382 | $62,382 | 623.8% | 7.78% | $-7,531 | -19.44% | 8.28 | 38.3% |
| 2 | 50/50 stop_breakout + monthly DCA | $105,780 | $95,780 | 957.8% | 9.34% | $-11,740 | -20.41% | 8.16 | 49.1% |
| 3 | stop_breakout_range_close | $85,802 | $75,802 | 758.0% | 8.48% | $-10,400 | -21.18% | 7.29 | 40.0% |
| 4 | hybrid_stop_breakout_plus_monthly_dca | $167,388 | $157,388 | 1573.9% | 11.26% | $-23,151 | -25.79% | 6.80 | 60.2% |
| 5 | QQQ monthly DCA cash-funded | $125,757 | $115,757 | 1157.6% | 10.06% | $-22,802 | -34.31% | 5.08 | 58.2% |
| 6 | limit_retest_after_close | $26,508 | $16,508 | 165.1% | 3.76% | $-3,337 | -20.84% | 4.95 | 17.3% |
| 7 | QQQ buy-and-hold | $93,099 | $83,099 | 831.0% | 8.82% | $-17,265 | -82.96% | 4.81 | 100.0% |
| 8 | QQQ/PSQ dual close-confirmed ORB | $48,160 | $38,160 | 381.6% | 6.13% | $-8,337 | -36.33% | 4.58 | 41.9% |
| 9 | PSQ inverse close-breakdown next-open | $6,654 | $-3,346 | -33.5% | -1.53% | $-5,975 | -47.51% | -0.56 | 3.9% |

## Trade Stats

| Variant | Trades | Win Rate | PF | Avg Return | Median Return | Avg Days | Worst | Best |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| stop_breakout_range_close | 114 | 31.6% | 4.56 | 2.18% | -0.33% | 33.3 | -3.74% | 44.74% |
| close_breakout_next_open | 72 | 30.6% | 4.54 | 3.17% | -0.88% | 50.5 | -3.76% | 41.10% |
| limit_retest_after_close | 71 | 36.6% | 3.40 | 1.55% | -0.43% | 23.1 | -3.42% | 32.78% |
| QQQ/PSQ dual close-confirmed ORB | 93 | 26.9% | 2.28 | 2.05% | -1.06% | 43.1 | -7.74% | 41.10% |
| PSQ inverse close-breakdown next-open | 21 | 14.3% | 0.40 | -1.79% | -2.88% | 17.5 | -7.74% | 12.77% |

## Charts

- [Equity comparison](charts/equity_comparison.png)
- [Latest yearly chart](charts/yearly/2026.png)

## Yearly OR Levels

| Year | OR High | OR Low | OR Range | OR Days | Trade Days | Chart |
|---:|---:|---:|---:|---:|---:|---|
| 2000 | 101.65 | 67.27 | 34.38 | 63 | 189 | [charts/yearly/2000.png](charts/yearly/2000.png) |
| 2001 | 58.31 | 32.06 | 26.26 | 62 | 186 | [charts/yearly/2001.png](charts/yearly/2001.png) |
| 2002 | 35.94 | 27.91 | 8.02 | 60 | 192 | [charts/yearly/2002.png](charts/yearly/2002.png) |
| 2003 | 23.17 | 19.67 | 3.50 | 61 | 191 | [charts/yearly/2003.png](charts/yearly/2003.png) |
| 2004 | 32.91 | 28.70 | 4.21 | 62 | 190 | [charts/yearly/2004.png](charts/yearly/2004.png) |
| 2005 | 34.33 | 30.62 | 3.71 | 61 | 191 | [charts/yearly/2005.png](charts/yearly/2005.png) |
| 2006 | 37.02 | 34.33 | 2.69 | 62 | 189 | [charts/yearly/2006.png](charts/yearly/2006.png) |
| 2007 | 39.06 | 36.07 | 2.99 | 61 | 190 | [charts/yearly/2007.png](charts/yearly/2007.png) |
| 2008 | 44.27 | 35.31 | 8.96 | 61 | 192 | [charts/yearly/2008.png](charts/yearly/2008.png) |
| 2009 | 27.35 | 22.12 | 5.22 | 61 | 191 | [charts/yearly/2009.png](charts/yearly/2009.png) |
| 2010 | 42.23 | 36.56 | 5.67 | 61 | 191 | [charts/yearly/2010.png](charts/yearly/2010.png) |
| 2011 | 51.72 | 47.10 | 4.62 | 62 | 190 | [charts/yearly/2011.png](charts/yearly/2011.png) |
| 2012 | 60.68 | 50.01 | 10.67 | 62 | 188 | [charts/yearly/2012.png](charts/yearly/2012.png) |
| 2013 | 61.97 | 59.05 | 2.92 | 60 | 192 | [charts/yearly/2013.png](charts/yearly/2013.png) |
| 2014 | 83.09 | 75.85 | 7.25 | 61 | 191 | [charts/yearly/2014.png](charts/yearly/2014.png) |
| 2015 | 100.62 | 91.37 | 9.25 | 61 | 191 | [charts/yearly/2015.png](charts/yearly/2015.png) |
| 2016 | 102.52 | 88.10 | 14.42 | 61 | 191 | [charts/yearly/2016.png](charts/yearly/2016.png) |
| 2017 | 124.94 | 111.67 | 13.27 | 62 | 189 | [charts/yearly/2017.png](charts/yearly/2017.png) |
| 2018 | 166.07 | 142.30 | 23.77 | 61 | 190 | [charts/yearly/2018.png](charts/yearly/2018.png) |
| 2019 | 175.07 | 142.89 | 32.19 | 61 | 191 | [charts/yearly/2019.png](charts/yearly/2019.png) |
| 2020 | 228.85 | 159.28 | 69.57 | 62 | 191 | [charts/yearly/2020.png](charts/yearly/2020.png) |
| 2021 | 327.78 | 288.29 | 39.49 | 61 | 191 | [charts/yearly/2021.png](charts/yearly/2021.png) |
| 2022 | 391.77 | 309.16 | 82.61 | 62 | 189 | [charts/yearly/2022.png](charts/yearly/2022.png) |
| 2023 | 315.57 | 255.41 | 60.17 | 62 | 188 | [charts/yearly/2023.png](charts/yearly/2023.png) |
| 2024 | 444.46 | 390.53 | 53.93 | 61 | 191 | [charts/yearly/2024.png](charts/yearly/2024.png) |
| 2025 | 537.40 | 455.13 | 82.28 | 60 | 190 | [charts/yearly/2025.png](charts/yearly/2025.png) |
| 2026 | 635.80 | 555.60 | 80.20 | 61 | 42 | [charts/yearly/2026.png](charts/yearly/2026.png) |

## Files

- `QQQ_daily_yearly_orb.csv`
- `PSQ_daily_yearly_orb.csv`
- `or_levels.csv`
- `trades.csv`
- `equity_curves.csv`
- `equity_summary.csv`
- `trade_summary.csv`
- `yearly_summary.csv`
