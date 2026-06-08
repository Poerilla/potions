# NQ MA500 Weekly Retest Replay - single_unit

Rules: 15m MA500 is computed from completed 15m closes. If the latest completed close is below MA500, arm/update a short limit at MA500 for the next bar; if above, arm/update a long limit. A close through the MA exits any opposite position at that bar close and flips orientation. One NQ contract per unit; risk 25.0 pts (~$500), target 200.0 pts, stop locks to 10.0 pts profit after 100.0 pts favorable move. Stops/market exits include 1 tick adverse slippage and $1.50 per closed unit. Same-bar stop/target ambiguity is stop-first.

Charts render `1h` price candles, but the MA line and replay decisions remain the original completed-bar `15m MA500`. Horizontal context lines show the previous calendar week's high, low, close, and 50% high-low midpoint. Weekly C3 uses the same local candle-theory rule as the monthly C3 work: C1 range, C2 closes beyond C1 high/low, the current week is C3.

| Metric | Value |
|---|---:|
| Weeks | 821 |
| Active weeks | 707 |
| Trades | 7668 |
| Net | $-105,169.24 |
| Closed DD | $-105,140.30 |
| Net / DD | -1.00 |
| Win rate | 11.5% |
| PF | 0.90 |
| Targets | 158 |
| Stops | 1234 |
| MA close flips | 6083 |

## Charts

| # | Week | Weekly C3 | Net | Trades | Chart |
|---:|---|---|---:|---:|---|
| 1 | 2025-05-26 |  | $-11,917.22 | 44 | [charts/001_2025-05-26.png](charts/001_2025-05-26.png) |
| 2 | 2026-02-23 |  | $-8,585.61 | 37 | [charts/002_2026-02-23.png](charts/002_2026-02-23.png) |
| 3 | 2025-01-27 |  | $-9,881.25 | 23 | [charts/003_2025-01-27.png](charts/003_2025-01-27.png) |
| 4 | 2020-03-23 | bearish_miss | $10,748.58 | 7 | [charts/004_2020-03-23.png](charts/004_2020-03-23.png) |
| 5 | 2021-07-26 | bullish_hit | $-6,710.06 | 42 | [charts/005_2021-07-26.png](charts/005_2021-07-26.png) |
| 6 | 2023-07-24 |  | $9,288.38 | 13 | [charts/006_2023-07-24.png](charts/006_2023-07-24.png) |
| 7 | 2020-05-25 | bullish_hit | $-6,596.82 | 32 | [charts/007_2020-05-25.png](charts/007_2020-05-25.png) |
| 8 | 2025-05-05 | bullish_hit | $-6,443.85 | 32 | [charts/008_2025-05-05.png](charts/008_2025-05-05.png) |
| 9 | 2020-04-20 | bullish_miss | $-6,681.23 | 24 | [charts/009_2020-04-20.png](charts/009_2020-04-20.png) |
| 10 | 2025-09-29 |  | $-6,529.38 | 23 | [charts/010_2025-09-29.png](charts/010_2025-09-29.png) |
| 11 | 2020-09-14 |  | $7,242.66 | 10 | [charts/011_2020-09-14.png](charts/011_2020-09-14.png) |
| 12 | 2020-10-26 | bearish_hit | $7,997.00 | 2 | [charts/012_2020-10-26.png](charts/012_2020-10-26.png) |
| 13 | 2026-02-16 |  | $-5,494.79 | 26 | [charts/013_2026-02-16.png](charts/013_2026-02-16.png) |
| 14 | 2021-10-04 | bearish_hit | $6,989.09 | 11 | [charts/014_2021-10-04.png](charts/014_2021-10-04.png) |
| 15 | 2023-11-27 |  | $-4,919.29 | 31 | [charts/015_2023-11-27.png](charts/015_2023-11-27.png) |
| 16 | 2014-12-01 | bullish_miss | $-2,908.02 | 51 | [charts/016_2014-12-01.png](charts/016_2014-12-01.png) |
| 17 | 2025-05-19 | bullish_hit | $-6,105.82 | 19 | [charts/017_2025-05-19.png](charts/017_2025-05-19.png) |
| 18 | 2020-04-27 |  | $6,894.93 | 10 | [charts/018_2020-04-27.png](charts/018_2020-04-27.png) |
| 19 | 2020-03-30 |  | $7,263.88 | 6 | [charts/019_2020-03-30.png](charts/019_2020-03-30.png) |
| 20 | 2022-02-21 | bearish_hit | $-5,738.85 | 20 | [charts/020_2022-02-21.png](charts/020_2022-02-21.png) |
| 21 | 2025-07-07 | bullish_hit | $-3,691.99 | 39 | [charts/021_2025-07-07.png](charts/021_2025-07-07.png) |
| 22 | 2024-08-19 | bullish_hit | $-5,853.69 | 16 | [charts/022_2024-08-19.png](charts/022_2024-08-19.png) |
| 23 | 2022-06-06 |  | $-5,101.95 | 22 | [charts/023_2022-06-06.png](charts/023_2022-06-06.png) |
| 24 | 2023-10-02 |  | $5,296.76 | 20 | [charts/024_2023-10-02.png](charts/024_2023-10-02.png) |
| 25 | 2024-04-08 | bearish_miss | $-4,967.42 | 22 | [charts/025_2024-04-08.png](charts/025_2024-04-08.png) |
| 26 | 2021-11-29 |  | $-4,489.07 | 26 | [charts/026_2021-11-29.png](charts/026_2021-11-29.png) |
| 27 | 2022-11-28 |  | $6,423.03 | 6 | [charts/027_2022-11-28.png](charts/027_2022-11-28.png) |
| 28 | 2019-09-02 |  | $-4,813.01 | 22 | [charts/028_2019-09-02.png](charts/028_2019-09-02.png) |
| 29 | 2020-11-09 | bullish_miss | $-4,212.39 | 27 | [charts/029_2020-11-09.png](charts/029_2020-11-09.png) |
| 30 | 2024-04-22 | bearish_miss | $5,696.09 | 12 | [charts/030_2024-04-22.png](charts/030_2024-04-22.png) |
| 31 | 2020-12-21 | bullish_miss | $-4,771.47 | 21 | [charts/031_2020-12-21.png](charts/031_2020-12-21.png) |
| 32 | 2021-03-15 |  | $5,855.32 | 10 | [charts/032_2021-03-15.png](charts/032_2021-03-15.png) |
| 33 | 2016-06-20 | bearish_hit | $-2,801.93 | 40 | [charts/033_2016-06-20.png](charts/033_2016-06-20.png) |
| 34 | 2021-04-19 | bullish_miss | $-4,039.33 | 27 | [charts/034_2021-04-19.png](charts/034_2021-04-19.png) |
| 35 | 2025-06-16 |  | $4,510.09 | 22 | [charts/035_2025-06-16.png](charts/035_2025-06-16.png) |
| 36 | 2020-07-13 | bullish_hit | $5,003.95 | 17 | [charts/036_2020-07-13.png](charts/036_2020-07-13.png) |
| 37 | 2024-09-30 | bullish_miss | $-4,200.29 | 24 | [charts/037_2024-09-30.png](charts/037_2024-09-30.png) |
| 38 | 2022-09-26 | bearish_hit | $5,084.83 | 15 | [charts/038_2022-09-26.png](charts/038_2022-09-26.png) |
| 39 | 2025-12-29 | bullish_miss | $-5,016.70 | 15 | [charts/039_2025-12-29.png](charts/039_2025-12-29.png) |
| 40 | 2017-09-04 | bullish_miss | $-2,673.36 | 38 | [charts/040_2017-09-04.png](charts/040_2017-09-04.png) |
| 41 | 2026-01-05 | bearish_miss | $-3,328.51 | 31 | [charts/041_2026-01-05.png](charts/041_2026-01-05.png) |
| 42 | 2023-01-16 | bullish_hit | $5,426.61 | 10 | [charts/042_2023-01-16.png](charts/042_2023-01-16.png) |
| 43 | 2022-07-04 |  | $4,673.96 | 17 | [charts/043_2022-07-04.png](charts/043_2022-07-04.png) |
| 44 | 2024-09-09 | bearish_miss | $-4,777.58 | 15 | [charts/044_2024-09-09.png](charts/044_2024-09-09.png) |
| 45 | 2025-07-21 | bullish_hit | $-4,833.48 | 14 | [charts/045_2025-07-21.png](charts/045_2025-07-21.png) |
| 46 | 2017-03-06 |  | $-1,939.84 | 42 | [charts/046_2017-03-06.png](charts/046_2017-03-06.png) |
| 47 | 2024-08-26 | bullish_miss | $4,393.73 | 16 | [charts/047_2024-08-26.png](charts/047_2024-08-26.png) |
| 48 | 2025-12-15 |  | $4,381.92 | 14 | [charts/048_2025-12-15.png](charts/048_2025-12-15.png) |
| 49 | 2023-03-13 |  | $-3,600.23 | 21 | [charts/049_2023-03-13.png](charts/049_2023-03-13.png) |
| 50 | 2023-12-18 | bullish_hit | $-3,769.67 | 19 | [charts/050_2023-12-18.png](charts/050_2023-12-18.png) |
| 51 | 2025-02-03 | bearish_miss | $3,156.99 | 24 | [charts/051_2025-02-03.png](charts/051_2025-02-03.png) |
| 52 | 2021-09-06 | bullish_hit | $-4,131.68 | 14 | [charts/052_2021-09-06.png](charts/052_2021-09-06.png) |
| 53 | 2016-04-18 |  | $-2,392.39 | 31 | [charts/053_2016-04-18.png](charts/053_2016-04-18.png) |
| 54 | 2019-07-29 | bullish_miss | $-2,111.20 | 33 | [charts/054_2019-07-29.png](charts/054_2019-07-29.png) |
| 55 | 2018-12-31 |  | $-3,303.07 | 21 | [charts/055_2018-12-31.png](charts/055_2018-12-31.png) |
| 56 | 2018-07-16 | bullish_hit | $-1,984.45 | 34 | [charts/056_2018-07-16.png](charts/056_2018-07-16.png) |
| 57 | 2019-09-16 |  | $-2,052.69 | 33 | [charts/057_2019-09-16.png](charts/057_2019-09-16.png) |
| 58 | 2024-04-01 |  | $-3,514.93 | 18 | [charts/058_2024-04-01.png](charts/058_2024-04-01.png) |
| 59 | 2013-01-28 |  | $-1,199.12 | 40 | [charts/059_2013-01-28.png](charts/059_2013-01-28.png) |
| 60 | 2020-01-27 |  | $-2,593.55 | 26 | [charts/060_2020-01-27.png](charts/060_2020-01-27.png) |
| 61 | 2022-04-25 | bearish_hit | $-3,634.06 | 15 | [charts/061_2022-04-25.png](charts/061_2022-04-25.png) |
| 62 | 2022-11-07 | bearish_miss | $-3,828.05 | 13 | [charts/062_2022-11-07.png](charts/062_2022-11-07.png) |
| 63 | 2024-10-21 |  | $-2,221.00 | 29 | [charts/063_2024-10-21.png](charts/063_2024-10-21.png) |
| 64 | 2021-05-17 | bearish_miss | $-2,081.85 | 29 | [charts/064_2021-05-17.png](charts/064_2021-05-17.png) |
| 65 | 2021-03-22 |  | $-3,371.40 | 16 | [charts/065_2021-03-22.png](charts/065_2021-03-22.png) |
| 66 | 2024-12-23 |  | $4,270.80 | 7 | [charts/066_2024-12-23.png](charts/066_2024-12-23.png) |
| 67 | 2016-08-15 | bullish_hit | $-1,346.85 | 36 | [charts/067_2016-08-15.png](charts/067_2016-08-15.png) |
| 68 | 2023-01-02 |  | $-1,906.17 | 30 | [charts/068_2023-01-02.png](charts/068_2023-01-02.png) |
| 69 | 2021-08-02 |  | $-2,895.83 | 19 | [charts/069_2021-08-02.png](charts/069_2021-08-02.png) |
| 70 | 2020-03-16 | bearish_hit | $2,962.20 | 18 | [charts/070_2020-03-16.png](charts/070_2020-03-16.png) |
| 71 | 2020-10-12 | bullish_hit | $-3,096.62 | 16 | [charts/071_2020-10-12.png](charts/071_2020-10-12.png) |
| 72 | 2023-08-28 |  | $-3,185.91 | 15 | [charts/072_2023-08-28.png](charts/072_2023-08-28.png) |
| 73 | 2014-07-28 | bullish_miss | $-183.26 | 45 | [charts/073_2014-07-28.png](charts/073_2014-07-28.png) |
| 74 | 2017-01-16 | bullish_hit | $-1,750.31 | 29 | [charts/074_2017-01-16.png](charts/074_2017-01-16.png) |
| 75 | 2025-11-10 | bearish_hit | $2,937.97 | 17 | [charts/075_2025-11-10.png](charts/075_2025-11-10.png) |
| 76 | 2022-07-11 |  | $-3,103.19 | 15 | [charts/076_2022-07-11.png](charts/076_2022-07-11.png) |
| 77 | 2021-04-26 |  | $-3,100.46 | 15 | [charts/077_2021-04-26.png](charts/077_2021-04-26.png) |
| 78 | 2023-04-03 | bullish_hit | $-3,065.14 | 15 | [charts/078_2023-04-03.png](charts/078_2023-04-03.png) |
| 79 | 2015-10-19 | bullish_hit | $3,464.28 | 11 | [charts/079_2015-10-19.png](charts/079_2015-10-19.png) |
| 80 | 2015-06-01 |  | $-1,840.88 | 27 | [charts/080_2015-06-01.png](charts/080_2015-06-01.png) |