# NQ MA500 Weekly Retest Replay - protected_rearm_max3

Rules: 15m MA500 is computed from completed 15m closes. If the latest completed close is below MA500, arm/update a short limit at MA500 for the next bar; if above, arm/update a long limit. A close through the MA exits any opposite position at that bar close and flips orientation. One NQ contract per unit; risk 25.0 pts (~$500), target 200.0 pts, stop locks to 10.0 pts profit after 100.0 pts favorable move. Stops/market exits include 1 tick adverse slippage and $1.50 per closed unit. Same-bar stop/target ambiguity is stop-first.

Charts render `1h` price candles, but the MA line and replay decisions remain the original completed-bar `15m MA500`. Horizontal context lines show the previous calendar week's high, low, close, and 50% high-low midpoint. Weekly C3 uses the same local candle-theory rule as the monthly C3 work: C1 range, C2 closes beyond C1 high/low, the current week is C3.

| Metric | Value |
|---|---:|
| Weeks | 821 |
| Active weeks | 707 |
| Trades | 7760 |
| Net | $-117,333.44 |
| Closed DD | $-117,304.50 |
| Net / DD | -1.00 |
| Win rate | 11.6% |
| PF | 0.89 |
| Targets | 159 |
| Stops | 1278 |
| MA close flips | 6129 |

## Charts

| # | Week | Weekly C3 | Net | Trades | Chart |
|---:|---|---|---:|---:|---|
| 1 | 2025-05-26 |  | $-11,917.22 | 44 | [charts/001_2025-05-26.png](charts/001_2025-05-26.png) |
| 2 | 2026-02-23 |  | $-9,092.11 | 38 | [charts/002_2026-02-23.png](charts/002_2026-02-23.png) |
| 3 | 2025-01-27 |  | $-9,869.38 | 23 | [charts/003_2025-01-27.png](charts/003_2025-01-27.png) |
| 4 | 2021-07-26 | bullish_hit | $-6,842.49 | 43 | [charts/004_2021-07-26.png](charts/004_2021-07-26.png) |
| 5 | 2020-03-23 | bearish_miss | $9,735.58 | 9 | [charts/005_2020-03-23.png](charts/005_2020-03-23.png) |
| 6 | 2023-07-24 |  | $9,288.38 | 13 | [charts/006_2023-07-24.png](charts/006_2023-07-24.png) |
| 7 | 2020-05-25 | bullish_hit | $-7,103.32 | 33 | [charts/007_2020-05-25.png](charts/007_2020-05-25.png) |
| 8 | 2025-05-05 | bullish_hit | $-6,443.85 | 32 | [charts/008_2025-05-05.png](charts/008_2025-05-05.png) |
| 9 | 2020-04-20 | bullish_miss | $-6,681.23 | 24 | [charts/009_2020-04-20.png](charts/009_2020-04-20.png) |
| 10 | 2025-09-29 |  | $-6,518.93 | 23 | [charts/010_2025-09-29.png](charts/010_2025-09-29.png) |
| 11 | 2025-05-19 | bullish_hit | $-6,612.32 | 20 | [charts/011_2025-05-19.png](charts/011_2025-05-19.png) |
| 12 | 2026-02-16 |  | $-5,633.65 | 27 | [charts/012_2026-02-16.png](charts/012_2026-02-16.png) |
| 13 | 2021-11-29 |  | $-5,502.07 | 28 | [charts/013_2021-11-29.png](charts/013_2021-11-29.png) |
| 14 | 2022-06-06 |  | $-5,867.20 | 24 | [charts/014_2022-06-06.png](charts/014_2022-06-06.png) |
| 15 | 2025-07-07 | bullish_hit | $-4,198.49 | 40 | [charts/015_2025-07-07.png](charts/015_2025-07-07.png) |
| 16 | 2020-06-01 | bullish_hit | $7,997.00 | 2 | [charts/016_2020-06-01.png](charts/016_2020-06-01.png) |
| 17 | 2020-10-26 | bearish_hit | $7,997.00 | 2 | [charts/017_2020-10-26.png](charts/017_2020-10-26.png) |
| 18 | 2023-11-27 |  | $-4,954.58 | 32 | [charts/018_2023-11-27.png](charts/018_2023-11-27.png) |
| 19 | 2014-12-01 | bullish_miss | $-2,908.02 | 51 | [charts/019_2014-12-01.png](charts/019_2014-12-01.png) |
| 20 | 2020-04-27 |  | $6,883.68 | 10 | [charts/020_2020-04-27.png](charts/020_2020-04-27.png) |
| 21 | 2020-03-30 |  | $7,263.88 | 6 | [charts/021_2020-03-30.png](charts/021_2020-03-30.png) |
| 22 | 2020-09-14 |  | $6,736.16 | 11 | [charts/022_2020-09-14.png](charts/022_2020-09-14.png) |
| 23 | 2022-02-21 | bearish_hit | $-5,738.85 | 20 | [charts/023_2022-02-21.png](charts/023_2022-02-21.png) |
| 24 | 2021-10-04 | bearish_hit | $6,482.59 | 12 | [charts/024_2021-10-04.png](charts/024_2021-10-04.png) |
| 25 | 2024-08-19 | bullish_hit | $-5,853.69 | 16 | [charts/025_2024-08-19.png](charts/025_2024-08-19.png) |
| 26 | 2024-04-08 | bearish_miss | $-4,967.42 | 22 | [charts/026_2024-04-08.png](charts/026_2024-04-08.png) |
| 27 | 2022-11-28 |  | $6,423.03 | 6 | [charts/027_2022-11-28.png](charts/027_2022-11-28.png) |
| 28 | 2019-09-02 |  | $-4,813.01 | 22 | [charts/028_2019-09-02.png](charts/028_2019-09-02.png) |
| 29 | 2020-11-09 | bullish_miss | $-4,212.39 | 27 | [charts/029_2020-11-09.png](charts/029_2020-11-09.png) |
| 30 | 2023-10-02 |  | $4,799.60 | 21 | [charts/030_2023-10-02.png](charts/030_2023-10-02.png) |
| 31 | 2020-12-21 | bullish_miss | $-4,771.47 | 21 | [charts/031_2020-12-21.png](charts/031_2020-12-21.png) |
| 32 | 2021-03-15 |  | $5,855.32 | 10 | [charts/032_2021-03-15.png](charts/032_2021-03-15.png) |
| 33 | 2024-09-30 | bullish_miss | $-4,226.64 | 26 | [charts/033_2024-09-30.png](charts/033_2024-09-30.png) |
| 34 | 2016-06-20 | bearish_hit | $-2,801.93 | 40 | [charts/034_2016-06-20.png](charts/034_2016-06-20.png) |
| 35 | 2021-04-19 | bullish_miss | $-4,039.33 | 27 | [charts/035_2021-04-19.png](charts/035_2021-04-19.png) |
| 36 | 2025-06-16 |  | $4,510.09 | 22 | [charts/036_2025-06-16.png](charts/036_2025-06-16.png) |
| 37 | 2020-07-13 | bullish_hit | $5,003.95 | 17 | [charts/037_2020-07-13.png](charts/037_2020-07-13.png) |
| 38 | 2026-01-05 | bearish_miss | $-3,406.08 | 32 | [charts/038_2026-01-05.png](charts/038_2026-01-05.png) |
| 39 | 2024-04-22 | bearish_miss | $5,289.11 | 13 | [charts/039_2024-04-22.png](charts/039_2024-04-22.png) |
| 40 | 2022-09-26 | bearish_hit | $5,084.83 | 15 | [charts/040_2022-09-26.png](charts/040_2022-09-26.png) |
| 41 | 2025-12-29 | bullish_miss | $-5,016.70 | 15 | [charts/041_2025-12-29.png](charts/041_2025-12-29.png) |
| 42 | 2017-09-04 | bullish_miss | $-2,673.36 | 38 | [charts/042_2017-09-04.png](charts/042_2017-09-04.png) |
| 43 | 2023-01-16 | bullish_hit | $5,426.61 | 10 | [charts/043_2023-01-16.png](charts/043_2023-01-16.png) |
| 44 | 2022-07-04 |  | $4,673.96 | 17 | [charts/044_2022-07-04.png](charts/044_2022-07-04.png) |
| 45 | 2024-09-09 | bearish_miss | $-4,777.58 | 15 | [charts/045_2024-09-09.png](charts/045_2024-09-09.png) |
| 46 | 2025-07-21 | bullish_hit | $-4,833.48 | 14 | [charts/046_2025-07-21.png](charts/046_2025-07-21.png) |
| 47 | 2017-03-06 |  | $-1,939.84 | 42 | [charts/047_2017-03-06.png](charts/047_2017-03-06.png) |
| 48 | 2024-08-26 | bullish_miss | $4,393.73 | 16 | [charts/048_2024-08-26.png](charts/048_2024-08-26.png) |
| 49 | 2024-04-01 |  | $-4,021.43 | 19 | [charts/049_2024-04-01.png](charts/049_2024-04-01.png) |
| 50 | 2023-12-18 | bullish_hit | $-3,893.52 | 20 | [charts/050_2023-12-18.png](charts/050_2023-12-18.png) |
| 51 | 2025-12-15 |  | $4,381.92 | 14 | [charts/051_2025-12-15.png](charts/051_2025-12-15.png) |
| 52 | 2023-03-13 |  | $-3,600.23 | 21 | [charts/052_2023-03-13.png](charts/052_2023-03-13.png) |
| 53 | 2025-02-03 | bearish_miss | $3,012.40 | 26 | [charts/053_2025-02-03.png](charts/053_2025-02-03.png) |
| 54 | 2020-01-27 |  | $-2,787.80 | 28 | [charts/054_2020-01-27.png](charts/054_2020-01-27.png) |
| 55 | 2023-04-10 |  | $-3,473.03 | 21 | [charts/055_2023-04-10.png](charts/055_2023-04-10.png) |
| 56 | 2021-09-06 | bullish_hit | $-4,131.68 | 14 | [charts/056_2021-09-06.png](charts/056_2021-09-06.png) |
| 57 | 2016-04-18 |  | $-2,392.39 | 31 | [charts/057_2016-04-18.png](charts/057_2016-04-18.png) |
| 58 | 2019-07-29 | bullish_miss | $-2,111.20 | 33 | [charts/058_2019-07-29.png](charts/058_2019-07-29.png) |
| 59 | 2018-12-31 |  | $-3,303.07 | 21 | [charts/059_2018-12-31.png](charts/059_2018-12-31.png) |
| 60 | 2018-07-16 | bullish_hit | $-1,984.45 | 34 | [charts/060_2018-07-16.png](charts/060_2018-07-16.png) |
| 61 | 2019-09-16 |  | $-2,052.69 | 33 | [charts/061_2019-09-16.png](charts/061_2019-09-16.png) |
| 62 | 2024-12-23 |  | $4,464.30 | 8 | [charts/062_2024-12-23.png](charts/062_2024-12-23.png) |
| 63 | 2013-01-28 |  | $-1,199.12 | 40 | [charts/063_2013-01-28.png](charts/063_2013-01-28.png) |
| 64 | 2024-10-21 |  | $-2,221.00 | 29 | [charts/064_2024-10-21.png](charts/064_2024-10-21.png) |
| 65 | 2022-04-25 | bearish_hit | $-3,440.80 | 16 | [charts/065_2022-04-25.png](charts/065_2022-04-25.png) |
| 66 | 2022-11-07 | bearish_miss | $-3,634.55 | 14 | [charts/066_2022-11-07.png](charts/066_2022-11-07.png) |
| 67 | 2021-05-17 | bearish_miss | $-2,081.85 | 29 | [charts/067_2021-05-17.png](charts/067_2021-05-17.png) |
| 68 | 2021-03-22 |  | $-3,371.40 | 16 | [charts/068_2021-03-22.png](charts/068_2021-03-22.png) |
| 69 | 2016-08-15 | bullish_hit | $-1,346.85 | 36 | [charts/069_2016-08-15.png](charts/069_2016-08-15.png) |
| 70 | 2023-01-02 |  | $-1,906.17 | 30 | [charts/070_2023-01-02.png](charts/070_2023-01-02.png) |
| 71 | 2021-08-02 |  | $-2,895.83 | 19 | [charts/071_2021-08-02.png](charts/071_2021-08-02.png) |
| 72 | 2020-03-16 | bearish_hit | $2,962.20 | 18 | [charts/072_2020-03-16.png](charts/072_2020-03-16.png) |
| 73 | 2024-02-12 | bullish_hit | $-2,118.71 | 26 | [charts/073_2024-02-12.png](charts/073_2024-02-12.png) |
| 74 | 2020-10-12 | bullish_hit | $-3,096.62 | 16 | [charts/074_2020-10-12.png](charts/074_2020-10-12.png) |
| 75 | 2023-08-28 |  | $-3,185.91 | 15 | [charts/075_2023-08-28.png](charts/075_2023-08-28.png) |
| 76 | 2014-07-28 | bullish_miss | $-183.26 | 45 | [charts/076_2014-07-28.png](charts/076_2014-07-28.png) |
| 77 | 2017-01-16 | bullish_hit | $-1,750.31 | 29 | [charts/077_2017-01-16.png](charts/077_2017-01-16.png) |
| 78 | 2025-11-10 | bearish_hit | $2,936.96 | 17 | [charts/078_2025-11-10.png](charts/078_2025-11-10.png) |
| 79 | 2021-04-26 |  | $-3,100.46 | 15 | [charts/079_2021-04-26.png](charts/079_2021-04-26.png) |
| 80 | 2023-04-03 | bullish_hit | $-3,065.14 | 15 | [charts/080_2023-04-03.png](charts/080_2023-04-03.png) |