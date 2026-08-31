# CONFIG — nq_wick_reject_4h_ny_open_5m_protected_pivot_v2

Frozen before run. Change vs V1: **observational pivot timeframe only (1m → 5m)**.

| Field | Value |
|-------|-------|
| study_id | `nq_wick_reject_4h_ny_open_5m_protected_pivot_v2` |
| parent | `nq_wick_reject_4h_ny_open_1m_protected_pivot_v1` (archived_negative, hash `ea16e8de589a75c2`) |
| instrument | NQ |
| timezone | America/New_York |
| NY open | 09:30 ET |
| formation window | 09:30–10:30 ET |
| observation horizon | through 13:00 ET |
| seed source | existing 4h WICK_REJECT ledger (`make_seeds_30`) |
| seed definition changed | false |
| first eligible NY open only | true |
| require seed active at open | true |
| pivot timeframe | 5m |
| left / right | 1 / 1 |
| strict extrema | true |
| equal H/L policy | reject |
| min pivot separation | 1 bar |
| pivot_ts | close of pivot 5m bar |
| pivot_available_at | close of following 5m bar |
| structure_complete_at | P4.pivot_available_at |
| selection | first consecutive four-pivot only |
| intervening ambiguity | reject |
| bear failure | 5m high > protected_HH + 1 tick |
| bull failure | 5m low < protected_LL − 1 tick |
| equal touch | report separately (held) |
| hard stop | total candidates < 40 → insufficient sample; archive; no tuning |
| screen | both sides ≥55% hold, n≥15 each, total≥40, causality 100% |

Not allowed: overwrite V1, timeframe chooser, entries/stops/P&L/plugin, post-hoc window widening.
