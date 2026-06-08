# MNQ Hourly Gap Fill Study

Definitions:

- Daily gap: prior trading day 16:00 ET close to current day 09:30 ET open; filled if price trades back to the prior close during the same 09:30-16:00 ET RTH session.
- Weekly gap: previous week final RTH close to first trading day 09:30 ET open; filled if price trades back to the prior close any time before the end of that trading week.
- Fill detection uses the 1-minute source for exact high/low touches. Weekly inspection charts are 4-hour candles.

## Summary

| Gap Type | Gaps | Filled | Fill Rate | Median Gap | Avg Gap | Max Gap |
|---|---:|---:|---:|---:|---:|---:|
| Daily | 1427 | 870 | 61.0% | 58.50 | 87.21 | 830.00 |
| Weekly | 362 | 286 | 79.0% | 58.50 | 102.71 | 998.75 |

## Daily Gap By Direction

| Direction | Gaps | Filled | Fill Rate | Median Gap |
|---|---:|---:|---:|---:|
| Gap Down | 630 | 381 | 60.5% | 59.88 |
| Gap Up | 797 | 489 | 61.4% | 57.50 |

## Weekly Gap By Direction

| Direction | Gaps | Filled | Fill Rate | Median Gap |
|---|---:|---:|---:|---:|
| Gap Down | 158 | 135 | 85.4% | 57.50 |
| Gap Up | 204 | 151 | 74.0% | 61.75 |

## Daily Gap Size Buckets

| Bucket | Gaps | Filled | Fill Rate | Min Gap | Median Gap | Max Gap |
|---|---:|---:|---:|---:|---:|---:|
| Q1 smallest | 359 | 317 | 88.3% | 0.25 | 12.75 | 25.75 |
| Q2 | 356 | 253 | 71.1% | 26.00 | 42.50 | 58.50 |
| Q3 | 356 | 186 | 52.2% | 58.75 | 82.25 | 116.25 |
| Q4 largest | 356 | 114 | 32.0% | 116.75 | 177.25 | 830.00 |

## Weekly Gap Size Buckets

| Bucket | Gaps | Filled | Fill Rate | Min Gap | Median Gap | Max Gap |
|---|---:|---:|---:|---:|---:|---:|
| Q1 smallest | 92 | 89 | 96.7% | 1.00 | 12.00 | 26.75 |
| Q2 | 90 | 73 | 81.1% | 27.25 | 43.88 | 58.50 |
| Q3 | 89 | 69 | 77.5% | 59.50 | 89.50 | 130.25 |
| Q4 largest | 91 | 55 | 60.4% | 133.00 | 213.50 | 998.75 |

## Weekly 4-Hour Charts

Weekly chart threshold: 50.0% fill rate.
Charts generated: 362.

Charts are under `weekly_gap_4h/`, organized by year. They include the week-open 09:30 marker, the prior Friday/previous-week RTH close line, and the first fill marker when present.

## Files

- `daily_gap_fills.csv`
- `weekly_gap_fills.csv`
- `README.md`
- `weekly_gap_4h/INDEX.md`
