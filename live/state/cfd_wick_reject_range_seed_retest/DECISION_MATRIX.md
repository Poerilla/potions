# CFD decision matrix — WICK_REJECT limit-retest replication

**Updated:** 2026-08-30 12:55 ET
**NQ reference:** locked primary holdout avg R failed (research signal only).
**Demo:** blocked for all CFD rows.

## Matrix

| Rule | Result |
|---|---|
| NAS100 matches NQ (dev+/holdout−) | YES |
| NAS100 + NQ both holdout+ | no (NQ holdout failed) |
| SPX500 holdout+ | YES |
| US30 holdout+ | YES |
| All CFDs fail holdout | no |

## Stance

**NAS100_MATCHES_NQ_PATTERN** — positive development, fails holdout. Still research only; supports data-path/execution portability only.

Do **not** promote on SPX500/US30 holdout+ alone:
- SPX500 holdout is **2 fills** (avg R +0.59) after a **negative development** (avg R −0.13) — not a portability claim.
- US30 holdout avg R +0.03 on 12 fills after **negative development** (avg R −0.34) — weak / inconsistent.
- Broader-index “also hold” gate requires coherent dev+holdout+, not thin holdout flips against failed development.

**Demo:** blocked. **Plugin:** blocked. Treat NQ+NAS100 as a shared Nasdaq-complex research footprint, not two independent confirmations.

## Per-market snapshot

| Market | status | elig | fills | fill% | dev avgR | hold avgR | hold net | hold N/S | note |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| NAS100 | complete | 58 | 46 | 79% | +0.089 | -0.229 | -884 | -0.70 | mirrors NQ pattern |
| SPX500 | complete | 52 | 33 | 63% | -0.127 | +0.591 | +73 | n/a (2 fills, 0 DD) | thin holdout; failed dev |
| US30 | complete | 49 | 35 | 71% | -0.337 | +0.032 | +383 | 0.80 | weak holdout; failed dev |

## Guardrails

- No CHOP20 filters.
- No per-CFD rule retune.
- NAS100 ≠ independent confirmation of NQ.
- XAUUSD not in this batch (separate metals family if ever run).
