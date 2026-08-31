# CFD WICK_REJECT range-seed limit-retest replication

**Hub:** `live/state/cfd_wick_reject_range_seed_retest/`
**Updated:** 2026-08-30 12:55 ET
**Frozen model:** NQ `nq_wick_reject_range_seed_retest` decision box (no rule changes).
**Role:** portability / research — **not** a demo candidate.
**V2B:** separate conditional-exposure experiment (not combined here).
**Mode:** FULL

## Stance

**NAS100_MATCHES_NQ_PATTERN** — positive development, fails holdout. Still research only; supports data-path/execution portability only.

SPX500/US30 show thin or inconsistent holdout+ against **failed development** — not broader-index confirmation. Demo blocked.

See `CENSUS_BOARD.md` and `DECISION_MATRIX.md`.

## Markets

- **NAS100** (`nas100/`): complete — dev avgR +0.089 / holdout −0.229 (NQ-like)
- **SPX500** (`spx500/`): complete — dev −0.127 / holdout +0.591 on **2** fills (thin)
- **US30** (`us30/`): complete — dev −0.337 / holdout +0.032 (weak)
