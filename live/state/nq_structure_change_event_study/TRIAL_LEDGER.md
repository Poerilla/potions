# Trial ledger — nq_structure_change_event_study

| Field | Value |
|---|---|
| market | NQ |
| timeframes | 4h primary, 1h secondary |
| engine | StructureProgramEngine_v1_existing |
| swing L/R | 2 / 2 |
| list / takeouts | 20 / 2 |
| penetration | 0.05 ATR + zero-buffer pass |
| reclaim window | 3 structure bars |
| holdout | last 25% by event time |
| phases run | 1–4 (event study) |
| phase 5 | NOT RUN |
