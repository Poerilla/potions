# Status — structure-change event study (cross-market)

**Hub:** `live/state/structure_change_event_study_cross_market/`  
**Updated:** 2026-08-29  
**Gate:** `APPROVAL_GATE.md` → **pending** (blocked on NQ atlas approval)

## Intent

Same standalone **market-structure event study** as NQ (LH–LL–HH / HL–HH–LL
protected-swing events → expansion atlas), extended to the CFD book, micros,
gold, and USDJPY — **only after** we approve the NQ Phase 1–4 readouts.

## Roster (no Phase 1 compute yet)

| Bucket | Keys | Status |
|---|---|---|
| Index CFDs | `nas100`, `us30` | PENDING_NQ_APPROVAL |
| FX / metal CFDs | `usdjpy_ny`, `eurusd_ny`, `xauusd_ny` | PENDING_NQ_APPROVAL |
| Micros | `mnq`, `mym` | PENDING_NQ_APPROVAL |
| Micro MES | `mes` | **BLOCKED_DATA** (no 1m on disk) |
| Extra 1m present | SPX500, GBPUSD | PENDING_WIRE (not in `FX_MARKETS` yet) |

See `PENDING_ROSTER.yaml` for paths, roles, and post-approval run order.

## Sequencing vs NQ

```text
1. US30 continuation stress + PMC fade×structure-bias   [upstream]
2. NQ Phase 1–4 event atlas                             [WAITING CPU]
3. Human approval of NQ atlas                           [THIS GATE]
4. Cross-market Phase 1 in roster order                 [NOT STARTED]
```

NQ `QUEUE.sh` CPU-clear email does **not** authorize this roster.

## Per-instrument stubs

Each `*/STATUS.md` under this hub inherits the NQ freeze and stays idle.
