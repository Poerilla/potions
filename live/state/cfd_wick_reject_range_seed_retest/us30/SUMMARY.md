# US30 WICK_REJECT range-seed limit-retest (CFD replication)

**Updated:** 2026-08-30 12:55 ET
**Hub:** `live/state/cfd_wick_reject_range_seed_retest/us30/`
**Stance:** RESEARCH only — not a demo candidate.
**Model:** frozen NQ decision box; tick=0.1 point_value=1 fee=$1.50
**Role:** independent_index_cfd
**Mode:** FULL

See `CENSUS.md` for pre-P&L seed census.

## Primary limit-retest

| Book | seeds | fills | fill% | net $ | stress $ | N/S | WR | PF | avg R | med R | stop% | TP1/2/R% | gap | L/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| primary_limit_retest_dev | 34 | 23 | 68% | -601 | -2003 | -0.30 | 30% | 0.79 | -0.337 | -1.000 | 78% | 48/30/13 | 3 | 8/15 |
| primary_limit_retest_holdout | 15 | 12 | 80% | +383 | -481 | 0.80 | 58% | 1.54 | +0.032 | +0.238 | 75% | 75/58/25 | 2 | 6/6 |
| primary_limit_retest_ALL | 49 | 35 | 71% | -219 | -2003 | -0.11 | 40% | 0.94 | -0.211 | -0.250 | 77% | 57/40/17 | 5 | 14/21 |

## Local read

- Dev avg R **-0.337** / holdout avg R **+0.032**
- Fills 35 / expired-cancelled 14 (fill rate 71%)
- Top5 |net| share (ALL): see summary top5_share.

Parent decision matrix: `../DECISION_MATRIX.md`.
