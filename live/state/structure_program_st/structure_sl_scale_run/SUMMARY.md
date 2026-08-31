# Structure-program ST — **structure_sl_scale_run** (NQ RTH)

15m swing structures (L-H-LL-HH / H-L-HH-LL), last-20 bull & bear lists, program flips after 2 opposing takeouts. ST-break → limit @ structure; **risk 8 pts**; **15 contracts** — 5 @ +22 pts, 5 @ +50, 5 @ +200; favourable ST-flip → BE (hold), adverse ST-flip flattens. Pending up to 3 RTH closes. Extension hits profiled.

## Meta

- **variant:** structure_sl_scale_run
- **risk_pts:** 8.0
- **ready_day:** 2020-03-12
- **n_days:** 2011
- **n_trades:** 325
- **structs_bull_formed:** 634
- **structs_bear_formed:** 652
- **final_program:** buy
- **bull_list:** 20
- **bear_list:** 20

## Results

| metric | value |
|---|---|
| trades | 325 |
| net $ | 2032875 |
| win% | 49.8 |
| PF | 9.605 |
| avg $/trade | 6255.0 |
| long / short | 169 / 156 |
| MAE mean / median | 9.9 / 5.2 |
| MFE mean / median | 72.1 / 22.2 |
| scaled campaigns | 162 (50%) |

### By exit reason

| exit_reason | count | sum | mean |
|---|---|---|---|
| be_stop | 52 | -2340.0 | -45.0 |
| risk_stop | 88 | -215160.0 | -2445.0 |
| scale_22+be_stop | 34 | 73270.0 | 2155.0 |
| scale_22+scale_50+be_stop | 64 | 457920.0 | 7155.0 |
| scale_22+scale_50+runner_200 | 64 | 1737920.0 | 27155.0 |
| st_flip | 23 | -18735.0 | -814.5652173913044 |

### By year

| year | count | sum | mean |
|---|---|---|---|
| 2020.0 | 51.0 | 238055.0 | 4667.745098039216 |
| 2021.0 | 48.0 | 189565.0 | 3949.2708333333335 |
| 2022.0 | 44.0 | 263820.0 | 5995.909090909091 |
| 2023.0 | 68.0 | 463115.0 | 6810.514705882353 |
| 2024.0 | 58.0 | 411840.0 | 7100.689655172414 |
| 2025.0 | 47.0 | 395885.0 | 8423.08510638298 |
| 2026.0 | 9.0 | 70595.0 | 7843.888888888889 |

### MAE / MFE profile

| cohort | n | mae_mean | mae_median | mae_p75 | mae_p90 | mae_p95 | mae_max | mfe_mean | mfe_median | mfe_p90 | pct_mae_le_10 | pct_mae_le_25 | pct_mae_le_50 | pct_mae_le_75 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 325 | 9.91 | 5.25 | 10.25 | 16.9 | 22.1 | 281.5 | 72.14 | 22.25 | 205.65 | 73.8 | 95.7 | 98.5 | 98.5 |
| winners | 162 | 10.76 | 1.38 | 6.75 | 17.48 | 32.66 | 281.5 | 138.0 | 147.12 | 214.9 | 81.5 | 93.2 | 96.9 | 96.9 |
| losers | 163 | 9.07 | 8.25 | 11.38 | 16.7 | 18.98 | 35.25 | 6.67 | 5.25 | 15.85 | 66.3 | 98.2 | 100.0 | 100.0 |

### MAE histogram (pts)

| mae_bucket | n | pct |
|---|---|---|
| 0-5 | 156 | 48.0 |
| 5-10 | 84 | 25.8 |
| 10-15 | 37 | 11.4 |
| 15-25 | 34 | 10.5 |
| 25-35 | 5 | 1.5 |
| 35-50 | 4 | 1.2 |
| 50-75 | 0 | 0.0 |
| 75-100 | 1 | 0.3 |
| 100-150 | 1 | 0.3 |
| 150-250 | 1 | 0.3 |
| 250+ | 2 | 0.6 |

### Extension hits (25 / 100 / 200 pts MFE while open)

Path touch rates. `*_no_risk_mae` = also never saw MAE ≥ risk (did not tag a full risk-stop drawdown before/while extending).

| cohort | n | pct_hit_25 | pct_hit_100 | pct_hit_200 | pct_hit_25_no_risk_mae | pct_hit_100_no_risk_mae | pct_hit_200_no_risk_mae | mfe_mean | mfe_median | mfe_p90 | mfe_max | st_be_share_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 325 | 48.3 | 30.5 | 19.7 | 37.5 | 25.2 | 19.7 | 72.14 | 22.25 | 205.65 | 321.0 | 60.9 |
| winners | 162 | 96.3 | 61.1 | 39.5 | 74.7 | 50.6 | 39.5 | 138.0 | 147.12 | 214.9 | 321.0 | 90.1 |
| losers | 163 | 0.6 | 0.0 | 0.0 | 0.6 | 0.0 | 0.0 | 6.67 | 5.25 | 15.85 | 29.25 | 31.9 |
| st_be_armed | 198 | 72.2 | 48.0 | 30.3 | 55.6 | 39.4 | 30.3 | 109.41 | 96.12 | 210.35 | 321.0 | 100.0 |

- Favourable ST→BE armed on **198 / 325** trades (61%).
