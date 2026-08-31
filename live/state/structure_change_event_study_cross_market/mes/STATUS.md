# Status — MES structure-change event study

**Parent:** `live/state/structure_change_event_study_cross_market/`  
**Market key:** `mes`  
**Role:** micro futures  
**Status:** **BLOCKED_DATA**

Inherits frozen engine + taxonomy from NQ Phase 0:
`nq_structure_change_event_study/STRUCTURE_CHANGE_RESEARCH_CONTRACT.yaml`
and `EVENT_TAXONOMY.md`.

No Phase 1 event ledger until `../APPROVAL_GATE.md` is `approved`
(after NQ Phases 1–4 review). Do not retune left/right, list, or takeouts.

## Data blocker

`MARKETS["mes"].dbn_path` → `mes/mes_1min_raw.csv` is missing. On disk:
`mes_5min_rth.csv`, `mes/data/mes_front_month_4h_from_1m.csv` only.
Restore continuous 1m (or explicitly approve an ES-proxy study) before Phase 1.
