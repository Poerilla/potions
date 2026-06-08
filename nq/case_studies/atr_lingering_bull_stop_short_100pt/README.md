# NQ Lingering Bullish ATR Stop Short Study

Short-only first pass.

Rules:
- Daily ATR Supertrend-style stop: ATR(14) x 3.
- On bullish-to-bearish ATR flip, extend the prior bullish ATR stop for 3 week(s).
- While the ATR trend remains bearish, wait for the first red daily candle that closes below that lingering line.
- After that signal close, place a sell limit at the lingering line on subsequent daily bars.
- Entry size: 1 contract. Target: 100 points. Intraday point stop: 100 points.
- Also exit at the next daily open after a daily close back above the lingering line.
- If stop and target are both inside the same daily bar, the model uses stop-first ordering.
- Fill-bar ordering is conservative: if the day opens below the sell limit and only later rallies into the limit, same-day target touches are ignored because the low may have printed before the fill.

Causality note: no same-day signal fill is allowed. The sell limit becomes live on the session after the signal candle closes.

## Results

Lingering lines found: 76  ·  Filled trades: 73  ·  Wins: 17  ·  Losses: 56  ·  Win rate: 23.3%  ·  Profit factor: 0.70
Net: -712.87 pts ($-14,257)
Closed-trade max DD: -1054.44 pts ($-21,089)
Worst MAE: -510.56 pts ($-10,211)  ·  Avg MAE: -60.86 pts ($-1,217)

## Audit Status

| Status | Count |
|---|---:|
| filled | 73 |
| limit_not_filled | 3 |

## Exit Reasons

| Exit Reason | Count |
|---|---:|
| Close-Over-Line-Next-Open | 43 |
| Point-Stop | 13 |
| Target | 17 |

## Charts

| Trade | Fill Date | Result | Net Pts | MAE Pts | Exit | Chart |
|---:|---|---|---:|---:|---|---|
| 1 | 2010-06-27 | Win | +100.00 | -9.61 | Target | [001_2010-06-27_win.png](charts/winners/001_2010-06-27_win.png) |
| 2 | 2010-08-16 | Loss | -20.19 | -40.19 | Close-Over-Line-Next-Open | [002_2010-08-16_loss.png](charts/losers/002_2010-08-16_loss.png) |
| 3 | 2010-11-17 | Loss | -29.58 | -38.33 | Close-Over-Line-Next-Open | [003_2010-11-17_loss.png](charts/losers/003_2010-11-17_loss.png) |
| 4 | 2011-01-31 | Loss | -22.77 | -24.02 | Close-Over-Line-Next-Open | [004_2011-01-31_loss.png](charts/losers/004_2011-01-31_loss.png) |
| 5 | 2011-02-23 | Loss | -15.07 | -20.07 | Close-Over-Line-Next-Open | [005_2011-02-23_loss.png](charts/losers/005_2011-02-23_loss.png) |
| 6 | 2011-05-17 | Loss | -9.32 | -13.07 | Close-Over-Line-Next-Open | [006_2011-05-17_loss.png](charts/losers/006_2011-05-17_loss.png) |
| 7 | 2011-08-04 | Win | +100.00 | -3.96 | Target | [007_2011-08-04_win.png](charts/winners/007_2011-08-04_win.png) |
| 8 | 2011-10-03 | Win | +100.00 | -7.93 | Target | [008_2011-10-03_win.png](charts/winners/008_2011-10-03_win.png) |
| 9 | 2011-11-29 | Loss | -57.77 | -60.77 | Close-Over-Line-Next-Open | [009_2011-11-29_loss.png](charts/losers/009_2011-11-29_loss.png) |
| 10 | 2012-04-11 | Loss | -4.22 | -19.72 | Close-Over-Line-Next-Open | [010_2012-04-11_loss.png](charts/losers/010_2012-04-11_loss.png) |
| 11 | 2012-07-25 | Loss | -12.47 | -28.47 | Close-Over-Line-Next-Open | [011_2012-07-25_loss.png](charts/losers/011_2012-07-25_loss.png) |
| 12 | 2012-09-27 | Loss | -29.56 | -34.81 | Close-Over-Line-Next-Open | [012_2012-09-27_loss.png](charts/losers/012_2012-09-27_loss.png) |
| 13 | 2012-12-31 | Loss | -90.62 | -69.37 | Close-Over-Line-Next-Open | [013_2012-12-31_loss.png](charts/losers/013_2012-12-31_loss.png) |
| 14 | 2013-04-19 | Loss | -12.01 | -19.01 | Close-Over-Line-Next-Open | [014_2013-04-19_loss.png](charts/losers/014_2013-04-19_loss.png) |
| 15 | 2013-06-06 | Loss | -3.10 | -9.60 | Close-Over-Line-Next-Open | [015_2013-06-06_loss.png](charts/losers/015_2013-06-06_loss.png) |
| 16 | 2013-08-22 | Loss | -46.15 | -46.90 | Close-Over-Line-Next-Open | [016_2013-08-22_loss.png](charts/losers/016_2013-08-22_loss.png) |
| 17 | 2013-10-10 | Loss | -48.38 | -66.88 | Close-Over-Line-Next-Open | [017_2013-10-10_loss.png](charts/losers/017_2013-10-10_loss.png) |
| 18 | 2014-01-29 | Loss | -1.62 | -11.12 | Close-Over-Line-Next-Open | [018_2014-01-29_loss.png](charts/losers/018_2014-01-29_loss.png) |
| 19 | 2014-03-31 | Loss | -39.85 | -43.10 | Close-Over-Line-Next-Open | [019_2014-03-31_loss.png](charts/losers/019_2014-03-31_loss.png) |
| 20 | 2014-08-03 | Loss | -2.40 | -5.65 | Close-Over-Line-Next-Open | [020_2014-08-03_loss.png](charts/losers/020_2014-08-03_loss.png) |
| 21 | 2014-10-03 | Loss | -5.90 | -22.90 | Close-Over-Line-Next-Open | [021_2014-10-03_loss.png](charts/losers/021_2014-10-03_loss.png) |
| 22 | 2014-12-15 | Win | +100.00 | -9.00 | Target | [022_2014-12-15_win.png](charts/winners/022_2014-12-15_win.png) |
| 23 | 2015-01-08 | Loss | -46.15 | -56.15 | Close-Over-Line-Next-Open | [023_2015-01-08_loss.png](charts/losers/023_2015-01-08_loss.png) |
| 24 | 2015-03-16 | Loss | -2.01 | -15.51 | Close-Over-Line-Next-Open | [024_2015-03-16_loss.png](charts/losers/024_2015-03-16_loss.png) |
| 25 | 2015-03-27 | Loss | -4.93 | -10.93 | Close-Over-Line-Next-Open | [025_2015-03-27_loss.png](charts/losers/025_2015-03-27_loss.png) |
| 26 | 2015-05-07 | Loss | -6.23 | -11.23 | Close-Over-Line-Next-Open | [026_2015-05-07_loss.png](charts/losers/026_2015-05-07_loss.png) |
| 27 | 2015-06-30 | Loss | -14.73 | -35.98 | Close-Over-Line-Next-Open | [027_2015-06-30_loss.png](charts/losers/027_2015-06-30_loss.png) |
| 28 | 2015-08-20 | Win | +100.00 | -5.95 | Target | [028_2015-08-20_win.png](charts/winners/028_2015-08-20_win.png) |
| 29 | 2015-09-29 | Loss | -13.60 | -25.85 | Close-Over-Line-Next-Open | [029_2015-09-29_loss.png](charts/losers/029_2015-09-29_loss.png) |
| 30 | 2015-11-16 | Loss | -18.24 | -24.24 | Close-Over-Line-Next-Open | [030_2015-11-16_loss.png](charts/losers/030_2015-11-16_loss.png) |
| 31 | 2015-12-14 | Loss | -9.44 | -13.94 | Close-Over-Line-Next-Open | [031_2015-12-14_loss.png](charts/losers/031_2015-12-14_loss.png) |
| 32 | 2016-05-10 | Loss | -8.14 | -13.89 | Close-Over-Line-Next-Open | [032_2016-05-10_loss.png](charts/losers/032_2016-05-10_loss.png) |
| 33 | 2016-06-20 | Loss | -11.30 | -33.55 | Close-Over-Line-Next-Open | [033_2016-06-20_loss.png](charts/losers/033_2016-06-20_loss.png) |
| 34 | 2016-09-12 | Loss | -27.83 | -37.83 | Close-Over-Line-Next-Open | [034_2016-09-12_loss.png](charts/losers/034_2016-09-12_loss.png) |
| 35 | 2016-11-02 | Win | +100.00 | -3.51 | Target | [035_2016-11-02_win.png](charts/winners/035_2016-11-02_win.png) |
| 36 | 2017-05-18 | Loss | -16.80 | -33.05 | Close-Over-Line-Next-Open | [036_2017-05-18_loss.png](charts/losers/036_2017-05-18_loss.png) |
| 37 | 2017-06-14 | Win | +100.00 | -16.34 | Target | [037_2017-06-14_win.png](charts/winners/037_2017-06-14_win.png) |
| 38 | 2017-08-11 | Loss | -41.73 | -50.23 | Close-Over-Line-Next-Open | [038_2017-08-11_loss.png](charts/losers/038_2017-08-11_loss.png) |
| 39 | 2017-12-05 | Loss | -15.22 | -51.72 | Close-Over-Line-Next-Open | [039_2017-12-05_loss.png](charts/losers/039_2017-12-05_loss.png) |
| 40 | 2018-03-27 | Win | +100.00 | -31.51 | Target | [040_2018-03-27_win.png](charts/winners/040_2018-03-27_win.png) |
| 41 | 2018-06-26 | Loss | -41.71 | -66.96 | Close-Over-Line-Next-Open | [041_2018-06-26_loss.png](charts/losers/041_2018-06-26_loss.png) |
| 42 | 2018-09-07 | Loss | -35.68 | -42.68 | Close-Over-Line-Next-Open | [042_2018-09-07_loss.png](charts/losers/042_2018-09-07_loss.png) |
| 43 | 2018-10-07 | Win | +100.00 | -2.61 | Target | [043_2018-10-07_win.png](charts/winners/043_2018-10-07_win.png) |
| 44 | 2018-12-10 | Loss | -31.58 | -66.08 | Close-Over-Line-Next-Open | [044_2018-12-10_loss.png](charts/losers/044_2018-12-10_loss.png) |
| 45 | 2019-05-10 | Win | +100.00 | -11.02 | Target | [045_2019-05-10_win.png](charts/winners/045_2019-05-10_win.png) |
| 46 | 2019-08-13 | Win | +100.00 | -18.30 | Target | [046_2019-08-13_win.png](charts/winners/046_2019-08-13_win.png) |
| 47 | 2019-10-03 | Loss | -62.13 | -80.13 | Close-Over-Line-Next-Open | [047_2019-10-03_loss.png](charts/losers/047_2019-10-03_loss.png) |
| 48 | 2020-09-04 | Win | +100.00 | -87.16 | Target | [048_2020-09-04_win.png](charts/winners/048_2020-09-04_win.png) |
| 49 | 2020-10-29 | Loss | -100.00 | -106.11 | Point-Stop | [049_2020-10-29_loss.png](charts/losers/049_2020-10-29_loss.png) |
| 50 | 2021-02-01 | Loss | -100.00 | -328.54 | Point-Stop | [050_2021-02-01_loss.png](charts/losers/050_2021-02-01_loss.png) |
| 51 | 2021-02-23 | Win | +100.00 | -37.13 | Target | [051_2021-02-23_win.png](charts/winners/051_2021-02-23_win.png) |
| 52 | 2021-05-14 | Win | +100.00 | -26.80 | Target | [052_2021-05-14_win.png](charts/winners/052_2021-05-14_win.png) |
| 53 | 2021-09-19 | Loss | -36.87 | -39.87 | Close-Over-Line-Next-Open | [053_2021-09-19_loss.png](charts/losers/053_2021-09-19_loss.png) |
| 54 | 2021-11-28 | Loss | -60.35 | -69.35 | Close-Over-Line-Next-Open | [054_2021-11-28_loss.png](charts/losers/054_2021-11-28_loss.png) |
| 55 | 2022-01-11 | Loss | -100.00 | -121.71 | Point-Stop | [055_2022-01-11_loss.png](charts/losers/055_2022-01-11_loss.png) |
| 56 | 2022-04-12 | Loss | -100.00 | -187.84 | Point-Stop | [056_2022-04-12_loss.png](charts/losers/056_2022-04-12_loss.png) |
| 57 | 2022-06-15 | Loss | -22.83 | -91.83 | Close-Over-Line-Next-Open | [057_2022-06-15_loss.png](charts/losers/057_2022-06-15_loss.png) |
| 58 | 2022-09-12 | Loss | -100.00 | -140.09 | Point-Stop | [058_2022-09-12_loss.png](charts/losers/058_2022-09-12_loss.png) |
| 59 | 2022-12-21 | Loss | -100.00 | -101.75 | Point-Stop | [059_2022-12-21_loss.png](charts/losers/059_2022-12-21_loss.png) |
| 60 | 2023-03-12 | Loss | -100.00 | -102.98 | Point-Stop | [060_2023-03-12_loss.png](charts/losers/060_2023-03-12_loss.png) |
| 61 | 2023-08-06 | Loss | -17.39 | -18.64 | Close-Over-Line-Next-Open | [061_2023-08-06_loss.png](charts/losers/061_2023-08-06_loss.png) |
| 62 | 2023-09-22 | Win | +100.00 | -14.75 | Target | [062_2023-09-22_win.png](charts/winners/062_2023-09-22_win.png) |
| 63 | 2023-11-01 | Loss | -100.00 | -166.22 | Point-Stop | [063_2023-11-01_loss.png](charts/losers/063_2023-11-01_loss.png) |
| 64 | 2024-01-08 | Loss | -100.00 | -170.64 | Point-Stop | [064_2024-01-08_loss.png](charts/losers/064_2024-01-08_loss.png) |
| 65 | 2024-04-16 | Win | +100.00 | -32.23 | Target | [065_2024-04-16_win.png](charts/winners/065_2024-04-16_win.png) |
| 66 | 2024-09-10 | Loss | -53.59 | -94.59 | Close-Over-Line-Next-Open | [066_2024-09-10_loss.png](charts/losers/066_2024-09-10_loss.png) |
| 67 | 2024-12-19 | Loss | -100.00 | -102.12 | Point-Stop | [067_2024-12-19_loss.png](charts/losers/067_2024-12-19_loss.png) |
| 68 | 2025-02-26 | Win | +100.00 | -75.66 | Target | [068_2025-02-26_win.png](charts/winners/068_2025-02-26_win.png) |
| 69 | 2025-08-03 | Loss | -11.32 | -15.32 | Close-Over-Line-Next-Open | [069_2025-08-03_loss.png](charts/losers/069_2025-08-03_loss.png) |
| 70 | 2025-10-12 | Loss | -100.00 | -248.31 | Point-Stop | [070_2025-10-12_loss.png](charts/losers/070_2025-10-12_loss.png) |
| 71 | 2025-11-14 | Loss | -100.00 | -117.13 | Point-Stop | [071_2025-11-14_loss.png](charts/losers/071_2025-11-14_loss.png) |
| 72 | 2026-01-21 | Loss | -100.00 | -510.56 | Point-Stop | [072_2026-01-21_loss.png](charts/losers/072_2026-01-21_loss.png) |
| 73 | 2026-02-08 | Loss | -52.09 | -71.59 | Close-Over-Line-Next-Open | [073_2026-02-08_loss.png](charts/losers/073_2026-02-08_loss.png) |
