# YM CHOP20 Range Breakouts

Causal daily detector using completed candles only. Each contiguous confirmed range segment freezes its final 20-day high/low after the segment's final close. The first later daily close outside that frozen box is the breakout.

## Summary

| Metric | Value |
|---|---:|
| Coverage | 2010-06-06 to 2026-05-06 |
| Daily bars | 4,942 |
| Confirmed range-like days | 181 |
| Range segments | 41 |
| Breakouts charted | 41 |
| Expired/no-break segments | 0 |
| Up / down breakouts | 28 / 13 |
| Median range length | 3.0 trading days |
| Median wait to breakout | 1.0 trading days |
| Avg forward 20d close change | 290.24 pts |
| Avg forward 60d close change | 416.68 pts |
| Avg forward 252d close change | 2,236.61 pts |

## Files

- [daily_regimes.csv](daily_regimes.csv)
- [range_segments.csv](range_segments.csv)
- [range_breakouts.csv](range_breakouts.csv)
- [expired_ranges.csv](expired_ranges.csv)
- [charts/](charts/)

## Breakout Charts

| # | Breakout | Dir | Range End | Wait | Chart |
|---:|---|---|---|---:|---|
| 1 | 2011-06-30 | up | 2011-06-29 | 1 | [chart](charts/001_2011-06-30_up_range_2011-06-28_to_2011-06-29.png) |
| 2 | 2011-11-21 | down | 2011-11-20 | 1 | [chart](charts/002_2011-11-21_down_range_2011-11-15_to_2011-11-20.png) |
| 3 | 2012-03-13 | up | 2012-03-08 | 4 | [chart](charts/003_2012-03-13_up_range_2012-03-07_to_2012-03-08.png) |
| 4 | 2012-04-06 | down | 2012-04-05 | 1 | [chart](charts/004_2012-04-06_down_range_2012-04-05_to_2012-04-05.png) |
| 5 | 2012-07-03 | up | 2012-07-01 | 2 | [chart](charts/005_2012-07-03_up_range_2012-07-01_to_2012-07-01.png) |
| 6 | 2012-10-10 | down | 2012-10-07 | 3 | [chart](charts/006_2012-10-10_down_range_2012-10-05_to_2012-10-07.png) |
| 7 | 2013-02-25 | down | 2013-02-24 | 1 | [chart](charts/007_2013-02-25_down_range_2013-02-19_to_2013-02-24.png) |
| 8 | 2013-04-02 | up | 2013-04-01 | 1 | [chart](charts/008_2013-04-02_up_range_2013-03-31_to_2013-04-01.png) |
| 9 | 2013-04-10 | up | 2013-04-08 | 2 | [chart](charts/009_2013-04-10_up_range_2013-04-04_to_2013-04-08.png) |
| 10 | 2013-08-14 | down | 2013-08-11 | 3 | [chart](charts/010_2013-08-14_down_range_2013-08-06_to_2013-08-11.png) |
| 11 | 2014-05-12 | up | 2014-05-11 | 1 | [chart](charts/011_2014-05-12_up_range_2014-05-11_to_2014-05-11.png) |
| 12 | 2014-09-18 | up | 2014-09-17 | 1 | [chart](charts/012_2014-09-18_up_range_2014-09-14_to_2014-09-17.png) |
| 13 | 2015-02-12 | up | 2015-02-01 | 10 | [chart](charts/013_2015-02-12_up_range_2015-01-25_to_2015-02-01.png) |
| 14 | 2015-05-10 | up | 2015-04-01 | 33 | [chart](charts/014_2015-05-10_up_range_2015-04-01_to_2015-04-01.png) |
| 15 | 2015-05-14 | up | 2015-05-13 | 1 | [chart](charts/015_2015-05-14_up_range_2015-04-30_to_2015-05-13.png) |
| 16 | 2015-12-11 | down | 2015-12-10 | 1 | [chart](charts/016_2015-12-11_down_range_2015-12-10_to_2015-12-10.png) |
| 17 | 2016-11-03 | down | 2016-10-23 | 10 | [chart](charts/017_2016-11-03_down_range_2016-10-03_to_2016-10-23.png) |
| 18 | 2016-11-03 | down | 2016-10-26 | 7 | [chart](charts/018_2016-11-03_down_range_2016-10-26_to_2016-10-26.png) |
| 19 | 2016-11-08 | up | 2016-11-07 | 1 | [chart](charts/019_2016-11-08_up_range_2016-11-03_to_2016-11-07.png) |
| 20 | 2017-01-25 | up | 2017-01-24 | 1 | [chart](charts/020_2017-01-25_up_range_2017-01-05_to_2017-01-24.png) |
| 21 | 2017-11-28 | up | 2017-11-24 | 3 | [chart](charts/021_2017-11-28_up_range_2017-11-14_to_2017-11-24.png) |
| 22 | 2018-04-17 | up | 2018-04-16 | 1 | [chart](charts/022_2018-04-17_up_range_2018-04-16_to_2018-04-16.png) |
| 23 | 2019-09-05 | up | 2019-09-01 | 4 | [chart](charts/023_2019-09-05_up_range_2019-08-27_to_2019-09-01.png) |
| 24 | 2019-10-01 | down | 2019-09-30 | 1 | [chart](charts/024_2019-10-01_down_range_2019-09-30_to_2019-09-30.png) |
| 25 | 2020-05-26 | up | 2020-05-04 | 19 | [chart](charts/025_2020-05-26_up_range_2020-05-04_to_2020-05-04.png) |
| 26 | 2020-07-14 | up | 2020-07-12 | 2 | [chart](charts/026_2020-07-14_up_range_2020-07-12_to_2020-07-12.png) |
| 27 | 2020-08-05 | up | 2020-08-04 | 1 | [chart](charts/027_2020-08-05_up_range_2020-08-04_to_2020-08-04.png) |
| 28 | 2020-12-28 | up | 2020-12-27 | 1 | [chart](charts/028_2020-12-28_up_range_2020-12-17_to_2020-12-27.png) |
| 29 | 2021-05-06 | up | 2021-05-05 | 1 | [chart](charts/029_2021-05-06_up_range_2021-05-03_to_2021-05-05.png) |
| 30 | 2021-10-15 | up | 2021-10-07 | 7 | [chart](charts/030_2021-10-15_up_range_2021-10-07_to_2021-10-07.png) |
| 31 | 2021-10-15 | up | 2021-10-12 | 3 | [chart](charts/031_2021-10-15_up_range_2021-10-12_to_2021-10-12.png) |
| 32 | 2022-03-18 | up | 2022-03-17 | 1 | [chart](charts/032_2022-03-18_up_range_2022-03-15_to_2022-03-17.png) |
| 33 | 2022-10-18 | up | 2022-10-17 | 1 | [chart](charts/033_2022-10-18_up_range_2022-10-16_to_2022-10-17.png) |
| 34 | 2023-02-21 | down | 2023-02-20 | 1 | [chart](charts/034_2023-02-21_down_range_2023-02-14_to_2023-02-20.png) |
| 35 | 2023-08-16 | down | 2023-08-15 | 1 | [chart](charts/035_2023-08-16_down_range_2023-08-11_to_2023-08-15.png) |
| 36 | 2024-01-22 | up | 2024-01-21 | 1 | [chart](charts/036_2024-01-22_up_range_2024-01-09_to_2024-01-21.png) |
| 37 | 2024-02-22 | up | 2024-02-21 | 1 | [chart](charts/037_2024-02-22_up_range_2024-02-19_to_2024-02-21.png) |
| 38 | 2025-02-21 | down | 2025-02-20 | 1 | [chart](charts/038_2025-02-21_down_range_2025-02-14_to_2025-02-20.png) |
| 39 | 2025-06-24 | up | 2025-06-23 | 1 | [chart](charts/039_2025-06-24_up_range_2025-06-18_to_2025-06-23.png) |
| 40 | 2025-08-01 | down | 2025-07-23 | 8 | [chart](charts/040_2025-08-01_down_range_2025-07-23_to_2025-07-23.png) |
| 41 | 2026-02-10 | up | 2026-02-09 | 1 | [chart](charts/041_2026-02-10_up_range_2026-01-27_to_2026-02-09.png) |
