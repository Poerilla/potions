# GOOGL RSI weekly >=50 Deferral Chart Pack

Yahoo adjusted OHLCV. Price is shown as monthly candles, with weekly and monthly smoothed RSI panels underneath.

Rule visualized: **block the first-trading-day monthly DCA buy when prior completed weekly RSI14 EMA14 is >=50**, then schedule deferred cash across the next **4 allowed monthly buys**.

Window: **2004-08-19 through 2026-06-03**.

Counts:

- Completed monthly RSI >=50 bars: **227**.
- Weekly RSI >=50 bars: **875**.
- Blocked monthly DCA buys: **201**.
- Allowed buys: **62**.
- Gross skipped/saved cash: **$201,000**.
- Redeployed estimate through catch-up: **$190,000**.
- Ending cash still unspent: **$11,000**.
- Ending equity: **$4,276,321** on **$263,000** contributed.
- Dropped final partial month from completed-month RSI: **2026-06-03**.

Legend:

- Red vertical lines / down markers = monthly DCA buy blocked by **RSI weekly >=50**.
- Green dotted vertical lines / up markers = catch-up buy larger than the normal monthly contribution.
- Orange monthly RSI points mark completed monthly RSI >=50.
- Purple weekly RSI points mark completed weekly RSI >=50.

## Charts

| Chart | Window | Monthly Bars | Blocked Buys | Catch-Up Buys |
|---|---:|---:|---:|---:|
| [`full_history.png`](full_history.png) | 2004-08-19 to 2026-06-03 | 263 | 201 | 33 |
| [`2004_2007.png`](segments/2004_2007.png) | 2004-08-19 to 2007-12-31 | 41 | 34 | 0 |
| [`2008_2011.png`](segments/2008_2011.png) | 2008-01-01 to 2011-12-31 | 48 | 22 | 12 |
| [`2012_2015.png`](segments/2012_2015.png) | 2012-01-01 to 2015-12-31 | 48 | 41 | 7 |
| [`2016_2019.png`](segments/2016_2019.png) | 2016-01-01 to 2019-12-31 | 48 | 43 | 5 |
| [`2020_2023.png`](segments/2020_2023.png) | 2020-01-01 to 2023-12-31 | 48 | 35 | 5 |
| [`2024_2026.png`](segments/2024_2026.png) | 2024-01-01 to 2026-06-03 | 30 | 26 | 4 |

## Files

- `monthly_candles.csv`
- `weekly_rsi.csv`
- `monthly_rsi.csv`
- `rsi_deferral_events.csv`
- `rsi_deferral_curve.csv`
