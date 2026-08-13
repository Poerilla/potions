# Matched-added-exposure validation suite

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
- **BORDERLINE PAPER** — same gates except `0.05 < p_master ≤ 0.10`.
  Shadow / controlled paper only — **no** historical size-up promotion claim.
- **RISK-BUDGET PROFILE** — `p_master > 0.10` or WF fails (or coverage too
  broad). Sensitivity / stress research only — not an HP-size deployment.
- **NOT VALIDATED** — fails equal-added random exposure / timing / causal.
- **PENDING** — required null/multiplier replay missing.

## Pair results (matched-added-exposure)

| decision | book | condition=bucket | mult | hp% | inc net | inc N/S | p_plac N/S | p_shift | p_master | WF+ | reapp |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SIZE-UP VALIDATED | eurusd_st_pmc_3r | Day of week=Thursday | 1.25× | 20% | +8754 | 8.39 | 0.023 | 0.008 | 0.024 | 86% | 0 |
| BORDERLINE PAPER | eurusd_st_pmc_3r | Day of week=Thursday | 1.50× | 20% | +17508 | 8.39 | 0.023 | 0.008 | 0.060 | 86% | 0 |
| RISK-BUDGET PROFILE | eurusd_st_pmc_3r | Day of week=Thursday | 2.00× | 20% | +35017 | 8.39 | 0.020 | 0.008 | 0.154 | 86% | 0 |
| SIZE-UP VALIDATED | us30_monday_or | Entry hour (NY)=11 | 1.25× | 9% | +4125 | 6.69 | 0.015 | 0.009 | 0.036 | 57% | 0 |
| BORDERLINE PAPER | us30_monday_or | Entry hour (NY)=11 | 1.50× | 9% | +8250 | 6.69 | 0.015 | 0.009 | 0.054 | 57% | 0 |
| RISK-BUDGET PROFILE | us30_monday_or | Entry hour (NY)=11 | 2.00× | 9% | +16500 | 6.69 | 0.016 | 0.009 | 0.106 | 57% | 0 |
| RISK-BUDGET PROFILE | eurusd_monday_or | Hourly RSI vs trade=rsi_against_side | 2.00× | 4% | +45136 | 9.02 | 0.000 | 0.002 | 0.014 | 12% | 0 |
| RISK-BUDGET PROFILE | usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 1.25× | 5% | +14410 | 6.74 | 0.046 | 0.027 | 0.280 | 0% | 0 |
| RISK-BUDGET PROFILE | usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 2.00× | 5% | +57638 | 6.74 | 0.035 | 0.028 | 0.463 | 71% | 0 |
| NOT VALIDATED | usdjpy_monday_or | Entry hour (NY)=5 | 1.25× | 3% | +11876 | 5.22 | 0.130 | 0.059 | 1.000 | 0% | 0 |
| NOT VALIDATED | usdjpy_monday_or | Entry hour (NY)=5 | 2.00× | 3% | +47502 | 5.22 | 0.070 | 0.060 | 0.810 | 50% | 0 |
| NOT VALIDATED | us30_monday_or | Day of week=Friday | 1.25× | 11% | +1791 | 1.38 | 0.174 | 0.282 | 0.978 | 0% | 0 |
| NOT VALIDATED | usdjpy_asia_range | 5m MA vs trade=ma_opposed | 1.25× | 12% | +17473 | 4.38 | 0.216 | 0.136 | 0.840 | 0% | 0 |
| NOT VALIDATED | usdjpy_asia_range | Entry hour (NY)=4 | 1.25× | 14% | +22042 | 6.91 | 0.106 | 0.036 | 0.282 | 0% | 0 |
| NOT VALIDATED | usdjpy_monday_or | Day of week=Thursday | 1.25× | 16% | +13008 | 3.00 | 0.194 | 0.406 | 1.000 | 0% | 0 |
| RISK-BUDGET PROFILE | usdjpy_monday_or | Entry hour (NY)=4 | 1.25× | 3% | +9609 | 6.37 | 0.011 | 0.033 | 0.996 | 0% | 0 |
| NOT VALIDATED | usdjpy_monday_or | Hourly RSI bucket=rsi_gt70 | 1.25× | 8% | +13837 | 5.77 | 0.044 | 0.058 | 1.000 | 0% | 0 |
| RISK-BUDGET PROFILE | usdjpy_monday_or | Prior-week range half=week_opposed | 1.25× | 70% | +73808 | 17.20 | 0.001 | 0.002 | 0.006 | 0% | 0 |
| RISK-BUDGET PROFILE | usdjpy_monday_or | Week of month=2 | 1.25× | 22% | +29808 | 9.61 | 0.038 | 0.018 | 0.794 | 0% | 0 |

## eurusd_st_pmc_3r Day of week=Thursday @ 1.25×

```
HP coverage:               20.2%
Boosted campaigns:         175
Incremental net:           +8754
Incremental stress:        1043
Incremental N/S:           8.39
Full-book N/S base→sized:  3.18 → 3.52 (Δ+0.34)

Matched-placebo median N/S: 3.11
Actual percentile:          97.7
p_incremental_N/S:          0.0230
p_incremental_net:          0.0736
p_full-book_N/S:            0.0568
p_drawdown_improvement:     0.1116
p_shift_inc_N/S:            0.0080
p_master_inc_N/S:           0.0240
Frozen WF pos Δnet frac:    0.86
Discovery reappear count:   0

Decision: SIZE-UP VALIDATED
```

## eurusd_st_pmc_3r Day of week=Thursday @ 1.50×

```
HP coverage:               20.2%
Boosted campaigns:         175
Incremental net:           +17508
Incremental stress:        2086
Incremental N/S:           8.39
Full-book N/S base→sized:  3.18 → 3.85 (Δ+0.67)

Matched-placebo median N/S: 3.11
Actual percentile:          97.7
p_incremental_N/S:          0.0230
p_incremental_net:          0.0736
p_full-book_N/S:            0.0602
p_drawdown_improvement:     0.1484
p_shift_inc_N/S:            0.0080
p_master_inc_N/S:           0.0599
Frozen WF pos Δnet frac:    0.86
Discovery reappear count:   0

Decision: BORDERLINE PAPER
```

## eurusd_st_pmc_3r Day of week=Thursday @ 2.00×

```
HP coverage:               20.2%
Boosted campaigns:         175
Incremental net:           +35017
Incremental stress:        4172
Incremental N/S:           8.39
Full-book N/S base→sized:  3.18 → 4.45 (Δ+1.27)

Matched-placebo median N/S: 3.00
Actual percentile:          98.0
p_incremental_N/S:          0.0198
p_incremental_net:          0.0714
p_full-book_N/S:            0.0416
p_drawdown_improvement:     0.0980
p_shift_inc_N/S:            0.0080
p_master_inc_N/S:           0.1537
Frozen WF pos Δnet frac:    0.86
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## us30_monday_or Entry hour (NY)=11 @ 1.25×

```
HP coverage:               9.5%
Boosted campaigns:         106
Incremental net:           +4125
Incremental stress:        617
Incremental N/S:           6.69
Full-book N/S base→sized:  1.96 → 2.16 (Δ+0.20)

Matched-placebo median N/S: 0.49
Actual percentile:          98.5
p_incremental_N/S:          0.0152
p_incremental_net:          0.0412
p_full-book_N/S:            0.0790
p_drawdown_improvement:     0.4621
p_shift_inc_N/S:            0.0090
p_master_inc_N/S:           0.0359
Frozen WF pos Δnet frac:    0.57
Discovery reappear count:   0

Decision: SIZE-UP VALIDATED
```

## us30_monday_or Entry hour (NY)=11 @ 1.50×

```
HP coverage:               9.5%
Boosted campaigns:         106
Incremental net:           +8250
Incremental stress:        1233
Incremental N/S:           6.69
Full-book N/S base→sized:  1.96 → 2.36 (Δ+0.40)

Matched-placebo median N/S: 0.49
Actual percentile:          98.5
p_incremental_N/S:          0.0152
p_incremental_net:          0.0412
p_full-book_N/S:            0.0810
p_drawdown_improvement:     0.4131
p_shift_inc_N/S:            0.0090
p_master_inc_N/S:           0.0539
Frozen WF pos Δnet frac:    0.57
Discovery reappear count:   0

Decision: BORDERLINE PAPER
```

## us30_monday_or Entry hour (NY)=11 @ 2.00×

```
HP coverage:               9.5%
Boosted campaigns:         106
Incremental net:           +16500
Incremental stress:        2467
Incremental N/S:           6.69
Full-book N/S base→sized:  1.96 → 2.72 (Δ+0.76)

Matched-placebo median N/S: 0.49
Actual percentile:          98.5
p_incremental_N/S:          0.0156
p_incremental_net:          0.0410
p_full-book_N/S:            0.0780
p_drawdown_improvement:     0.3481
p_shift_inc_N/S:            0.0090
p_master_inc_N/S:           0.1058
Frozen WF pos Δnet frac:    0.57
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## eurusd_monday_or Hourly RSI vs trade=rsi_against_side @ 2.00×

```
HP coverage:               3.7%
Boosted campaigns:         106
Incremental net:           +45136
Incremental stress:        5006
Incremental N/S:           9.02
Full-book N/S base→sized:  1.90 → 2.77 (Δ+0.88)

Matched-placebo median N/S: -0.36
Actual percentile:          100.0
p_incremental_N/S:          0.0004
p_incremental_net:          0.0008
p_full-book_N/S:            0.0020
p_drawdown_improvement:     0.0852
p_shift_inc_N/S:            0.0020
p_master_inc_N/S:           0.0140
Frozen WF pos Δnet frac:    0.12
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## usdjpy_asia_range Hourly RSI bucket=rsi_gt70 @ 1.25×

```
HP coverage:               5.5%
Boosted campaigns:         47
Incremental net:           +14410
Incremental stress:        2137
Incremental N/S:           6.74
Full-book N/S base→sized:  8.65 → 9.26 (Δ+0.61)

Matched-placebo median N/S: 1.36
Actual percentile:          nan
p_incremental_N/S:          0.0456
p_incremental_net:          0.0132
p_full-book_N/S:            0.0358
p_drawdown_improvement:     nan
p_shift_inc_N/S:            0.0270
p_master_inc_N/S:           0.2800
Frozen WF pos Δnet frac:    nan
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## usdjpy_asia_range Hourly RSI bucket=rsi_gt70 @ 2.00×

```
HP coverage:               5.5%
Boosted campaigns:         47
Incremental net:           +57638
Incremental stress:        8547
Incremental N/S:           6.74
Full-book N/S base→sized:  8.65 → 11.02 (Δ+2.37)

Matched-placebo median N/S: 0.88
Actual percentile:          96.5
p_incremental_N/S:          0.0354
p_incremental_net:          0.0032
p_full-book_N/S:            0.0100
p_drawdown_improvement:     0.3147
p_shift_inc_N/S:            0.0280
p_master_inc_N/S:           0.4631
Frozen WF pos Δnet frac:    0.71
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## usdjpy_monday_or Entry hour (NY)=5 @ 1.25×

```
HP coverage:               3.5%
Boosted campaigns:         66
Incremental net:           +11876
Incremental stress:        2273
Incremental N/S:           5.22
Full-book N/S base→sized:  14.47 → 15.36 (Δ+0.88)

Matched-placebo median N/S: 2.16
Actual percentile:          nan
p_incremental_N/S:          0.1302
p_incremental_net:          0.0570
p_full-book_N/S:            0.0128
p_drawdown_improvement:     nan
p_shift_inc_N/S:            0.0590
p_master_inc_N/S:           1.0000
Frozen WF pos Δnet frac:    nan
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## usdjpy_monday_or Entry hour (NY)=5 @ 2.00×

```
HP coverage:               3.5%
Boosted campaigns:         66
Incremental net:           +47502
Incremental stress:        9092
Incremental N/S:           5.22
Full-book N/S base→sized:  14.47 → 16.70 (Δ+2.23)

Matched-placebo median N/S: 1.27
Actual percentile:          93.0
p_incremental_N/S:          0.0698
p_incremental_net:          0.0228
p_full-book_N/S:            0.0056
p_drawdown_improvement:     0.0378
p_shift_inc_N/S:            0.0599
p_master_inc_N/S:           0.8104
Frozen WF pos Δnet frac:    0.50
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## us30_monday_or Day of week=Friday @ 1.25×

```
HP coverage:               11.2%
Boosted campaigns:         125
Incremental net:           +1791
Incremental stress:        1301
Incremental N/S:           1.38
Full-book N/S base→sized:  1.96 → 2.11 (Δ+0.15)

Matched-placebo median N/S: 0.21
Actual percentile:          nan
p_incremental_N/S:          0.1738
p_incremental_net:          0.2530
p_full-book_N/S:            0.1564
p_drawdown_improvement:     nan
p_shift_inc_N/S:            0.2820
p_master_inc_N/S:           0.9780
Frozen WF pos Δnet frac:    nan
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## usdjpy_asia_range 5m MA vs trade=ma_opposed @ 1.25×

```
HP coverage:               12.0%
Boosted campaigns:         103
Incremental net:           +17473
Incremental stress:        3989
Incremental N/S:           4.38
Full-book N/S base→sized:  8.65 → 9.30 (Δ+0.65)

Matched-placebo median N/S: 2.27
Actual percentile:          nan
p_incremental_N/S:          0.2156
p_incremental_net:          0.0568
p_full-book_N/S:            0.0522
p_drawdown_improvement:     nan
p_shift_inc_N/S:            0.1360
p_master_inc_N/S:           0.8400
Frozen WF pos Δnet frac:    nan
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## usdjpy_asia_range Entry hour (NY)=4 @ 1.25×

```
HP coverage:               13.9%
Boosted campaigns:         120
Incremental net:           +22042
Incremental stress:        3188
Incremental N/S:           6.91
Full-book N/S base→sized:  8.65 → 9.37 (Δ+0.72)

Matched-placebo median N/S: 2.88
Actual percentile:          nan
p_incremental_N/S:          0.1062
p_incremental_net:          0.0502
p_full-book_N/S:            0.1112
p_drawdown_improvement:     nan
p_shift_inc_N/S:            0.0360
p_master_inc_N/S:           0.2820
Frozen WF pos Δnet frac:    nan
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## usdjpy_monday_or Day of week=Thursday @ 1.25×

```
HP coverage:               15.6%
Boosted campaigns:         297
Incremental net:           +13008
Incremental stress:        4339
Incremental N/S:           3.00
Full-book N/S base→sized:  14.47 → 14.31 (Δ-0.16)

Matched-placebo median N/S: 1.31
Actual percentile:          nan
p_incremental_N/S:          0.1944
p_incremental_net:          0.1890
p_full-book_N/S:            0.2760
p_drawdown_improvement:     nan
p_shift_inc_N/S:            0.4060
p_master_inc_N/S:           1.0000
Frozen WF pos Δnet frac:    nan
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## usdjpy_monday_or Entry hour (NY)=4 @ 1.25×

```
HP coverage:               3.4%
Boosted campaigns:         64
Incremental net:           +9609
Incremental stress:        1508
Incremental N/S:           6.37
Full-book N/S base→sized:  14.47 → 14.95 (Δ+0.47)

Matched-placebo median N/S: 0.76
Actual percentile:          nan
p_incremental_N/S:          0.0110
p_incremental_net:          0.0246
p_full-book_N/S:            0.0056
p_drawdown_improvement:     nan
p_shift_inc_N/S:            0.0330
p_master_inc_N/S:           0.9960
Frozen WF pos Δnet frac:    nan
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## usdjpy_monday_or Hourly RSI bucket=rsi_gt70 @ 1.25×

```
HP coverage:               7.8%
Boosted campaigns:         149
Incremental net:           +13837
Incremental stress:        2399
Incremental N/S:           5.77
Full-book N/S base→sized:  14.47 → 14.26 (Δ-0.21)

Matched-placebo median N/S: 2.14
Actual percentile:          nan
p_incremental_N/S:          0.0442
p_incremental_net:          0.0728
p_full-book_N/S:            0.5112
p_drawdown_improvement:     nan
p_shift_inc_N/S:            0.0580
p_master_inc_N/S:           1.0000
Frozen WF pos Δnet frac:    nan
Discovery reappear count:   0

Decision: NOT VALIDATED
```

## usdjpy_monday_or Prior-week range half=week_opposed @ 1.25×

```
HP coverage:               70.4%
Boosted campaigns:         1343
Incremental net:           +73808
Incremental stress:        4290
Incremental N/S:           17.20
Full-book N/S base→sized:  14.47 → 15.79 (Δ+1.32)

Matched-placebo median N/S: 9.32
Actual percentile:          nan
p_incremental_N/S:          0.0008
p_incremental_net:          0.0030
p_full-book_N/S:            0.0034
p_drawdown_improvement:     nan
p_shift_inc_N/S:            0.0020
p_master_inc_N/S:           0.0060
Frozen WF pos Δnet frac:    nan
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## usdjpy_monday_or Week of month=2 @ 1.25×

```
HP coverage:               21.9%
Boosted campaigns:         418
Incremental net:           +29808
Incremental stress:        3103
Incremental N/S:           9.61
Full-book N/S base→sized:  14.47 → 15.93 (Δ+1.45)

Matched-placebo median N/S: 4.39
Actual percentile:          nan
p_incremental_N/S:          0.0378
p_incremental_net:          0.1050
p_full-book_N/S:            0.0146
p_drawdown_improvement:     nan
p_shift_inc_N/S:            0.0180
p_master_inc_N/S:           0.7940
Frozen WF pos Δnet frac:    nan
Discovery reappear count:   0

Decision: RISK-BUDGET PROFILE
```

## Rare HP sizing sensitivity (NOT validation)

Linear campaign scaling only. Do **not** promote from this table; run `--rare-2x` (or the intended multiplier) through the full null suite.

### Incidence < 10% (top by avg lift, 2×/3×/4×)

| book | condition=bucket | hp% | mult | Δnet | stress× | N/S base→sz | inc N/S | raw_loss× |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 5.5 | 2× | +57638 | 1.04 | 8.65→11.02 | 6.74 | 1.06 |
| usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 5.5 | 3× | +115276 | 1.25 | 8.65→11.42 | 6.74 | 1.12 |
| usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 5.5 | 4× | +172915 | 1.56 | 8.65→10.90 | 6.74 | 1.17 |
| usdjpy_monday_or | Entry hour (NY)=5 | 3.5 | 2× | +47502 | 1.01 | 14.47→16.70 | 5.22 | 1.03 |
| usdjpy_monday_or | Entry hour (NY)=5 | 3.5 | 3× | +95004 | 1.10 | 14.47→17.36 | 5.22 | 1.07 |
| usdjpy_monday_or | Entry hour (NY)=5 | 3.5 | 4× | +142507 | 1.20 | 14.47→17.91 | 5.22 | 1.10 |
| usdjpy_monday_or | Entry hour (NY)=4 | 3.4 | 2× | +38435 | 1.05 | 14.47→15.59 | 6.37 | 1.03 |
| usdjpy_monday_or | Entry hour (NY)=4 | 3.4 | 3× | +76870 | 1.17 | 14.47→15.64 | 6.37 | 1.06 |
| usdjpy_monday_or | Entry hour (NY)=4 | 3.4 | 4× | +115306 | 1.37 | 14.47→14.69 | 6.37 | 1.09 |
| eurusd_monday_or | Hourly RSI vs trade=rsi_against_side | 3.7 | 2× | +45136 | 0.99 | 1.90→2.77 | 9.02 | 1.02 |
| eurusd_monday_or | Hourly RSI vs trade=rsi_against_side | 3.7 | 3× | +90272 | 0.99 | 1.90→3.62 | 9.02 | 1.05 |
| eurusd_monday_or | Hourly RSI vs trade=rsi_against_side | 3.7 | 4× | +135408 | 1.01 | 1.90→4.36 | 9.02 | 1.07 |
| eurusd_monday_or | Entry hour (NY)=4 | 1.8 | 2× | +21565 | 1.07 | 1.90→2.15 | 2.09 | 1.03 |
| eurusd_monday_or | Entry hour (NY)=4 | 1.8 | 3× | +43130 | 1.13 | 1.90→2.38 | 2.09 | 1.05 |
| eurusd_monday_or | Entry hour (NY)=4 | 1.8 | 4× | +64695 | 1.21 | 1.90→2.56 | 2.09 | 1.08 |
| eurusd_monday_or | Entry hour (NY)=18 | 3.0 | 2× | +28010 | 1.04 | 1.90→2.33 | 3.77 | 1.02 |
| eurusd_monday_or | Entry hour (NY)=18 | 3.0 | 3× | +56020 | 1.08 | 1.90→2.71 | 3.77 | 1.05 |
| eurusd_monday_or | Entry hour (NY)=18 | 3.0 | 4× | +84030 | 1.13 | 1.90→3.06 | 3.77 | 1.07 |
| eurusd_monday_or | 5m MA vs trade=ma_opposed | 9.4 | 2× | +76629 | 1.03 | 1.90→3.23 | 12.15 | 1.07 |
| eurusd_monday_or | 5m MA vs trade=ma_opposed | 9.4 | 3× | +153259 | 1.09 | 1.90→4.36 | 12.15 | 1.14 |
| eurusd_monday_or | 5m MA vs trade=ma_opposed | 9.4 | 4× | +229888 | 1.16 | 1.90→5.32 | 12.15 | 1.21 |
| usdjpy_monday_or | Hourly RSI bucket=rsi_gt70 | 7.8 | 2× | +55350 | 1.27 | 14.47→13.52 | 5.77 | 1.07 |
| usdjpy_monday_or | Hourly RSI bucket=rsi_gt70 | 7.8 | 3× | +110699 | 1.55 | 14.47→12.84 | 5.77 | 1.14 |
| usdjpy_monday_or | Hourly RSI bucket=rsi_gt70 | 7.8 | 4× | +166049 | 1.83 | 14.47→12.37 | 5.77 | 1.21 |
| usdjpy_monday_or | Entry hour (NY)=1 | 9.0 | 2× | +60908 | 1.43 | 14.47→12.25 | 4.02 | 1.09 |
| usdjpy_monday_or | Entry hour (NY)=1 | 9.0 | 3× | +121816 | 1.92 | 14.47→10.65 | 4.02 | 1.17 |
| usdjpy_monday_or | Entry hour (NY)=1 | 9.0 | 4× | +182724 | 2.42 | 14.47→9.71 | 4.02 | 1.26 |
| eurusd_monday_or | Entry hour (NY)=10 | 5.1 | 2× | +27143 | 1.01 | 1.90→2.37 | 2.24 | 1.05 |
| eurusd_monday_or | Entry hour (NY)=10 | 5.1 | 3× | +54285 | 1.06 | 1.90→2.75 | 2.24 | 1.10 |
| eurusd_monday_or | Entry hour (NY)=10 | 5.1 | 4× | +81428 | 1.26 | 1.90→2.69 | 2.24 | 1.14 |
| us30_monday_or | Entry hour (NY)=11 | 9.5 | 2× | +16500 | 1.10 | 1.96→2.72 | 6.69 | 1.07 |
| us30_monday_or | Entry hour (NY)=11 | 9.5 | 3× | +33001 | 1.20 | 1.96→3.36 | 6.69 | 1.13 |
| us30_monday_or | Entry hour (NY)=11 | 9.5 | 4× | +49501 | 1.30 | 1.96→3.89 | 6.69 | 1.20 |
| eurusd_monday_or | Entry hour (NY)=14 | 7.6 | 2× | +33277 | 1.04 | 1.90→2.42 | 2.95 | 1.06 |
| eurusd_monday_or | Entry hour (NY)=14 | 7.6 | 3× | +66554 | 1.11 | 1.90→2.83 | 2.95 | 1.12 |
| eurusd_monday_or | Entry hour (NY)=14 | 7.6 | 4× | +99831 | 1.25 | 1.90→2.99 | 2.95 | 1.18 |
| us30_monday_or | Entry hour (NY)=8 | 4.8 | 2× | +7174 | 1.02 | 1.96→2.37 | 2.75 | 1.04 |
| us30_monday_or | Entry hour (NY)=8 | 4.8 | 3× | +14347 | 1.03 | 1.96→2.77 | 2.75 | 1.08 |
| us30_monday_or | Entry hour (NY)=8 | 4.8 | 4× | +21521 | 1.05 | 1.96→3.16 | 2.75 | 1.12 |
| eurusd_monday_or | Entry hour (NY)=16 | 4.4 | 2× | +16841 | 0.90 | 1.90→2.46 | 1.15 | 1.04 |
| eurusd_monday_or | Entry hour (NY)=16 | 4.4 | 3× | +33683 | 0.86 | 1.90→2.94 | 1.15 | 1.08 |
| eurusd_monday_or | Entry hour (NY)=16 | 4.4 | 4× | +50524 | 0.94 | 1.90→3.01 | 1.15 | 1.12 |
| usdjpy_monday_or | Entry hour (NY)=15 | 6.9 | 2× | +32611 | 1.11 | 14.47→14.43 | 2.93 | 1.06 |
| usdjpy_monday_or | Entry hour (NY)=15 | 6.9 | 3× | +65221 | 1.29 | 14.47→13.70 | 2.93 | 1.11 |
| usdjpy_monday_or | Entry hour (NY)=15 | 6.9 | 4× | +97832 | 1.47 | 14.47→13.14 | 2.93 | 1.17 |

## Artifacts

- `pairs/<slug>/RESULT.json` + campaign_table / null CSVs / WF
- `rare_size_impact.csv` (sensitivity only)
- `SUMMARY.md` / `EMAIL.txt`
