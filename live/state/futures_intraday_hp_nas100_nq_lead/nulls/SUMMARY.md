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
| RISK THROTTLE | nas100_nq_lead_prior_opposed | Hourly RSI vs trade=rsi_against_side | 1.25× | 34% | +3093 | +1.60 | 0.004 | 0.022 | 0.701 | 100% | 4 |
| RISK THROTTLE | nas100_nq_lead_prior_opposed | ST-event direction vs trade=st_opposed_proxy | 1.25× | 34% | +3093 | +1.60 | 0.005 | 0.022 | 0.727 | 100% | 0 |
| NOT VALIDATED | nas100_nq_lead_prior_opposed | Overnight compression=on_comp | 1.25× | 30% | +1636 | +0.23 | 0.323 | 0.368 | 1.000 | 100% | 0 |

## nas100_nq_lead_prior_opposed Hourly RSI vs trade=rsi_against_side @ 1.25×

```
HP coverage:               33.6%
Boosted campaigns:         94
Incremental net (report):  +3093
Incremental stress:        146
Incremental sleeve N/S:    21.24
Full-book N/S base→sized:  17.94 → 19.54 (Δ+1.60)

Matched-placebo median ΔN/S: -0.44
Actual ΔN/S percentile:      99.6
p_delta_NS (placebo):        0.0044
p_candidate_NS (book):       0.0044
p_delta_net (report):        0.0018
p_drawdown_improvement:      0.0790
p_shift_delta_NS:            0.0220
p_master_delta_NS:           0.7006
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    4

Decision: RISK THROTTLE
```

## nas100_nq_lead_prior_opposed ST-event direction vs trade=st_opposed_proxy @ 1.25×

```
HP coverage:               33.6%
Boosted campaigns:         94
Incremental net (report):  +3093
Incremental stress:        146
Incremental sleeve N/S:    21.24
Full-book N/S base→sized:  17.94 → 19.54 (Δ+1.60)

Matched-placebo median ΔN/S: -0.40
Actual ΔN/S percentile:      99.5
p_delta_NS (placebo):        0.0050
p_candidate_NS (book):       0.0050
p_delta_net (report):        0.0018
p_drawdown_improvement:      0.0858
p_shift_delta_NS:            0.0220
p_master_delta_NS:           0.7265
Frozen WF pos Δnet frac:     1.00
Discovery reappear count:    0

Decision: RISK THROTTLE
```

## nas100_nq_lead_prior_opposed Overnight compression=on_comp @ 1.25×

```
HP coverage:               29.6%
Boosted campaigns:         83
Incremental net (report):  +1636
Incremental stress:        128
Incremental sleeve N/S:    12.81
Full-book N/S base→sized:  17.94 → 18.17 (Δ+0.23)

Matched-placebo median ΔN/S: -0.15
Actual ΔN/S percentile:      67.8
p_delta_NS (placebo):        0.3225
p_candidate_NS (book):       0.3225
p_delta_net (report):        0.5557
p_drawdown_improvement:      0.2781
p_shift_delta_NS:            0.3676
p_master_delta_NS:           1.0000
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
