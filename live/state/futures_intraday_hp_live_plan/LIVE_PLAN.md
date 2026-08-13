# Futures HP live plan

Study: `futures_intraday_hp_sizeup_v1`

Only **exact 1.25×** has null-suite standing. No 1.5×/2×/3×/4× inferred from a
1.25× pass (see `COMPARISON.md` for sensitivity).

Full rollout contract: [`DEPLOYMENT_PLAN.md`](DEPLOYMENT_PLAN.md).

## Tier A — paper 1.25× (SIZE-UP VALIDATED)

_None — no SIZE-UP VALIDATED survivors after portfolio sleeve gate._

## Tier B — provisional paper 1.25×

| book | condition=bucket | mult | p_plac | p_shift | p_master |
|---|---|---:|---:|---:|---:|
| nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 1.25× | 0.018 | 0.014 | 0.074 |

## Tier C — shadow profile only

_None._

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

- `hp_size_rules.yaml` / `hp_size_rules.json`
- `COMPARISON.md` / `size_sensitivity.csv`
- `prior_opposed_overlap_report.csv`
- `DEPLOYMENT_PLAN.md`
