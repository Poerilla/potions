# GOOGL Monthly RSI70 Deferral Chart Pack

Yahoo adjusted OHLCV. Price is shown as monthly candles, with weekly and monthly smoothed RSI panels underneath.

Rule visualized: **block the first-trading-day monthly DCA buy when prior completed monthly RSI14 EMA14 is >=70**, then allow later buys to spend up to **2.0x** the normal `$1,000` monthly amount.

Window: **2004-08-19 through 2026-06-03**.

Counts:

- Completed monthly RSI >=70 bars: **46**.
- Weekly RSI >=70 bars: **103**.
- Blocked monthly DCA buys: **46**.
- Allowed buys: **217**.
- Gross skipped/saved cash: **$46,000**.
- Redeployed estimate through 2x catch-up: **$41,000**.
- Ending cash still unspent: **$5,000**.
- Ending equity: **$4,944,145** on **$263,000** contributed.
- Dropped final partial month from completed-month RSI: **2026-06-03**.

Legend:

- Red vertical lines / down markers = monthly DCA buy blocked by prior completed monthly RSI >=70.
- Green dotted vertical lines / up markers = catch-up buy larger than the normal monthly contribution.
- Orange monthly RSI points mark completed monthly RSI >=70.
- Purple weekly RSI points mark completed weekly RSI >=70.

## Charts

| Chart | Window | Monthly Bars | Blocked Buys | Catch-Up Buys |
|---|---:|---:|---:|---:|
| [`full_history.png`](full_history.png) | 2004-08-19 to 2026-06-03 | 263 | 46 | 41 |
| [`2004_2007.png`](segments/2004_2007.png) | 2004-08-19 to 2007-12-31 | 41 | 13 | 0 |
| [`2008_2011.png`](segments/2008_2011.png) | 2008-01-01 to 2011-12-31 | 48 | 2 | 15 |
| [`2012_2015.png`](segments/2012_2015.png) | 2012-01-01 to 2015-12-31 | 48 | 9 | 9 |
| [`2016_2019.png`](segments/2016_2019.png) | 2016-01-01 to 2019-12-31 | 48 | 5 | 5 |
| [`2020_2023.png`](segments/2020_2023.png) | 2020-01-01 to 2023-12-31 | 48 | 12 | 12 |
| [`2024_2026.png`](segments/2024_2026.png) | 2024-01-01 to 2026-06-03 | 30 | 5 | 0 |

## Files

- `monthly_candles.csv`
- `weekly_rsi.csv`
- `monthly_rsi.csv`
- `rsi70_dca_events.csv`
- `rsi70_dca_curve.csv`
