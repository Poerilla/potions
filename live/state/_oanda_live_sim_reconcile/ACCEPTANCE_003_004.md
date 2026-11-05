# OANDA -003 / -004 live↔sim — acceptance (2026-09-04)

**Decision:** close enough. Leave practice sleeves running; recheck next week.

| Account | Demo | Reconcile | Notes |
|---------|------|-----------|-------|
| `-004` | `usdjpy_asia_range_london_oanda` | **MATCH** | 1 entry post-restart; exact vs Engine |
| `-003` | `nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda` | accepted skew | Same 2 buys; live fill +3–4m vs 5m bar stamp |

Artifacts: `acc_003_004_summary.json`, `EMAIL_003_004.txt`.

No code or daemon change from this check.
