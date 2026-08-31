# SPX500 WICK_REJECT range-seed limit-retest (CFD replication)

**Updated:** 2026-08-30 12:52 ET
**Hub:** `live/state/cfd_wick_reject_range_seed_retest/spx500/`
**Stance:** RESEARCH only — not a demo candidate.
**Model:** frozen NQ decision box; tick=0.1 point_value=1 fee=$1.50
**Role:** independent_index_cfd
**Mode:** FULL

See `CENSUS.md` for pre-P&L seed census.

## Primary limit-retest

| Book | seeds | fills | fill% | net $ | stress $ | N/S | WR | PF | avg R | med R | stop% | TP1/2/R% | gap | L/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| primary_limit_retest_dev | 47 | 31 | 66% | -468 | -530 | -0.88 | 32% | 0.28 | -0.127 | -0.251 | 74% | 71/32/19 | 4 | 18/13 |
| primary_limit_retest_holdout | 5 | 2 | 40% | +73 | +0 | 99.00 | 100% | 99.00 | +0.591 | +0.591 | 50% | 100/100/50 | 1 | 1/1 |
| primary_limit_retest_ALL | 52 | 33 | 63% | -394 | -530 | -0.74 | 36% | 0.39 | -0.084 | -0.250 | 73% | 73/36/21 | 5 | 19/14 |

## Local read

- Dev avg R **-0.127** / holdout avg R **+0.591**
- Fills 33 / expired-cancelled 19 (fill rate 63%)
- Top5 |net| share (ALL): see summary top5_share.

Parent decision matrix: `../DECISION_MATRIX.md`.
