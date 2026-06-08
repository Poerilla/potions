# MNQ Monthly Candlestick Theory Study

## Theory Summary

| Direction | Setups | Hits | Hit Rate | C3 Close Beyond | Close Rate | Avg Extension | Median Extension | Avg Adverse | Worst Adverse |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bearish | 11 | 7 | 63.64% | 3 | 27.27% | 1006.86 | 680.50 | 117.39 | 738.25 |
| bullish | 35 | 29 | 82.86% | 19 | 54.29% | 601.02 | 563.50 | 91.29 | 718.75 |
| all | 46 | 36 | 78.26% | 22 | 47.83% | 679.93 | 575.25 | 97.53 | 738.25 |

## Strategy: Breakout-Candle Entry · TP = 2R

Opening candle = first daily bar of C3.  R = its H−L.
Breakout candle: first bar that closes beyond opening candle H (bull) or L (bear).
Entry at breakout close.  SL = entry ± 2R.  TP = entry ± 2R.
open_eom = filled but C3 ended before TP/SL (excluded from PnL).

| Direction | Setups | No Breakout | Resolved | open_eom | TP | SL | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg Breakout Day | Avg days→TP | Avg days→SL | Total PnL (R) | Total PnL (pts) | Swept Opposing (n/%) | Clean Body→TP (n/%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 35 | 7 | 22 | 6 | 18 | 4 | 81.82% | 0.740 | 163.12 | 5.7 | 6.0 | 2.5 | +28.00 | +3380.50 | 11 / 39.3% | 15 / 83.3% |
| bearish | 11 | 4 | 6 | 1 | 5 | 1 | 83.33% | 0.421 | 195.50 | 6.1 | 4.4 | 2.0 | +8.00 | +2692.00 | 6 / 85.7% | 4 / 80.0% |
| all | 46 | 11 | 28 | 7 | 23 | 5 | 82.14% | 0.672 | 170.06 | 5.8 | 5.7 | 2.4 | +36.00 | +6072.50 | 17 / 48.6% | 19 / 82.6% |

## Strategy: Breakout-Candle Entry · TP = 3R

Same entry/SL rules.  TP = entry ± 3R.

| Direction | Setups | No Breakout | Resolved | open_eom | TP | SL | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg Breakout Day | Avg days→TP | Avg days→SL | Total PnL (R) | Total PnL (pts) | Swept Opposing (n/%) | Clean Body→TP (n/%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 35 | 7 | 20 | 8 | 15 | 5 | 75.00% | 0.819 | 182.68 | 5.7 | 5.6 | 5.0 | +35.00 | +2926.25 | 11 / 39.3% | 13 / 86.7% |
| bearish | 11 | 4 | 6 | 1 | 5 | 1 | 83.33% | 0.506 | 218.79 | 6.1 | 6.2 | 2.0 | +13.00 | +4159.00 | 6 / 85.7% | 4 / 80.0% |
| all | 46 | 11 | 26 | 9 | 20 | 6 | 76.92% | 0.746 | 191.01 | 5.8 | 5.8 | 4.5 | +48.00 | +7085.25 | 17 / 48.6% | 17 / 85.0% |

## Variant: Clean-Body-Exit · TP = 2R

Entry at breakout close.  Exit when any bar CLOSES back through OC boundary
(close < OC_high for bull, close > OC_low for bear).  TP = entry ± 2R.
TP takes priority over close-exit on the same bar.

| Direction | Active | No Breakout | Skipped | Resolved | open_eom | TP | Loss | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg days→TP | Avg days→Loss | Total PnL (R) | Total PnL (pts) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 28 | 7 | 0 | 27 | 1 | 16 | 11 | 59.26% | 1.217 | 149.61 | 3.6 | 4.6 | +15.650 | +678.25 |
| bearish | 7 | 4 | 0 | 6 | 1 | 5 | 1 | 83.33% | 0.736 | 151.92 | 2.0 | 3.0 | +9.670 | +2225.25 |
| all | 35 | 11 | 0 | 33 | 2 | 21 | 12 | 63.64% | 1.129 | 150.03 | 3.2 | 4.5 | +25.320 | +2903.50 |

## Variant: Clean-Body-Exit · TP = 3R

Same close-based exit.  TP = entry ± 3R.

| Direction | Active | No Breakout | Skipped | Resolved | open_eom | TP | Loss | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg days→TP | Avg days→Loss | Total PnL (R) | Total PnL (pts) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 28 | 7 | 0 | 27 | 1 | 14 | 13 | 51.85% | 1.277 | 162.02 | 4.0 | 6.0 | +24.150 | +783.00 |
| bearish | 7 | 4 | 0 | 6 | 1 | 5 | 1 | 83.33% | 0.905 | 175.21 | 3.2 | 3.0 | +14.670 | +3404.50 |
| all | 35 | 11 | 0 | 33 | 2 | 19 | 14 | 57.58% | 1.209 | 164.42 | 3.8 | 5.8 | +38.830 | +4187.50 |

## Variant: Swept-Opposing-Only · TP = 2R

Only trades setups where a bar before the breakout swept OC's opposing extreme.
SL = OC_low (bull) / OC_high (bear).  TP = entry ± 2R (R = OC range).  Skipped = no sweep.

| Direction | Active | No Breakout | Skipped | Resolved | open_eom | TP | Loss | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg days→TP | Avg days→Loss | Total PnL (R) | Total PnL (pts) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 11 | 7 | 17 | 9 | 2 | 7 | 2 | 77.78% | 0.983 | 120.19 | 4.6 | 3.0 | +11.500 | +682.25 |
| bearish | 6 | 4 | 1 | 5 | 1 | 4 | 1 | 80.00% | 0.874 | 175.30 | 5.0 | 2.0 | +6.460 | +1883.75 |
| all | 17 | 11 | 18 | 14 | 3 | 11 | 3 | 78.57% | 0.944 | 139.88 | 4.7 | 2.7 | +17.970 | +2566.00 |

## Variant: Swept-Opposing-Only · TP = 3R

Same SL rules.  TP = entry ± 3R.

| Direction | Active | No Breakout | Skipped | Resolved | open_eom | TP | Loss | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg days→TP | Avg days→Loss | Total PnL (R) | Total PnL (pts) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 11 | 7 | 17 | 8 | 3 | 6 | 2 | 75.00% | 1.007 | 103.41 | 1.7 | 3.0 | +15.500 | +389.50 |
| bearish | 6 | 4 | 1 | 5 | 1 | 4 | 1 | 80.00% | 1.077 | 203.25 | 7.2 | 2.0 | +10.460 | +2918.75 |
| all | 17 | 11 | 18 | 13 | 4 | 10 | 3 | 76.92% | 1.034 | 141.81 | 3.9 | 2.7 | +25.970 | +3308.25 |

## Skipped / Failure Sweep Context

- High failure sweeps: 20
- Low failure sweeps: 22
- Unique non-signal failure-sweep months: 32
- Non-signal rolling windows: 35

## Charts

- [All C3 occurrences timeline](charts/timeline_all_c3.png)
- [Daily C3 chart index](charts/daily/INDEX.md)

| Setup | Direction | C1 | C2 | C3 | Hit | Extension | Chart |
|---:|---|---|---|---|---|---:|---|
| 1 | bullish | 2019-06 | 2019-07 | 2019-08 | False | -37.25 | [001_bullish_2019-08_c3_miss.png](charts/misses/001_bullish_2019-08_c3_miss.png) |
| 2 | bearish | 2019-07 | 2019-08 | 2019-09 | False | -356.50 | [002_bearish_2019-09_c3_miss.png](charts/misses/002_bearish_2019-09_c3_miss.png) |
| 3 | bullish | 2019-09 | 2019-10 | 2019-11 | True | +316.75 | [003_bullish_2019-11_c3_hit.png](charts/hits/003_bullish_2019-11_c3_hit.png) |
| 4 | bullish | 2019-10 | 2019-11 | 2019-12 | True | +384.50 | [004_bullish_2019-12_c3_hit.png](charts/hits/004_bullish_2019-12_c3_hit.png) |
| 5 | bullish | 2019-11 | 2019-12 | 2020-01 | True | +444.25 | [005_bullish_2020-01_c3_hit.png](charts/hits/005_bullish_2020-01_c3_hit.png) |
| 6 | bullish | 2019-12 | 2020-01 | 2020-02 | True | +475.50 | [006_bullish_2020-02_c3_hit.png](charts/hits/006_bullish_2020-02_c3_hit.png) |
| 7 | bearish | 2020-01 | 2020-02 | 2020-03 | True | +1495.50 | [007_bearish_2020-03_c3_hit.png](charts/hits/007_bearish_2020-03_c3_hit.png) |
| 8 | bearish | 2020-02 | 2020-03 | 2020-04 | False | -746.75 | [008_bearish_2020-04_c3_miss.png](charts/misses/008_bearish_2020-04_c3_miss.png) |
| 9 | bullish | 2020-04 | 2020-05 | 2020-06 | True | +692.00 | [009_bullish_2020-06_c3_hit.png](charts/hits/009_bullish_2020-06_c3_hit.png) |
| 10 | bullish | 2020-05 | 2020-06 | 2020-07 | True | +762.25 | [010_bullish_2020-07_c3_hit.png](charts/hits/010_bullish_2020-07_c3_hit.png) |
| 11 | bullish | 2020-06 | 2020-07 | 2020-08 | True | +1106.75 | [011_bullish_2020-08_c3_hit.png](charts/hits/011_bullish_2020-08_c3_hit.png) |
| 12 | bullish | 2020-07 | 2020-08 | 2020-09 | True | +301.00 | [012_bullish_2020-09_c3_hit.png](charts/hits/012_bullish_2020-09_c3_hit.png) |
| 13 | bullish | 2020-10 | 2020-11 | 2020-12 | True | +510.25 | [013_bullish_2020-12_c3_hit.png](charts/hits/013_bullish_2020-12_c3_hit.png) |
| 14 | bullish | 2020-11 | 2020-12 | 2021-01 | True | +681.50 | [014_bullish_2021-01_c3_hit.png](charts/hits/014_bullish_2021-01_c3_hit.png) |
| 15 | bullish | 2021-03 | 2021-04 | 2021-05 | False | -116.50 | [015_bullish_2021-05_c3_miss.png](charts/misses/015_bullish_2021-05_c3_miss.png) |
| 16 | bullish | 2021-05 | 2021-06 | 2021-07 | True | +535.25 | [016_bullish_2021-07_c3_hit.png](charts/hits/016_bullish_2021-07_c3_hit.png) |
| 17 | bullish | 2021-06 | 2021-07 | 2021-08 | True | +543.00 | [017_bullish_2021-08_c3_hit.png](charts/hits/017_bullish_2021-08_c3_hit.png) |
| 18 | bullish | 2021-07 | 2021-08 | 2021-09 | True | +31.50 | [018_bullish_2021-09_c3_hit.png](charts/hits/018_bullish_2021-09_c3_hit.png) |
| 19 | bullish | 2021-09 | 2021-10 | 2021-11 | True | +870.50 | [019_bullish_2021-11_c3_hit.png](charts/hits/019_bullish_2021-11_c3_hit.png) |
| 20 | bullish | 2021-10 | 2021-11 | 2021-12 | False | -109.00 | [020_bullish_2021-12_c3_miss.png](charts/misses/020_bullish_2021-12_c3_miss.png) |
| 21 | bearish | 2021-12 | 2022-01 | 2022-02 | True | +680.50 | [021_bearish_2022-02_c3_hit.png](charts/hits/021_bearish_2022-02_c3_hit.png) |
| 22 | bearish | 2022-03 | 2022-04 | 2022-05 | True | +1311.75 | [022_bearish_2022-05_c3_hit.png](charts/hits/022_bearish_2022-05_c3_hit.png) |
| 23 | bearish | 2022-04 | 2022-05 | 2022-06 | True | +422.50 | [023_bearish_2022-06_c3_hit.png](charts/hits/023_bearish_2022-06_c3_hit.png) |
| 24 | bearish | 2022-08 | 2022-09 | 2022-10 | True | +540.00 | [024_bearish_2022-10_c3_hit.png](charts/hits/024_bearish_2022-10_c3_hit.png) |
| 25 | bullish | 2022-10 | 2022-11 | 2022-12 | True | +211.50 | [025_bullish_2022-12_c3_hit.png](charts/hits/025_bullish_2022-12_c3_hit.png) |
| 26 | bullish | 2023-02 | 2023-03 | 2023-04 | True | +37.25 | [026_bullish_2023-04_c3_hit.png](charts/hits/026_bullish_2023-04_c3_hit.png) |
| 27 | bullish | 2023-04 | 2023-05 | 2023-06 | True | +905.50 | [027_bullish_2023-06_c3_hit.png](charts/hits/027_bullish_2023-06_c3_hit.png) |
| 28 | bullish | 2023-05 | 2023-06 | 2023-07 | True | +587.00 | [028_bullish_2023-07_c3_hit.png](charts/hits/028_bullish_2023-07_c3_hit.png) |
| 29 | bullish | 2023-06 | 2023-07 | 2023-08 | False | -173.50 | [029_bullish_2023-08_c3_miss.png](charts/misses/029_bullish_2023-08_c3_miss.png) |
| 30 | bearish | 2023-09 | 2023-10 | 2023-11 | False | -274.50 | [030_bearish_2023-11_c3_miss.png](charts/misses/030_bearish_2023-11_c3_miss.png) |
| 31 | bullish | 2023-10 | 2023-11 | 2023-12 | True | +957.75 | [031_bullish_2023-12_c3_hit.png](charts/hits/031_bullish_2023-12_c3_hit.png) |
| 32 | bullish | 2023-11 | 2023-12 | 2024-01 | True | +628.50 | [032_bullish_2024-01_c3_hit.png](charts/hits/032_bullish_2024-01_c3_hit.png) |
| 33 | bullish | 2023-12 | 2024-01 | 2024-02 | True | +351.00 | [033_bullish_2024-02_c3_hit.png](charts/hits/033_bullish_2024-02_c3_hit.png) |
| 34 | bullish | 2024-01 | 2024-02 | 2024-03 | True | +563.50 | [034_bullish_2024-03_c3_hit.png](charts/hits/034_bullish_2024-03_c3_hit.png) |
| 35 | bullish | 2024-02 | 2024-03 | 2024-04 | False | -97.25 | [035_bullish_2024-04_c3_miss.png](charts/misses/035_bullish_2024-04_c3_miss.png) |
| 36 | bearish | 2024-03 | 2024-04 | 2024-05 | False | -272.25 | [036_bearish_2024-05_c3_miss.png](charts/misses/036_bearish_2024-05_c3_miss.png) |
| 37 | bullish | 2024-05 | 2024-06 | 2024-07 | True | +612.00 | [037_bullish_2024-07_c3_hit.png](charts/hits/037_bullish_2024-07_c3_hit.png) |
| 38 | bullish | 2024-08 | 2024-09 | 2024-10 | True | +252.00 | [038_bullish_2024-10_c3_hit.png](charts/hits/038_bullish_2024-10_c3_hit.png) |
| 39 | bullish | 2024-10 | 2024-11 | 2024-12 | True | +1086.00 | [039_bullish_2024-12_c3_hit.png](charts/hits/039_bullish_2024-12_c3_hit.png) |
| 40 | bearish | 2025-02 | 2025-03 | 2025-04 | True | +2524.25 | [040_bearish_2025-04_c3_hit.png](charts/hits/040_bearish_2025-04_c3_hit.png) |
| 41 | bullish | 2025-04 | 2025-05 | 2025-06 | True | +1075.25 | [041_bullish_2025-06_c3_hit.png](charts/hits/041_bullish_2025-06_c3_hit.png) |
| 42 | bullish | 2025-05 | 2025-06 | 2025-07 | True | +914.00 | [042_bullish_2025-07_c3_hit.png](charts/hits/042_bullish_2025-07_c3_hit.png) |
| 43 | bullish | 2025-06 | 2025-07 | 2025-08 | True | +221.00 | [043_bullish_2025-08_c3_hit.png](charts/hits/043_bullish_2025-08_c3_hit.png) |
| 44 | bullish | 2025-08 | 2025-09 | 2025-10 | True | +1372.25 | [044_bullish_2025-10_c3_hit.png](charts/hits/044_bullish_2025-10_c3_hit.png) |
| 45 | bullish | 2025-09 | 2025-10 | 2025-11 | False | -133.75 | [045_bullish_2025-11_c3_miss.png](charts/misses/045_bullish_2025-11_c3_miss.png) |
| 46 | bearish | 2026-01 | 2026-02 | 2026-03 | True | +73.50 | [046_bearish_2026-03_c3_hit.png](charts/hits/046_bearish_2026-03_c3_hit.png) |

CSV outputs: `monthly_candles.csv` · `setups.csv` · `summary.csv` · `strat_2r_trades.csv` · `strat_3r_trades.csv` · `strat_clean_body_2r_trades.csv` · `strat_clean_body_3r_trades.csv` · `strat_swept_opposing_2r_trades.csv` · `strat_swept_opposing_3r_trades.csv`
