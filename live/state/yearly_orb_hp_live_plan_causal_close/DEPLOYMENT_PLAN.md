# Yearly ORB HP live plan (`yearly_orb_hp_sizeup_causal_close`)

Hub: `live/state/yearly_orb_hp_live_plan_causal_close/`
Profile: `live/state/yearly_daily_condition_profile_futures_causal_close/`
Nulls 1.25×: `live/state/yearly_orb_hp_sizeup_nulls_causal_close/`
Nulls 2×: `live/state/yearly_orb_hp_sizeup_nulls_2x_causal_close/`

**Books:** NQ L_4_1_1, ES L_4_2_1, YM L_4_1_1.
Causal next-open range-close (`live_after_ts=decision_bar.ts`). Same NQ `L_4_1_1` / ES `L_4_2_1` / YM `L_4_1_1` cells as the pre-causal HP study — not the causal-best OCO cells.
Canonical objective: whole-book **ΔN/S**. Δnet is report-only.
Do **not** infer 2× from a 1.25× pass.

## NQ win-rate audit

Recounted from broker-like campaign tape (`nq_yorb` fills, net>0):

- **20 / 68 = 29.4%** (Wilson 95% CI **19.9–41.1%**)
- Net $764,503  avg $11,243

This is the **baseline book** win rate, not an HP size-up claim.
Size-up still needs the matched-added-exposure gates below.

Year-by-year WR:

| year | n | wins | WR |
|---:|---:|---:|---:|
| 2011 | 14 | 2 | 14.3% |
| 2012 | 4 | 0 | 0.0% |
| 2013 | 3 | 2 | 66.7% |
| 2014 | 1 | 1 | 100.0% |
| 2015 | 9 | 1 | 11.1% |
| 2016 | 2 | 1 | 50.0% |
| 2018 | 5 | 3 | 60.0% |
| 2019 | 6 | 2 | 33.3% |
| 2020 | 2 | 1 | 50.0% |
| 2021 | 4 | 0 | 0.0% |
| 2022 | 6 | 2 | 33.3% |
| 2023 | 3 | 1 | 33.3% |
| 2024 | 6 | 2 | 33.3% |
| 2025 | 3 | 2 | 66.7% |

## Baseline WR (all three)

| book | n | wins | WR | Wilson 95% | net |
|---|---:|---:|---:|---:|---:|
| nq_yorb | 68 | 20 | 29.4% | 19.9–41.1% | $764,503 |
| es_yorb | 73 | 15 | 20.5% | 12.9–31.2% | $68,396 |
| ym_yorb | 81 | 18 | 22.2% | 14.5–32.4% | $157,766 |

## HP pairs tested

- `nq_yorb` week_of_month=2
- `nq_yorb` or_width_bucket=or_wide
- `es_yorb` rsi_align=rsi_against_side
- `es_yorb` quarter=Q4
- `ym_yorb` atr_pct_bucket=atr_pctl_q4
- `ym_yorb` prior_year_ret_bucket=prior_yr_mid

## Tier A — paper 1.25× (SIZE-UP VALIDATED)

_None._

## Tier B — provisional paper 1.25×

_None._

## Exact 2× (separate hub)

_None._

## Tier C / not validated

All remaining pairs (including coverage-fail and master-fail) stay **no size change**.

## Stance

- Highest-conviction yearly ORB HP size-up is whatever survives ΔN/S gates above.
- Book WR is a **tape recount**, not a promotion of 1.25×/2×.
- At most one HP multiplier per index sleeve per session.
- Causal-close tape: do not compare these WRs to the pre-causal 86%/76%/90% recount.

