# Would-be winners: broker STOP vs old-pandas Friday

Old pandas **skipped same-day stop checks** after entry (`break` bug).
Broker resting stop fired. Charts show hourly path, prev-day extreme (SL),
broker entry/stop, and old-pandas hold to Friday.

**Prev-day extreme on these charts:** prior NY *calendar date with bars*
(consecutive day-table row). For **Mondays that is often Sunday** (13/41 here),
not Friday — so the red SL line can be a thin weekend session. Wider-SL work
uses prior **weekday session** (Sun→Friday) instead; see
`../eurusd_st_daybias_f30_wide_sl/SUMMARY.md`.

Charting **41** of 41 broker-stop / research-period_end pairs.

| # | Day | Side | Broker $ | Research $ | Chart |
|---:|---|---|---:|---:|---|
| 1 | 2020-06-01 | long | $-31 | $1106 | [001_2020-06-01_long.png](001_2020-06-01_long.png) |
| 2 | 2022-02-08 | short | $-18 | $675 | [002_2022-02-08_short.png](002_2022-02-08_short.png) |
| 3 | 2023-07-10 | long | $-31 | $655 | [003_2023-07-10_long.png](003_2023-07-10_long.png) |
| 4 | 2019-11-04 | short | $-19 | $517 | [004_2019-11-04_short.png](004_2019-11-04_short.png) |
| 5 | 2026-03-02 | short | $-57 | $489 | [005_2026-03-02_short.png](005_2026-03-02_short.png) |
| 6 | 2020-11-04 | long | $-201 | $484 | [006_2020-11-04_long.png](006_2020-11-04_long.png) |
| 7 | 2017-12-04 | short | $-39 | $466 | [007_2017-12-04_short.png](007_2017-12-04_short.png) |
| 8 | 2021-04-05 | long | $-32 | $419 | [008_2021-04-05_long.png](008_2021-04-05_long.png) |
| 9 | 2019-06-03 | long | $-31 | $418 | [009_2019-06-03_long.png](009_2019-06-03_long.png) |
| 10 | 2021-11-15 | short | $-20 | $412 | [010_2021-11-15_short.png](010_2021-11-15_short.png) |
| 11 | 2017-04-05 | short | $-85 | $406 | [011_2017-04-05_short.png](011_2017-04-05_short.png) |
| 12 | 2019-10-15 | long | $-55 | $368 | [012_2019-10-15_long.png](012_2019-10-15_long.png) |
| 13 | 2020-07-13 | long | $-33 | $296 | [013_2020-07-13_long.png](013_2020-07-13_long.png) |
| 14 | 2019-01-15 | short | $-58 | $275 | [014_2019-01-15_short.png](014_2019-01-15_short.png) |
| 15 | 2017-10-09 | long | $-36 | $215 | [015_2017-10-09_long.png](015_2017-10-09_long.png) |
| 16 | 2019-05-07 | long | $-51 | $208 | [016_2019-05-07_long.png](016_2019-05-07_long.png) |
| 17 | 2026-01-01 | short | $-69 | $205 | [017_2026-01-01_short.png](017_2026-01-01_short.png) |
| 18 | 2025-08-05 | long | $-69 | $185 | [018_2025-08-05_long.png](018_2025-08-05_long.png) |
| 19 | 2020-10-07 | long | $-127 | $175 | [019_2020-10-07_long.png](019_2020-10-07_long.png) |
| 20 | 2024-10-08 | short | $-59 | $166 | [020_2024-10-08_short.png](020_2024-10-08_short.png) |
| 21 | 2024-10-14 | short | $-28 | $158 | [021_2024-10-14_short.png](021_2024-10-14_short.png) |
| 22 | 2015-08-07 | long | $-111 | $156 | [022_2015-08-07_long.png](022_2015-08-07_long.png) |
| 23 | 2024-12-09 | short | $-33 | $154 | [023_2024-12-09_short.png](023_2024-12-09_short.png) |
| 24 | 2016-08-05 | short | $-71 | $139 | [024_2016-08-05_short.png](024_2016-08-05_short.png) |
| 25 | 2018-02-01 | long | $-142 | $125 | [025_2018-02-01_long.png](025_2018-02-01_long.png) |
| 26 | 2023-10-06 | long | $-83 | $123 | [026_2023-10-06_long.png](026_2023-10-06_long.png) |
| 27 | 2025-01-02 | short | $-28 | $116 | [027_2025-01-02_short.png](027_2025-01-02_short.png) |
| 28 | 2022-07-14 | long | $-194 | $114 | [028_2022-07-14_long.png](028_2022-07-14_long.png) |
| 29 | 2016-02-10 | long | $-269 | $92 | [029_2016-02-10_long.png](029_2016-02-10_long.png) |
| 30 | 2020-08-14 | long | $-117 | $90 | [030_2020-08-14_long.png](030_2020-08-14_long.png) |
| 31 | 2023-12-07 | short | $-77 | $76 | [031_2023-12-07_short.png](031_2023-12-07_short.png) |
| 32 | 2025-10-03 | short | $-121 | $56 | [032_2025-10-03_short.png](032_2025-10-03_short.png) |
| 33 | 2019-11-01 | long | $-72 | $50 | [033_2019-11-01_long.png](033_2019-11-01_long.png) |
| 34 | 2024-02-08 | long | $-48 | $42 | [034_2024-02-08_long.png](034_2024-02-08_long.png) |
| 35 | 2019-07-12 | long | $-69 | $31 | [035_2019-07-12_long.png](035_2019-07-12_long.png) |
| 36 | 2021-03-12 | long | $-122 | $27 | [036_2021-03-12_long.png](036_2021-03-12_long.png) |
| 37 | 2017-09-01 | short | $-158 | $25 | [037_2017-09-01_short.png](037_2017-09-01_short.png) |
| 38 | 2021-10-08 | long | $-47 | $24 | [038_2021-10-08_long.png](038_2021-10-08_long.png) |
| 39 | 2023-11-10 | long | $-108 | $23 | [039_2023-11-10_long.png](039_2023-11-10_long.png) |
| 40 | 2020-09-04 | short | $-124 | $16 | [040_2020-09-04_short.png](040_2020-09-04_short.png) |
| 41 | 2023-04-17 | short | $-27 | $5 | [041_2023-04-17_short.png](041_2023-04-17_short.png) |
