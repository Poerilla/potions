# NQ WICK_REJECT range-seed OCO boundary stops

**Updated:** 2026-08-30 11:49 ET
**Hub:** `live/state/nq_wick_reject_range_seed_oco_stops/`
**Model:** 4h WICK_REJECT seeds range → OCO buy-stop@high / sell-stop@low → opposite-edge stop → 0.5W/1W/2W 50/25/25.
**Contrast:** no 1h close confirm; no limit retest. First boundary stop fill wins.
**Execution:** RTH 1m, gap-through stop entries/exits, $1.50/leg, NQ $20/pt.
**Holdout:** atlas slice locked (same seeds as limit-retest hub).
**Mode:** FULL

Eligible seeds: **91** (age overlaps=19).
Limit-retest ALL (prior hub): fills=67 net=+29346 WR=54% PF=1.62 avgR=+0.132

## Locked books

| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | gap | L/S n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| oco_boundary_stops_dev | 74 | 74 | 100% | -5144 | -70 | 49% | 0.90 | +0.058 | -0.147 | 55% | 80/55/34 | 3 | 43/31 |
| oco_boundary_stops_holdout | 17 | 17 | 100% | +2654 | +156 | 47% | 1.09 | +0.015 | -0.250 | 59% | 65/47/41 | 0 | 6/11 |
| oco_boundary_stops_ALL | 91 | 91 | 100% | -2490 | -27 | 48% | 0.97 | +0.050 | -0.193 | 56% | 77/54/35 | 3 | 49/42 |

## Stance

**REJECT OCO stops on locked dev (net/R ≤ 0)**

Primary decision uses locked **dev** only. Compare to limit-retest hub for entry-quality delta.

## Guardrails

- Same seed eligibility as limit-retest (width 0.25–2.00×4h ATR, early-close exclude).
- Same-bar dual touch: no fill that minute.
- One trade per seed; no re-entry; no DCA.
- No structure-bias / RSI / TOD / SMT filters; targets frozen.
