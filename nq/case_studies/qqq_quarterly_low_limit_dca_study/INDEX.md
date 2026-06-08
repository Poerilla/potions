# QQQ Previous-Quarter-Low Limit DCA Study

Data: Yahoo adjusted daily OHLCV for `QQQ`.
Window: **2000-01-03 through 2026-06-02**.

## Rule

- Each completed quarter defines a low from adjusted daily lows.
- In the next quarter, place one resting buy limit at the **previous quarter's low**. Q1 uses the prior year's Q4 low when available.
- If any daily low touches that level, buy all available cash at the limit price. One fill maximum per quarter.
- Cashflow comparison: contribute **$1,000/month**. Monthly DCA buys first trading day open; this variant holds cash until a quarterly low retest or fallback.
- If a calendar year has **no** quarterly-low fill, buy all available cash on the final trading day of that year at the close.
- No fees, taxes, cash interest, or slippage.

## Result

| Variant | End Equity | Net | Vs Monthly DCA | Max DD | Net/DD | Deployed | Avg Exposure | Quarterly Fills | Fill Rate | Year-End Fallbacks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Previous-quarter-low limit | $3,857,353 | $3,539,353 | $-154,207 | $-685,184 | 5.17 | 99.1% | 94.3% | 33 / 105 | 31.4% | 7 |

Monthly DCA baseline: **$4,011,560 ending equity**, **$3,693,560 net**, **$-714,352 max DD**, **5.17 Net/DD**.

## Fill Cadence

- Eligible quarters: **105**.
- Previous-quarter-low fills: **33**, or **31.4%** of eligible quarters.
- Expected cadence: **1.27 quarterly-low fills/year** over complete years.
- Years with no quarterly-low fill and a year-end fallback: **7**.
- Average quarterly-low buy: **$6,242**; average fallback buy: **$15,571**.

## By Year

| Year | Eligible Quarters | Quarterly Fills | Fill Rate | Fallbacks | Total Buys | Buy Amount |
|---:|---:|---:|---:|---:|---:|---:|
| 2000 | 3 | 2 | 66.7% | 0 | 2 | $10,000 |
| 2001 | 4 | 3 | 75.0% | 0 | 3 | $11,000 |
| 2002 | 4 | 3 | 75.0% | 0 | 3 | $13,000 |
| 2003 | 4 | 0 | 0.0% | 1 | 1 | $14,000 |
| 2004 | 4 | 1 | 25.0% | 0 | 1 | $7,000 |
| 2005 | 4 | 1 | 25.0% | 0 | 1 | $9,000 |
| 2006 | 4 | 2 | 50.0% | 0 | 2 | $15,000 |
| 2007 | 4 | 0 | 0.0% | 1 | 1 | $17,000 |
| 2008 | 4 | 3 | 75.0% | 0 | 3 | $10,000 |
| 2009 | 4 | 0 | 0.0% | 1 | 1 | $14,000 |
| 2010 | 4 | 1 | 25.0% | 0 | 1 | $7,000 |
| 2011 | 4 | 2 | 50.0% | 0 | 2 | $13,000 |
| 2012 | 4 | 1 | 25.0% | 0 | 1 | $15,000 |
| 2013 | 4 | 0 | 0.0% | 1 | 1 | $13,000 |
| 2014 | 4 | 1 | 25.0% | 0 | 1 | $10,000 |
| 2015 | 4 | 1 | 25.0% | 0 | 1 | $10,000 |
| 2016 | 4 | 1 | 25.0% | 0 | 1 | $5,000 |
| 2017 | 4 | 0 | 0.0% | 1 | 1 | $23,000 |
| 2018 | 4 | 1 | 25.0% | 0 | 1 | $10,000 |
| 2019 | 4 | 0 | 0.0% | 1 | 1 | $14,000 |
| 2020 | 4 | 1 | 25.0% | 0 | 1 | $3,000 |
| 2021 | 4 | 1 | 25.0% | 0 | 1 | $19,000 |
| 2022 | 4 | 4 | 100.0% | 0 | 4 | $12,000 |
| 2023 | 4 | 1 | 25.0% | 0 | 1 | $12,000 |
| 2024 | 4 | 0 | 0.0% | 1 | 1 | $14,000 |
| 2025 | 4 | 2 | 50.0% | 0 | 2 | $4,000 |
| 2026 | 2 | 1 | 50.0% | 0 | 1 | $11,000 |

## Recent Events

| Date | Event | Buy Amount | Price | Quarter | Prior Quarter | Prior Q Low | Daily Low |
|---|---|---:|---:|---|---|---:|---:|
| 2011-08-05 | prev_quarter_low_limit | $2,000 | 47.04 | 2011Q3 | 2011Q2 | 47.04 | 46.00 |
| 2012-11-16 | prev_quarter_low_limit | $15,000 | 54.92 | 2012Q4 | 2012Q3 | 54.92 | 54.58 |
| 2013-12-31 | year_end_no_quarter_fill | $13,000 | 79.67 | 2013Q4 | 2013Q3 | 64.23 | 79.27 |
| 2014-10-13 | prev_quarter_low_limit | $10,000 | 85.58 | 2014Q4 | 2014Q3 | 85.58 | 85.10 |
| 2015-08-21 | prev_quarter_low_limit | $10,000 | 96.17 | 2015Q3 | 2015Q2 | 96.17 | 94.60 |
| 2016-01-15 | prev_quarter_low_limit | $5,000 | 93.05 | 2016Q1 | 2015Q4 | 93.05 | 92.44 |
| 2017-12-29 | year_end_no_quarter_fill | $23,000 | 147.63 | 2017Q4 | 2017Q3 | 128.17 | 147.58 |
| 2018-10-11 | prev_quarter_low_limit | $10,000 | 161.42 | 2018Q4 | 2018Q3 | 161.42 | 159.94 |
| 2019-12-31 | year_end_no_quarter_fill | $14,000 | 204.90 | 2019Q4 | 2019Q3 | 171.98 | 203.54 |
| 2020-03-12 | prev_quarter_low_limit | $3,000 | 174.84 | 2020Q1 | 2019Q4 | 174.84 | 170.52 |
| 2021-10-04 | prev_quarter_low_limit | $19,000 | 342.03 | 2021Q4 | 2021Q3 | 342.03 | 340.73 |
| 2022-01-24 | prev_quarter_low_limit | $3,000 | 340.73 | 2022Q1 | 2021Q4 | 340.73 | 325.42 |
| 2022-04-26 | prev_quarter_low_limit | $3,000 | 309.16 | 2022Q2 | 2022Q1 | 309.16 | 308.96 |
| 2022-09-30 | prev_quarter_low_limit | $5,000 | 262.57 | 2022Q3 | 2022Q2 | 262.57 | 261.41 |
| 2022-10-10 | prev_quarter_low_limit | $1,000 | 261.41 | 2022Q4 | 2022Q3 | 261.41 | 258.03 |
| 2023-10-23 | prev_quarter_low_limit | $12,000 | 346.21 | 2023Q4 | 2023Q3 | 346.21 | 345.97 |
| 2024-12-31 | year_end_no_quarter_fill | $14,000 | 508.01 | 2024Q4 | 2024Q3 | 419.52 | 507.05 |
| 2025-03-10 | prev_quarter_low_limit | $3,000 | 473.63 | 2025Q1 | 2024Q4 | 473.63 | 465.71 |
| 2025-04-03 | prev_quarter_low_limit | $1,000 | 455.13 | 2025Q2 | 2025Q1 | 455.13 | 447.97 |
| 2026-03-20 | prev_quarter_low_limit | $11,000 | 579.26 | 2026Q1 | 2025Q4 | 579.26 | 577.81 |

## Charts

- Equity vs monthly DCA: [`charts/equity_vs_monthly.png`](charts/equity_vs_monthly.png)
- Buy events by year: [`charts/fills_by_year.png`](charts/fills_by_year.png)
- Fill rate by calendar quarter: [`charts/fill_rate_by_quarter.png`](charts/fill_rate_by_quarter.png)
- No-fill year chart pack: [`charts/no_fill_years/INDEX.md`](charts/no_fill_years/INDEX.md)

## Files

- `summary.csv`
- `events.csv`
- `counts_by_year.csv`
- `quarters.csv`
- `curves.csv`
