# Futures HP live plan

Study: `futures_intraday_hp_sizeup_v1`

Only **exact 1.25×** has null-suite standing. No 1.5×/2×/3×/4× inferred from a
1.25× pass (see `COMPARISON.md` for sensitivity).

Full rollout contract: [`DEPLOYMENT_PLAN.md`](DEPLOYMENT_PLAN.md).

## Tier A — paper 1.25× (SIZE-UP VALIDATED)

| book | condition=bucket | mult | p_plac | p_shift | p_master |
|---|---|---:|---:|---:|---:|
| es_prior_opposed_legacy | ST-event age=st_age_gt180m | 1.25× | 0.007 | 0.006 | 0.010 |
| ym_prior_opposed_rl | Overnight range third=on_middle | 1.25× | 0.020 | 0.017 | 0.044 |

## Tier B — provisional paper 1.25×

| book | condition=bucket | mult | p_plac | p_shift | p_master |
|---|---|---:|---:|---:|---:|
| nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 1.25× | 0.008 | 0.005 | 0.088 |

## Tier C — shadow profile only

| book | condition=bucket |
|---|---|
| nq_st_pmc_3r | Entry hour (NY)=11 |
| nq_v2b_s113 | Prior RTH close location=prior_close_mid_third |
| ym_prior_opposed_rl | Prior RTH range percentile=prior_range_norm |
| ym_st_pmc_3r | Day of week=Thursday |

## No action

All NOT VALIDATED shortlist rows.

## Portfolio rules

- **At most one prior-opposed HP multiplier across ES/YM/NQ per session** until
  the incremental-sleeve overlap report clears simultaneous boosts
  (`prior_opposed_overlap_report.csv`).
- One HP multiplier per economic index sleeve (no NQ+MNQ / YM+MYM / ES+MES).
- No same-regime ST+PMC stacking without a separate overlap pass.
- Tier A/B: keep 1.0× baseline ledger + book incremental 0.25× separately;
  **do not stack** yet.
- Tier C: annotate only — no size change.

## Artifacts

- `hp_size_rules.yaml` / `hp_size_rules.json` (Tier A authorized rules)
- `COMPARISON.md` / `size_sensitivity.csv` / `size_sensitivity_yearly.csv`
- `prior_opposed_overlap_report.csv`
- `DEPLOYMENT_PLAN.md`
