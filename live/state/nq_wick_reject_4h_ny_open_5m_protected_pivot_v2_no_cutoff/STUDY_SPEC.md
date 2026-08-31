# STUDY_SPEC — 5m protected-pivot V2 no-cutoff diagnostic

## Why this exists

Archived V2 (`d3b30d168b0bb59b`) hard-stopped at **7 candidates** (<40). Of 84
non-candidates, **43** were `FINAL_PIVOT_AFTER_CUTOFF` (P4 after 10:30).

User requested a re-run **without the 10:30 cutoff** to measure how many of those
near-misses become candidates when formation may complete any time before 13:00.

## Change vs V2

| Knob | V2 (archived) | This diagnostic |
|------|---------------|-----------------|
| formation_cutoff | 10:30 | **none** (bound = obs_end) |
| observation_end | 13:00 | 13:00 (unchanged) |
| pivots / structure / protection | 5m L1/R1 | unchanged |
| hub | `..._v2/` | `..._v2_no_cutoff/` |

## Disposition rules (unchanged screen)

- eligible opens ≥80, candidates ≥40, ≥15/side
- both-side hold ≥55% for screen pass
- hard stop if candidates <40
- descriptive only; no plugin / P&L / V1 overwrite
