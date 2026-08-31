# CONFIG — nq_wick_reject_4h_ny_open_5m_protected_pivot_v2_no_cutoff

Diagnostic vs archived V2: **remove 10:30 formation cutoff** (formation through obs_end).

| Field | Value |
|-------|-------|
| study_id | `nq_wick_reject_4h_ny_open_5m_protected_pivot_v2_no_cutoff` |
| parent | `..._5m_..._v2` (insufficient_sample_archive, hash `d3b30d168b0bb59b`, n=7) |
| grandparent | `..._1m_..._v1` (archived_negative) |
| instrument | NQ |
| timezone | America/New_York |
| NY open | 09:30 ET |
| formation window | 09:30–13:00 ET (**no 10:30 cutoff**) |
| observation horizon | through 13:00 ET |
| seed source | existing 4h WICK_REJECT ledger (`make_seeds_30`) |
| pivot timeframe | 5m |
| left / right | 1 / 1 |
| strict extrema | true |
| equal H/L policy | reject |
| structure_complete_at | P4.pivot_available_at (< 13:00) |
| selection | first consecutive four-pivot only |
| hard stop | total candidates < 40 → insufficient sample |
| screen | both sides ≥55% hold, n≥15 each, total≥40, causality 100% |

Note: late structures have short protection observation windows to 13:00.
Does not overwrite archived V2; not a family-rescue by default.
