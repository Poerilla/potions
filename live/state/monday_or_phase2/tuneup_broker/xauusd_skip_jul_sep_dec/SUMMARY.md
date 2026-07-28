# XAUUSD — skip Jul/Sep/Dec (StrategyPlugin confirmed)

## Broker ladder (Engine + PaperBroker)

| Stage | Net ≈$ | MTM DD ≈$ | N/S | Units |
|---|---:|---:|---:|---:|
| Phase 1 baseline | +437,940 | −230,359 | 1.90 | 12139 |
| Sitout +100 only | +510,243 | −214,892 | 2.37 | 11170 |
| **Sitout +100 + skip Jul/Sep/Dec (core)** | **+580,139** | **−172,265** | **3.37** | 8388 |

**vs sitout-only:** +$69.9k net · MTM DD $42.6k shallower · ΔN/S **+0.99**.  
**vs Phase 1:** +$142.2k net · MTM DD $58.1k shallower · ΔN/S **+1.47**.

Plugin knobs (locked on `M2_S2_R3` / `PAIR_TUNEUPS`):

- `week_sitout_after_pts=100`
- `skip_entry_months=[7, 9, 12]` (NY calendar; no new primary/shifted entries)

States:

- Core: `tuneup_broker/states/xauusd_m2_s2_r3_tuneup/`
- Archive sitout-only: `tuneup_broker/states/xauusd_m2_s2_r3_sitout100_only/`

Earlier fill-proxy quick study (trade-equity) pointed the same direction (net↑, DD↑); broker confirms with dollar MTM.
