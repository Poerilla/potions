# US30 PMC confirmed fade × 4h structure-bias

**Hub:** `live/state/us30_pmc_failed_break_fade_structure_bias/`
**DSR:** `TRL-2026-00189` (parent `TRL-2026-00187`)
**Status:** Phase 1 descriptive + Phase 2 variants COMPLETE — ARCHIVE_OVERLAY.

## Frozen base (parent confirmed)

| Param | Value |
|---|---|
| Level | PMC only |
| Signal | 5m reclaim + 1 confirmation bar ≤60m |
| Entry | next 1m open after confirmation |
| Stop | sweep extreme ± 1 tick |
| Scale-out | 50%@1R / 25%@2R / 25%@4R (2/1/1) |
| Costs | fee $1.50/unit + 1-tick adverse entry/stop |
| Structure | causal 4h StructureProgramEngine (unchanged) |

Causal snaps: **4486** completed 4h bars. Bias attached at `confirm_ts` with `structure_feature_available_at ≤ confirm_ts < entry_ts`.

## Phase 1 — descriptive alignment (no filter)

| Group | N | Net | N/S | PF | WR | Median R | MAE | MFE | 1R | 2R | 4R | runner_share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALIGNED | 45 | 1348 | 0.40 | 1.14 | 53.3% | 0.06 | -96.1 | 116.8 | 49% | 20% | 9% | 64% |
| OPPOSED | 43 | 1093 | 0.39 | 1.12 | 46.5% | -0.01 | -71.1 | 105.9 | 47% | 23% | 5% | 51% |
| NEUTRAL | 0 | 0 | 0.00 | 0.00 | 0.0% | 0.00 | 0.0 | 0.0 | 0% | 0% | 0% | 0% |
| UNAVAILABLE | 41 | 170 | 0.14 | 1.04 | 48.8% | -0.04 | -34.1 | 49.9 | 51% | 22% | 7% | 267% |

### ALIGNED branches

| Branch | N | Net | N/S | WR | runner_share |
|---|---:|---:|---:|---:|---:|
| ALIGNED_LONG | 24 | 1761 | 1.06 | 62.5% | 23% |
| ALIGNED_SHORT | 21 | -413 | -0.13 | 42.9% | -109% |

## Phase 2 — strategy variants (same fills)

| Variant | N | Net | Stress | N/S | WR | PF | Runner share |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 129 | 2612 | -3239 | 0.81 | 49.6% | 1.11 | 72% |
| aligned_only | 45 | 1348 | -3385 | 0.40 | 53.3% | 1.14 | 64% |
| aligned_plus_neut | 45 | 1348 | -3385 | 0.40 | 53.3% | 1.14 | 64% |

## Scale-out diagnostics (report only)

| Scope | Plan | N | Net | N/S | WR | hit_1r | hit_2r | hit_4r | runner_share |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ALL | full_1r_2r_4r | 129 | 2612 | 0.81 | 49.6% | 49% | 22% | 7% | 72% |
| ALL | no_runner_cap_2r | 129 | 2807 | 0.83 | 49.6% | 49% | 22% | 0% | 0% |
| ALL | reduced_runner_50_50 | 129 | 2807 | 0.83 | 49.6% | 49% | 22% | 0% | 0% |
| ALIGNED | full_1r_2r_4r | 45 | 1348 | 0.40 | 53.3% | 49% | 20% | 9% | 64% |
| ALIGNED | no_runner_cap_2r | 45 | 1483 | 0.43 | 53.3% | 49% | 20% | 0% | 0% |
| ALIGNED | reduced_runner_50_50 | 45 | 1483 | 0.43 | 53.3% | 49% | 20% | 0% | 0% |
| OPPOSED | full_1r_2r_4r | 43 | 1093 | 0.39 | 46.5% | 47% | 23% | 5% | 51% |
| OPPOSED | no_runner_cap_2r | 43 | 1058 | 0.35 | 46.5% | 47% | 23% | 0% | 0% |
| OPPOSED | reduced_runner_50_50 | 43 | 1058 | 0.35 | 46.5% | 47% | 23% | 0% | 0% |
| NEUTRAL | full_1r_2r_4r | 0 | 0 | 0.00 | 0.0% | 0% | 0% | 0% | 0% |
| NEUTRAL | no_runner_cap_2r | 0 | 0 | 0.00 | 0.0% | 0% | 0% | 0% | 0% |
| NEUTRAL | reduced_runner_50_50 | 0 | 0 | 0.00 | 0.0% | 0% | 0% | 0% | 0% |
| UNAVAILABLE | full_1r_2r_4r | 41 | 170 | 0.14 | 48.8% | 51% | 22% | 7% | 267% |
| UNAVAILABLE | no_runner_cap_2r | 41 | 266 | 0.22 | 48.8% | 51% | 22% | 0% | 0% |
| UNAVAILABLE | reduced_runner_50_50 | 41 | 266 | 0.22 | 48.8% | 51% | 22% | 0% | 0% |
| baseline | full_1r_2r_4r | 129 | 2612 | 0.81 | 49.6% | 49% | 22% | 7% | 72% |
| baseline | no_runner_cap_2r | 129 | 2807 | 0.83 | 49.6% | 49% | 22% | 0% | 0% |
| baseline | reduced_runner_50_50 | 129 | 2807 | 0.83 | 49.6% | 49% | 22% | 0% | 0% |
| aligned_only | full_1r_2r_4r | 45 | 1348 | 0.40 | 53.3% | 49% | 20% | 9% | 64% |
| aligned_only | no_runner_cap_2r | 45 | 1483 | 0.43 | 53.3% | 49% | 20% | 0% | 0% |
| aligned_only | reduced_runner_50_50 | 45 | 1483 | 0.43 | 53.3% | 49% | 20% | 0% | 0% |
| aligned_plus_neut | full_1r_2r_4r | 45 | 1348 | 0.40 | 53.3% | 49% | 20% | 9% | 64% |
| aligned_plus_neut | no_runner_cap_2r | 45 | 1483 | 0.43 | 53.3% | 49% | 20% | 0% | 0% |
| aligned_plus_neut | reduced_runner_50_50 | 45 | 1483 | 0.43 | 53.3% | 49% | 20% | 0% | 0% |

_`no_runner_cap_2r` and `reduced_runner_50_50` both use 2@1R + 2@2R (fold/eliminate 4R); reported separately per plan._

## Stance

**ARCHIVE_OVERLAY** — ALIGNED N/S ≤ baseline or ALIGNED net negative — archive structure-bias overlay; close fade workstream if no other path.

## Decision gates (reference)

| Result | Action |
|---|---|
| ALIGNED N/S ≤ baseline or negative | Archive overlay |
| ALIGNED improves but N ≲ 50 | Shadow only; no demo |
| ALIGNED improves, lower stress, stable, runner not worse | Plugin port candidate |
| aligned+neutral works, aligned-only does not | OPPOSED-skip throttle |
| One directional branch drives benefit | Descriptive only |
| Runner removal collapses result | No demo until characterized |

No size-up / no scale-in / no extra filters in this trial.
