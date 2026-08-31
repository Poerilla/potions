# NQ WICK_REJECT range-seed breakout–retest

**Updated:** 2026-08-30 10:58 ET
**Hub:** `live/state/nq_wick_reject_range_seed_retest/`
**Model:** 4h WICK_REJECT seeds range → 1h close break → limit retest → opposite-edge stop → 0.5W/1W/2W 50/25/25.
**Execution:** RTH 1m stop-first, gap-through stops, limit fill at boundary, $1.50/leg fee, NQ $20/pt.
**Holdout:** atlas slice (earliest ~75% dev / latest ~25% holdout) — locked read.
**Mode:** FULL

## Phase 0 — viability census

| Metric | Value |
|---|---:|
| Atlas 4h WICK_REJECT (pen≥0.05) | 122 |
| Eligible seeds (width/early/dedupe) | 91 |
| Rejected | 31 |

Reject reasons: `{"duplicate_confirm_bar": 17, "width_gt_2.00_ATR": 12, "early_close_session": 2}`

Width distribution (eligible):

| Stat | points | ticks | ×4h ATR | ×1m ATR |
|---|---:|---:|---:|---:|
| min | 10.25 | 41.0 | 0.349 | 6.76 |
| p25 | 25.12 | 100.5 | 0.740 | 13.30 |
| median | 56.50 | 226.0 | 1.020 | 16.25 |
| p75 | 161.38 | 645.5 | 1.386 | 18.78 |
| max | 504.75 | 2019.0 | 1.919 | 36.26 |

## Phase 1 — directional revelation (eligible seeds)

| Outcome | n | rate |
|---|---:|---:|
| Expire with no 1h break | 0 | 0.0% |
| First break high | 55 | 60.4% |
| First break low | 36 | 39.6% |
| Any 1h break | 91 | 100.0% |
| Both sides broke (path flag) | 0 | 0.0% |
| Retest touch after break | 76 | 83.5% |

Among first-breaks: persist≥1/2/4 1h closes outside = **91 / 74 / 48**; re-entry inside rate = **56.0%**; hit 0.5W/1W/2W = **77 / 60 / 39**; retest-hold = **74**.

## Phase 2–3 — locked primary + controls

| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | gap | L/S n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| primary_limit_retest_dev | 74 | 53 | 72% | +23880 | +451 | 57% | 1.90 | +0.177 | +0.249 | 55% | 75/55/34 | 7 | 33/20 |
| primary_limit_retest_holdout | 17 | 14 | 82% | +5467 | +390 | 43% | 1.27 | -0.036 | -0.250 | 64% | 64/43/36 | 0 | 7/7 |
| primary_limit_retest_ALL | 91 | 67 | 74% | +29346 | +438 | 54% | 1.62 | +0.132 | +0.249 | 57% | 73/52/34 | 7 | 40/27 |
| ctrl_immediate_break_dev | 74 | 74 | 100% | +7182 | +97 | 54% | 1.19 | +0.015 | +0.089 | 46% | 86/69/42 | 7 | 46/28 |
| ctrl_immediate_break_holdout | 17 | 17 | 100% | -3107 | -183 | 53% | 0.89 | -0.096 | +0.041 | 53% | 71/53/47 | 0 | 9/8 |
| ctrl_immediate_break_ALL | 91 | 91 | 100% | +4074 | +45 | 54% | 1.06 | -0.005 | +0.045 | 47% | 84/66/43 | 7 | 55/36 |
| ctrl_marketable_boundary_dev | 74 | 74 | 100% | +37767 | +510 | 69% | 2.37 | +0.347 | +0.676 | 46% | 86/69/42 | 7 | 46/28 |
| ctrl_marketable_boundary_holdout | 17 | 17 | 100% | +16128 | +949 | 53% | 1.75 | +0.146 | +0.250 | 53% | 71/53/47 | 0 | 9/8 |
| ctrl_marketable_boundary_ALL | 91 | 91 | 100% | +53894 | +592 | 66% | 2.10 | +0.309 | +0.664 | 47% | 84/66/43 | 7 | 55/36 |

## Stance

**RESEARCH — positive locked dev, failed holdout**

- Locked **dev**: 53 fills, +$23.9k, PF 1.90, avg R **+0.18** — clears the viability bar and shows positive expectancy after costs/gap-through.
- Locked **holdout**: 14 fills, +$5.5k dollars but avg R **−0.04** — dollar PF 1.27 is not enough; R fails the locked read.
- **Phase 3:** limit-retest beats immediate chase on locked dev (+$451/fill vs +$97). Synthetic **marketable-at-boundary** (no path retest) is stronger still (+$510/fill, holdout avg R +0.15) — so the edge may sit more in **break + range geometry** than in waiting for a pullback fill. Retest remains the frozen primary until a predeclared follow-on contract says otherwise.
- Do **not** promote to StrategyPlugin until Engine seed-state machine + cancel/replace are verified.
- Phase 4 robustness deferred while holdout R is non-positive on the primary.

Primary decision uses locked **dev** only; holdout is a frozen read.

## Concentration (primary ALL fills)

Top1/3/5 |net| share: **6.6% / 16.8% / 26.1%**.

## Guardrails

- No structure-bias / RSI / TOD / SMT filters.
- No target optimization; W-multiples frozen.
- One seed per market; one trade per seed; no DCA / re-entry.
- Early-close sessions excluded; width 0.25–2.00 × 4h ATR20.
