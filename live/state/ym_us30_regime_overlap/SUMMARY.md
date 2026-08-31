# YM ↔ US30 regime overlap

Join key: NY session date (+ direction). Independent `trade_id`s — not joined across markets.
Classifier: SEPARATE_REGIMES | CONDITIONAL_OVERLAP | SAME_SLEEVE | UNRESOLVED
(Legacy OR rule `Jaccard < t OR |ρ| < t` removed.)

## Primary: YM prior-opposed vs US30 ST+PMC 3R

| metric | value |
|---|---:|
| YM PO campaigns / days | 436 / 421 |
| US30 ST campaigns / days | 578 / 512 |
| Shared session days | 150 (Jaccard 19.2%) |
| Dir agree on shared days | 0.06 |
| Same-day same-dir events | 9 |
| Shared-day P&L correlation | -0.107 (n=150) |
| Union-day P&L correlation | -0.059 |
| Regime class | **SEPARATE_REGIMES** |
| Recommended sizing | independent strategy allocations; still subject to underlying-market and portfolio stress caps |

## All pairs

| pair | shared days | Jaccard | dir-agree | shared ρ | union ρ | class |
|---|---:|---:|---:|---:|---:|---|
| YM prior-opposed vs US30 ST+PMC 3R | 150 | 0.19 | 0.06 | -0.107 | -0.059 | SEPARATE_REGIMES |
| YM prior-opposed vs US30 prior-opposed | 71 | 0.13 | 0.986 | 0.549 | 0.129 | CONDITIONAL_OVERLAP |
| YM ST+PMC 3R vs US30 ST+PMC 3R | 417 | 0.42 | 0.998 | 0.851 | 0.546 | SAME_SLEEVE |
| YM ST+PMC 3R vs US30 prior-opposed | 52 | 0.05 | 0.788 | 0.004 | -0.004 | CONDITIONAL_OVERLAP |
| YM prior-opposed vs YM ST+PMC 3R | 183 | 0.16 | 0.044 | -0.129 | -0.051 | SEPARATE_REGIMES |
| US30 prior-opposed vs US30 ST+PMC 3R | 52 | 0.08 | 0.808 | 0.052 | -0.001 | CONDITIONAL_OVERLAP |

## Interpretation

- **SEPARATE_REGIMES** — low date overlap AND low shared-day relationship; independent allocations (still under portfolio caps).
- **CONDITIONAL_OVERLAP** — sparse co-occurrence but high shared-day agreement/correlation; shared risk cap when both fire.
- **SAME_SLEEVE** — meaningful overlap + high agreement/correlation; one shared allocation.
- **UNRESOLVED** — insufficient sample or inconsistent/missing accounting.

## Exact-book identities

- `ym_v2b_prior_opposed_stpmc_only_S_1_1_3` vs `us30_hourly_st_pmc_sl50_tp150_3r_1mfill`
- `ym_v2b_prior_opposed_stpmc_only_S_1_1_3` vs `us30_v2b_oco_prior_opposed_S_1_1_3`
- `ym_hourly_st_pmc_sl50_tp150_3r_1mfill` vs `us30_hourly_st_pmc_sl50_tp150_3r_1mfill`
- `ym_hourly_st_pmc_sl50_tp150_3r_1mfill` vs `us30_v2b_oco_prior_opposed_S_1_1_3`
- `ym_v2b_prior_opposed_stpmc_only_S_1_1_3` vs `ym_hourly_st_pmc_sl50_tp150_3r_1mfill`
- `us30_v2b_oco_prior_opposed_S_1_1_3` vs `us30_hourly_st_pmc_sl50_tp150_3r_1mfill`

## Artifacts

- `overlap_summary.csv`, `overlap.json`

