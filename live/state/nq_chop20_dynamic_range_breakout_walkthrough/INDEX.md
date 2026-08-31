# NQ CHOP20 Dynamic Daily Range Breakout Walkthrough

Daily-bar diagnostic for close-confirmed breakouts from causal CHOP20 range boxes. This is not a broker-like StrategyPlugin replay yet.

## Rules

- Active range updates on every completed daily bar classified as `RANGING` or `COMPRESSED_RANGE`.
- When flat, buy the daily close above the active range high or sell short the daily close below the active range low.
- One campaign at a time; unlimited later attempts are allowed on the same active range until a newer range-like bar updates it.
- Three units: 1 exits at `0.5R`, 1 exits at `1R`, and 1 exits at `4R`, where `R` is the active range width.
- Any remaining units exit when a later daily close returns into/through the breakout side of the range.
- Diagnostic realism: `1` tick adverse slippage on close-entry/cancel/data-end exits, `$1.50` per closed unit, limit targets at target price.

## Headline

| Metric | Value |
|---|---:|
| Trades | 59 |
| Unit exits | 177 |
| Net | $329,247 |
| Closed DD | $-173,404 |
| MTM stress DD | $-251,240 |
| Net / Stress | 1.31 |
| Win rate | 49.2% |
| Profit factor | 1.47 |
| Avg / median trade | $5,580 / $-607 |
| Best / worst trade | $150,283 / $-106,550 |
| Avg / median bars held | 74.0 / 39.0 |

![Equity](equity_curve.png)

## Yearly

| Year | Trades | Net | MTM DD | Win | PF |
|---:|---:|---:|---:|---:|---:|
| 2011 | 6 | $-7,710 | $-16,526 | 16.7% | 0.26 |
| 2013 | 3 | $25,044 | $-6,027 | 66.7% | 14.01 |
| 2014 | 1 | $10,638 | $-7,040 | 100.0% | NA |
| 2015 | 5 | $1,798 | $-38,286 | 40.0% | 1.07 |
| 2016 | 3 | $-12,696 | $-52,454 | 33.3% | 0.51 |
| 2017 | 3 | $40,796 | $-28,074 | 100.0% | NA |
| 2018 | 4 | $-63,580 | $-107,614 | 75.0% | 0.40 |
| 2019 | 4 | $57,292 | $-116,156 | 100.0% | NA |
| 2020 | 6 | $-56,600 | $-109,187 | 16.7% | 0.11 |
| 2021 | 1 | $150,283 | $-89,205 | 100.0% | NA |
| 2022 | 5 | $-145,792 | $-251,240 | 0.0% | 0.00 |
| 2023 | 2 | $111,698 | $-202,149 | 100.0% | NA |
| 2024 | 6 | $129,736 | $-93,556 | 66.7% | 3.16 |
| 2025 | 9 | $58,420 | $-112,700 | 33.3% | 1.48 |
| 2026 | 1 | $29,920 | $-40,396 | 100.0% | NA |

## Exit Mix

| Exit reason | Units | Net |
|---|---:|---:|
| tp_4r | 23 | $584,146 |
| tp_1r | 34 | $288,759 |
| tp_0_5r | 39 | $153,929 |
| data_end | 1 | $6,524 |
| range_close_cancel | 80 | $-704,110 |

## Files

- [trades.csv](trades.csv)
- [unit_exits.csv](unit_exits.csv)
- [active_ranges.csv](active_ranges.csv)
- [equity_curve.csv](equity_curve.csv)
- [yearly_summary.csv](yearly_summary.csv)
- [charts/](charts/)

## Trade Charts

| # | Entry | Dir | Exit | Net | Reason | Chart |
|---:|---|---|---|---:|---|---|
| 1 | 2011-08-02 | short | 2011-10-13 | $2,756 | partial_targets_then_range_cancel | [chart](charts/001_2011-08-02_short_range_2011-08-01_to_2011-10-13.png) |
| 2 | 2011-10-20 | short | 2011-10-21 | $-2,044 | range_close_cancel | [chart](charts/002_2011-10-20_short_range_2011-08-01_to_2011-10-21.png) |
| 3 | 2011-11-01 | short | 2011-11-03 | $-3,844 | range_close_cancel | [chart](charts/003_2011-11-01_short_range_2011-08-01_to_2011-11-03.png) |
| 4 | 2011-11-20 | short | 2011-11-30 | $-607 | partial_targets_then_range_cancel | [chart](charts/004_2011-11-20_short_range_2011-11-18_to_2011-11-30.png) |
| 5 | 2011-12-14 | short | 2011-12-20 | $-2,404 | range_close_cancel | [chart](charts/005_2011-12-14_short_range_2011-11-18_to_2011-12-20.png) |
| 6 | 2011-12-21 | short | 2011-12-22 | $-1,564 | range_close_cancel | [chart](charts/006_2011-12-21_short_range_2011-11-18_to_2011-12-22.png) |
| 7 | 2012-01-18 | long | 2013-07-12 | $17,568 | all_targets | [chart](charts/007_2012-01-18_long_range_2011-11-18_to_2013-07-12.png) |
| 8 | 2013-07-14 | long | 2013-11-14 | $9,400 | all_targets | [chart](charts/008_2013-07-14_long_range_2013-04-09_to_2013-11-14.png) |
| 9 | 2013-11-15 | long | 2013-11-18 | $-1,924 | range_close_cancel | [chart](charts/009_2013-11-15_long_range_2013-11-13_to_2013-11-18.png) |
| 10 | 2013-11-22 | long | 2014-06-24 | $10,638 | all_targets | [chart](charts/010_2013-11-22_long_range_2013-11-13_to_2014-06-24.png) |
| 11 | 2014-06-25 | long | 2015-02-13 | $15,148 | all_targets | [chart](charts/011_2014-06-25_long_range_2014-05-12_to_2015-02-13.png) |
| 12 | 2015-02-15 | long | 2015-08-24 | $-3,177 | partial_targets_then_range_cancel | [chart](charts/012_2015-02-15_long_range_2014-09-30_to_2015-08-24.png) |
| 13 | 2015-08-25 | short | 2015-08-26 | $-15,694 | range_close_cancel | [chart](charts/013_2015-08-25_short_range_2014-09-30_to_2015-08-26.png) |
| 14 | 2015-08-27 | long | 2015-09-28 | $-7,757 | partial_targets_then_range_cancel | [chart](charts/014_2015-08-27_long_range_2014-09-30_to_2015-09-28.png) |
| 15 | 2015-09-30 | long | 2015-10-27 | $13,278 | all_targets | [chart](charts/015_2015-09-30_long_range_2014-09-30_to_2015-10-27.png) |
| 16 | 2015-10-28 | long | 2016-02-05 | $-24,637 | partial_targets_then_range_cancel | [chart](charts/016_2015-10-28_long_range_2014-09-30_to_2016-02-05.png) |
| 17 | 2016-02-08 | short | 2016-02-12 | $-1,337 | partial_targets_then_range_cancel | [chart](charts/017_2016-02-08_short_range_2014-09-30_to_2016-02-12.png) |
| 18 | 2016-02-17 | long | 2016-07-26 | $13,278 | all_targets | [chart](charts/018_2016-02-17_long_range_2014-09-30_to_2016-07-26.png) |
| 19 | 2016-07-27 | long | 2017-02-13 | $14,516 | all_targets | [chart](charts/019_2016-07-27_long_range_2016-05-23_to_2017-02-13.png) |
| 20 | 2017-02-14 | long | 2017-05-16 | $12,426 | all_targets | [chart](charts/020_2017-02-14_long_range_2016-10-12_to_2017-05-16.png) |
| 21 | 2017-05-17 | long | 2017-10-12 | $13,856 | all_targets | [chart](charts/021_2017-05-17_long_range_2017-03-29_to_2017-10-12.png) |
| 22 | 2017-10-13 | long | 2018-01-05 | $14,323 | all_targets | [chart](charts/022_2017-10-13_long_range_2017-09-24_to_2018-01-05.png) |
| 23 | 2018-01-07 | long | 2018-03-13 | $14,323 | all_targets | [chart](charts/023_2018-01-07_long_range_2017-09-24_to_2018-03-13.png) |
| 24 | 2018-03-14 | long | 2018-08-28 | $14,323 | all_targets | [chart](charts/024_2018-03-14_long_range_2017-09-24_to_2018-08-28.png) |
| 25 | 2018-08-29 | long | 2018-12-24 | $-106,550 | range_close_cancel | [chart](charts/025_2018-08-29_long_range_2017-09-24_to_2018-12-24.png) |
| 26 | 2018-12-26 | long | 2019-01-18 | $14,323 | all_targets | [chart](charts/026_2018-12-26_long_range_2017-09-24_to_2019-01-18.png) |
| 27 | 2019-01-20 | long | 2019-03-13 | $14,323 | all_targets | [chart](charts/027_2019-01-20_long_range_2017-09-24_to_2019-03-13.png) |
| 28 | 2019-03-14 | long | 2019-04-23 | $14,323 | all_targets | [chart](charts/028_2019-03-14_long_range_2017-09-24_to_2019-04-23.png) |
| 29 | 2019-04-24 | long | 2019-11-26 | $14,323 | all_targets | [chart](charts/029_2019-04-24_long_range_2017-09-24_to_2019-11-26.png) |
| 30 | 2019-11-27 | long | 2020-03-12 | $-13,102 | partial_targets_then_range_cancel | [chart](charts/030_2019-11-27_long_range_2019-09-04_to_2020-03-12.png) |
| 31 | 2020-03-13 | long | 2020-03-15 | $-16,954 | range_close_cancel | [chart](charts/031_2020-03-13_long_range_2019-09-04_to_2020-03-15.png) |
| 32 | 2020-03-16 | short | 2020-03-18 | $-4,682 | partial_targets_then_range_cancel | [chart](charts/032_2020-03-16_short_range_2019-09-04_to_2020-03-18.png) |
| 33 | 2020-03-19 | short | 2020-03-24 | $7,023 | partial_targets_then_range_cancel | [chart](charts/033_2020-03-19_short_range_2019-09-04_to_2020-03-24.png) |
| 34 | 2020-03-26 | long | 2020-03-27 | $-19,054 | range_close_cancel | [chart](charts/034_2020-03-26_long_range_2019-09-04_to_2020-03-27.png) |
| 35 | 2020-03-30 | long | 2020-03-31 | $-9,830 | range_close_cancel | [chart](charts/035_2020-03-30_long_range_2019-09-04_to_2020-03-31.png) |
| 36 | 2020-04-06 | long | 2021-01-25 | $150,283 | all_targets | [chart](charts/036_2020-04-06_long_range_2020-04-05_to_2021-01-25.png) |
| 37 | 2021-01-26 | long | 2022-06-13 | $-16,144 | partial_targets_then_range_cancel | [chart](charts/037_2021-01-26_long_range_2020-09-30_to_2022-06-13.png) |
| 38 | 2022-06-14 | short | 2022-07-29 | $-92,794 | range_close_cancel | [chart](charts/038_2022-06-14_short_range_2022-03-17_to_2022-07-29.png) |
| 39 | 2022-07-31 | short | 2022-08-01 | $-1,954 | range_close_cancel | [chart](charts/039_2022-07-31_short_range_2022-03-17_to_2022-08-01.png) |
| 40 | 2022-08-02 | short | 2022-08-03 | $-19,894 | range_close_cancel | [chart](charts/040_2022-08-02_short_range_2022-03-17_to_2022-08-03.png) |
| 41 | 2022-08-23 | short | 2022-08-25 | $-15,004 | range_close_cancel | [chart](charts/041_2022-08-23_short_range_2022-03-17_to_2022-08-25.png) |
| 42 | 2022-08-26 | short | 2023-03-26 | $35,666 | partial_targets_then_range_cancel | [chart](charts/042_2022-08-26_short_range_2022-03-17_to_2023-03-26.png) |
| 43 | 2023-03-27 | long | 2023-07-13 | $76,033 | all_targets | [chart](charts/043_2023-03-27_long_range_2023-03-15_to_2023-07-13.png) |
| 44 | 2023-07-14 | long | 2024-02-07 | $58,956 | all_targets | [chart](charts/044_2023-07-14_long_range_2023-04-28_to_2024-02-07.png) |
| 45 | 2024-02-08 | long | 2024-06-17 | $53,593 | all_targets | [chart](charts/045_2024-02-08_long_range_2023-12-10_to_2024-06-17.png) |
| 46 | 2024-06-18 | long | 2024-08-02 | $-14,500 | partial_targets_then_range_cancel | [chart](charts/046_2024-06-18_long_range_2024-04-14_to_2024-08-02.png) |
| 47 | 2024-08-07 | short | 2024-08-08 | $-45,560 | range_close_cancel | [chart](charts/047_2024-08-07_short_range_2024-04-14_to_2024-08-08.png) |
| 48 | 2024-08-13 | long | 2024-09-06 | $4,926 | partial_targets_then_range_cancel | [chart](charts/048_2024-08-13_long_range_2024-04-14_to_2024-09-06.png) |
| 49 | 2024-09-09 | long | 2024-12-04 | $72,320 | all_targets | [chart](charts/049_2024-09-09_long_range_2024-04-14_to_2024-12-04.png) |
| 50 | 2024-12-05 | long | 2025-02-27 | $7,756 | partial_targets_then_range_cancel | [chart](charts/050_2024-12-05_long_range_2024-11-05_to_2025-02-27.png) |
| 51 | 2025-02-28 | long | 2025-03-03 | $-23,630 | range_close_cancel | [chart](charts/051_2025-02-28_long_range_2024-11-05_to_2025-03-03.png) |
| 52 | 2025-03-10 | short | 2025-03-19 | $-43,730 | range_close_cancel | [chart](charts/052_2025-03-10_short_range_2024-11-05_to_2025-03-19.png) |
| 53 | 2025-03-20 | short | 2025-03-23 | $-13,310 | range_close_cancel | [chart](charts/053_2025-03-20_short_range_2024-11-05_to_2025-03-23.png) |
| 54 | 2025-03-27 | short | 2025-04-06 | $85,796 | all_targets | [chart](charts/054_2025-03-27_short_range_2024-11-05_to_2025-04-06.png) |
| 55 | 2025-04-07 | short | 2025-05-02 | $-25,430 | partial_targets_then_range_cancel | [chart](charts/055_2025-04-07_short_range_2024-11-05_to_2025-05-02.png) |
| 56 | 2025-05-05 | short | 2025-05-06 | $-3,620 | range_close_cancel | [chart](charts/056_2025-05-05_short_range_2024-11-05_to_2025-05-06.png) |
| 57 | 2025-05-07 | short | 2025-05-08 | $-11,210 | range_close_cancel | [chart](charts/057_2025-05-07_short_range_2024-11-05_to_2025-05-08.png) |
| 58 | 2025-05-12 | long | 2025-08-13 | $85,796 | all_targets | [chart](charts/058_2025-05-12_long_range_2024-11-05_to_2025-08-13.png) |
| 59 | 2025-08-14 | long | 2026-03-08 | $29,920 | data_end | [chart](charts/059_2025-08-14_long_range_2024-11-05_to_2026-03-08.png) |

## Causality Notes

- The range state and active range high/low are known only after each completed daily candle.
- The strategy only enters on a later daily close outside the active range.
- Daily highs/lows are used to model resting target fills after entry; same-day target sequencing inside a daily bar is not tick-proven.
- A production version should re-run this through 1m or tick data before promotion.
