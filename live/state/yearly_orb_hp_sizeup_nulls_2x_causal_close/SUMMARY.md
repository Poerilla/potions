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
| NOT VALIDATED | nq_yorb | week_of_month=2 | 2.00× | 32% | +534932 | +8.33 | 0.171 | 0.144 | 0.056 | nan% | 0 |
| NOT VALIDATED | nq_yorb | or_width_bucket=or_wide | 2.00× | 29% | +709830 | -0.45 | 1.000 | 0.953 | 1.000 | nan% | 0 |
| NOT VALIDATED | es_yorb | rsi_align=rsi_against_side | 2.00× | 18% | +169238 | +0.66 | 0.829 | 0.752 | 0.944 | nan% | 0 |
| NOT VALIDATED | es_yorb | quarter=Q4 | 2.00× | 26% | +56563 | +0.35 | 1.000 | 0.889 | 1.000 | nan% | 0 |
| NOT VALIDATED | ym_yorb | atr_pct_bucket=atr_pctl_q4 | 2.00× | 23% | +108014 | -0.04 | 0.262 | 0.281 | 1.000 | nan% | 0 |
| NOT VALIDATED | ym_yorb | prior_year_ret_bucket=prior_yr_mid | 2.00× | 25% | +187895 | +2.92 | 1.000 | 0.921 | 0.469 | nan% | 0 |

## nq_yorb week_of_month=2 @ 2.00×

```
HP coverage:               32.4%
Boosted campaigns:         22
Incremental net (report):  +534932
Incremental stress:        15588
Incremental sleeve N/S:    34.32
Full-book N/S base→sized:  12.63 → 20.96 (Δ+8.33)

Matched-placebo median ΔN/S: 4.13
Actual ΔN/S percentile:      82.9
p_delta_NS (placebo):        0.1708
p_candidate_NS (book):       0.1708
p_delta_net (report):        0.3703
p_drawdown_improvement:      0.1538
p_shift_delta_NS:            0.1439
p_master_delta_NS:           0.0559
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## nq_yorb or_width_bucket=or_wide @ 2.00×

```
HP coverage:               29.4%
Boosted campaigns:         20
Incremental net (report):  +709830
Incremental stress:        60507
Incremental sleeve N/S:    11.73
Full-book N/S base→sized:  12.63 → 12.18 (Δ-0.45)

Matched-placebo median ΔN/S: -0.45
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.9530
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_yorb rsi_align=rsi_against_side @ 2.00×

```
HP coverage:               17.8%
Boosted campaigns:         13
Incremental net (report):  +169238
Incremental stress:        72492
Incremental sleeve N/S:    2.33
Full-book N/S base→sized:  0.47 → 1.14 (Δ+0.66)

Matched-placebo median ΔN/S: 0.85
Actual ΔN/S percentile:      17.1
p_delta_NS (placebo):        0.8292
p_candidate_NS (book):       0.8292
p_delta_net (report):        0.8292
p_drawdown_improvement:      0.8292
p_shift_delta_NS:            0.7522
p_master_delta_NS:           0.9441
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_yorb quarter=Q4 @ 2.00×

```
HP coverage:               26.0%
Boosted campaigns:         19
Incremental net (report):  +56563
Incremental stress:        30424
Incremental sleeve N/S:    1.86
Full-book N/S base→sized:  0.47 → 0.83 (Δ+0.35)

Matched-placebo median ΔN/S: 0.35
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.8891
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## ym_yorb atr_pct_bucket=atr_pctl_q4 @ 2.00×

```
HP coverage:               23.5%
Boosted campaigns:         19
Incremental net (report):  +108014
Incremental stress:        43344
Incremental sleeve N/S:    2.49
Full-book N/S base→sized:  2.60 → 2.55 (Δ-0.04)

Matched-placebo median ΔN/S: -0.23
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

## ym_yorb prior_year_ret_bucket=prior_yr_mid @ 2.00×

```
HP coverage:               24.7%
Boosted campaigns:         20
Incremental net (report):  +187895
Incremental stress:        10404
Incremental sleeve N/S:    18.06
Full-book N/S base→sized:  2.60 → 5.52 (Δ+2.92)

Matched-placebo median ΔN/S: 2.92
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.9211
p_master_delta_NS:           0.4691
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
