# Futures HP size-up nulls (`futures_intraday_hp_sizeup_v1`)

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
| NOT VALIDATED | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 1.25× | 28% | +39544 | +1.23 | 0.089 | 0.088 | 0.880 | 100% | 2 |
| NOT VALIDATED | es_prior_opposed_legacy | Week of month=1 | 1.25× | 29% | +40781 | +0.21 | 0.508 | 0.491 | 1.000 | 100% | 0 |
| NOT VALIDATED | es_prior_opposed_legacy | Prior RTH close location=prior_close_mid_third | 1.25× | 25% | +29217 | +0.66 | 0.299 | 0.284 | 1.000 | 100% | 0 |
| NOT VALIDATED | es_st_pmc_ma_bull | Day of week=Tuesday | 1.25× | 22% | +16134 | +0.30 | 0.248 | 0.186 | 0.944 | 71% | 1 |
| RISK THROTTLE | es_st_pmc_ma_bull | ST-event age=st_age_gt180m | 1.25× | 28% | +17612 | +0.34 | 0.024 | 0.028 | 0.870 | 71% | 1 |
| NOT VALIDATED | es_st_pmc_ma_bull | Prior RTH range percentile=prior_range_norm | 1.25× | 26% | +14238 | +0.16 | 0.831 | 0.636 | 1.000 | 86% | 0 |
| NOT VALIDATED | es_prior_opposed_legacy | Yearly ORB direction=yor_up | 1.25× | 57% | +61521 | +2.20 | 0.423 | 0.319 | 0.267 | 75% | 0 |
| NOT VALIDATED | es_prior_opposed_legacy | Monthly OR direction=mor_down | 1.25× | 32% | +40005 | +1.10 | 0.221 | 0.201 | 0.914 | 100% | 0 |
| NOT VALIDATED | es_st_pmc_ma_bull | Monthly OR direction=mor_up | 1.25× | 60% | +37441 | +0.55 | 0.825 | 0.584 | 0.361 | 71% | 0 |
| NOT VALIDATED | es_prior_opposed_legacy | Weekly ATR trend vs trade=w_atr_aligned | 1.25× | 43% | +47142 | -0.40 | 0.389 | 0.456 | 1.000 | 100% | 0 |
| NOT VALIDATED | es_prior_opposed_legacy | Prior quarter type=q_break_up | 1.25× | 77% | +78983 | +2.59 | 1.000 | 0.724 | 0.144 | 100% | 0 |

## es_prior_opposed_legacy ST-event age=st_age_gt180m @ 1.25×

```
HP coverage:               27.8%
Boosted campaigns:         68
Incremental net (report):  +39544
Incremental stress:        1721
Incremental sleeve N/S:    22.98
Full-book N/S base→sized:  12.48 → 13.70 (Δ+1.23)

Matched-placebo median ΔN/S: 0.23
Actual ΔN/S percentile:      91.1
p_delta_NS (placebo):        0.0890
p_candidate_NS (book):       0.0890
p_delta_net (report):        0.0412
p_drawdown_improvement:      0.1880
p_shift_delta_NS:            0.0879
p_master_delta_NS:           0.8802
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    2

Decision: NOT VALIDATED
```

## es_prior_opposed_legacy Week of month=1 @ 1.25×

```
HP coverage:               29.4%
Boosted campaigns:         72
Incremental net (report):  +40781
Incremental stress:        3738
Incremental sleeve N/S:    10.91
Full-book N/S base→sized:  12.48 → 12.68 (Δ+0.21)

Matched-placebo median ΔN/S: 0.22
Actual ΔN/S percentile:      49.2
p_delta_NS (placebo):        0.5085
p_candidate_NS (book):       0.5085
p_delta_net (report):        0.2643
p_drawdown_improvement:      0.5989
p_shift_delta_NS:            0.4905
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_prior_opposed_legacy Prior RTH close location=prior_close_mid_third @ 1.25×

```
HP coverage:               24.9%
Boosted campaigns:         61
Incremental net (report):  +29217
Incremental stress:        2768
Incremental sleeve N/S:    10.56
Full-book N/S base→sized:  12.48 → 13.14 (Δ+0.66)

Matched-placebo median ΔN/S: 0.30
Actual ΔN/S percentile:      70.1
p_delta_NS (placebo):        0.2987
p_candidate_NS (book):       0.2987
p_delta_net (report):        0.2494
p_drawdown_improvement:      0.4391
p_shift_delta_NS:            0.2837
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_st_pmc_ma_bull Day of week=Tuesday @ 1.25×

```
HP coverage:               22.4%
Boosted campaigns:         50
Incremental net (report):  +16134
Incremental stress:        3143
Incremental sleeve N/S:    5.13
Full-book N/S base→sized:  2.25 → 2.55 (Δ+0.30)

Matched-placebo median ΔN/S: 0.19
Actual ΔN/S percentile:      75.2
p_delta_NS (placebo):        0.2480
p_candidate_NS (book):       0.2480
p_delta_net (report):        0.2480
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.1858
p_master_delta_NS:           0.9441
Frozen WF pos Δnet frac:     0.71
Discovery reappear count:    1

Decision: NOT VALIDATED
```

## es_st_pmc_ma_bull ST-event age=st_age_gt180m @ 1.25×

```
HP coverage:               27.8%
Boosted campaigns:         62
Incremental net (report):  +17612
Incremental stress:        4764
Incremental sleeve N/S:    3.70
Full-book N/S base→sized:  2.25 → 2.59 (Δ+0.34)

Matched-placebo median ΔN/S: 0.09
Actual ΔN/S percentile:      97.6
p_delta_NS (placebo):        0.0240
p_candidate_NS (book):       0.0240
p_delta_net (report):        0.0396
p_drawdown_improvement:      0.3347
p_shift_delta_NS:            0.0280
p_master_delta_NS:           0.8703
Frozen WF pos Δnet frac:     0.71
Discovery reappear count:    1

Decision: RISK THROTTLE
```

## es_st_pmc_ma_bull Prior RTH range percentile=prior_range_norm @ 1.25×

```
HP coverage:               25.6%
Boosted campaigns:         57
Incremental net (report):  +14238
Incremental stress:        5039
Incremental sleeve N/S:    2.83
Full-book N/S base→sized:  2.25 → 2.41 (Δ+0.16)

Matched-placebo median ΔN/S: 0.27
Actual ΔN/S percentile:      16.9
p_delta_NS (placebo):        0.8306
p_candidate_NS (book):       0.8306
p_delta_net (report):        0.8306
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.6364
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     0.86
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_prior_opposed_legacy Yearly ORB direction=yor_up @ 1.25×

```
HP coverage:               56.7%
Boosted campaigns:         139
Incremental net (report):  +61521
Incremental stress:        4216
Incremental sleeve N/S:    14.59
Full-book N/S base→sized:  12.48 → 14.68 (Δ+2.20)

Matched-placebo median ΔN/S: 2.20
Actual ΔN/S percentile:      57.7
p_delta_NS (placebo):        0.4227
p_candidate_NS (book):       0.4227
p_delta_net (report):        0.4227
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.3187
p_master_delta_NS:           0.2675
Frozen WF pos Δnet frac:     0.75
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_prior_opposed_legacy Monthly OR direction=mor_down @ 1.25×

```
HP coverage:               32.2%
Boosted campaigns:         79
Incremental net (report):  +40005
Incremental stress:        4702
Incremental sleeve N/S:    8.51
Full-book N/S base→sized:  12.48 → 13.58 (Δ+1.10)

Matched-placebo median ΔN/S: 0.71
Actual ΔN/S percentile:      77.9
p_delta_NS (placebo):        0.2208
p_candidate_NS (book):       0.2208
p_delta_net (report):        0.1142
p_drawdown_improvement:      0.4683
p_shift_delta_NS:            0.2008
p_master_delta_NS:           0.9142
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_st_pmc_ma_bull Monthly OR direction=mor_up @ 1.25×

```
HP coverage:               60.1%
Boosted campaigns:         134
Incremental net (report):  +37441
Incremental stress:        6935
Incremental sleeve N/S:    5.40
Full-book N/S base→sized:  2.25 → 2.80 (Δ+0.55)

Matched-placebo median ΔN/S: 0.62
Actual ΔN/S percentile:      17.5
p_delta_NS (placebo):        0.8250
p_candidate_NS (book):       0.8250
p_delta_net (report):        0.8250
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.5844
p_master_delta_NS:           0.3613
Frozen WF pos Δnet frac:     0.71
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_prior_opposed_legacy Weekly ATR trend vs trade=w_atr_aligned @ 1.25×

```
HP coverage:               43.3%
Boosted campaigns:         106
Incremental net (report):  +47142
Incremental stress:        5713
Incremental sleeve N/S:    8.25
Full-book N/S base→sized:  12.48 → 12.08 (Δ-0.40)

Matched-placebo median ΔN/S: -0.58
Actual ΔN/S percentile:      61.1
p_delta_NS (placebo):        0.3887
p_candidate_NS (book):       0.3887
p_delta_net (report):        0.5551
p_drawdown_improvement:      0.3291
p_shift_delta_NS:            0.4555
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_prior_opposed_legacy Prior quarter type=q_break_up @ 1.25×

```
HP coverage:               77.1%
Boosted campaigns:         189
Incremental net (report):  +78983
Incremental stress:        4702
Incremental sleeve N/S:    16.80
Full-book N/S base→sized:  12.48 → 15.06 (Δ+2.59)

Matched-placebo median ΔN/S: 2.59
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.7243
p_master_delta_NS:           0.1437
Frozen WF pos Δnet frac:     1.00
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
