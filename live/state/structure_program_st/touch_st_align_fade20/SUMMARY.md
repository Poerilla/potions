# Structure-program ST — **touch_st_align_fade20** (NQ RTH)

15m swing structures (L-H-LL-HH / H-L-HH-LL), last-20 bull & bear lists, program flips after 2 opposing takeouts. Same as touch_st_align, but if still through for **20** consecutive minutes → **fade limit @ structure key** (opposite side, stop = key ±25) instead of waiting for continuation ST flip. Ladder 5@+25/±12 then +50/+200; fav ST→BE.

## Meta

- **variant:** touch_st_align_fade20
- **risk_pts:** 8.0
- **ready_day:** 2020-03-12
- **n_days:** 2011
- **n_trades:** 670
- **structs_bull_formed:** 634
- **structs_bear_formed:** 652
- **final_program:** buy
- **bull_list:** 20
- **bear_list:** 20

## Results

| metric | value |
|---|---|
| trades | 670 |
| net $ | 669587 |
| win% | 45.5 |
| PF | 1.342 |
| avg $/trade | 999.4 |
| long / short | 370 / 300 |
| MAE mean / median | 22.6 / 14.5 |
| MFE mean / median | 47.9 / 21.8 |
| scaled campaigns | 305 (46%) |

### By exit reason

| exit_reason | count | sum | mean |
|---|---|---|---|
| be_stop | 72 | -3240.0 | -45.0 |
| risk_stop | 77 | -884878.47 | -11491.92818181818 |
| scale_25+be_stop | 109 | 116395.0 | 1067.8440366972477 |
| scale_25+scale_50+be_stop | 103 | 746265.0 | 7245.291262135922 |
| scale_25+scale_50+runner_200 | 62 | 1702210.0 | 27455.0 |
| scale_25+scale_50+st_flip | 5 | 35100.0 | 7020.0 |
| scale_25+st_flip | 16 | 26130.0 | 1633.125 |
| scale_25+tight_stop | 10 | 550.0 | 55.0 |
| st_flip | 216 | -1068945.0 | -4948.819444444444 |

### By year

| year | count | sum | mean |
|---|---|---|---|
| 2020.0 | 91.0 | 122252.23000000001 | 1343.431098901099 |
| 2021.0 | 101.0 | 28421.83 | 281.40425742574257 |
| 2022.0 | 106.0 | 130255.94 | 1228.8296226415096 |
| 2023.0 | 117.0 | 23028.13 | 196.82162393162395 |
| 2024.0 | 115.0 | 15892.720000000001 | 138.19756521739131 |
| 2025.0 | 96.0 | 315196.73 | 3283.299270833333 |
| 2026.0 | 44.0 | 34538.95 | 784.9761363636363 |

### MAE / MFE profile

| cohort | n | mae_mean | mae_median | mae_p75 | mae_p90 | mae_p95 | mae_max | mfe_mean | mfe_median | mfe_p90 | pct_mae_le_10 | pct_mae_le_25 | pct_mae_le_50 | pct_mae_le_75 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 670 | 22.6 | 14.5 | 26.25 | 47.03 | 71.75 | 414.75 | 47.92 | 21.75 | 180.35 | 36.7 | 73.1 | 90.7 | 95.4 |
| winners | 305 | 21.43 | 14.5 | 24.25 | 37.4 | 57.15 | 414.75 | 94.5 | 60.25 | 204.25 | 35.1 | 77.4 | 93.8 | 96.1 |
| losers | 365 | 23.58 | 14.5 | 31.75 | 51.75 | 75.25 | 203.5 | 9.0 | 7.0 | 21.0 | 38.1 | 69.6 | 88.2 | 94.8 |

### MAE histogram (pts)

| mae_bucket | n | pct |
|---|---|---|
| 0-5 | 133 | 19.9 |
| 5-10 | 113 | 16.9 |
| 10-15 | 95 | 14.2 |
| 15-25 | 149 | 22.2 |
| 25-35 | 69 | 10.3 |
| 35-50 | 49 | 7.3 |
| 50-75 | 31 | 4.6 |
| 75-100 | 14 | 2.1 |
| 100-150 | 9 | 1.3 |
| 150-250 | 7 | 1.0 |
| 250+ | 1 | 0.1 |

### Extension hits (25 / 100 / 200 pts MFE while open)

Path touch rates. `*_no_risk_mae` = also never saw MAE ≥ risk (did not tag a full risk-stop drawdown before/while extending).

| cohort | n | pct_hit_25 | pct_hit_100 | pct_hit_200 | pct_hit_25_no_risk_mae | pct_hit_100_no_risk_mae | pct_hit_200_no_risk_mae | mfe_mean | mfe_median | mfe_p90 | mfe_max | st_be_share_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 670 | 45.7 | 14.8 | 9.3 | 18.2 | 7.3 | 5.2 | 47.92 | 21.75 | 180.35 | 431.25 | 36.9 |
| winners | 305 | 100.0 | 32.5 | 20.3 | 39.7 | 16.1 | 11.5 | 94.5 | 60.25 | 204.25 | 431.25 | 57.4 |
| losers | 365 | 0.3 | 0.0 | 0.0 | 0.3 | 0.0 | 0.0 | 9.0 | 7.0 | 21.0 | 30.25 | 19.7 |
| st_be_armed | 247 | 71.3 | 32.0 | 17.4 | 42.1 | 16.2 | 10.5 | 85.31 | 55.5 | 202.75 | 431.25 | 100.0 |

- Favourable ST→BE armed on **247 / 670** trades (37%).
