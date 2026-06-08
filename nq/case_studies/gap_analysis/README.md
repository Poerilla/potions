# NQ Hourly Gap Fill Study

Definitions:

- Daily gap: prior trading day 16:00 ET close to current day 09:30 ET open; filled if price trades back to the prior close during the same 09:30-16:00 ET RTH session.
- Weekly gap: previous week final RTH close to first trading day 09:30 ET open; filled if price trades back to the prior close any time before the end of that trading week.
- Fill detection uses the 1-minute source for exact high/low touches. Weekly inspection charts are 4-hour candles.

## Summary

| Gap Type | Gaps | Filled | Fill Rate | Median Gap | Avg Gap | Max Gap |
|---|---:|---:|---:|---:|---:|---:|
| Daily | 3199 | 2020 | 63.1% | 21.00 | 47.34 | 822.25 |
| Weekly | 817 | 661 | 80.9% | 22.75 | 53.96 | 999.25 |

## Daily Gap By Direction

| Direction | Gaps | Filled | Fill Rate | Median Gap |
|---|---:|---:|---:|---:|
| Gap Down | 1392 | 897 | 64.4% | 21.25 |
| Gap Up | 1807 | 1123 | 62.1% | 20.75 |

## Weekly Gap By Direction

| Direction | Gaps | Filled | Fill Rate | Median Gap |
|---|---:|---:|---:|---:|
| Gap Down | 355 | 306 | 86.2% | 22.50 |
| Gap Up | 462 | 355 | 76.8% | 23.62 |

## Daily Gap Size Buckets

| Bucket | Gaps | Filled | Fill Rate | Min Gap | Median Gap | Max Gap |
|---|---:|---:|---:|---:|---:|---:|
| Q1 smallest | 804 | 703 | 87.4% | 0.25 | 3.75 | 8.00 |
| Q2 | 798 | 531 | 66.5% | 8.25 | 13.25 | 21.00 |
| Q3 | 798 | 453 | 56.8% | 21.25 | 33.75 | 56.25 |
| Q4 largest | 799 | 333 | 41.7% | 56.50 | 108.00 | 822.25 |

## Weekly Gap Size Buckets

| Bucket | Gaps | Filled | Fill Rate | Min Gap | Median Gap | Max Gap |
|---|---:|---:|---:|---:|---:|---:|
| Q1 smallest | 206 | 199 | 96.6% | 0.25 | 3.50 | 7.75 |
| Q2 | 203 | 169 | 83.3% | 8.00 | 13.00 | 22.75 |
| Q3 | 204 | 157 | 77.0% | 23.00 | 34.25 | 54.75 |
| Q4 largest | 204 | 136 | 66.7% | 55.00 | 119.88 | 999.25 |

## Weekly 4-Hour Charts

Weekly chart threshold: 50.0% fill rate.
Charts generated: 817.

Charts are under `weekly_gap_4h/`, organized by year. They include the week-open 09:30 marker, the prior Friday/previous-week RTH close line, and the first fill marker when present.

## Files

- `daily_gap_fills.csv`
- `weekly_gap_fills.csv`
- `README.md`
- `weekly_gap_4h/INDEX.md`
