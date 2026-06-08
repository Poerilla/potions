# GOOGL RSI weekly >=65 Deferral Chart Pack

Yahoo adjusted OHLCV. Price is shown as monthly candles, with weekly and monthly smoothed RSI panels underneath.

Rule visualized: **block the first-trading-day monthly DCA buy when prior completed weekly RSI14 EMA14 is >=65**, then allow later buys to spend up to **2.0x** the normal `$1,000` monthly amount.

Window: **2004-08-19 through 2026-06-03**.

Counts:

- Completed monthly RSI >=65 bars: **98**.
- Weekly RSI >=65 bars: **216**.
- Blocked monthly DCA buys: **50**.
- Allowed buys: **213**.
- Gross skipped/saved cash: **$50,000**.
- Redeployed estimate through 2x catch-up: **$45,000**.
- Ending cash still unspent: **$5,000**.
- Ending equity: **$4,777,447** on **$263,000** contributed.
- Dropped final partial month from completed-month RSI: **2026-06-03**.

Legend:

- Red vertical lines / down markers = monthly DCA buy blocked by **RSI weekly >=65**.
- Green dotted vertical lines / up markers = catch-up buy larger than the normal monthly contribution.
- Orange monthly RSI points mark completed monthly RSI >=65.
- Purple weekly RSI points mark completed weekly RSI >=65.

## Charts

| Chart | Window | Monthly Bars | Blocked Buys | Catch-Up Buys |
|---|---:|---:|---:|---:|
| [`full_history.png`](full_history.png) | 2004-08-19 to 2026-06-03 | 263 | 50 | 45 |
| [`2004_2007.png`](segments/2004_2007.png) | 2004-08-19 to 2007-12-31 | 41 | 11 | 9 |
| [`2008_2011.png`](segments/2008_2011.png) | 2008-01-01 to 2011-12-31 | 48 | 5 | 7 |
| [`2012_2015.png`](segments/2012_2015.png) | 2012-01-01 to 2015-12-31 | 48 | 9 | 9 |
| [`2016_2019.png`](segments/2016_2019.png) | 2016-01-01 to 2019-12-31 | 48 | 4 | 4 |
| [`2020_2023.png`](segments/2020_2023.png) | 2020-01-01 to 2023-12-31 | 48 | 13 | 13 |
| [`2024_2026.png`](segments/2024_2026.png) | 2024-01-01 to 2026-06-03 | 30 | 8 | 3 |

## Files

- `monthly_candles.csv`
- `weekly_rsi.csv`
- `monthly_rsi.csv`
- `rsi_deferral_events.csv`
- `rsi_deferral_curve.csv`
