# SPX500 — range-seed census (pre-P&L)

**Model:** frozen NQ WICK_REJECT → 1h break → limit retest (CFD economics only).
**Role:** independent_index_cfd
**Horizon:** 2015-01-01 → 2026-08-28 (3630 RTH days)

| Metric | Value |
|---|---:|
| Atlas 4h WICK_REJECT (pen≥0.05) | 80 |
| Eligible seeds | 52 |
| Rejected | 28 |
| 1h confirmed breaks | 52 |
| Retest orders placed | 52 |

Reject reasons: `{'width_gt_2.00_ATR': 14, 'duplicate_confirm_bar': 12, 'early_close_session': 2}`

## Seed-width distribution (eligible)

| Stat | points | ×4h ATR |
|---|---:|---:|
| min | 4.80 | 0.507 |
| p25 | 18.35 | 0.836 |
| median | 31.70 | 1.043 |
| p75 | 54.65 | 1.411 |
| max | 138.40 | 1.945 |
