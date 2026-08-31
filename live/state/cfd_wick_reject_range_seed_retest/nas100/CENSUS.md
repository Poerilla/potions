# NAS100 — range-seed census (pre-P&L)

**Model:** frozen NQ WICK_REJECT → 1h break → limit retest (CFD economics only).
**Role:** implementation_parity_vs_NQ
**Horizon:** 2016-11-14 → 2025-10-01 (2747 RTH days)

| Metric | Value |
|---|---:|
| Atlas 4h WICK_REJECT (pen≥0.05) | 70 |
| Eligible seeds | 58 |
| Rejected | 12 |
| 1h confirmed breaks | 58 |
| Retest orders placed | 58 |

Reject reasons: `{'width_gt_2.00_ATR': 9, 'duplicate_confirm_bar': 2, 'early_close_session': 1}`

## Seed-width distribution (eligible)

| Stat | points | ×4h ATR |
|---|---:|---:|
| min | 21.00 | 0.281 |
| p25 | 80.75 | 0.709 |
| median | 130.75 | 0.963 |
| p75 | 198.87 | 1.291 |
| max | 502.20 | 1.898 |
