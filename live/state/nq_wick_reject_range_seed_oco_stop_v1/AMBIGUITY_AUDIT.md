# OCO ambiguity & stop-entry audit (read before P&L)

**study_id:** `nq_wick_reject_range_seed_oco_stop_v1`
**Updated:** 2026-08-30 12:03 ET

## Same-1m dual-boundary policy

- **Primary:** mark AMBIGUOUS and **exclude** from decision books (no favorable side pick).
- **Stress:** fill the worse of LONG vs SHORT full simulations (adverse-first stress).

| Metric | Value |
|---|---:|
| Eligible seeds | 91 |
| Primary FILLED (decision) | 91 |
| Primary AMBIGUOUS excluded | 0 |
| Primary EXPIRED | 0 |
| Stress collision fills | 0 |
| Primary fill gap-through entry n | 23 |
| Primary fill gap-through stop n | 3 |
| Causality ok among fills | 91 / 91 |

## Every primary collision (excluded)

_None._

## Guard

No hidden favorable resolution of same-minute two-sided breaks in the primary book.
