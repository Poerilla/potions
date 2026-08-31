# NAS100 WICK_REJECT range-seed limit-retest (CFD replication)

**Updated:** 2026-08-30 12:48 ET
**Hub:** `live/state/cfd_wick_reject_range_seed_retest/nas100/`
**Stance:** RESEARCH only — not a demo candidate.
**Model:** frozen NQ decision box; tick=0.1 point_value=1 fee=$1.50
**Role:** implementation_parity_vs_NQ
**Mode:** FULL

See `CENSUS.md` for pre-P&L seed census.

## Primary limit-retest

| Book | seeds | fills | fill% | net $ | stress $ | N/S | WR | PF | avg R | med R | stop% | TP1/2/R% | gap | L/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| primary_limit_retest_dev | 44 | 34 | 77% | +762 | -745 | 1.02 | 53% | 1.50 | +0.089 | +0.249 | 56% | 65/50/38 | 3 | 21/13 |
| primary_limit_retest_holdout | 14 | 12 | 86% | -884 | -1264 | -0.70 | 50% | 0.35 | -0.229 | -0.004 | 75% | 50/42/25 | 4 | 3/9 |
| primary_limit_retest_ALL | 58 | 46 | 79% | -121 | -1264 | -0.10 | 52% | 0.96 | +0.006 | +0.233 | 61% | 61/48/35 | 7 | 24/22 |

## Local read

- Dev avg R **+0.089** / holdout avg R **-0.229**
- Fills 46 / expired-cancelled 12 (fill rate 79%)
- Top5 |net| share (ALL): see summary top5_share.

Parent decision matrix: `../DECISION_MATRIX.md`.
