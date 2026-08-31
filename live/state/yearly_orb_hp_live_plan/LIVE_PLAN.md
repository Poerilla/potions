# Yearly ORB HP live plan (`yearly_orb_hp_sizeup_v1`)

Hub: `live/state/yearly_orb_hp_live_plan/`
Profile: `../yearly_daily_condition_profile/`
Nulls 1.25×: `../yearly_orb_hp_sizeup_nulls/`
Nulls 2×: `../yearly_orb_hp_sizeup_nulls_2x/`

**Books:** NQ L_4_1_1, ES L_4_2_1, YM L_4_1_1 (sizing-best N/S).
Canonical objective: whole-book **ΔN/S**. Δnet is report-only.
Do **not** infer 2× from a 1.25× pass.

## NQ 86% win-rate audit

Recounted from broker-like campaign tape (`nq_yorb` fills, net>0):

- **59 / 68 = 86.8%** (Wilson 95% CI **76.7–92.9%**)
- Net $1,417,383  avg $20,844

This is the **baseline book** win rate, not an HP size-up claim.
Size-up still needs the matched-added-exposure gates below.

Year-by-year WR:

| year | n | wins | WR |
|---:|---:|---:|---:|
| 2011 | 14 | 12 | 85.7% |
| 2012 | 4 | 3 | 75.0% |
| 2013 | 3 | 3 | 100.0% |
| 2014 | 1 | 1 | 100.0% |
| 2015 | 9 | 7 | 77.8% |
| 2016 | 2 | 2 | 100.0% |
| 2018 | 5 | 4 | 80.0% |
| 2019 | 6 | 5 | 83.3% |
| 2020 | 2 | 2 | 100.0% |
| 2021 | 4 | 3 | 75.0% |
| 2022 | 6 | 6 | 100.0% |
| 2023 | 3 | 3 | 100.0% |
| 2024 | 6 | 6 | 100.0% |
| 2025 | 3 | 2 | 66.7% |

## Baseline WR (all three)

| book | n | wins | WR | Wilson 95% | net |
|---|---:|---:|---:|---:|---:|
| nq_yorb | 68 | 59 | 86.8% | 76.7–92.9% | $1,417,383 |
| es_yorb | 73 | 56 | 76.7% | 65.8–84.9% | $657,146 |
| ym_yorb | 81 | 73 | 90.1% | 81.7–94.9% | $515,736 |

## HP pairs tested

- `nq_yorb` ma_stack=ma_mixed
- `nq_yorb` ma_align=ma_mixed
- `es_yorb` atr_pct_bucket=atr_pctl_q4
- `es_yorb` side=short
- `ym_yorb` side=short
- `ym_yorb` atr_pct_bucket=atr_pctl_q4

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
- NQ ~86% WR is a **tape recount**, not a promotion of 1.25×/2×.
- At most one HP multiplier per index sleeve per session.

