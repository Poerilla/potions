# Structure-program ST — **touch_st_align** (NQ RTH)

15m swing structures (L-H-LL-HH / H-L-HH-LL), last-20 bull & bear lists, program flips after 2 opposing takeouts. Structure key touch+trade-through → wait ST flip aligned with program → **market entry** on flip; initial SL = new ST trail; **15 contracts** — 5 @ +25 (then SL→±12), 5 @ +50, 5 @ +200; fav ST→BE. Pending ≤3 RTH closes.

## Meta

- **variant:** touch_st_align
- **risk_pts:** 8.0
- **ready_day:** 2020-03-12
- **n_days:** 2011
- **n_trades:** 1215
- **structs_bull_formed:** 634
- **structs_bear_formed:** 652
- **final_program:** buy
- **bull_list:** 20
- **bear_list:** 20

## Results

| metric | value |
|---|---|
| trades | 1215 |
| net $ | 1369068 |
| win% | 57.7 |
| PF | 1.297 |
| avg $/trade | 1126.8 |
| long / short | 580 / 635 |
| MAE mean / median | 29.1 / 19.5 |
| MFE mean / median | 59.9 / 29.8 |
| scaled campaigns | 701 (58%) |

### By exit reason

| exit_reason | count | sum | mean |
|---|---|---|---|
| be_stop | 9 | -405.0 | -45.0 |
| risk_stop | 197 | -2271372.42 | -11529.80923857868 |
| scale_25+be_stop | 225 | 182775.0 | 812.3333333333334 |
| scale_25+scale_50+be_stop | 240 | 1743600.0 | 7265.0 |
| scale_25+scale_50+runner_200 | 140 | 3843700.0 | 27455.0 |
| scale_25+scale_50+st_flip | 16 | 112530.0 | 7033.125 |
| scale_25+st_flip | 59 | 96845.0 | 1641.4406779661017 |
| scale_25+tight_stop | 21 | 1155.0 | 55.0 |
| st_flip | 308 | -2339760.0 | -7596.623376623376 |

### By year

| year | count | sum | mean |
|---|---|---|---|
| 2020.0 | 148.0 | 135620.47999999998 | 916.3545945945945 |
| 2021.0 | 201.0 | 156720.12 | 779.7020895522388 |
| 2022.0 | 187.0 | 167962.41 | 898.194705882353 |
| 2023.0 | 204.0 | 124494.21 | 610.2657352941177 |
| 2024.0 | 196.0 | 326928.72 | 1668.0036734693876 |
| 2025.0 | 145.0 | 614171.36 | 4235.664551724138 |
| 2026.0 | 134.0 | -156829.72000000003 | -1170.3710447761196 |

### MAE / MFE profile

| cohort | n | mae_mean | mae_median | mae_p75 | mae_p90 | mae_p95 | mae_max | mfe_mean | mfe_median | mfe_p90 | pct_mae_le_10 | pct_mae_le_25 | pct_mae_le_50 | pct_mae_le_75 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 1215 | 29.14 | 19.5 | 33.75 | 57.45 | 78.8 | 427.5 | 59.91 | 29.75 | 201.0 | 22.6 | 61.6 | 86.8 | 94.2 |
| winners | 701 | 24.07 | 15.5 | 26.25 | 44.25 | 68.0 | 427.5 | 96.29 | 61.5 | 206.0 | 31.2 | 73.5 | 92.0 | 95.7 |
| losers | 514 | 36.04 | 27.25 | 44.0 | 68.92 | 83.96 | 288.25 | 10.28 | 9.25 | 21.0 | 10.9 | 45.5 | 79.8 | 92.0 |

### MAE histogram (pts)

| mae_bucket | n | pct |
|---|---|---|
| 0-5 | 111 | 9.1 |
| 5-10 | 164 | 13.5 |
| 10-15 | 167 | 13.7 |
| 15-25 | 307 | 25.3 |
| 25-35 | 179 | 14.7 |
| 35-50 | 127 | 10.5 |
| 50-75 | 89 | 7.3 |
| 75-100 | 28 | 2.3 |
| 100-150 | 23 | 1.9 |
| 150-250 | 14 | 1.2 |
| 250+ | 6 | 0.5 |

### Extension hits (25 / 100 / 200 pts MFE while open)

Path touch rates. `*_no_risk_mae` = also never saw MAE ≥ risk (did not tag a full risk-stop drawdown before/while extending).

| cohort | n | pct_hit_25 | pct_hit_100 | pct_hit_200 | pct_hit_25_no_risk_mae | pct_hit_100_no_risk_mae | pct_hit_200_no_risk_mae | mfe_mean | mfe_median | mfe_p90 | mfe_max | st_be_share_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 1215 | 57.7 | 19.9 | 11.5 | 21.2 | 9.9 | 6.3 | 59.91 | 29.75 | 201.0 | 493.5 | 30.9 |
| winners | 701 | 100.0 | 34.5 | 20.0 | 36.7 | 17.1 | 11.0 | 96.29 | 61.5 | 206.0 | 493.5 | 52.2 |
| losers | 514 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 10.28 | 9.25 | 21.0 | 24.75 | 1.8 |
| st_be_armed | 375 | 97.6 | 50.7 | 24.8 | 50.9 | 23.7 | 12.8 | 119.56 | 101.25 | 209.4 | 416.5 | 100.0 |

- Favourable ST→BE armed on **375 / 1215** trades (31%).
