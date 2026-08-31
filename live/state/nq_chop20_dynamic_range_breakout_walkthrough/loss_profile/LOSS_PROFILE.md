# NQ CHOP20 Dynamic Range Loss Profile

Loss anatomy for the daily close-confirmed CHOP20 range breakout walkthrough.

## Base Loss Profile

| Metric | Value |
|---|---:|
| Base trades | 59 |
| Base net | $329,247 |
| Base MTM stress DD | $-251,240 |
| Base Net / Stress | 1.31 |
| Losing trades | 30 |
| Losing-trade net | $-561,942 |
| Winning-trade net | $891,190 |
| Losers that first moved at least 0.5R favorably | 10 |
| Losers that first moved at least 1R favorably | 5 |

## What The Losses Say

- The raw rule is not symmetric on NQ: long breakouts carried the book, while short breakouts were the major drag.
- The largest loss bucket is not failed targets; it is the close-back-inside exit waiting too long before admitting the breakout failed.
- A meaningful number of losing campaigns had useful favorable movement first, so stop-to-breakeven after the first partial is worth testing on intraday data.
- Some entries fire from stale range references long after the range was formed. That can create huge breakout gaps and poor invalidation geometry.

## By Direction

| Bucket | Trades | Losers | Net | Win | Worst | Median Age | Median Gap | Median MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| long | 37 | 12 | $502,691 | 67.6% | $-106,550 | 104.0 | 1.46R | -1.02R |
| short | 22 | 18 | $-173,444 | 18.2% | $-92,794 | 116.5 | 0.15R | -0.40R |

## By Exit Reason

| Bucket | Trades | Losers | Net | Win | Worst | Median Age | Median Gap | Median MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all_targets | 23 | 0 | $803,144 | 100.0% | $9,400 | 88.0 | 1.43R | -0.50R |
| data_end | 1 | 0 | $29,920 | 100.0% | $29,920 | 241.0 | 3.97R | -1.11R |
| partial_targets_then_range_cancel | 15 | 10 | $-53,248 | 33.3% | $-25,430 | 117.0 | 0.85R | -1.18R |
| range_close_cancel | 20 | 20 | $-450,570 | 0.0% | $-106,550 | 115.5 | 0.13R | -0.44R |

## By Range Age

| Bucket | Trades | Losers | Net | Win | Worst | Median Age | Median Gap | Median MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0-5 | 4 | 2 | $150,507 | 50.0% | $-1,924 | 1.0 | 0.09R | -0.37R |
| 6-20 | 3 | 0 | $100,994 | 100.0% | $10,638 | 10.0 | 0.49R | -0.27R |
| 21-60 | 9 | 3 | $103,967 | 66.7% | $-14,500 | 41.0 | 1.18R | -0.95R |
| 61-126 | 18 | 12 | $-93,358 | 33.3% | $-92,794 | 99.0 | 0.76R | -0.92R |
| 127-252 | 14 | 8 | $139,264 | 42.9% | $-25,430 | 158.0 | 0.20R | -0.57R |
| 253+ | 11 | 5 | $-72,127 | 54.5% | $-106,550 | 390.0 | 1.84R | -1.59R |

## By Breakout Gap

| Bucket | Trades | Losers | Net | Win | Worst | Median Age | Median Gap | Median MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| <=0.10R | 12 | 8 | $255,158 | 33.3% | $-19,894 | 119.5 | 0.05R | -0.18R |
| 0.10-0.25R | 11 | 8 | $23,148 | 27.3% | $-23,630 | 79.0 | 0.15R | -0.39R |
| 0.25-0.50R | 8 | 4 | $64,726 | 50.0% | $-45,560 | 167.5 | 0.34R | -0.83R |
| 0.50-1.00R | 5 | 1 | $-3,448 | 80.0% | $-43,730 | 104.0 | 0.73R | -1.08R |
| >1.00R | 23 | 9 | $-10,338 | 60.9% | $-106,550 | 105.0 | 2.88R | -2.06R |

## Structure Sweep

| Variant | Trades | Net | MTM DD | Net/Stress | Win | PF | Worst | Long Net | Short Net |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `touch_broken_boundary_runner_2r_max_age_60` | 119 | $594,062 | $-61,155 | 9.71 | 35.3% | 2.76 | $-27,814 | $502,445 | $91,617 |
| `touch_broken_boundary_max_age_60` | 75 | $483,732 | $-57,100 | 8.47 | 36.0% | 2.94 | $-27,814 | $410,632 | $73,100 |
| `touch_broken_boundary_max_age_60_long_only` | 46 | $392,148 | $-57,100 | 6.87 | 41.3% | 3.48 | $-25,504 | $392,148 | $0 |
| `base_max_age_60` | 58 | $474,932 | $-71,964 | 6.60 | 41.4% | 2.73 | $-34,130 | $366,850 | $108,082 |
| `base_max_age_60_long_only` | 36 | $342,260 | $-63,442 | 5.39 | 41.7% | 2.87 | $-34,130 | $342,260 | $0 |
| `touch_broken_boundary_long_only` | 56 | $523,198 | $-108,610 | 4.82 | 57.1% | 2.50 | $-99,004 | $523,198 | $0 |
| `base_long_only` | 37 | $511,726 | $-116,156 | 4.41 | 70.3% | 2.47 | $-106,550 | $511,726 | $0 |
| `touch_broken_boundary_runner_2r` | 134 | $644,164 | $-166,384 | 3.87 | 47.8% | 1.70 | $-121,204 | $641,460 | $2,705 |

## More Sensible Next Structures

1. Treat the breakout boundary as a real stop zone, not only a close-cancel line. The daily diagnostic strongly dislikes waiting for a daily close after the breakout has already failed.
2. Separate long and short logic. The long side deserves further testing; the short side needs an additional regime filter or a different exit shape before it should be trusted.
3. Add a freshness rule. Very old ranges can still be visually meaningful, but the current unlimited-memory version creates stale geometry and oversized failed-breakout losses.
4. Test stop-to-breakeven after the 0.5R partial on 1m/tick data. It addresses the exact loser class where the trade worked briefly, then reversed.
5. Prefer the next serious pass on 4h/1h or 1m bars. Daily OHLC cannot prove target/stop sequencing, especially when a boundary stop and a target are both touched in the same daily candle.

## Worst Losses

| Trade | Entry | Dir | Exit | Net | Age | Gap | MFE | MAE | Reason |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| 25 | 2018-08-29 | long | 2018-12-24 | $-106,550 | 288 | 12.66R | 0.45R | -13.67R | range_close_cancel |
| 38 | 2022-06-14 | short | 2022-07-29 | $-92,794 | 75 | 1.04R | 0.25R | -1.09R | range_close_cancel |
| 47 | 2024-08-07 | short | 2024-08-08 | $-45,560 | 99 | 0.32R | 0.03R | -1.18R | range_close_cancel |
| 52 | 2025-03-10 | short | 2025-03-19 | $-43,730 | 107 | 0.90R | 0.21R | -1.08R | range_close_cancel |
| 55 | 2025-04-07 | short | 2025-05-02 | $-25,430 | 131 | 2.88R | 1.32R | -3.22R | partial_targets_then_range_cancel |
| 16 | 2015-10-28 | long | 2016-02-05 | $-24,637 | 336 | 4.53R | 0.61R | -5.65R | partial_targets_then_range_cancel |
| 51 | 2025-02-28 | long | 2025-03-03 | $-23,630 | 99 | 0.15R | 0.27R | -0.76R | range_close_cancel |
| 40 | 2022-08-02 | short | 2022-08-03 | $-19,894 | 117 | 0.03R | 0.02R | -0.28R | range_close_cancel |
| 34 | 2020-03-26 | long | 2020-03-27 | $-19,054 | 175 | 0.20R | 0.03R | -0.75R | range_close_cancel |
| 31 | 2020-03-13 | long | 2020-03-15 | $-16,954 | 164 | 0.08R | 0.22R | -0.65R | range_close_cancel |

## Files

- [loss_trades.csv](loss_trades.csv)
- [loss_by_direction.csv](loss_by_direction.csv)
- [loss_by_exit_reason.csv](loss_by_exit_reason.csv)
- [loss_by_attempt.csv](loss_by_attempt.csv)
- [loss_by_range_age.csv](loss_by_range_age.csv)
- [loss_by_breakout_gap.csv](loss_by_breakout_gap.csv)
- [loss_by_width_quartile.csv](loss_by_width_quartile.csv)
- [structure_sweep.csv](structure_sweep.csv)
- [worst_losses.csv](worst_losses.csv)

## Caution

The sweep is still daily-resolution. Variants with touch stops are directionally useful because they show whether tighter invalidation helps, but they require 1m/tick replay before ranking.
