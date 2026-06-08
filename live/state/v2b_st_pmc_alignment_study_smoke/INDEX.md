# MYM ST+PMC vs MNQ v2b Alignment Study

Best ST+PMC proxy: `MYM hourly ST+PMC base_1x_50sl_150tp`.
V2B proxy: `MNQ v2b 1/0/1`.

Alignment is by NY session date and direction:

- `aligned`: MYM ST+PMC trade direction appears in same-day MNQ v2b campaigns.
- `opposed`: MNQ v2b traded only the opposite direction.
- `no_v2b`: no MNQ v2b entry on that session.

## Summary

| Category | Trades | Win % | Net | Avg | PF | Same-day v2b net |
|---|---:|---:|---:|---:|---:|---:|
| aligned | 350 | 34.29% | $2587.08 | $7.39 | 1.415 | $-19501.50 |
| opposed | 155 | 33.55% | $1041.00 | $6.72 | 1.374 | $48798.00 |
| no_v2b | 220 | 37.73% | $2267.15 | $10.31 | 1.591 | $0.00 |
| not_aligned | 375 | 36.00% | $3308.15 | $8.82 | 1.500 | $48798.00 |
| all | 725 | 35.17% | $5895.23 | $8.13 | 1.459 | $29296.50 |

## Charts

| # | Date | Category | ST Side | ST PnL | V2B dirs | V2B entries | Chart |
|---:|---|---|---|---:|---|---:|---|
| 1 | 2024-08-06 | aligned | short | $-27 | long,short | 2 | [0001_2024-08-06_aligned_short.png](charts/aligned/0001_2024-08-06_aligned_short.png) |
| 2 | 2024-08-08 | aligned | short | $-27 | long,short | 2 | [0002_2024-08-08_aligned_short.png](charts/aligned/0002_2024-08-08_aligned_short.png) |
| 3 | 2024-08-13 | opposed | short | $-27 | long | 1 | [0003_2024-08-13_opposed_short.png](charts/not_aligned/0003_2024-08-13_opposed_short.png) |
| 4 | 2024-08-13 | opposed | short | $-27 | long | 1 | [0004_2024-08-13_opposed_short.png](charts/not_aligned/0004_2024-08-13_opposed_short.png) |
| 5 | 2024-08-16 | opposed | short | $-27 | long | 1 | [0005_2024-08-16_opposed_short.png](charts/not_aligned/0005_2024-08-16_opposed_short.png) |
| 6 | 2024-08-22 | aligned | short | $74 | short | 1 | [0006_2024-08-22_aligned_short.png](charts/aligned/0006_2024-08-22_aligned_short.png) |
| 7 | 2024-08-23 | aligned | short | $-27 | long,short | 2 | [0007_2024-08-23_aligned_short.png](charts/aligned/0007_2024-08-23_aligned_short.png) |
| 8 | 2024-08-26 | opposed | long | $74 | short | 1 | [0008_2024-08-26_opposed_long.png](charts/not_aligned/0008_2024-08-26_opposed_long.png) |
| 9 | 2024-08-27 | aligned | long | $-27 | long,short | 2 | [0009_2024-08-27_aligned_long.png](charts/aligned/0009_2024-08-27_aligned_long.png) |
| 10 | 2024-08-29 | aligned | long | $-27 | long,short | 2 | [0010_2024-08-29_aligned_long.png](charts/aligned/0010_2024-08-29_aligned_long.png) |
| 11 | 2024-08-30 | aligned | long | $74 | long,short | 2 | [0011_2024-08-30_aligned_long.png](charts/aligned/0011_2024-08-30_aligned_long.png) |
| 12 | 2024-08-30 | aligned | long | $-27 | long,short | 2 | [0012_2024-08-30_aligned_long.png](charts/aligned/0012_2024-08-30_aligned_long.png) |