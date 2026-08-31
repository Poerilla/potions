# Status — NQ WICK_REJECT range-seed retest

**Hub:** `live/state/nq_wick_reject_range_seed_retest/`
**Updated:** 2026-08-30 12:30 ET
**Stance:** RESEARCH only — **not a demo candidate**

| Phase | Status |
|---|---|
| 0 viability census | DONE — 91/122 eligible; 67 fills (viable) |
| 1 directional revelation | DONE — 100% 1h break; 84% retest touch |
| 2 locked primary replay | DONE — dev PF 1.90 / holdout avgR −0.04 |
| 3 fixed controls | DONE — retest > chase; boundary fill ≥ retest |
| OCO stop-entry contrast | DONE — failed (adverse selection / breakout friction) |
| 4 bounded robustness | DEFERRED |
| StrategyPlugin | BLOCKED |
| Demo | **BLOCKED** |

## Follow-on (separate tracks)

1. **CFD replication** (`live/state/cfd_wick_reject_range_seed_retest/`) — frozen model on NAS100→SPX500→US30; portability only; no rule retune; no CHOP20 filters.
2. **V2B alignment** (`live/state/nq_v2b_wick_range_alignment/`) — resolved seeded-range break as causal regime label for prior-opposed V2B; not a hybrid strategy.
3. **4h confirm family** (`live/state/nq_wick_reject_4h_swing_retest_v1/`) — separate contract `nq_wick_reject_4h_swing_retest_v1`: S1 = 4h close + seed-boundary retest (30×4h seed / 48h life); S2 swing-level deferred. Not a tweak of this 1h book.

OCO failure implies the synthetic boundary-fill control is **not** executable evidence. Limit-retest remains a weak research signal (dev+ / holdout avg R fail).

Driver: `python -m live.nq_wick_reject_range_seed_retest --email`
