# NQ WICK_REJECT range-seed OCO stop v1

**Updated:** 2026-08-30 12:03 ET
**study_id:** `nq_wick_reject_range_seed_oco_stop_v1`
**Hub:** `live/state/nq_wick_reject_range_seed_oco_stop_v1/`
**Model:** 4h WICK_REJECT seed → OCO buy-stop@high+1tick / sell-stop@low−1tick → opposite-edge stop → 0.5W/1W/2W 50/25/25.
**Contrast:** no 1h close confirm; no limit retest. First boundary stop fill wins.
**Execution:** RTH 1m, gap-through stop entries/exits, $1.50/leg, NQ $20/pt, stop-first.
**Same-1m dual:** primary = AMBIGUOUS exclude; stress = adverse worse-of-both.
**Holdout:** atlas slice locked (same seeds as limit-retest hub).
**Mode:** FULL

Eligible seeds: **91** (age overlaps=19). Primary ambiguous excluded: **0**.

## Locked books

| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | gap | L/S n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| oco_stop_v1_primary_dev | 74 | 74 | 100% | -5414 | -73 | 49% | 0.89 | +0.052 | -0.147 | 55% | 80/55/34 | 3 | 43/31 |
| oco_stop_v1_primary_holdout | 17 | 17 | 100% | +2579 | +152 | 47% | 1.09 | +0.013 | -0.252 | 59% | 65/47/41 | 0 | 6/11 |
| oco_stop_v1_primary_ALL | 91 | 91 | 100% | -2836 | -31 | 48% | 0.96 | +0.045 | -0.193 | 56% | 77/54/35 | 3 | 49/42 |
| oco_stop_v1_stress_2tick_dev | 74 | 74 | 100% | -6154 | -83 | 49% | 0.88 | +0.037 | -0.153 | 55% | 80/55/34 | 3 | 43/31 |
| oco_stop_v1_stress_2tick_holdout | 17 | 17 | 100% | +2409 | +142 | 47% | 1.08 | +0.011 | -0.254 | 59% | 65/47/41 | 0 | 6/11 |
| oco_stop_v1_stress_2tick_ALL | 91 | 91 | 100% | -3746 | -41 | 48% | 0.95 | +0.032 | -0.204 | 56% | 77/54/35 | 3 | 49/42 |
| oco_stop_v1_stress_adverse_coll_dev | 74 | 74 | 100% | -5414 | -73 | 49% | 0.89 | +0.052 | -0.147 | 55% | 80/55/34 | 3 | 43/31 |
| oco_stop_v1_stress_adverse_coll_holdout | 17 | 17 | 100% | +2579 | +152 | 47% | 1.09 | +0.013 | -0.252 | 59% | 65/47/41 | 0 | 6/11 |
| oco_stop_v1_stress_adverse_coll_ALL | 91 | 91 | 100% | -2836 | -31 | 48% | 0.96 | +0.045 | -0.193 | 56% | 77/54/35 | 3 | 49/42 |

## Stance

**RESEARCH ONLY — OCO stop v1 does not clear promotion gates**

- PASS: Development and holdout both positive avg campaign R
- FAIL: Holdout PF materially above 1 after costs (PF>1.15)
- FAIL: OCO primary remains positive under 2-tick adverse entry stress
- PASS: No hidden favorable resolution of same-minute two-sided breaks
- FAIL: Results not dominated by few campaigns / 2W runners (top5 |net| share=22%, TP3 win share=79%)
- PASS: Campaign count sufficient; long and short paths present

See `AMBIGUITY_AUDIT.md` (before P&L) and `COMPARISON_BOARD.md`.

## Guardrails

- Same seed eligibility as limit-retest (width 0.25–2.00×4h ATR, early-close exclude).
- Entry stops at seed_high+1tick / seed_low−1tick; risk stop opposite ±1 tick.
- Same-bar dual touch: primary exclude; no favorable side selection.
- One trade per seed; no re-entry; no DCA.
- No structure-bias / RSI / TOD / SMT filters; targets frozen.
