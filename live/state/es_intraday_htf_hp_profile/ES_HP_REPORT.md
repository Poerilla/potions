# ES broker-like HP + HTF condition study

Hubs:
- Profile: `live/state/es_intraday_htf_hp_profile/`
- Nulls @1.25×: `live/state/es_intraday_htf_hp_nulls/` (did **not** rewrite LIVE_PLAN)

Books: `es_prior_opposed_legacy` (n=245, N/S 12.48), `es_st_pmc_ma_bull` (n=223, N/S 2.25).

## Stance

**No ES 1.25× size-up validated.** Sole interesting null label is
`es_st_pmc_ma_bull` ST-age>180m → **RISK THROTTLE** (placebo/shift pass on ΔN/S;
master fails). All HTF pairs **NOT VALIDATED**. Aligns with prior Phase-3 ES demotion.

## Usual shortlist @1.25×

| decision | book | condition=bucket | hp% | ΔN/S | p_master |
|---|---|---|---:|---:|---:|
| NOT VALIDATED | prior-opposed | ST-age>180m | 28% | +1.23 | 0.88 |
| NOT VALIDATED | prior-opposed | Week of month=1 | 29% | +0.21 | 1.00 |
| NOT VALIDATED | prior-opposed | prior RTH mid-third | 25% | +0.66 | 1.00 |
| NOT VALIDATED | ST+PMC | Tuesday | 22% | +0.30 | 0.94 |
| RISK THROTTLE | ST+PMC | ST-age>180m | 28% | +0.34 | 0.87 |
| NOT VALIDATED | ST+PMC | prior RTH range norm | 26% | +0.16 | 1.00 |

## HTF diagnostics (new)

Definitions: `HTF_FEATURES.md`. Most buckets exceed 5–35% HP coverage
(regime labels, not tight sleeves).

| book | condition=bucket | n | cov | WR lift | avg lift | null @1.25× |
|---|---|---:|---:|---:|---:|---|
| prior-opposed | yor_up | 139 | 57% | +3.2pp | +$347 | NOT VALIDATED |
| prior-opposed | mor_down | 79 | 32% | −0.4pp | +$602 | NOT VALIDATED |
| ST+PMC | mor_up | 134 | 60% | +7.0pp | +$686 | NOT VALIDATED (notable WR) |
| prior-opposed | w_atr_aligned | 106 | 43% | −0.5pp | +$356 | NOT VALIDATED (ΔN/S −0.40) |
| prior-opposed | q_break_up | 189 | 77% | +0.3pp | +$248 | NOT VALIDATED |

Sparse buckets (n&lt;40): `yor_down`, `yor_inside`, `mor_inside`, `q_inside` — not profiled.

## Takeaway

HTF regime tags do **not** unlock an ES HP size-up. Monthly OR up on ST+PMC
lifts WR in-sample but fails matched-added-exposure. Keep ES prior-opposed /
ST-age as **Tier C shadow** only under the futures LIVE_PLAN.
