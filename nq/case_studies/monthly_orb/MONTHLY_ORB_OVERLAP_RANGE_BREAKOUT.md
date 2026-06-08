# NQ Monthly ORB Overlap-Range Breakout

Rules:

- Build monthly ORs from the first 3 daily rows of each calendar month.
- If adjacent monthly ORs overlap, combine them into one range.
- If later monthly ORs overlap the active combined range, expand the range.
- If a later monthly OR gaps away, the active cluster is done and the engine waits for the next adjacent overlap.
- Entry is the daily close that breaks out of the active combined range.
- Stop is at fraction ``stop_frac`` of the combined range from the wrong side for the breakout (default **0.5** = midpoint). Smaller ``stop_frac`` places the stop **deeper** (wider).
- Target is one combined range beyond the breakout-side boundary (1R).
- Default **one contract**; optional **two contracts** with one lot off at 1R and one runner to **2R** or **3R**, runner stop to breakeven after 1R fills (conservative same-bar: full stop before TP when both touch).
- One live trade at a time, max two entries per overlap cluster.
- One favorable extension is allowed if a later overlapping month expands the range and price breaks the expanded range in the trade direction.

Dollar figures use NQ point value of $20/point per contract.

## Summary

| Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts | Avg MAE / risk |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 58 | 8,437.8 | $168,755 | $-28,215 | 56.9% | 2.24 | 196.8 | 862.8 | 0.73 |

## Direction Split

| Direction | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |
|---|---:|---:|---:|---:|---:|---:|
| Long | 33 | 8,327.1 | $166,542 | $-21,272 | 66.7% | 4.12 |
| Short | 25 | 110.6 | $2,212 | $-34,682 | 44.0% | 1.03 |

## Exit Mix

- Target: **33**
- Midpoint-Stop: **25**

## Cluster Events

- entry: **58**
- start: **44**
- expand: **35**
- skip_overextended: **3**

## Yearly Split

| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|
| 2010 | 2 | 187.2 | 2 | 0 | 10.0 | 12.5 |
| 2011 | 3 | -11.5 | 1 | 2 | 58.4 | 95.5 |
| 2012 | 7 | 102.1 | 4 | 3 | 37.9 | 80.0 |
| 2013 | 1 | 61.2 | 1 | 0 | 3.0 | 3.0 |
| 2014 | 4 | 188.4 | 3 | 1 | 47.8 | 128.8 |
| 2015 | 6 | -7.5 | 2 | 4 | 85.2 | 142.5 |
| 2016 | 4 | -145.1 | 1 | 3 | 105.8 | 165.5 |
| 2017 | 2 | 290.5 | 2 | 0 | 44.9 | 52.5 |
| 2018 | 6 | 319.0 | 4 | 2 | 160.8 | 489.5 |
| 2019 | 3 | -106.0 | 1 | 2 | 175.2 | 244.8 |
| 2020 | 3 | 2,061.4 | 2 | 1 | 392.7 | 654.2 |
| 2021 | 1 | -572.0 | 0 | 1 | 844.5 | 844.5 |
| 2022 | 3 | 1,081.6 | 2 | 1 | 249.8 | 543.8 |
| 2023 | 4 | 1,394.1 | 3 | 1 | 358.9 | 754.2 |
| 2024 | 3 | 3,284.0 | 3 | 0 | 227.3 | 479.8 |
| 2025 | 5 | 923.4 | 2 | 3 | 546.5 | 862.8 |
| 2026 | 1 | -613.1 | 0 | 1 | 623.2 | 623.2 |

## Outputs

- `nq/nq_monthly_orb_overlap_range_breakout.csv`
- `nq/nq_monthly_orb_overlap_range_breakout_events.csv`
- Charts: `case_studies/monthly_orb/overlap_range_breakout/INDEX.md`
- Stop / MAE / 2-lot runner sweep: `case_studies/monthly_orb/MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT_SENSITIVITY.md` (regenerate: `python scripts/monthly_orb_overlap_range_breakout.py --sensitivity`)
