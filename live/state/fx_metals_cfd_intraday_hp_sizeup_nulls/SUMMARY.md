# FX / metals / CFD HP size-up nulls (`fx_metals_cfd_intraday_hp_sizeup_nulls`)

Question: if we add the same extra capital to the same number of
baseline campaigns, does the HP condition beat random placement of
that **incremental sleeve**?

Placebo: year|month boost-count matched (never stratifies on the
tested feature). Also: clustered timing shifts, selection-aware
master null (**selects by ΔN/S**), nested discovery WF (HP coverage ≤35%)
+ frozen-candidate WF.

Canonical objective: whole-book **ΔN/S** (higher better). Δnet is
viability/reporting only — not the winner selector.

Linear 2×/3×/4× tables below are **sizing sensitivity only** — not
validation. Each intended multiplier needs its own null suite.

## Decision rule

- **SIZE-UP VALIDATED** — causal, coverage <35%, `p_delta_ns≤0.05`
  on placebo/shift/master, frozen WF acceptable,
  full-book stress ≤1.35× baseline. Authorized: shadow → controlled paper.
- **PROVISIONAL PAPER** — same gates except `0.05 < p_master_ΔNS ≤ 0.10`.
  Shadow / controlled paper only — **no** historical size-up promotion claim.
- **RISK THROTTLE** — `p_master_ΔNS > 0.10` or WF fails (or coverage too
  broad). May raise N/S without superior incremental selection — not alpha.
- **NOT VALIDATED** — fails equal-added random exposure / timing / causal.
- **PENDING** — required null/multiplier replay missing.

## Pair results (matched-added-exposure)

| decision | book | condition=bucket | mult | hp% | Δnet | ΔN/S | p_plac ΔNS | p_shift ΔNS | p_master ΔNS | WF+ | reapp |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NOT VALIDATED | usdjpy_monday_or | Monday session range vs ATR=mon_wide | 1.25× | 28% | +32138 | -2.69 | 0.925 | 0.972 | 1.000 | 75% | 0 |
| NOT VALIDATED | us30_monday_or | Monday session range vs ATR=mon_wide | 1.25× | 29% | +10480 | +0.55 | 0.130 | 0.002 | 0.224 | 57% | 1 |
| NOT VALIDATED | eurusd_monday_or | Monday session range vs ATR=mon_wide | 1.25× | 23% | +21345 | +0.11 | 0.812 | 0.285 | 1.000 | 50% | 0 |
| NOT VALIDATED | gbpusd_monday_or | Monday session range vs ATR=mon_wide | 1.25× | 24% | +35945 | +0.28 | 0.368 | 0.088 | 0.998 | 62% | 0 |
| NOT VALIDATED | xauusd_monday_or | Monday session range vs ATR=mon_wide | 1.25× | 22% | +19377 | -0.27 | 0.999 | 0.926 | 1.000 | 50% | 0 |
| NOT VALIDATED | usdjpy_monday_or | Monday session range vs ATR=mon_norm | 1.25× | 32% | +31911 | +0.83 | 0.234 | 0.078 | 0.938 | 100% | 0 |
| NOT VALIDATED | us30_monday_or | Prior-day range percentile=prior_range_exp | 1.25× | 20% | +9412 | +0.51 | 0.076 | 0.009 | 0.255 | 86% | 3 |
| NOT VALIDATED | usdjpy_monday_or | Prior-day range percentile=prior_range_norm | 1.25× | 20% | +23862 | +0.85 | 0.104 | 0.067 | 0.902 | 62% | 0 |
| NOT VALIDATED | eurusd_st_pmc_3r | Prior-day range percentile=prior_range_exp | 1.25× | 32% | +13357 | +0.45 | 0.185 | 0.061 | 0.723 | 86% | 0 |
| NOT VALIDATED | usdjpy_st_pmc_3r | Prior-day range percentile=prior_range_exp | 1.25× | 37% | +8796 | +0.46 | 0.108 | 0.012 | 0.287 | 62% | 0 |
| NOT VALIDATED | gbpusd_st_pmc_3r | Prior-day range percentile=prior_range_norm | 1.25× | 30% | +11351 | -0.62 | 0.852 | 0.794 | 1.000 | 75% | 0 |
| NOT VALIDATED | us30_st_pmc_3r | Prior-day range percentile=prior_range_norm | 1.25× | 31% | +2213 | +0.65 | 0.010 | 0.102 | 0.966 | 100% | 2 |
| NOT VALIDATED | eurusd_st_pmc_3r | Day of week=Thursday | 1.25× | 20% | +8754 | +0.34 | 0.055 | 0.059 | 0.976 | 86% | 0 |
| NOT VALIDATED | nas100_st_pmc_3r | Prior quarter type=q_break_down | 1.25× | 14% | +799 | +1.24 | 1.000 | 0.563 | 0.902 | 29% | 0 |
| RISK THROTTLE | us30_london_prior_opposed | London OR width vs ATR=lor_norm | 1.25× | 31% | +3108 | +0.78 | 0.036 | 0.046 | 0.926 | 100% | 0 |
| NOT VALIDATED | usdjpy_asia_range | Prior-day range percentile=prior_range_norm | 1.25× | 28% | +17266 | -0.21 | 0.227 | 0.483 | 1.000 | 71% | 0 |
| NOT VALIDATED | us30_monday_or | Entry hour (NY)=11 | 1.25× | 9% | +4125 | +0.20 | 0.080 | 0.073 | 0.992 | 57% | 0 |
| NOT VALIDATED | xauusd_quarterly_breakout | Prior-quarter range width=pqw_q2 | 1.25× | 23% | +107896 | +0.35 | 1.000 | 0.898 | 1.000 | nan% | 0 |
| NOT VALIDATED | audjpy_quarterly_breakout | Prior-quarter range width=pqw_q1 | 1.25× | 34% | +16715 | +0.03 | 1.000 | 0.857 | 0.373 | nan% | 0 |
| NOT VALIDATED | eurusd_quarterly_breakout | Prior-day range percentile=prior_range_comp | 1.25× | 35% | +50968 | +0.36 | 1.000 | 0.841 | 0.615 | nan% | 0 |
| NOT VALIDATED | eurusd_quarterly_breakout | ATR causal rolling percentile=atr_pctl_q2 | 1.25× | 20% | +38504 | +0.16 | 0.247 | 0.214 | 1.000 | nan% | 0 |
| NOT VALIDATED | gbpusd_quarterly_breakout | ATR causal rolling percentile=atr_pctl_q1 | 1.25× | 41% | +73924 | +0.07 | 0.124 | 0.143 | 1.000 | nan% | 0 |
| NOT VALIDATED | usdjpy_quarterly_breakout | ATR causal rolling percentile=atr_pctl_q4 | 1.25× | 33% | +48315 | +0.23 | 0.257 | 0.245 | 0.842 | nan% | 0 |
| NOT VALIDATED | audjpy_quarterly_breakout | Prior-day range percentile=prior_range_exp | 1.25× | 41% | +47231 | +0.11 | 0.525 | 0.424 | 0.074 | nan% | 0 |
| NOT VALIDATED | xauusd_quarterly_breakout | ATR causal rolling percentile=atr_pctl_q2 | 1.25× | 23% | +113959 | +0.37 | 1.000 | 0.866 | 1.000 | nan% | 0 |
| NOT VALIDATED | eurusd_quarterly_breakout | Prior-quarter range width=pqw_q2 | 1.25× | 23% | +17901 | +0.08 | 1.000 | 0.884 | 1.000 | nan% | 0 |

## usdjpy_monday_or Monday session range vs ATR=mon_wide @ 1.25×

```
HP coverage:               27.7%
Boosted campaigns:         528
Incremental net (report):  +32138
Incremental stress:        7506
Incremental sleeve N/S:    4.28
Full-book N/S base→sized:  14.47 → 11.78 (Δ-2.69)

Matched-placebo median ΔN/S: -0.90
Actual ΔN/S percentile:      7.5
p_delta_NS (placebo):        0.9254
p_candidate_NS (book):       0.9254
p_delta_net (report):        0.3547
p_drawdown_improvement:      0.9574
p_shift_delta_NS:            0.9720
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     0.75
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## us30_monday_or Monday session range vs ATR=mon_wide @ 1.25×

```
HP coverage:               29.3%
Boosted campaigns:         329
Incremental net (report):  +10480
Incremental stress:        3643
Incremental sleeve N/S:    2.88
Full-book N/S base→sized:  1.96 → 2.51 (Δ+0.55)

Matched-placebo median ΔN/S: 0.35
Actual ΔN/S percentile:      87.0
p_delta_NS (placebo):        0.1304
p_candidate_NS (book):       0.1304
p_delta_net (report):        0.0422
p_drawdown_improvement:      0.5141
p_shift_delta_NS:            0.0020
p_master_delta_NS:           0.2236
Frozen WF pos Δnet frac:     0.57
Discovery reappear count:    1

Decision: NOT VALIDATED
```

## eurusd_monday_or Monday session range vs ATR=mon_wide @ 1.25×

```
HP coverage:               23.2%
Boosted campaigns:         665
Incremental net (report):  +21345
Incremental stress:        10056
Incremental sleeve N/S:    2.12
Full-book N/S base→sized:  1.90 → 2.01 (Δ+0.11)

Matched-placebo median ΔN/S: 0.25
Actual ΔN/S percentile:      18.8
p_delta_NS (placebo):        0.8118
p_candidate_NS (book):       0.8118
p_delta_net (report):        0.6451
p_drawdown_improvement:      0.9322
p_shift_delta_NS:            0.2847
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     0.50
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## gbpusd_monday_or Monday session range vs ATR=mon_wide @ 1.25×

```
HP coverage:               24.1%
Boosted campaigns:         679
Incremental net (report):  +35945
Incremental stress:        12141
Incremental sleeve N/S:    2.96
Full-book N/S base→sized:  2.99 → 3.27 (Δ+0.28)

Matched-placebo median ΔN/S: 0.22
Actual ΔN/S percentile:      63.2
p_delta_NS (placebo):        0.3681
p_candidate_NS (book):       0.3681
p_delta_net (report):        0.6589
p_drawdown_improvement:      0.1600
p_shift_delta_NS:            0.0879
p_master_delta_NS:           0.9980
Frozen WF pos Δnet frac:     0.62
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## xauusd_monday_or Monday session range vs ATR=mon_wide @ 1.25×

```
HP coverage:               22.0%
Boosted campaigns:         874
Incremental net (report):  +19377
Incremental stress:        47956
Incremental sleeve N/S:    0.40
Full-book N/S base→sized:  1.94 → 1.67 (Δ-0.27)

Matched-placebo median ΔN/S: 0.11
Actual ΔN/S percentile:      0.1
p_delta_NS (placebo):        0.9990
p_candidate_NS (book):       0.9990
p_delta_net (report):        0.9878
p_drawdown_improvement:      0.9998
p_shift_delta_NS:            0.9261
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     0.50
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## usdjpy_monday_or Monday session range vs ATR=mon_norm @ 1.25×

```
HP coverage:               32.2%
Boosted campaigns:         614
Incremental net (report):  +31911
Incremental stress:        3986
Incremental sleeve N/S:    8.01
Full-book N/S base→sized:  14.47 → 15.30 (Δ+0.83)

Matched-placebo median ΔN/S: 0.40
Actual ΔN/S percentile:      76.6
p_delta_NS (placebo):        0.2344
p_candidate_NS (book):       0.2344
p_delta_net (report):        0.4167
p_drawdown_improvement:      0.1858
p_shift_delta_NS:            0.0779
p_master_delta_NS:           0.9381
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## us30_monday_or Prior-day range percentile=prior_range_exp @ 1.25×

```
HP coverage:               20.2%
Boosted campaigns:         227
Incremental net (report):  +9412
Incremental stress:        2098
Incremental sleeve N/S:    4.49
Full-book N/S base→sized:  1.96 → 2.47 (Δ+0.51)

Matched-placebo median ΔN/S: 0.22
Actual ΔN/S percentile:      92.4
p_delta_NS (placebo):        0.0758
p_candidate_NS (book):       0.0758
p_delta_net (report):        0.0354
p_drawdown_improvement:      0.3783
p_shift_delta_NS:            0.0090
p_master_delta_NS:           0.2555
Frozen WF pos Δnet frac:     0.86
Discovery reappear count:    3

Decision: NOT VALIDATED
```

## usdjpy_monday_or Prior-day range percentile=prior_range_norm @ 1.25×

```
HP coverage:               20.4%
Boosted campaigns:         389
Incremental net (report):  +23862
Incremental stress:        3313
Incremental sleeve N/S:    7.20
Full-book N/S base→sized:  14.47 → 15.33 (Δ+0.85)

Matched-placebo median ΔN/S: -0.36
Actual ΔN/S percentile:      89.6
p_delta_NS (placebo):        0.1042
p_candidate_NS (book):       0.1042
p_delta_net (report):        0.0970
p_drawdown_improvement:      0.2072
p_shift_delta_NS:            0.0669
p_master_delta_NS:           0.9022
Frozen WF pos Δnet frac:     0.62
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## eurusd_st_pmc_3r Prior-day range percentile=prior_range_exp @ 1.25×

```
HP coverage:               32.5%
Boosted campaigns:         281
Incremental net (report):  +13357
Incremental stress:        2263
Incremental sleeve N/S:    5.90
Full-book N/S base→sized:  3.18 → 3.63 (Δ+0.45)

Matched-placebo median ΔN/S: 0.23
Actual ΔN/S percentile:      81.6
p_delta_NS (placebo):        0.1846
p_candidate_NS (book):       0.1846
p_delta_net (report):        0.0796
p_drawdown_improvement:      0.4493
p_shift_delta_NS:            0.0609
p_master_delta_NS:           0.7226
Frozen WF pos Δnet frac:     0.86
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## usdjpy_st_pmc_3r Prior-day range percentile=prior_range_exp @ 1.25×

```
HP coverage:               37.1%
Boosted campaigns:         322
Incremental net (report):  +8796
Incremental stress:        1482
Incremental sleeve N/S:    5.93
Full-book N/S base→sized:  1.83 → 2.29 (Δ+0.46)

Matched-placebo median ΔN/S: 0.26
Actual ΔN/S percentile:      89.2
p_delta_NS (placebo):        0.1082
p_candidate_NS (book):       0.1082
p_delta_net (report):        0.3237
p_drawdown_improvement:      0.0474
p_shift_delta_NS:            0.0120
p_master_delta_NS:           0.2874
Frozen WF pos Δnet frac:     0.62
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## gbpusd_st_pmc_3r Prior-day range percentile=prior_range_norm @ 1.25×

```
HP coverage:               29.7%
Boosted campaigns:         304
Incremental net (report):  +11351
Incremental stress:        2609
Incremental sleeve N/S:    4.35
Full-book N/S base→sized:  8.68 → 8.06 (Δ-0.62)

Matched-placebo median ΔN/S: 0.01
Actual ΔN/S percentile:      14.8
p_delta_NS (placebo):        0.8522
p_candidate_NS (book):       0.8522
p_delta_net (report):        0.3205
p_drawdown_improvement:      0.9170
p_shift_delta_NS:            0.7942
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     0.75
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## us30_st_pmc_3r Prior-day range percentile=prior_range_norm @ 1.25×

```
HP coverage:               31.3%
Boosted campaigns:         181
Incremental net (report):  +2213
Incremental stress:        69
Incremental sleeve N/S:    32.10
Full-book N/S base→sized:  44.20 → 44.84 (Δ+0.65)

Matched-placebo median ΔN/S: -1.39
Actual ΔN/S percentile:      99.0
p_delta_NS (placebo):        0.0098
p_candidate_NS (book):       0.0098
p_delta_net (report):        0.0014
p_drawdown_improvement:      0.2164
p_shift_delta_NS:            0.1019
p_master_delta_NS:           0.9661
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    2

Decision: NOT VALIDATED
```

## eurusd_st_pmc_3r Day of week=Thursday @ 1.25×

```
HP coverage:               20.2%
Boosted campaigns:         175
Incremental net (report):  +8754
Incremental stress:        1043
Incremental sleeve N/S:    8.39
Full-book N/S base→sized:  3.18 → 3.52 (Δ+0.34)

Matched-placebo median ΔN/S: 0.05
Actual ΔN/S percentile:      94.5
p_delta_NS (placebo):        0.0552
p_candidate_NS (book):       0.0552
p_delta_net (report):        0.0700
p_drawdown_improvement:      0.1028
p_shift_delta_NS:            0.0589
p_master_delta_NS:           0.9760
Frozen WF pos Δnet frac:     0.86
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## nas100_st_pmc_3r Prior quarter type=q_break_down @ 1.25×

```
HP coverage:               13.8%
Boosted campaigns:         66
Incremental net (report):  +799
Incremental stress:        52
Incremental sleeve N/S:    15.49
Full-book N/S base→sized:  23.66 → 24.90 (Δ+1.24)

Matched-placebo median ΔN/S: 1.24
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.5634
p_master_delta_NS:           0.9022
Frozen WF pos Δnet frac:     0.29
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## us30_london_prior_opposed London OR width vs ATR=lor_norm @ 1.25×

```
HP coverage:               30.7%
Boosted campaigns:         92
Incremental net (report):  +3108
Incremental stress:        278
Incremental sleeve N/S:    11.17
Full-book N/S base→sized:  7.90 → 8.68 (Δ+0.78)

Matched-placebo median ΔN/S: 0.03
Actual ΔN/S percentile:      96.4
p_delta_NS (placebo):        0.0360
p_candidate_NS (book):       0.0360
p_delta_net (report):        0.0950
p_drawdown_improvement:      0.0826
p_shift_delta_NS:            0.0460
p_master_delta_NS:           0.9261
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    0

Decision: RISK THROTTLE
```

## usdjpy_asia_range Prior-day range percentile=prior_range_norm @ 1.25×

```
HP coverage:               28.2%
Boosted campaigns:         243
Incremental net (report):  +17266
Incremental stress:        4346
Incremental sleeve N/S:    3.97
Full-book N/S base→sized:  8.65 → 8.44 (Δ-0.21)

Matched-placebo median ΔN/S: -0.54
Actual ΔN/S percentile:      77.4
p_delta_NS (placebo):        0.2266
p_candidate_NS (book):       0.2266
p_delta_net (report):        0.0944
p_drawdown_improvement:      0.5973
p_shift_delta_NS:            0.4825
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     0.71
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## us30_monday_or Entry hour (NY)=11 @ 1.25×

```
HP coverage:               9.5%
Boosted campaigns:         106
Incremental net (report):  +4125
Incremental stress:        617
Incremental sleeve N/S:    6.69
Full-book N/S base→sized:  1.96 → 2.16 (Δ+0.20)

Matched-placebo median ΔN/S: -0.00
Actual ΔN/S percentile:      92.1
p_delta_NS (placebo):        0.0796
p_candidate_NS (book):       0.0796
p_delta_net (report):        0.0400
p_drawdown_improvement:      0.4745
p_shift_delta_NS:            0.0729
p_master_delta_NS:           0.9920
Frozen WF pos Δnet frac:     0.57
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## xauusd_quarterly_breakout Prior-quarter range width=pqw_q2 @ 1.25×

```
HP coverage:               23.0%
Boosted campaigns:         26
Incremental net (report):  +107896
Incremental stress:        37682
Incremental sleeve N/S:    2.86
Full-book N/S base→sized:  3.71 → 4.07 (Δ+0.35)

Matched-placebo median ΔN/S: 0.35
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.8981
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## audjpy_quarterly_breakout Prior-quarter range width=pqw_q1 @ 1.25×

```
HP coverage:               34.2%
Boosted campaigns:         40
Incremental net (report):  +16715
Incremental stress:        14714
Incremental sleeve N/S:    1.14
Full-book N/S base→sized:  -0.66 → -0.63 (Δ+0.03)

Matched-placebo median ΔN/S: 0.03
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.8571
p_master_delta_NS:           0.3733
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## eurusd_quarterly_breakout Prior-day range percentile=prior_range_comp @ 1.25×

```
HP coverage:               34.5%
Boosted campaigns:         38
Incremental net (report):  +50968
Incremental stress:        17631
Incremental sleeve N/S:    2.89
Full-book N/S base→sized:  0.85 → 1.22 (Δ+0.36)

Matched-placebo median ΔN/S: 0.36
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.8412
p_master_delta_NS:           0.6148
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## eurusd_quarterly_breakout ATR causal rolling percentile=atr_pctl_q2 @ 1.25×

```
HP coverage:               20.0%
Boosted campaigns:         22
Incremental net (report):  +38504
Incremental stress:        20410
Incremental sleeve N/S:    1.89
Full-book N/S base→sized:  0.85 → 1.01 (Δ+0.16)

Matched-placebo median ΔN/S: 0.15
Actual ΔN/S percentile:      75.3
p_delta_NS (placebo):        0.2474
p_candidate_NS (book):       0.2474
p_delta_net (report):        0.2474
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.2138
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## gbpusd_quarterly_breakout ATR causal rolling percentile=atr_pctl_q1 @ 1.25×

```
HP coverage:               41.2%
Boosted campaigns:         42
Incremental net (report):  +73924
Incremental stress:        33273
Incremental sleeve N/S:    2.22
Full-book N/S base→sized:  1.78 → 1.85 (Δ+0.07)

Matched-placebo median ΔN/S: 0.03
Actual ΔN/S percentile:      87.6
p_delta_NS (placebo):        0.1238
p_candidate_NS (book):       0.1238
p_delta_net (report):        0.1238
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.1429
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## usdjpy_quarterly_breakout ATR causal rolling percentile=atr_pctl_q4 @ 1.25×

```
HP coverage:               33.3%
Boosted campaigns:         37
Incremental net (report):  +48315
Incremental stress:        21762
Incremental sleeve N/S:    2.22
Full-book N/S base→sized:  0.11 → 0.34 (Δ+0.23)

Matched-placebo median ΔN/S: 0.15
Actual ΔN/S percentile:      74.3
p_delta_NS (placebo):        0.2567
p_candidate_NS (book):       0.2567
p_delta_net (report):        0.2567
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.2448
p_master_delta_NS:           0.8423
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## audjpy_quarterly_breakout Prior-day range percentile=prior_range_exp @ 1.25×

```
HP coverage:               41.0%
Boosted campaigns:         48
Incremental net (report):  +47231
Incremental stress:        27509
Incremental sleeve N/S:    1.72
Full-book N/S base→sized:  -0.66 → -0.55 (Δ+0.11)

Matched-placebo median ΔN/S: 0.11
Actual ΔN/S percentile:      47.5
p_delta_NS (placebo):        0.5251
p_candidate_NS (book):       0.5251
p_delta_net (report):        0.4399
p_drawdown_improvement:      0.4235
p_shift_delta_NS:            0.4236
p_master_delta_NS:           0.0739
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## xauusd_quarterly_breakout ATR causal rolling percentile=atr_pctl_q2 @ 1.25×

```
HP coverage:               23.0%
Boosted campaigns:         26
Incremental net (report):  +113959
Incremental stress:        29751
Incremental sleeve N/S:    3.83
Full-book N/S base→sized:  3.71 → 4.09 (Δ+0.37)

Matched-placebo median ΔN/S: 0.37
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.8661
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## eurusd_quarterly_breakout Prior-quarter range width=pqw_q2 @ 1.25×

```
HP coverage:               22.7%
Boosted campaigns:         25
Incremental net (report):  +17901
Incremental stress:        17991
Incremental sleeve N/S:    0.99
Full-book N/S base→sized:  0.85 → 0.94 (Δ+0.08)

Matched-placebo median ΔN/S: 0.08
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.8841
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## Rare HP sizing sensitivity (NOT validation)

Linear campaign scaling only. Do **not** promote from this table; run `--rare-2x` (or the intended multiplier) through the full null suite.

_none_
## Artifacts

- `pairs/<slug>/RESULT.json` + campaign_table / null CSVs / WF
- `rare_size_impact.csv` (sensitivity only)
- `SUMMARY.md` / `EMAIL.txt`
