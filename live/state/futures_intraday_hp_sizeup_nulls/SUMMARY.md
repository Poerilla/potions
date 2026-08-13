# Futures HP size-up nulls (`futures_intraday_hp_sizeup_v1`)

Question: if we add the same extra capital to the same number of
baseline campaigns, does the HP condition beat random placement of
that **incremental sleeve**?

Placebo: year|month boost-count matched (never stratifies on the
tested feature). Also: clustered timing shifts, selection-aware
master null, nested discovery WF (HP coverage ≤35%) + frozen-candidate WF.

Linear 2×/3×/4× tables below are **sizing sensitivity only** — not
validation. Each intended multiplier needs its own null suite.

## Decision rule

- **SIZE-UP VALIDATED** — causal, coverage <35%, `p_placebo≤0.05`,
  `p_shift≤0.05`, `p_master≤0.05`, frozen WF acceptable,
  full-book stress ≤1.35× baseline. Authorized: shadow → controlled paper.
- **PROVISIONAL PAPER** — same gates except `0.05 < p_master ≤ 0.10`.
  Shadow / controlled paper only — **no** historical size-up promotion claim.
- **RISK-BUDGET PROFILE** — `p_master > 0.10` or WF fails (or coverage too
  broad). Sensitivity / stress research only — not an HP-size deployment.
- **NOT VALIDATED** — fails equal-added random exposure / timing / causal.
- **PENDING** — required null/multiplier replay missing.

## Pair results (matched-added-exposure)

| decision | book | condition=bucket | mult | hp% | inc net | inc N/S | p_plac N/S | p_shift | p_master | WF+ | reapp |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SIZE-UP VALIDATED | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 1.25× | 28% | +39544 | 22.98 | 0.007 | 0.006 | 0.010 | 100% | 2 |
| NOT VALIDATED | es_prior_opposed_legacy | Week of month=1 | 1.25× | 29% | +40781 | 10.91 | 0.253 | 0.199 | 0.749 | 100% | 0 |
| NOT VALIDATED | es_prior_opposed_legacy | Prior RTH close location=prior_close_mid_third | 1.25× | 25% | +29217 | 10.56 | 0.092 | 0.083 | 0.782 | 100% | 0 |
| NOT VALIDATED | es_st_pmc_ma_bull | Day of week=Tuesday | 1.25× | 22% | +16134 | 5.13 | 0.082 | 0.065 | 0.174 | 71% | 0 |
| NOT VALIDATED | es_st_pmc_ma_bull | ST-event age=st_age_gt180m | 1.25× | 28% | +17612 | 3.70 | 0.084 | 0.082 | 0.437 | 71% | 0 |
| NOT VALIDATED | es_st_pmc_ma_bull | Prior RTH range percentile=prior_range_norm | 1.25× | 26% | +14238 | 2.83 | 0.906 | 0.691 | 0.695 | 86% | 0 |
| NOT VALIDATED | nq_or_complement_skipflat | Day of week=Thursday | 1.25× | 20% | +63732 | 5.16 | 0.067 | 0.069 | 0.587 | 80% | 0 |
| NOT VALIDATED | nq_or_complement_skipflat | Opening 15m range vs ATR=or_norm | 1.25× | 29% | +106565 | 4.74 | 0.026 | 0.085 | 0.717 | 100% | 2 |
| NOT VALIDATED | nq_or_complement_skipflat | Opening 15m volume percentile=vol_low | 1.25× | 29% | +49564 | 4.63 | 0.051 | 0.099 | 0.739 | 60% | 0 |
| PROVISIONAL PAPER | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 1.25× | 30% | +145488 | 29.31 | 0.008 | 0.005 | 0.088 | 100% | 1 |
| NOT VALIDATED | nq_prior_opposed_rl | ST-event age=st_age_30_90m | 1.25× | 27% | +125654 | 20.73 | 0.056 | 0.043 | 0.659 | 80% | 0 |
| NOT VALIDATED | nq_prior_opposed_rl | NQ-ES dispersion=disp_mid | 1.25× | 32% | +121080 | 15.99 | 0.182 | 0.166 | 0.938 | 100% | 2 |
| NOT VALIDATED | nq_st_pmc_3r | Overnight compression=on_comp | 1.25× | 30% | +34984 | 23.01 | 0.232 | 0.063 | 0.226 | 100% | 0 |
| RISK-BUDGET PROFILE | nq_st_pmc_3r | Entry hour (NY)=11 | 1.25× | 8% | +15937 | 21.11 | 0.023 | 0.011 | 0.445 | 62% | 0 |
| NOT VALIDATED | nq_st_pmc_3r | Hourly RSI bucket=rsi_55_70 | 1.25× | 32% | +42846 | 20.25 | 0.164 | 0.052 | 0.491 | 100% | 5 |
| RISK-BUDGET PROFILE | nq_v2b_s113 | Prior RTH close location=prior_close_mid_third | 1.25× | 24% | +123947 | 6.06 | 0.027 | 0.047 | 0.321 | 100% | 0 |
| NOT VALIDATED | nq_v2b_s113 | Opening 15m range vs ATR=or_norm | 1.25× | 30% | +155211 | 6.04 | 0.035 | 0.053 | 0.301 | 100% | 2 |
| NOT VALIDATED | nq_v2b_s113 | Overnight range third=on_lower | 1.25× | 33% | +116196 | 4.51 | 0.205 | 0.156 | 0.727 | 80% | 0 |
| SIZE-UP VALIDATED | ym_prior_opposed_rl | Overnight range third=on_middle | 1.25× | 25% | +29468 | 14.17 | 0.020 | 0.017 | 0.044 | 100% | 0 |
| NOT VALIDATED | ym_prior_opposed_rl | Month=12 | 1.25× | 9% | +17204 | 10.83 | 1.000 | 0.512 | 0.238 | 60% | 0 |
| RISK-BUDGET PROFILE | ym_prior_opposed_rl | Prior RTH range percentile=prior_range_norm | 1.25× | 29% | +27852 | 10.28 | 0.046 | 0.046 | 0.307 | 100% | 0 |
| RISK-BUDGET PROFILE | ym_st_pmc_3r | Day of week=Thursday | 1.25× | 22% | +9325 | 20.30 | 0.015 | 0.007 | 0.830 | 100% | 0 |
| NOT VALIDATED | ym_st_pmc_3r | Overnight compression=on_comp | 1.25× | 28% | +10131 | 15.80 | 0.058 | 0.073 | 0.974 | 88% | 0 |
| NOT VALIDATED | ym_st_pmc_3r | Prior RTH range percentile=prior_range_norm | 1.25× | 29% | +10396 | 14.42 | 0.288 | 0.105 | 0.998 | 88% | 3 |

## es_prior_opposed_legacy ST-event age=st_age_gt180m @ 1.25×

```
HP coverage:               27.8%
Boosted campaigns:         68
Incremental net:           +39544
Incremental stress:        1721
Incremental N/S:           22.98
Full-book N/S base→sized:  12.48 → 13.70 (Δ+1.23)

Matched-placebo median N/S: 7.40
Actual percentile:          99.3
p_incremental_N/S:          0.0074
p_incremental_net:          0.0412
p_full-book_N/S:            0.0890
p_drawdown_improvement:     0.1880
p_shift_inc_N/S:            0.0060
p_master_inc_N/S:           0.0100
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   2

Decision: SIZE-UP VALIDATED
```

## es_prior_opposed_legacy Week of month=1 @ 1.25×

```
HP coverage:               29.4%
Boosted campaigns:         72
Incremental net:           +40781
Incremental stress:        3738
Incremental N/S:           10.91
Full-book N/S base→sized:  12.48 → 12.68 (Δ+0.21)

Matched-placebo median N/S: 7.63
Actual percentile:          74.7
p_incremental_N/S:          0.2527
p_incremental_net:          0.2643
p_full-book_N/S:            0.5085
p_drawdown_improvement:     0.5989
p_shift_inc_N/S:            0.1988
p_master_inc_N/S:           0.7485
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## es_prior_opposed_legacy Prior RTH close location=prior_close_mid_third @ 1.25×

```
HP coverage:               24.9%
Boosted campaigns:         61
Incremental net:           +29217
Incremental stress:        2768
Incremental N/S:           10.56
Full-book N/S base→sized:  12.48 → 13.14 (Δ+0.66)

Matched-placebo median N/S: 5.19
Actual percentile:          90.8
p_incremental_N/S:          0.0924
p_incremental_net:          0.2494
p_full-book_N/S:            0.2987
p_drawdown_improvement:     0.4391
p_shift_inc_N/S:            0.0829
p_master_inc_N/S:           0.7824
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## es_st_pmc_ma_bull Day of week=Tuesday @ 1.25×

```
HP coverage:               22.4%
Boosted campaigns:         50
Incremental net:           +16134
Incremental stress:        3143
Incremental N/S:           5.13
Full-book N/S base→sized:  2.25 → 2.55 (Δ+0.30)

Matched-placebo median N/S: 1.77
Actual percentile:          91.9
p_incremental_N/S:          0.0816
p_incremental_net:          0.2480
p_full-book_N/S:            0.2480
p_drawdown_improvement:     1.0000
p_shift_inc_N/S:            0.0649
p_master_inc_N/S:           0.1737
Frozen WF pos Δnet frac:    0.71
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## es_st_pmc_ma_bull ST-event age=st_age_gt180m @ 1.25×

```
HP coverage:               27.8%
Boosted campaigns:         62
Incremental net:           +17612
Incremental stress:        4764
Incremental N/S:           3.70
Full-book N/S base→sized:  2.25 → 2.59 (Δ+0.34)

Matched-placebo median N/S: 1.44
Actual percentile:          91.6
p_incremental_N/S:          0.0838
p_incremental_net:          0.0396
p_full-book_N/S:            0.0240
p_drawdown_improvement:     0.3347
p_shift_inc_N/S:            0.0819
p_master_inc_N/S:           0.4371
Frozen WF pos Δnet frac:    0.71
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## es_st_pmc_ma_bull Prior RTH range percentile=prior_range_norm @ 1.25×

```
HP coverage:               25.6%
Boosted campaigns:         57
Incremental net:           +14238
Incremental stress:        5039
Incremental N/S:           2.83
Full-book N/S base→sized:  2.25 → 2.41 (Δ+0.16)

Matched-placebo median N/S: 5.33
Actual percentile:          9.4
p_incremental_N/S:          0.9062
p_incremental_net:          0.8302
p_full-book_N/S:            0.8306
p_drawdown_improvement:     1.0000
p_shift_inc_N/S:            0.6913
p_master_inc_N/S:           0.6946
Frozen WF pos Δnet frac:    0.86
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## nq_or_complement_skipflat Day of week=Thursday @ 1.25×

```
HP coverage:               19.8%
Boosted campaigns:         144
Incremental net:           +63732
Incremental stress:        12346
Incremental N/S:           5.16
Full-book N/S base→sized:  4.41 → 4.82 (Δ+0.40)

Matched-placebo median N/S: 1.40
Actual percentile:          93.3
p_incremental_N/S:          0.0674
p_incremental_net:          0.0656
p_full-book_N/S:            0.0306
p_drawdown_improvement:     0.0946
p_shift_inc_N/S:            0.0689
p_master_inc_N/S:           0.5868
Frozen WF pos Δnet frac:    0.80
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## nq_or_complement_skipflat Opening 15m range vs ATR=or_norm @ 1.25×

```
HP coverage:               29.4%
Boosted campaigns:         214
Incremental net:           +106565
Incremental stress:        22461
Incremental N/S:           4.74
Full-book N/S base→sized:  4.41 → 4.72 (Δ+0.31)

Matched-placebo median N/S: 1.24
Actual percentile:          97.4
p_incremental_N/S:          0.0258
p_incremental_net:          0.0046
p_full-book_N/S:            0.0120
p_drawdown_improvement:     0.4633
p_shift_inc_N/S:            0.0849
p_master_inc_N/S:           0.7166
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   2

Decision: NOT VALIDATED
```

## nq_or_complement_skipflat Opening 15m volume percentile=vol_low @ 1.25×

```
HP coverage:               29.4%
Boosted campaigns:         214
Incremental net:           +49564
Incremental stress:        10710
Incremental N/S:           4.63
Full-book N/S base→sized:  4.41 → 4.53 (Δ+0.11)

Matched-placebo median N/S: 1.62
Actual percentile:          94.9
p_incremental_N/S:          0.0510
p_incremental_net:          0.3309
p_full-book_N/S:            0.2847
p_drawdown_improvement:     0.3189
p_shift_inc_N/S:            0.0989
p_master_inc_N/S:           0.7385
Frozen WF pos Δnet frac:    0.60
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## nq_prior_opposed_rl Opening 15m range vs ATR=or_norm @ 1.25×

```
HP coverage:               29.9%
Boosted campaigns:         129
Incremental net:           +145488
Incremental stress:        4964
Incremental N/S:           29.31
Full-book N/S base→sized:  24.06 → 28.75 (Δ+4.70)

Matched-placebo median N/S: 10.56
Actual percentile:          99.2
p_incremental_N/S:          0.0082
p_incremental_net:          0.0514
p_full-book_N/S:            0.0162
p_drawdown_improvement:     0.0296
p_shift_inc_N/S:            0.0050
p_master_inc_N/S:           0.0878
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   1

Decision: PROVISIONAL PAPER
```

## nq_prior_opposed_rl ST-event age=st_age_30_90m @ 1.25×

```
HP coverage:               27.3%
Boosted campaigns:         118
Incremental net:           +125654
Incremental stress:        6060
Incremental N/S:           20.73
Full-book N/S base→sized:  24.06 → 27.55 (Δ+3.49)

Matched-placebo median N/S: 10.33
Actual percentile:          94.4
p_incremental_N/S:          0.0560
p_incremental_net:          0.1086
p_full-book_N/S:            0.0680
p_drawdown_improvement:     0.1038
p_shift_inc_N/S:            0.0430
p_master_inc_N/S:           0.6587
Frozen WF pos Δnet frac:    0.80
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## nq_prior_opposed_rl NQ-ES dispersion=disp_mid @ 1.25×

```
HP coverage:               31.9%
Boosted campaigns:         138
Incremental net:           +121080
Incremental stress:        7574
Incremental N/S:           15.99
Full-book N/S base→sized:  24.06 → 24.68 (Δ+0.62)

Matched-placebo median N/S: 10.80
Actual percentile:          81.8
p_incremental_N/S:          0.1820
p_incremental_net:          0.3345
p_full-book_N/S:            0.4333
p_drawdown_improvement:     0.4629
p_shift_inc_N/S:            0.1658
p_master_inc_N/S:           0.9381
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   2

Decision: NOT VALIDATED
```

## nq_st_pmc_3r Overnight compression=on_comp @ 1.25×

```
HP coverage:               29.9%
Boosted campaigns:         203
Incremental net:           +34984
Incremental stress:        1520
Incremental N/S:           23.01
Full-book N/S base→sized:  21.47 → 24.75 (Δ+3.27)

Matched-placebo median N/S: 18.70
Actual percentile:          76.8
p_incremental_N/S:          0.2324
p_incremental_net:          0.5445
p_full-book_N/S:            0.3511
p_drawdown_improvement:     0.2949
p_shift_inc_N/S:            0.0629
p_master_inc_N/S:           0.2255
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## nq_st_pmc_3r Entry hour (NY)=11 @ 1.25×

```
HP coverage:               8.2%
Boosted campaigns:         56
Incremental net:           +15937
Incremental stress:        755
Incremental N/S:           21.11
Full-book N/S base→sized:  21.47 → 23.16 (Δ+1.69)

Matched-placebo median N/S: 7.41
Actual percentile:          97.8
p_incremental_N/S:          0.0226
p_incremental_net:          0.1144
p_full-book_N/S:            0.1248
p_drawdown_improvement:     1.0000
p_shift_inc_N/S:            0.0110
p_master_inc_N/S:           0.4451
Frozen WF pos Δnet frac:    0.62
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## nq_st_pmc_3r Hourly RSI bucket=rsi_55_70 @ 1.25×

```
HP coverage:               31.8%
Boosted campaigns:         216
Incremental net:           +42846
Incremental stress:        2116
Incremental N/S:           20.25
Full-book N/S base→sized:  21.47 → 23.72 (Δ+2.25)

Matched-placebo median N/S: 14.83
Actual percentile:          83.6
p_incremental_N/S:          0.1638
p_incremental_net:          0.0702
p_full-book_N/S:            0.1862
p_drawdown_improvement:     0.2246
p_shift_inc_N/S:            0.0519
p_master_inc_N/S:           0.4910
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   5

Decision: NOT VALIDATED
```

## nq_v2b_s113 Prior RTH close location=prior_close_mid_third @ 1.25×

```
HP coverage:               24.5%
Boosted campaigns:         339
Incremental net:           +123947
Incremental stress:        20454
Incremental N/S:           6.06
Full-book N/S base→sized:  8.90 → 8.75 (Δ-0.15)

Matched-placebo median N/S: 1.39
Actual percentile:          97.3
p_incremental_N/S:          0.0270
p_incremental_net:          0.0174
p_full-book_N/S:            0.2140
p_drawdown_improvement:     0.6821
p_shift_inc_N/S:            0.0470
p_master_inc_N/S:           0.3214
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## nq_v2b_s113 Opening 15m range vs ATR=or_norm @ 1.25×

```
HP coverage:               30.0%
Boosted campaigns:         416
Incremental net:           +155211
Incremental stress:        25716
Incremental N/S:           6.04
Full-book N/S base→sized:  8.90 → 9.77 (Δ+0.87)

Matched-placebo median N/S: 1.71
Actual percentile:          96.5
p_incremental_N/S:          0.0354
p_incremental_net:          0.0044
p_full-book_N/S:            0.0046
p_drawdown_improvement:     0.0690
p_shift_inc_N/S:            0.0529
p_master_inc_N/S:           0.3014
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   2

Decision: NOT VALIDATED
```

## nq_v2b_s113 Overnight range third=on_lower @ 1.25×

```
HP coverage:               33.1%
Boosted campaigns:         459
Incremental net:           +116196
Incremental stress:        25745
Incremental N/S:           4.51
Full-book N/S base→sized:  8.90 → 8.99 (Δ+0.09)

Matched-placebo median N/S: 2.54
Actual percentile:          79.5
p_incremental_N/S:          0.2052
p_incremental_net:          0.1852
p_full-book_N/S:            0.2474
p_drawdown_improvement:     0.4021
p_shift_inc_N/S:            0.1558
p_master_inc_N/S:           0.7265
Frozen WF pos Δnet frac:    0.80
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## ym_prior_opposed_rl Overnight range third=on_middle @ 1.25×

```
HP coverage:               24.8%
Boosted campaigns:         108
Incremental net:           +29468
Incremental stress:        2079
Incremental N/S:           14.17
Full-book N/S base→sized:  9.74 → 10.25 (Δ+0.51)

Matched-placebo median N/S: 4.83
Actual percentile:          98.0
p_incremental_N/S:          0.0204
p_incremental_net:          0.1742
p_full-book_N/S:            0.2855
p_drawdown_improvement:     0.7235
p_shift_inc_N/S:            0.0170
p_master_inc_N/S:           0.0439
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   0

Decision: SIZE-UP VALIDATED
```

## ym_prior_opposed_rl Month=12 @ 1.25×

```
HP coverage:               9.2%
Boosted campaigns:         40
Incremental net:           +17204
Incremental stress:        1588
Incremental N/S:           10.83
Full-book N/S base→sized:  9.74 → 10.32 (Δ+0.58)

Matched-placebo median N/S: 10.83
Actual percentile:          0.0
p_incremental_N/S:          1.0000
p_incremental_net:          1.0000
p_full-book_N/S:            1.0000
p_drawdown_improvement:     1.0000
p_shift_inc_N/S:            0.5125
p_master_inc_N/S:           0.2375
Frozen WF pos Δnet frac:    0.60
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## ym_prior_opposed_rl Prior RTH range percentile=prior_range_norm @ 1.25×

```
HP coverage:               29.4%
Boosted campaigns:         128
Incremental net:           +27852
Incremental stress:        2710
Incremental N/S:           10.28
Full-book N/S base→sized:  9.74 → 10.24 (Δ+0.50)

Matched-placebo median N/S: 4.32
Actual percentile:          95.5
p_incremental_N/S:          0.0456
p_incremental_net:          0.2158
p_full-book_N/S:            0.1298
p_drawdown_improvement:     0.1828
p_shift_inc_N/S:            0.0460
p_master_inc_N/S:           0.3074
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## ym_st_pmc_3r Day of week=Thursday @ 1.25×

```
HP coverage:               21.8%
Boosted campaigns:         215
Incremental net:           +9325
Incremental stress:        459
Incremental N/S:           20.30
Full-book N/S base→sized:  18.06 → 19.20 (Δ+1.15)

Matched-placebo median N/S: 9.24
Actual percentile:          98.5
p_incremental_N/S:          0.0152
p_incremental_net:          0.0444
p_full-book_N/S:            0.0094
p_drawdown_improvement:     0.0952
p_shift_inc_N/S:            0.0070
p_master_inc_N/S:           0.8303
Frozen WF pos Δnet frac:    1.00
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## ym_st_pmc_3r Overnight compression=on_comp @ 1.25×

```
HP coverage:               28.3%
Boosted campaigns:         279
Incremental net:           +10131
Incremental stress:        641
Incremental N/S:           15.80
Full-book N/S base→sized:  18.06 → 18.18 (Δ+0.12)

Matched-placebo median N/S: 9.81
Actual percentile:          94.3
p_incremental_N/S:          0.0576
p_incremental_net:          0.0662
p_full-book_N/S:            0.1964
p_drawdown_improvement:     0.3557
p_shift_inc_N/S:            0.0729
p_master_inc_N/S:           0.9741
Frozen WF pos Δnet frac:    0.88
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## ym_st_pmc_3r Prior RTH range percentile=prior_range_norm @ 1.25×

```
HP coverage:               28.6%
Boosted campaigns:         282
Incremental net:           +10396
Incremental stress:        721
Incremental N/S:           14.42
Full-book N/S base→sized:  18.06 → 18.09 (Δ+0.03)

Matched-placebo median N/S: 11.84
Actual percentile:          71.3
p_incremental_N/S:          0.2875
p_incremental_net:          0.1806
p_full-book_N/S:            0.6679
p_drawdown_improvement:     0.8458
p_shift_inc_N/S:            0.1049
p_master_inc_N/S:           0.9980
Frozen WF pos Δnet frac:    0.88
Discovery reappear count:   3

Decision: NOT VALIDATED
```

## Rare HP sizing sensitivity (NOT validation)

Linear campaign scaling only. Do **not** promote from this table; run `--rare-2x` (or the intended multiplier) through the full null suite.

_none_
## Artifacts

- `pairs/<slug>/RESULT.json` + campaign_table / null CSVs / WF
- `rare_size_impact.csv` (sensitivity only)
- `SUMMARY.md` / `EMAIL.txt`
