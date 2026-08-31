# Matched-added-exposure validation suite

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
- **BORDERLINE PAPER** — same gates except `0.05 < p_master_ΔNS ≤ 0.10`.
  Shadow / controlled paper only — **no** historical size-up promotion claim.
- **RISK THROTTLE** — `p_master_ΔNS > 0.10` or WF fails (or coverage too
  broad). May raise N/S without superior incremental selection — not alpha.
- **NOT VALIDATED** — fails equal-added random exposure / timing / causal.
- **PENDING** — required null/multiplier replay missing.

## Pair results (matched-added-exposure)

| decision | book | condition=bucket | mult | hp% | Δnet | ΔN/S | p_plac ΔNS | p_shift ΔNS | p_master ΔNS | WF+ | reapp |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NOT VALIDATED | nq_yorb | week_of_month=2 | 1.25× | 32% | +133733 | +2.21 | 0.365 | 0.321 | 0.210 | nan% | 0 |
| NOT VALIDATED | nq_yorb | or_width_bucket=or_wide | 1.25× | 29% | +177458 | -0.18 | 1.000 | 0.966 | 1.000 | nan% | 0 |
| NOT VALIDATED | es_yorb | rsi_align=rsi_against_side | 1.25× | 18% | +42310 | +0.24 | 0.829 | 0.750 | 0.858 | nan% | 0 |
| NOT VALIDATED | es_yorb | quarter=Q4 | 1.25× | 26% | +14141 | +0.09 | 1.000 | 0.894 | 1.000 | nan% | 0 |
| NOT VALIDATED | ym_yorb | atr_pct_bucket=atr_pctl_q4 | 1.25× | 23% | +27004 | -0.02 | 0.262 | 0.281 | 1.000 | nan% | 0 |
| NOT VALIDATED | ym_yorb | prior_year_ret_bucket=prior_yr_mid | 1.25× | 25% | +46974 | +0.75 | 1.000 | 0.921 | 0.563 | nan% | 0 |

## nq_yorb week_of_month=2 @ 1.25×

```
HP coverage:               32.4%
Boosted campaigns:         22
Incremental net (report):  +133733
Incremental stress:        3897
Incremental sleeve N/S:    34.32
Full-book N/S base→sized:  12.63 → 14.85 (Δ+2.21)

Matched-placebo median ΔN/S: 2.07
Actual ΔN/S percentile:      63.5
p_delta_NS (placebo):        0.3647
p_candidate_NS (book):       0.3647
p_delta_net (report):        0.3703
p_drawdown_improvement:      0.9452
p_shift_delta_NS:            0.3207
p_master_delta_NS:           0.2096
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## nq_yorb or_width_bucket=or_wide @ 1.25×

```
HP coverage:               29.4%
Boosted campaigns:         20
Incremental net (report):  +177458
Incremental stress:        15127
Incremental sleeve N/S:    11.73
Full-book N/S base→sized:  12.63 → 12.45 (Δ-0.18)

Matched-placebo median ΔN/S: -0.18
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.9660
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_yorb rsi_align=rsi_against_side @ 1.25×

```
HP coverage:               17.8%
Boosted campaigns:         13
Incremental net (report):  +42310
Incremental stress:        18123
Incremental sleeve N/S:    2.33
Full-book N/S base→sized:  0.47 → 0.71 (Δ+0.24)

Matched-placebo median ΔN/S: 0.29
Actual ΔN/S percentile:      17.1
p_delta_NS (placebo):        0.8292
p_candidate_NS (book):       0.8292
p_delta_net (report):        0.8292
p_drawdown_improvement:      0.8292
p_shift_delta_NS:            0.7502
p_master_delta_NS:           0.8583
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_yorb quarter=Q4 @ 1.25×

```
HP coverage:               26.0%
Boosted campaigns:         19
Incremental net (report):  +14141
Incremental stress:        7606
Incremental sleeve N/S:    1.86
Full-book N/S base→sized:  0.47 → 0.57 (Δ+0.09)

Matched-placebo median ΔN/S: 0.09
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.8941
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## ym_yorb atr_pct_bucket=atr_pctl_q4 @ 1.25×

```
HP coverage:               23.5%
Boosted campaigns:         19
Incremental net (report):  +27004
Incremental stress:        10836
Incremental sleeve N/S:    2.49
Full-book N/S base→sized:  2.60 → 2.58 (Δ-0.02)

Matched-placebo median ΔN/S: -0.09
Actual ΔN/S percentile:      73.8
p_delta_NS (placebo):        0.2621
p_candidate_NS (book):       0.2621
p_delta_net (report):        0.3367
p_drawdown_improvement:      0.3011
p_shift_delta_NS:            0.2807
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## ym_yorb prior_year_ret_bucket=prior_yr_mid @ 1.25×

```
HP coverage:               24.7%
Boosted campaigns:         20
Incremental net (report):  +46974
Incremental stress:        2601
Incremental sleeve N/S:    18.06
Full-book N/S base→sized:  2.60 → 3.34 (Δ+0.75)

Matched-placebo median ΔN/S: 0.75
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.9211
p_master_delta_NS:           0.5629
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
