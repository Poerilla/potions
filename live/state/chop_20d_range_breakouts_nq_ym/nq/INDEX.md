# NQ CHOP20 Range Breakouts

Causal daily detector using completed candles only. Each contiguous confirmed range segment freezes its final 20-day high/low after the segment's final close. The first later daily close outside that frozen box is the breakout.

## Summary

| Metric | Value |
|---|---:|
| Coverage | 2010-06-06 to 2026-03-08 |
| Daily bars | 4,887 |
| Confirmed range-like days | 153 |
| Range segments | 38 |
| Breakouts charted | 37 |
| Expired/no-break segments | 1 |
| Up / down breakouts | 23 / 14 |
| Median range length | 3.0 trading days |
| Median wait to breakout | 1.0 trading days |
| Avg forward 20d close change | 57.24 pts |
| Avg forward 60d close change | 445.83 pts |
| Avg forward 252d close change | 1,277.06 pts |

## Files

- [daily_regimes.csv](daily_regimes.csv)
- [range_segments.csv](range_segments.csv)
- [range_breakouts.csv](range_breakouts.csv)
- [expired_ranges.csv](expired_ranges.csv)
- [charts/](charts/)

## Breakout Charts

| # | Breakout | Dir | Range End | Wait | Chart |
|---:|---|---|---|---:|---|
| 1 | 2011-08-02 | down | 2011-08-01 | 1 | [chart](charts/001_2011-08-02_down_range_2011-07-29_to_2011-08-01.png) |
| 2 | 2011-11-20 | down | 2011-11-18 | 1 | [chart](charts/002_2011-11-20_down_range_2011-11-03_to_2011-11-18.png) |
| 3 | 2012-07-03 | up | 2012-07-02 | 1 | [chart](charts/003_2012-07-03_up_range_2012-07-01_to_2012-07-02.png) |
| 4 | 2012-12-28 | down | 2012-12-21 | 5 | [chart](charts/004_2012-12-28_down_range_2012-12-18_to_2012-12-21.png) |
| 5 | 2013-02-19 | up | 2013-02-18 | 1 | [chart](charts/005_2013-02-19_up_range_2013-01-27_to_2013-02-18.png) |
| 6 | 2013-04-10 | up | 2013-04-09 | 1 | [chart](charts/006_2013-04-10_up_range_2013-03-26_to_2013-04-09.png) |
| 7 | 2013-09-09 | up | 2013-09-08 | 1 | [chart](charts/007_2013-09-09_up_range_2013-08-28_to_2013-09-08.png) |
| 8 | 2013-10-09 | down | 2013-10-07 | 2 | [chart](charts/008_2013-10-09_down_range_2013-10-04_to_2013-10-07.png) |
| 9 | 2013-11-14 | up | 2013-11-13 | 1 | [chart](charts/009_2013-11-14_up_range_2013-11-13_to_2013-11-13.png) |
| 10 | 2014-03-16 | down | 2014-03-14 | 1 | [chart](charts/010_2014-03-16_down_range_2014-03-11_to_2014-03-14.png) |
| 11 | 2014-05-21 | up | 2014-05-12 | 8 | [chart](charts/011_2014-05-21_up_range_2014-05-11_to_2014-05-12.png) |
| 12 | 2014-10-01 | down | 2014-09-30 | 1 | [chart](charts/012_2014-10-01_down_range_2014-09-28_to_2014-09-30.png) |
| 13 | 2016-04-26 | down | 2016-04-25 | 1 | [chart](charts/013_2016-04-26_down_range_2016-04-22_to_2016-04-25.png) |
| 14 | 2016-05-24 | up | 2016-05-23 | 1 | [chart](charts/014_2016-05-24_up_range_2016-05-20_to_2016-05-23.png) |
| 15 | 2016-09-09 | down | 2016-09-08 | 1 | [chart](charts/015_2016-09-09_down_range_2016-08-30_to_2016-09-08.png) |
| 16 | 2016-10-24 | up | 2016-10-12 | 10 | [chart](charts/016_2016-10-24_up_range_2016-10-10_to_2016-10-12.png) |
| 17 | 2017-04-04 | up | 2017-03-29 | 5 | [chart](charts/017_2017-04-04_up_range_2017-03-29_to_2017-03-29.png) |
| 18 | 2017-09-25 | down | 2017-09-24 | 1 | [chart](charts/018_2017-09-25_down_range_2017-09-22_to_2017-09-24.png) |
| 19 | 2019-09-05 | up | 2019-08-27 | 8 | [chart](charts/019_2019-09-05_up_range_2019-08-27_to_2019-08-27.png) |
| 20 | 2019-09-05 | up | 2019-09-04 | 1 | [chart](charts/020_2019-09-05_up_range_2019-08-30_to_2019-09-04.png) |
| 21 | 2020-04-06 | up | 2020-04-05 | 1 | [chart](charts/021_2020-04-06_up_range_2020-04-03_to_2020-04-05.png) |
| 22 | 2020-08-04 | up | 2020-08-02 | 2 | [chart](charts/022_2020-08-04_up_range_2020-07-31_to_2020-08-02.png) |
| 23 | 2020-10-08 | up | 2020-09-30 | 7 | [chart](charts/023_2020-10-08_up_range_2020-09-29_to_2020-09-30.png) |
| 24 | 2021-05-04 | down | 2021-05-03 | 1 | [chart](charts/024_2021-05-04_down_range_2021-05-02_to_2021-05-03.png) |
| 25 | 2021-08-23 | up | 2021-08-20 | 2 | [chart](charts/025_2021-08-23_up_range_2021-08-15_to_2021-08-20.png) |
| 26 | 2021-12-27 | up | 2021-12-26 | 1 | [chart](charts/026_2021-12-27_up_range_2021-12-16_to_2021-12-26.png) |
| 27 | 2022-03-18 | up | 2022-03-17 | 1 | [chart](charts/027_2022-03-18_up_range_2022-03-14_to_2022-03-17.png) |
| 28 | 2023-03-16 | up | 2023-03-15 | 1 | [chart](charts/028_2023-03-16_up_range_2023-03-15_to_2023-03-15.png) |
| 29 | 2023-05-10 | up | 2023-04-24 | 14 | [chart](charts/029_2023-05-10_up_range_2023-04-23_to_2023-04-24.png) |
| 30 | 2023-05-08 | up | 2023-04-28 | 8 | [chart](charts/030_2023-05-08_up_range_2023-04-28_to_2023-04-28.png) |
| 31 | 2023-12-11 | up | 2023-12-10 | 1 | [chart](charts/031_2023-12-11_up_range_2023-12-08_to_2023-12-10.png) |
| 32 | 2024-03-31 | up | 2024-03-20 | 8 | [chart](charts/032_2024-03-31_up_range_2024-03-18_to_2024-03-20.png) |
| 33 | 2024-04-15 | down | 2024-04-05 | 8 | [chart](charts/033_2024-04-15_down_range_2024-04-05_to_2024-04-05.png) |
| 34 | 2024-04-15 | down | 2024-04-14 | 1 | [chart](charts/034_2024-04-15_down_range_2024-04-11_to_2024-04-14.png) |
| 35 | 2024-11-06 | up | 2024-11-05 | 1 | [chart](charts/035_2024-11-06_up_range_2024-11-01_to_2024-11-05.png) |
| 36 | 2026-01-20 | down | 2026-01-19 | 1 | [chart](charts/036_2026-01-20_down_range_2026-01-19_to_2026-01-19.png) |
| 37 | 2026-03-08 | down | 2026-02-27 | 7 | [chart](charts/037_2026-03-08_down_range_2026-02-27_to_2026-02-27.png) |
