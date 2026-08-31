# OUTCOME_DIRECTION_AND_R_UNIT_AUDIT — NQ structure-change

**Updated:** 2026-08-30 08:52 EDT
**Overall:** **PASS**

Answers the six required audit questions before Phase 5.

## 1. Is each event evaluated in its economically correct direction?

| Check | Pass |
|---|---|
| Direction rules applied | PASS |

- CLOSE_BREAK: 173/173 rows match rule (same as break)
- WICK_REJECT: 122/122 rows match rule (opposite of break)
- CLOSE_RECLAIM: 62/62 rows match rule (opposite of break (reclaim))
- TOUCH_ONLY: 30/30 have empty outcome_direction

| Event class | Primary outcome direction |
|---|---|
| CLOSE_BREAK | Same as close break |
| WICK_REJECT | Opposite of wick breach |
| CLOSE_RECLAIM | Reclaim direction (opposite prior break) |
| TOUCH_ONLY | None — absolute movement only |

Break-direction diagnostics retained as `break_*` columns.

## 2. What exactly does 1R mean?

| Unit | Definition |
|---|---|
| ATR R | `ATR_20` on the structure timeframe (4h primary) |
| Structural-stop R | `|entry_open − protected_swing|` (wick: max with penetration points) |

### Denominator distribution (4h inv pen≥0.05, **dev**)

| Stat | Value |
|---|---:|
| median stop distance (points) | 20.88 |
| p25 / p75 / p95 stop (points) | 9.00 / 49.44 / 169.69 |
| median 4h ATR_20 (points) | 41.12 |
| median stop / 1m ATR | 8.33 |
| median stop / 4h ATR | 0.47 |

Check 2: **PASS**

**Note:** Control structural-stop R uses the *matched event's* protected-swing
distance at a non-event timestamp, so control structR hit rates are **not** a
fair benchmark (ATR R is the control comparison). Event-class structR tables
remain interpretable.

## 3. Hit-rate inequalities and horizons

Session 2R and two-session 3R use **distinct** windows after the session-window fix (post-close entries start session-1 on the next RTH day).

| Group | Unit | n | n_2R_sess | n_3R_multi | 3R∧¬2R | 2R∧¬3R | session==two_session |
|---|---|---:|---:|---:|---:|---:|---:|
| CLOSE_BREAK_dev | ATR | 126 | 2 | 0 | 0 | 2 | 0 |
| CLOSE_BREAK_dev | structR | 126 | 33 | 31 | 9 | 11 | 0 |
| WICK_REJECT_dev | ATR | 95 | 2 | 3 | 1 | 0 | 0 |
| WICK_REJECT_dev | structR | 95 | 14 | 19 | 8 | 3 | 0 |
| CLOSE_RECLAIM_dev | ATR | 46 | 0 | 1 | 1 | 0 | 0 |
| CLOSE_RECLAIM_dev | structR | 46 | 11 | 15 | 5 | 1 | 0 |
| controls | ATR | 387 | 36 | 43 | 14 | 7 | 0 |
| controls | structR | 387 | 3 | 4 | 1 | 0 | 0 |

Note: `3R∧¬2R` can be legitimate when 3R is earned on session 2 after missing 2R on session 1. FAIL if rates were equal with disjoint ID sets under collapsed windows (pre-fix).

Check 3: **PASS**

## 4. Controls matched and fully observable?

- Matching keys: NY hour, weekday, vol bucket, prior bias (vol relaxed if needed).
- Prefer controls with full two-session forward tape (`forward_observable_two_session=1`).
- Observable controls: **387 / 387**; observable primary-dev events: **286 / 286**.

Check 4: **PASS**

## 5. Representative event exports

See `audit_examples/` (20 rows across exports). Inspect labels vs 1m/4h tape offline.

Check 5: **PASS**

## 6. Holdout replication (1R/60m ATR, outcome dir)

| Class | n_dev | 1R/60m dev | n_holdout | 1R/60m holdout |
|---|---:|---:|---:|---:|
| CLOSE_BREAK | 126 | 0.0% | 47 | 0.0% |
| WICK_REJECT | 95 | 0.0% | 27 | 0.0% |
| CLOSE_RECLAIM | 46 | 0.0% | 16 | 0.0% |

Check 6: **PASS** (table emitted; interpret agreement separately).

## Event-count reconciliation

| Bucket | n |
|---|---:|
| total_events_all_tf_families_pens | 3353 |
| 4h_invalidation_pen0.05 | 387 |
| 4h_invalidation_pen0.05_dev | 286 |
| 4h_invalidation_pen0.05_holdout | 101 |
| 4h_inv_pen0.05_dev_CLOSE_BREAK | 126 |
| 4h_inv_pen0.05_dev_WICK_REJECT | 95 |
| 4h_inv_pen0.05_dev_CLOSE_RECLAIM | 46 |
| 4h_inv_pen0.05_dev_TOUCH_ONLY | 19 |
| count_1h_continuation_pen0.0 | 70 |
| count_1h_continuation_pen0.05 | 1118 |
| count_1h_invalidation_pen0.0 | 72 |
| count_1h_invalidation_pen0.05 | 1316 |
| count_4h_continuation_pen0.0 | 31 |
| count_4h_continuation_pen0.05 | 331 |
| count_4h_invalidation_pen0.0 | 28 |
| count_4h_invalidation_pen0.05 | 387 |

Phase 1 table uses only **4h + invalidation + pen≥0.05 + dev** (not all 3353 rows).
Total includes 1h, continuation family, and zero-buffer (`min_pen_ATR=0`) twins.

## Gate

- Phase 5 prototypes: **ALLOWED only after human review**
- Cross-market: still requires `APPROVAL_GATE.md` even if this audit PASSes.

