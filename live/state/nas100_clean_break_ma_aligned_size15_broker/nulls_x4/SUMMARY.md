# NAS100 clean-break — arm-asof ma_aligned nulls @ 4.00×

HP contract: `arm_asof_no_qty_refresh` (`ma5_align_arm=ma_aligned`).
Source campaigns: `live/state/nas100_clean_break_ma_aligned_size15_broker/arm_asof_campaigns.csv`.
Parent Engine scales: `live/state/nas100_clean_break_ma_aligned_size15_broker`.
DSR: TRL-2026-00202 (parent TRL-2026-00201).

Coverage note: arm-asof HP is ~55% of campaigns — above the
35% SIZE-UP VALIDATED gate, so expect RISK THROTTLE even if
placebo/shift beat unless coverage is re-scoped.
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
| NOT VALIDATED | nas100_v2b_clean_break_trail06 | 5m MA vs trade (arm-asof)=ma_aligned | 4.00× | 55% | +28526 | +1.69 | 0.255 | 0.164 | 0.860 | 86% | 0 |

## nas100_v2b_clean_break_trail06 5m MA vs trade (arm-asof)=ma_aligned @ 4.00×

```
HP coverage:               55.5%
Boosted campaigns:         647
Incremental net (report):  +28526
Incremental stress:        3505
Incremental sleeve N/S:    8.14
Full-book N/S base→sized:  6.57 → 8.25 (Δ+1.69)

Matched-placebo median ΔN/S: 0.38
Actual ΔN/S percentile:      74.6
p_delta_NS (placebo):        0.2549
p_candidate_NS (book):       0.2549
p_delta_net (report):        0.1774
p_drawdown_improvement:      0.4533
p_shift_delta_NS:            0.1635
p_master_delta_NS:           0.8603
Frozen WF pos Δnet frac:     0.86
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
