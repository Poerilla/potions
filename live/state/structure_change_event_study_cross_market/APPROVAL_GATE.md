# Approval gate — cross-market structure-change event study

**Default: NOT APPROVED.** Cross-market Phase 1 must not start until both
conditions below are met.

## Prerequisites

1. NQ hub (`live/state/nq_structure_change_event_study/`) has completed Phase 1–4
   artifacts (atlas + close-vs-wick + timing + 1h incremental + causality).
2. Human review of those NQ results decides the event definitions / horizons
   are worth transferring (no silent re-tuning of StructureProgramEngine).

## Gate status

```yaml
status: pending          # pending | approved | rejected
approved_by: null
approved_at: null
notes: >
  Armed 2026-08-29 per operator: CFDs + micros + gold + USDJPY stay pending
  until NQ structure analysis is approved by us.
markets_authorized_on_approve: null   # null = full PENDING_ROSTER run_order; or list subset
```

## How to approve

Edit this file: set `status: approved`, fill `approved_by` / `approved_at`,
optionally restrict `markets_authorized_on_approve`. Then start Phase 1 from
the parent hub (do not auto-launch from the NQ CPU-clear email alone).
