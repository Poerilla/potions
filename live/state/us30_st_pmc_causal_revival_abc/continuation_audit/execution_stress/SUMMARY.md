# Continuation v1 — adverse execution stress (Engine)

Cell: `path_c_continuation_break_2r_10r` (frozen contract `us30_st_pmc_completed_hour_continuation_v1`)
DSR: `TRL-2026-00188` (parent TRL-2026-00186)

| slippage_ticks | net | stress | N/S | units | trades |
|---:|---:|---:|---:|---:|---:|
| 1 | $25371 | $-13783 | 1.84 | 5207 | 1736 |
| 2 | $24468 | $-14155 | 1.73 | 5207 | 1736 |
| 4 | $22664 | $-14898 | 1.52 | 5207 | 1736 |
| 8 | $19112 | $-16384 | 1.17 | 5207 | 1736 |

## Stance

- Baseline ticks=1 N/S 1.84; harshest ticks=8 N/S 1.17.
- Economically credible under ordinary adverse cases: **YES**.
- Still **not demo-promote**; stress is necessary not sufficient.

