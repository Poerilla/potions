# NQ Monthly Candlestick Theory Study

## Theory Summary

| Direction | Setups | Hits | Hit Rate | C3 Close Beyond | Close Rate | Avg Extension | Median Extension | Avg Adverse | Worst Adverse |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bearish | 19 | 12 | 63.16% | 3 | 15.79% | 635.21 | 305.38 | 68.12 | 739.75 |
| bullish | 86 | 71 | 82.56% | 44 | 51.16% | 311.97 | 169.25 | 55.20 | 719.25 |
| all | 105 | 83 | 79.05% | 47 | 44.76% | 358.70 | 170.75 | 57.54 | 739.75 |

## Strategy: Breakout-Candle Entry · TP = 2R

Opening candle = first daily bar of C3.  R = its H−L.
Breakout candle: first bar that closes beyond opening candle H (bull) or L (bear).
Entry at breakout close.  SL = entry ± 2R.  TP = entry ± 2R.
open_eom = filled but C3 ended before TP/SL (excluded from PnL).

| Direction | Setups | No Breakout | Resolved | open_eom | TP | SL | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg Breakout Day | Avg days→TP | Avg days→SL | Total PnL (R) | Total PnL (pts) | Swept Opposing (n/%) | Clean Body→TP (n/%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 86 | 10 | 62 | 14 | 33 | 29 | 53.23% | 1.101 | 99.93 | 5.5 | 7.0 | 4.5 | +8.00 | +2787.00 | 35 / 46.1% | 26 / 78.8% |
| bearish | 19 | 4 | 13 | 2 | 8 | 5 | 61.54% | 0.778 | 157.02 | 6.2 | 5.4 | 4.0 | +6.00 | +2942.00 | 9 / 60.0% | 7 / 87.5% |
| all | 105 | 14 | 75 | 16 | 41 | 34 | 54.67% | 1.045 | 109.82 | 5.6 | 6.7 | 4.4 | +14.00 | +5729.00 | 44 / 48.4% | 33 / 80.5% |

## Strategy: Breakout-Candle Entry · TP = 3R

Same entry/SL rules.  TP = entry ± 3R.

| Direction | Setups | No Breakout | Resolved | open_eom | TP | SL | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg Breakout Day | Avg days→TP | Avg days→SL | Total PnL (R) | Total PnL (pts) | Swept Opposing (n/%) | Clean Body→TP (n/%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 86 | 10 | 57 | 19 | 26 | 31 | 45.61% | 1.186 | 107.18 | 5.5 | 7.3 | 4.8 | +16.00 | +2309.75 | 35 / 46.1% | 22 / 84.6% |
| bearish | 19 | 4 | 11 | 4 | 6 | 5 | 54.55% | 0.875 | 173.50 | 6.2 | 6.0 | 4.0 | +8.00 | +4106.00 | 9 / 60.0% | 5 / 83.3% |
| all | 105 | 14 | 68 | 23 | 32 | 36 | 47.06% | 1.135 | 117.91 | 5.6 | 7.1 | 4.7 | +24.00 | +6415.75 | 44 / 48.4% | 27 / 84.4% |

## Variant: Clean-Body-Exit · TP = 2R

Entry at breakout close.  Exit when any bar CLOSES back through OC boundary
(close < OC_high for bull, close > OC_low for bear).  TP = entry ± 2R.
TP takes priority over close-exit on the same bar.

| Direction | Active | No Breakout | Skipped | Resolved | open_eom | TP | Loss | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg days→TP | Avg days→Loss | Total PnL (R) | Total PnL (pts) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 76 | 10 | 0 | 73 | 3 | 32 | 41 | 43.84% | 1.835 | 87.09 | 4.0 | 4.3 | +1.550 | +43.50 |
| bearish | 15 | 4 | 0 | 14 | 1 | 9 | 5 | 64.29% | 1.563 | 131.43 | 3.7 | 2.2 | +9.470 | +2563.00 |
| all | 91 | 14 | 0 | 87 | 4 | 41 | 46 | 47.13% | 1.791 | 94.22 | 4.0 | 4.1 | +11.020 | +2606.50 |

## Variant: Clean-Body-Exit · TP = 3R

Same close-based exit.  TP = entry ± 3R.

| Direction | Active | No Breakout | Skipped | Resolved | open_eom | TP | Loss | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg days→TP | Avg days→Loss | Total PnL (R) | Total PnL (pts) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 76 | 10 | 0 | 72 | 4 | 25 | 47 | 34.72% | 2.047 | 94.29 | 5.4 | 4.6 | -10.860 | +115.75 |
| bearish | 15 | 4 | 0 | 14 | 1 | 6 | 8 | 42.86% | 1.583 | 132.91 | 3.5 | 5.4 | +2.310 | +3006.50 |
| all | 91 | 14 | 0 | 86 | 5 | 31 | 55 | 36.05% | 1.972 | 100.58 | 5.0 | 4.7 | -8.550 | +3122.25 |

## Variant: Swept-Opposing-Only · TP = 2R

Only trades setups where a bar before the breakout swept OC's opposing extreme.
SL = OC_low (bull) / OC_high (bear).  TP = entry ± 2R (R = OC range).  Skipped = no sweep.

| Direction | Active | No Breakout | Skipped | Resolved | open_eom | TP | Loss | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg days→TP | Avg days→Loss | Total PnL (R) | Total PnL (pts) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 35 | 10 | 41 | 31 | 4 | 16 | 15 | 51.61% | 2.101 | 72.84 | 6.2 | 3.3 | +8.760 | +631.50 |
| bearish | 9 | 4 | 6 | 7 | 2 | 6 | 1 | 85.71% | 0.871 | 163.96 | 6.3 | 2.0 | +10.460 | +2338.00 |
| all | 44 | 14 | 47 | 38 | 6 | 22 | 16 | 57.89% | 1.874 | 89.62 | 6.3 | 3.2 | +19.220 | +2969.50 |

## Variant: Swept-Opposing-Only · TP = 3R

Same SL rules.  TP = entry ± 3R.

| Direction | Active | No Breakout | Skipped | Resolved | open_eom | TP | Loss | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg days→TP | Avg days→Loss | Total PnL (R) | Total PnL (pts) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 35 | 10 | 41 | 29 | 6 | 14 | 15 | 48.28% | 2.186 | 67.08 | 5.7 | 3.3 | +18.760 | +456.00 |
| bearish | 9 | 4 | 6 | 6 | 3 | 4 | 2 | 66.67% | 1.047 | 181.17 | 7.2 | 11.0 | +9.300 | +2914.25 |
| all | 44 | 14 | 47 | 35 | 9 | 18 | 17 | 51.43% | 1.991 | 86.64 | 6.1 | 4.2 | +28.070 | +3370.25 |

## Skipped / Failure Sweep Context

- High failure sweeps: 46
- Low failure sweeps: 46
- Unique non-signal failure-sweep months: 73
- Non-signal rolling windows: 83

## Charts

- [All C3 occurrences timeline](charts/timeline_all_c3.png)
- [Daily C3 chart index](charts/daily/INDEX.md)

| Setup | Direction | C1 | C2 | C3 | Hit | Extension | Chart |
|---:|---|---|---|---|---|---:|---|
| 1 | bullish | 2010-08 | 2010-09 | 2010-10 | True | +104.75 | [001_bullish_2010-10_c3_hit.png](charts/hits/001_bullish_2010-10_c3_hit.png) |
| 2 | bullish | 2010-09 | 2010-10 | 2010-11 | True | +61.25 | [002_bullish_2010-11_c3_hit.png](charts/hits/002_bullish_2010-11_c3_hit.png) |
| 3 | bullish | 2010-11 | 2010-12 | 2011-01 | True | +107.50 | [003_bullish_2011-01_c3_hit.png](charts/hits/003_bullish_2011-01_c3_hit.png) |
| 4 | bullish | 2010-12 | 2011-01 | 2011-02 | True | +56.50 | [004_bullish_2011-02_c3_hit.png](charts/hits/004_bullish_2011-02_c3_hit.png) |
| 5 | bullish | 2011-01 | 2011-02 | 2011-03 | False | -24.25 | [005_bullish_2011-03_c3_miss.png](charts/misses/005_bullish_2011-03_c3_miss.png) |
| 6 | bullish | 2011-03 | 2011-04 | 2011-05 | True | +12.25 | [006_bullish_2011-05_c3_hit.png](charts/hits/006_bullish_2011-05_c3_hit.png) |
| 7 | bullish | 2011-06 | 2011-07 | 2011-08 | False | -40.50 | [007_bullish_2011-08_c3_miss.png](charts/misses/007_bullish_2011-08_c3_miss.png) |
| 8 | bearish | 2011-07 | 2011-08 | 2011-09 | False | -136.00 | [008_bearish_2011-09_c3_miss.png](charts/misses/008_bearish_2011-09_c3_miss.png) |
| 9 | bullish | 2011-09 | 2011-10 | 2011-11 | False | -9.25 | [009_bullish_2011-11_c3_miss.png](charts/misses/009_bullish_2011-11_c3_miss.png) |
| 10 | bullish | 2011-12 | 2012-01 | 2012-02 | True | +166.75 | [010_bullish_2012-02_c3_hit.png](charts/hits/010_bullish_2012-02_c3_hit.png) |
| 11 | bullish | 2012-01 | 2012-02 | 2012-03 | True | +145.00 | [011_bullish_2012-03_c3_hit.png](charts/hits/011_bullish_2012-03_c3_hit.png) |
| 12 | bullish | 2012-02 | 2012-03 | 2012-04 | True | +1.25 | [012_bullish_2012-04_c3_hit.png](charts/hits/012_bullish_2012-04_c3_hit.png) |
| 13 | bearish | 2012-04 | 2012-05 | 2012-06 | True | +31.25 | [013_bearish_2012-06_c3_hit.png](charts/hits/013_bearish_2012-06_c3_hit.png) |
| 14 | bullish | 2012-06 | 2012-07 | 2012-08 | True | +144.50 | [014_bullish_2012-08_c3_hit.png](charts/hits/014_bullish_2012-08_c3_hit.png) |
| 15 | bullish | 2012-07 | 2012-08 | 2012-09 | True | +69.25 | [015_bullish_2012-09_c3_hit.png](charts/hits/015_bullish_2012-09_c3_hit.png) |
| 16 | bearish | 2012-09 | 2012-10 | 2012-11 | True | +112.50 | [016_bearish_2012-11_c3_hit.png](charts/hits/016_bearish_2012-11_c3_hit.png) |
| 17 | bullish | 2012-12 | 2013-01 | 2013-02 | True | +17.75 | [017_bullish_2013-02_c3_hit.png](charts/hits/017_bullish_2013-02_c3_hit.png) |
| 18 | bullish | 2013-02 | 2013-03 | 2013-04 | True | +67.25 | [018_bullish_2013-04_c3_hit.png](charts/hits/018_bullish_2013-04_c3_hit.png) |
| 19 | bullish | 2013-03 | 2013-04 | 2013-05 | True | +169.25 | [019_bullish_2013-05_c3_hit.png](charts/hits/019_bullish_2013-05_c3_hit.png) |
| 20 | bullish | 2013-04 | 2013-05 | 2013-06 | False | -46.50 | [020_bullish_2013-06_c3_miss.png](charts/misses/020_bullish_2013-06_c3_miss.png) |
| 21 | bullish | 2013-06 | 2013-07 | 2013-08 | True | +43.00 | [021_bullish_2013-08_c3_hit.png](charts/hits/021_bullish_2013-08_c3_hit.png) |
| 22 | bullish | 2013-08 | 2013-09 | 2013-10 | True | +160.25 | [022_bullish_2013-10_c3_hit.png](charts/hits/022_bullish_2013-10_c3_hit.png) |
| 23 | bullish | 2013-09 | 2013-10 | 2013-11 | True | +94.75 | [023_bullish_2013-11_c3_hit.png](charts/hits/023_bullish_2013-11_c3_hit.png) |
| 24 | bullish | 2013-10 | 2013-11 | 2013-12 | True | +98.25 | [024_bullish_2013-12_c3_hit.png](charts/hits/024_bullish_2013-12_c3_hit.png) |
| 25 | bullish | 2013-11 | 2013-12 | 2014-01 | True | +40.50 | [025_bullish_2014-01_c3_hit.png](charts/hits/025_bullish_2014-01_c3_hit.png) |
| 26 | bullish | 2014-01 | 2014-02 | 2014-03 | True | +18.00 | [026_bullish_2014-03_c3_hit.png](charts/hits/026_bullish_2014-03_c3_hit.png) |
| 27 | bullish | 2014-04 | 2014-05 | 2014-06 | True | +110.75 | [027_bullish_2014-06_c3_hit.png](charts/hits/027_bullish_2014-06_c3_hit.png) |
| 28 | bullish | 2014-05 | 2014-06 | 2014-07 | True | +140.00 | [028_bullish_2014-07_c3_hit.png](charts/hits/028_bullish_2014-07_c3_hit.png) |
| 29 | bullish | 2014-06 | 2014-07 | 2014-08 | True | +94.75 | [029_bullish_2014-08_c3_hit.png](charts/hits/029_bullish_2014-08_c3_hit.png) |
| 30 | bullish | 2014-07 | 2014-08 | 2014-09 | True | +32.75 | [030_bullish_2014-09_c3_hit.png](charts/hits/030_bullish_2014-09_c3_hit.png) |
| 31 | bullish | 2014-09 | 2014-10 | 2014-11 | True | +184.50 | [031_bullish_2014-11_c3_hit.png](charts/hits/031_bullish_2014-11_c3_hit.png) |
| 32 | bullish | 2014-10 | 2014-11 | 2014-12 | False | -12.50 | [032_bullish_2014-12_c3_miss.png](charts/misses/032_bullish_2014-12_c3_miss.png) |
| 33 | bullish | 2015-01 | 2015-02 | 2015-03 | True | +18.50 | [033_bullish_2015-03_c3_hit.png](charts/hits/033_bullish_2015-03_c3_hit.png) |
| 34 | bullish | 2015-06 | 2015-07 | 2015-08 | False | -57.00 | [034_bullish_2015-08_c3_miss.png](charts/misses/034_bullish_2015-08_c3_miss.png) |
| 35 | bearish | 2015-07 | 2015-08 | 2015-09 | False | -132.50 | [035_bearish_2015-09_c3_miss.png](charts/misses/035_bearish_2015-09_c3_miss.png) |
| 36 | bullish | 2015-09 | 2015-10 | 2015-11 | True | +39.50 | [036_bullish_2015-11_c3_hit.png](charts/hits/036_bullish_2015-11_c3_hit.png) |
| 37 | bearish | 2015-12 | 2016-01 | 2016-02 | True | +121.25 | [037_bearish_2016-02_c3_hit.png](charts/hits/037_bearish_2016-02_c3_hit.png) |
| 38 | bullish | 2016-02 | 2016-03 | 2016-04 | True | +74.25 | [038_bullish_2016-04_c3_hit.png](charts/hits/038_bullish_2016-04_c3_hit.png) |
| 39 | bullish | 2016-06 | 2016-07 | 2016-08 | True | +97.75 | [039_bullish_2016-08_c3_hit.png](charts/hits/039_bullish_2016-08_c3_hit.png) |
| 40 | bullish | 2016-07 | 2016-08 | 2016-09 | True | +55.50 | [040_bullish_2016-09_c3_hit.png](charts/hits/040_bullish_2016-09_c3_hit.png) |
| 41 | bullish | 2016-08 | 2016-09 | 2016-10 | True | +27.25 | [041_bullish_2016-10_c3_hit.png](charts/hits/041_bullish_2016-10_c3_hit.png) |
| 42 | bullish | 2016-12 | 2017-01 | 2017-02 | True | +192.75 | [042_bullish_2017-02_c3_hit.png](charts/hits/042_bullish_2017-02_c3_hit.png) |
| 43 | bullish | 2017-01 | 2017-02 | 2017-03 | True | +91.50 | [043_bullish_2017-03_c3_hit.png](charts/hits/043_bullish_2017-03_c3_hit.png) |
| 44 | bullish | 2017-02 | 2017-03 | 2017-04 | True | +146.25 | [044_bullish_2017-04_c3_hit.png](charts/hits/044_bullish_2017-04_c3_hit.png) |
| 45 | bullish | 2017-03 | 2017-04 | 2017-05 | True | +220.25 | [045_bullish_2017-05_c3_hit.png](charts/hits/045_bullish_2017-05_c3_hit.png) |
| 46 | bullish | 2017-04 | 2017-05 | 2017-06 | True | +88.25 | [046_bullish_2017-06_c3_hit.png](charts/hits/046_bullish_2017-06_c3_hit.png) |
| 47 | bullish | 2017-07 | 2017-08 | 2017-09 | True | +18.75 | [047_bullish_2017-09_c3_hit.png](charts/hits/047_bullish_2017-09_c3_hit.png) |
| 48 | bullish | 2017-09 | 2017-10 | 2017-11 | True | +170.75 | [048_bullish_2017-11_c3_hit.png](charts/hits/048_bullish_2017-11_c3_hit.png) |
| 49 | bullish | 2017-10 | 2017-11 | 2017-12 | True | +116.25 | [049_bullish_2017-12_c3_hit.png](charts/hits/049_bullish_2017-12_c3_hit.png) |
| 50 | bullish | 2017-12 | 2018-01 | 2018-02 | False | -38.25 | [050_bullish_2018-02_c3_miss.png](charts/misses/050_bullish_2018-02_c3_miss.png) |
| 51 | bullish | 2018-04 | 2018-05 | 2018-06 | True | +335.00 | [051_bullish_2018-06_c3_hit.png](charts/hits/051_bullish_2018-06_c3_hit.png) |
| 52 | bullish | 2018-05 | 2018-06 | 2018-07 | True | +171.50 | [052_bullish_2018-07_c3_hit.png](charts/hits/052_bullish_2018-07_c3_hit.png) |
| 53 | bullish | 2018-07 | 2018-08 | 2018-09 | False | -1.25 | [053_bullish_2018-09_c3_miss.png](charts/misses/053_bullish_2018-09_c3_miss.png) |
| 54 | bearish | 2018-09 | 2018-10 | 2018-11 | True | +131.00 | [054_bearish_2018-11_c3_hit.png](charts/hits/054_bearish_2018-11_c3_hit.png) |
| 55 | bearish | 2018-11 | 2018-12 | 2019-01 | False | -316.00 | [055_bearish_2019-01_c3_miss.png](charts/misses/055_bearish_2019-01_c3_miss.png) |
| 56 | bullish | 2019-01 | 2019-02 | 2019-03 | True | +376.25 | [056_bullish_2019-03_c3_hit.png](charts/hits/056_bullish_2019-03_c3_hit.png) |
| 57 | bullish | 2019-02 | 2019-03 | 2019-04 | True | +334.75 | [057_bullish_2019-04_c3_hit.png](charts/hits/057_bullish_2019-04_c3_hit.png) |
| 58 | bullish | 2019-03 | 2019-04 | 2019-05 | False | -7.00 | [058_bullish_2019-05_c3_miss.png](charts/misses/058_bullish_2019-05_c3_miss.png) |
| 59 | bearish | 2019-04 | 2019-05 | 2019-06 | True | +188.00 | [059_bearish_2019-06_c3_hit.png](charts/hits/059_bearish_2019-06_c3_hit.png) |
| 60 | bullish | 2019-06 | 2019-07 | 2019-08 | False | -37.25 | [060_bullish_2019-08_c3_miss.png](charts/misses/060_bullish_2019-08_c3_miss.png) |
| 61 | bearish | 2019-07 | 2019-08 | 2019-09 | False | -356.25 | [061_bearish_2019-09_c3_miss.png](charts/misses/061_bearish_2019-09_c3_miss.png) |
| 62 | bullish | 2019-09 | 2019-10 | 2019-11 | True | +317.75 | [062_bullish_2019-11_c3_hit.png](charts/hits/062_bullish_2019-11_c3_hit.png) |
| 63 | bullish | 2019-10 | 2019-11 | 2019-12 | True | +384.75 | [063_bullish_2019-12_c3_hit.png](charts/hits/063_bullish_2019-12_c3_hit.png) |
| 64 | bullish | 2019-11 | 2019-12 | 2020-01 | True | +443.75 | [064_bullish_2020-01_c3_hit.png](charts/hits/064_bullish_2020-01_c3_hit.png) |
| 65 | bullish | 2019-12 | 2020-01 | 2020-02 | True | +475.75 | [065_bullish_2020-02_c3_hit.png](charts/hits/065_bullish_2020-02_c3_hit.png) |
| 66 | bearish | 2020-01 | 2020-02 | 2020-03 | True | +1497.50 | [066_bearish_2020-03_c3_hit.png](charts/hits/066_bearish_2020-03_c3_hit.png) |
| 67 | bearish | 2020-02 | 2020-03 | 2020-04 | False | -747.25 | [067_bearish_2020-04_c3_miss.png](charts/misses/067_bearish_2020-04_c3_miss.png) |
| 68 | bullish | 2020-04 | 2020-05 | 2020-06 | True | +692.25 | [068_bullish_2020-06_c3_hit.png](charts/hits/068_bullish_2020-06_c3_hit.png) |
| 69 | bullish | 2020-05 | 2020-06 | 2020-07 | True | +762.25 | [069_bullish_2020-07_c3_hit.png](charts/hits/069_bullish_2020-07_c3_hit.png) |
| 70 | bullish | 2020-06 | 2020-07 | 2020-08 | True | +1106.50 | [070_bullish_2020-08_c3_hit.png](charts/hits/070_bullish_2020-08_c3_hit.png) |
| 71 | bullish | 2020-07 | 2020-08 | 2020-09 | True | +300.25 | [071_bullish_2020-09_c3_hit.png](charts/hits/071_bullish_2020-09_c3_hit.png) |
| 72 | bullish | 2020-10 | 2020-11 | 2020-12 | True | +509.50 | [072_bullish_2020-12_c3_hit.png](charts/hits/072_bullish_2020-12_c3_hit.png) |
| 73 | bullish | 2020-11 | 2020-12 | 2021-01 | True | +681.50 | [073_bullish_2021-01_c3_hit.png](charts/hits/073_bullish_2021-01_c3_hit.png) |
| 74 | bullish | 2021-03 | 2021-04 | 2021-05 | False | -116.50 | [074_bullish_2021-05_c3_miss.png](charts/misses/074_bullish_2021-05_c3_miss.png) |
| 75 | bullish | 2021-05 | 2021-06 | 2021-07 | True | +535.50 | [075_bullish_2021-07_c3_hit.png](charts/hits/075_bullish_2021-07_c3_hit.png) |
| 76 | bullish | 2021-06 | 2021-07 | 2021-08 | True | +543.25 | [076_bullish_2021-08_c3_hit.png](charts/hits/076_bullish_2021-08_c3_hit.png) |
| 77 | bullish | 2021-07 | 2021-08 | 2021-09 | True | +31.50 | [077_bullish_2021-09_c3_hit.png](charts/hits/077_bullish_2021-09_c3_hit.png) |
| 78 | bullish | 2021-09 | 2021-10 | 2021-11 | True | +869.25 | [078_bullish_2021-11_c3_hit.png](charts/hits/078_bullish_2021-11_c3_hit.png) |
| 79 | bullish | 2021-10 | 2021-11 | 2021-12 | False | -108.00 | [079_bullish_2021-12_c3_miss.png](charts/misses/079_bullish_2021-12_c3_miss.png) |
| 80 | bearish | 2021-12 | 2022-01 | 2022-02 | True | +680.25 | [080_bearish_2022-02_c3_hit.png](charts/hits/080_bearish_2022-02_c3_hit.png) |
| 81 | bearish | 2022-03 | 2022-04 | 2022-05 | True | +1310.25 | [081_bearish_2022-05_c3_hit.png](charts/hits/081_bearish_2022-05_c3_hit.png) |
| 82 | bearish | 2022-04 | 2022-05 | 2022-06 | True | +422.75 | [082_bearish_2022-06_c3_hit.png](charts/hits/082_bearish_2022-06_c3_hit.png) |
| 83 | bearish | 2022-08 | 2022-09 | 2022-10 | True | +539.50 | [083_bearish_2022-10_c3_hit.png](charts/hits/083_bearish_2022-10_c3_hit.png) |
| 84 | bullish | 2022-10 | 2022-11 | 2022-12 | True | +220.25 | [084_bullish_2022-12_c3_hit.png](charts/hits/084_bullish_2022-12_c3_hit.png) |
| 85 | bullish | 2023-02 | 2023-03 | 2023-04 | True | +37.25 | [085_bullish_2023-04_c3_hit.png](charts/hits/085_bullish_2023-04_c3_hit.png) |
| 86 | bullish | 2023-04 | 2023-05 | 2023-06 | True | +905.50 | [086_bullish_2023-06_c3_hit.png](charts/hits/086_bullish_2023-06_c3_hit.png) |
| 87 | bullish | 2023-05 | 2023-06 | 2023-07 | True | +587.25 | [087_bullish_2023-07_c3_hit.png](charts/hits/087_bullish_2023-07_c3_hit.png) |
| 88 | bullish | 2023-06 | 2023-07 | 2023-08 | False | -173.50 | [088_bullish_2023-08_c3_miss.png](charts/misses/088_bullish_2023-08_c3_miss.png) |
| 89 | bearish | 2023-09 | 2023-10 | 2023-11 | False | -270.50 | [089_bearish_2023-11_c3_miss.png](charts/misses/089_bearish_2023-11_c3_miss.png) |
| 90 | bullish | 2023-10 | 2023-11 | 2023-12 | True | +956.75 | [090_bullish_2023-12_c3_hit.png](charts/hits/090_bullish_2023-12_c3_hit.png) |
| 91 | bullish | 2023-11 | 2023-12 | 2024-01 | True | +628.25 | [091_bullish_2024-01_c3_hit.png](charts/hits/091_bullish_2024-01_c3_hit.png) |
| 92 | bullish | 2023-12 | 2024-01 | 2024-02 | True | +351.25 | [092_bullish_2024-02_c3_hit.png](charts/hits/092_bullish_2024-02_c3_hit.png) |
| 93 | bullish | 2024-01 | 2024-02 | 2024-03 | True | +564.25 | [093_bullish_2024-03_c3_hit.png](charts/hits/093_bullish_2024-03_c3_hit.png) |
| 94 | bullish | 2024-02 | 2024-03 | 2024-04 | False | -98.00 | [094_bullish_2024-04_c3_miss.png](charts/misses/094_bullish_2024-04_c3_miss.png) |
| 95 | bearish | 2024-03 | 2024-04 | 2024-05 | False | -273.00 | [095_bearish_2024-05_c3_miss.png](charts/misses/095_bearish_2024-05_c3_miss.png) |
| 96 | bullish | 2024-05 | 2024-06 | 2024-07 | True | +612.75 | [096_bullish_2024-07_c3_hit.png](charts/hits/096_bullish_2024-07_c3_hit.png) |
| 97 | bullish | 2024-08 | 2024-09 | 2024-10 | True | +250.50 | [097_bullish_2024-10_c3_hit.png](charts/hits/097_bullish_2024-10_c3_hit.png) |
| 98 | bullish | 2024-10 | 2024-11 | 2024-12 | True | +1085.00 | [098_bullish_2024-12_c3_hit.png](charts/hits/098_bullish_2024-12_c3_hit.png) |
| 99 | bearish | 2025-02 | 2025-03 | 2025-04 | True | +2516.75 | [099_bearish_2025-04_c3_hit.png](charts/hits/099_bearish_2025-04_c3_hit.png) |
| 100 | bullish | 2025-04 | 2025-05 | 2025-06 | True | +1076.00 | [100_bullish_2025-06_c3_hit.png](charts/hits/100_bullish_2025-06_c3_hit.png) |
| 101 | bullish | 2025-05 | 2025-06 | 2025-07 | True | +910.25 | [101_bullish_2025-07_c3_hit.png](charts/hits/101_bullish_2025-07_c3_hit.png) |
| 102 | bullish | 2025-06 | 2025-07 | 2025-08 | True | +223.50 | [102_bullish_2025-08_c3_hit.png](charts/hits/102_bullish_2025-08_c3_hit.png) |
| 103 | bullish | 2025-08 | 2025-09 | 2025-10 | True | +1371.75 | [103_bullish_2025-10_c3_hit.png](charts/hits/103_bullish_2025-10_c3_hit.png) |
| 104 | bullish | 2025-09 | 2025-10 | 2025-11 | False | -133.00 | [104_bullish_2025-11_c3_miss.png](charts/misses/104_bullish_2025-11_c3_miss.png) |
| 105 | bearish | 2026-01 | 2026-02 | 2026-03 | True | +71.50 | [105_bearish_2026-03_c3_hit.png](charts/hits/105_bearish_2026-03_c3_hit.png) |

CSV outputs: `monthly_candles.csv` · `setups.csv` · `summary.csv` · `strat_2r_trades.csv` · `strat_3r_trades.csv` · `strat_clean_body_2r_trades.csv` · `strat_clean_body_3r_trades.csv` · `strat_swept_opposing_2r_trades.csv` · `strat_swept_opposing_3r_trades.csv`
