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
| NOT VALIDATED | nq_yorb | ma_stack=ma_mixed | 1.25× | 26% | +163081 | +5.47 | 0.053 | 0.048 | 1.000 | nan% | 0 |
| NOT VALIDATED | nq_yorb | ma_align=ma_mixed | 1.25× | 26% | +163081 | +5.47 | 0.053 | 0.048 | 1.000 | nan% | 0 |
| NOT VALIDATED | es_yorb | atr_pct_bucket=atr_pctl_q4 | 1.25× | 30% | +127902 | +3.45 | 0.495 | 0.434 | 0.347 | nan% | 0 |
| NOT VALIDATED | es_yorb | side=short | 1.25× | 26% | +70025 | +1.89 | 1.000 | 0.876 | 0.898 | nan% | 0 |
| NOT VALIDATED | ym_yorb | side=short | 1.25× | 21% | +41810 | +2.03 | 1.000 | 0.878 | 1.000 | nan% | 0 |
| NOT VALIDATED | ym_yorb | atr_pct_bucket=atr_pctl_q4 | 1.25× | 23% | +54297 | +1.19 | 0.237 | 0.240 | 1.000 | nan% | 0 |

## nq_yorb ma_stack=ma_mixed @ 1.25×

```
HP coverage:               26.5%
Boosted campaigns:         18
Incremental net (report):  +163081
Incremental stress:        0
Incremental sleeve N/S:    99.00
Full-book N/S base→sized:  47.52 → 52.98 (Δ+5.47)

Matched-placebo median ΔN/S: 4.79
Actual ΔN/S percentile:      94.7
p_delta_NS (placebo):        0.0530
p_candidate_NS (book):       0.0530
p_delta_net (report):        0.0530
p_drawdown_improvement:      0.6735
p_shift_delta_NS:            0.0480
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## nq_yorb ma_align=ma_mixed @ 1.25×

```
HP coverage:               26.5%
Boosted campaigns:         18
Incremental net (report):  +163081
Incremental stress:        0
Incremental sleeve N/S:    99.00
Full-book N/S base→sized:  47.52 → 52.98 (Δ+5.47)

Matched-placebo median ΔN/S: 4.79
Actual ΔN/S percentile:      94.7
p_delta_NS (placebo):        0.0530
p_candidate_NS (book):       0.0530
p_delta_net (report):        0.0530
p_drawdown_improvement:      0.6735
p_shift_delta_NS:            0.0480
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_yorb atr_pct_bucket=atr_pctl_q4 @ 1.25×

```
HP coverage:               30.1%
Boosted campaigns:         22
Incremental net (report):  +127902
Incremental stress:        1906
Incremental sleeve N/S:    67.11
Full-book N/S base→sized:  17.70 → 21.15 (Δ+3.45)

Matched-placebo median ΔN/S: 3.18
Actual ΔN/S percentile:      50.5
p_delta_NS (placebo):        0.4949
p_candidate_NS (book):       0.4949
p_delta_net (report):        0.4949
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.4336
p_master_delta_NS:           0.3473
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## es_yorb side=short @ 1.25×

```
HP coverage:               26.0%
Boosted campaigns:         19
Incremental net (report):  +70025
Incremental stress:        5843
Incremental sleeve N/S:    11.98
Full-book N/S base→sized:  17.70 → 19.59 (Δ+1.89)

Matched-placebo median ΔN/S: 1.89
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.8761
p_master_delta_NS:           0.8982
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## ym_yorb side=short @ 1.25×

```
HP coverage:               21.0%
Boosted campaigns:         17
Incremental net (report):  +41810
Incremental stress:        0
Incremental sleeve N/S:    99.00
Full-book N/S base→sized:  25.08 → 27.11 (Δ+2.03)

Matched-placebo median ΔN/S: 2.03
Actual ΔN/S percentile:      0.0
p_delta_NS (placebo):        1.0000
p_candidate_NS (book):       1.0000
p_delta_net (report):        1.0000
p_drawdown_improvement:      1.0000
p_shift_delta_NS:            0.8781
p_master_delta_NS:           1.0000
Frozen WF pos Δnet frac:     nan
Discovery reappear count:    0

Decision: NOT VALIDATED
```

## ym_yorb atr_pct_bucket=atr_pctl_q4 @ 1.25×

```
HP coverage:               23.5%
Boosted campaigns:         19
Incremental net (report):  +54297
Incremental stress:        1315
Incremental sleeve N/S:    41.30
Full-book N/S base→sized:  25.08 → 26.27 (Δ+1.19)

Matched-placebo median ΔN/S: 0.88
Actual ΔN/S percentile:      76.3
p_delta_NS (placebo):        0.2374
p_candidate_NS (book):       0.2374
p_delta_net (report):        0.2785
p_drawdown_improvement:      0.5027
p_shift_delta_NS:            0.2398
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
