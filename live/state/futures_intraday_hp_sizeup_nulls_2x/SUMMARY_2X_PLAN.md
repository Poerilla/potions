# Futures HP 2× null suite (predeclared)

Study: `futures_intraday_hp_sizeup_v1`
Hub: `live/state/futures_intraday_hp_sizeup_nulls_2x/`

Predeclared before run (Tier A/B @ 1.25×): ES ST-age>180m, YM overnight-middle,
NQ OR-norm. **Exact 2×** matched-added-exposure only — no inference from 1.25×.

## Results

| decision | book | condition=bucket | mult | p_plac | p_shift | p_master |
|---|---|---|---:|---:|---:|---:|
| NOT VALIDATED | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 2.00× | 0.106 | 0.099 | 0.619 |
| NOT VALIDATED | ym_prior_opposed_rl | Overnight range third=on_middle | 2.00× | 0.161 | 0.100 | 0.980 |
| PROVISIONAL PAPER | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 2.00× | 0.042 | 0.028 | 0.064 |

## Portfolio overlap

See `portfolio_overlap.csv`.

## Stance

- SIZE-UP VALIDATED @ 2× → candidate for separate 2× paper review (not auto-deploy).
- Does **not** rewrite `futures_intraday_hp_live_plan/` (1.25× remains canonical).
