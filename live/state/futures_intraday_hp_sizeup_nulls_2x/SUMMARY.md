# Futures HP size-up nulls @ 2× (`futures_intraday_hp_sizeup_v1`, predeclared)

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
| NOT VALIDATED | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 2.00× | 28% | +158178 | +4.08 | 0.106 | 0.099 | 0.619 | 100% | 2 |
| NOT VALIDATED | ym_prior_opposed_rl | Overnight range third=on_middle | 2.00× | 25% | +117872 | +1.81 | 0.161 | 0.100 | 0.980 | 100% | 1 |
| PROVISIONAL PAPER | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 2.00× | 30% | +581952 | +12.20 | 0.042 | 0.028 | 0.064 | 100% | 1 |

## es_prior_opposed_legacy ST-event age=st_age_gt180m @ 2.00×

```
HP coverage:               27.8%
Boosted campaigns:         68
Incremental net (report):  +158178
Incremental stress:        6882
Incremental sleeve N/S:    22.98
Full-book N/S base→sized:  12.48 → 16.55 (Δ+4.08)

Matched-placebo median ΔN/S: 0.39
Actual ΔN/S percentile:      89.4
p_delta_NS (placebo):        0.1062
p_candidate_NS (book):       0.1062
p_delta_net (report):        0.0412
p_drawdown_improvement:      0.1964
p_shift_delta_NS:            0.0989
p_master_delta_NS:           0.6188
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    2

Decision: NOT VALIDATED
```

## ym_prior_opposed_rl Overnight range third=on_middle @ 2.00×

```
HP coverage:               24.8%
Boosted campaigns:         108
Incremental net (report):  +117872
Incremental stress:        8318
Incremental sleeve N/S:    14.17
Full-book N/S base→sized:  9.74 → 11.55 (Δ+1.81)

Matched-placebo median ΔN/S: 0.51
Actual ΔN/S percentile:      83.9
p_delta_NS (placebo):        0.1614
p_candidate_NS (book):       0.1614
p_delta_net (report):        0.1700
p_drawdown_improvement:      0.3759
p_shift_delta_NS:            0.0999
p_master_delta_NS:           0.9800
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    1

Decision: NOT VALIDATED
```

## nq_prior_opposed_rl Opening 15m range vs ATR=or_norm @ 2.00×

```
HP coverage:               29.9%
Boosted campaigns:         129
Incremental net (report):  +581952
Incremental stress:        19855
Incremental sleeve N/S:    29.31
Full-book N/S base→sized:  24.06 → 36.26 (Δ+12.20)

Matched-placebo median ΔN/S: 0.61
Actual ΔN/S percentile:      95.8
p_delta_NS (placebo):        0.0422
p_candidate_NS (book):       0.0422
p_delta_net (report):        0.0514
p_drawdown_improvement:      0.0768
p_shift_delta_NS:            0.0280
p_master_delta_NS:           0.0639
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    1

Decision: PROVISIONAL PAPER
```

## Rare HP sizing sensitivity (NOT validation)

Linear campaign scaling only. Do **not** promote from this table; run `--rare-2x` (or the intended multiplier) through the full null suite.

_none_
## Artifacts

- `pairs/<slug>/RESULT.json` + campaign_table / null CSVs / WF
- `rare_size_impact.csv` (sensitivity only)
- `SUMMARY.md` / `EMAIL.txt`
