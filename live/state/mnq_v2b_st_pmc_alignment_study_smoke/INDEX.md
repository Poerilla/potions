# MNQ ST+PMC vs MNQ v2b Alignment Study

ST+PMC proxy: `hourly ST+PMC sl25_tp75_3r`.
V2B proxy: `v2b S_1_1_3`.

Alignment is by NY session date and direction:

- `aligned`: ST+PMC trade direction appears in same-day v2b campaigns.
- `opposed`: v2b traded only the opposite direction.
- `no_v2b`: no v2b entry on that session.

## Summary

| Category | Trades | Win % | Net | Avg | PF | Same-day v2b net |
|---|---:|---:|---:|---:|---:|---:|
| aligned | 357 | 38.66% | $9063.01 | $25.39 | 1.793 | $-74311.50 |
| opposed | 198 | 22.73% | $-1280.14 | $-6.47 | 0.839 | $156902.00 |
| no_v2b | 250 | 28.80% | $923.69 | $3.69 | 1.095 | $0.00 |
| not_aligned | 448 | 26.12% | $-356.46 | $-0.80 | 0.980 | $156902.00 |
| all | 805 | 31.68% | $8706.56 | $10.82 | 1.299 | $82590.50 |

## Charts

| # | Date | Category | ST Side | ST PnL | V2B dirs | V2B entries | Chart |
|---:|---|---|---|---:|---|---:|---|
| 1 | 2021-03-04 | aligned | short | $148 | long,short | 2 | [0001_2021-03-04_aligned_short.png](charts/aligned/0001_2021-03-04_aligned_short.png) |
| 2 | 2021-03-04 | aligned | short | $-52 | long,short | 2 | [0002_2021-03-04_aligned_short.png](charts/aligned/0002_2021-03-04_aligned_short.png) |
| 3 | 2021-03-04 | aligned | short | $148 | long,short | 2 | [0003_2021-03-04_aligned_short.png](charts/aligned/0003_2021-03-04_aligned_short.png) |
| 4 | 2021-03-05 | aligned | short | $-52 | long,short | 2 | [0004_2021-03-05_aligned_short.png](charts/aligned/0004_2021-03-05_aligned_short.png) |
| 5 | 2021-03-09 | opposed | short | $-52 | long | 1 | [0005_2021-03-09_opposed_short.png](charts/not_aligned/0005_2021-03-09_opposed_short.png) |
| 6 | 2021-03-14 | no_v2b | short | $148 | - | 0 | [0006_2021-03-14_no_v2b_short.png](charts/not_aligned/0006_2021-03-14_no_v2b_short.png) |
| 7 | 2021-03-16 | aligned | long | $-52 | long,short | 2 | [0007_2021-03-16_aligned_long.png](charts/aligned/0007_2021-03-16_aligned_long.png) |
| 8 | 2021-03-16 | aligned | long | $-52 | long,short | 2 | [0008_2021-03-16_aligned_long.png](charts/aligned/0008_2021-03-16_aligned_long.png) |
| 9 | 2021-03-17 | opposed | short | $-52 | long | 1 | [0009_2021-03-17_opposed_short.png](charts/not_aligned/0009_2021-03-17_opposed_short.png) |
| 10 | 2021-03-18 | opposed | long | $-52 | short | 1 | [0010_2021-03-18_opposed_long.png](charts/not_aligned/0010_2021-03-18_opposed_long.png) |
| 11 | 2021-03-18 | opposed | long | $-52 | short | 1 | [0011_2021-03-18_opposed_long.png](charts/not_aligned/0011_2021-03-18_opposed_long.png) |
| 12 | 2021-03-22 | opposed | short | $-52 | long | 1 | [0012_2021-03-22_opposed_short.png](charts/not_aligned/0012_2021-03-22_opposed_short.png) |