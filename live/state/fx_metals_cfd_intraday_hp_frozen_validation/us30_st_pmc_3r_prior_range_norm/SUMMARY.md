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
| NOT VALIDATED | us30_st_pmc_3r | Prior-day range percentile=prior_range_norm | 1.25× | 31% | +2213 | +0.65 | 0.009 | 0.096 | 0.972 | 100% | 2 |

## us30_st_pmc_3r Prior-day range percentile=prior_range_norm @ 1.25×

```
HP coverage:               31.3%
Boosted campaigns:         181
Incremental net (report):  +2213
Incremental stress:        69
Incremental sleeve N/S:    32.10
Full-book N/S base→sized:  44.20 → 44.84 (Δ+0.65)

Matched-placebo median ΔN/S: -1.38
Actual ΔN/S percentile:      99.1
p_delta_NS (placebo):        0.0088
p_candidate_NS (book):       0.0088
p_delta_net (report):        0.0016
p_drawdown_improvement:      0.2264
p_shift_delta_NS:            0.0959
p_master_delta_NS:           0.9721
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    2

Decision: NOT VALIDATED
```

## Rare HP sizing sensitivity (NOT validation)

Linear campaign scaling only. Do **not** promote from this table; run `--rare-2x` (or the intended multiplier) through the full null suite.

_none_
## Artifacts

- `pairs/<slug>/RESULT.json` + campaign_table / null CSVs / WF
- `rare_size_impact.csv` (sensitivity only)
- `SUMMARY.md` / `EMAIL.txt`
