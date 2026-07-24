# Monday OR sizing sweep — hub

**Phase 1 complete (2026-07-20).**  
Driver: `live/monday_or_sizing_sweep.py` · adapted plan: [`ADAPTED_PLAN.md`](ADAPTED_PLAN.md)

## Headline

| Pair | Baseline `M1_S1_R1` | **Winner** | CE | ≈USD net |
|---|---|---|---:|---:|
| EURUSD | 2.21 · +$125k | **`M1_S2_R2`** | **3.28** | +$179k |
| USDJPY | 8.90 · +$205k | **`M3_S3_R2`** | **13.37** | +$241k |

- **EURUSD:** main stays 3=(2@30,1@50); shifted **2**=(1@30,1@50); max primary/week **3**.
- **USDJPY:** main **2**=(1@30,1@50); shifted **4**=(2@30,2@50); max primary/week **3**.
- Shared lesson: **max 2 primary/week was too tight** (R2 wins everywhere in the top tier).

## Files

| File | Content |
|---|---|
| [`PHASE1_RESULTS.md`](PHASE1_RESULTS.md) | Narrative + next steps |
| [`SUMMARY.md`](SUMMARY.md) | EURUSD top-15 table |
| [`results.csv`](results.csv) | EURUSD 27 cells |
| [`results_all.csv`](results_all.csv) | EURUSD + USDJPY merged |
| [`../monday_or_sizing_sweep_usdjpy/SUMMARY.md`](../monday_or_sizing_sweep_usdjpy/SUMMARY.md) | USDJPY top-15 |
| [`../eurusd_monday_or_breakout_15m/MONDAY_ORB_FAMILY.md`](../eurusd_monday_or_breakout_15m/MONDAY_ORB_FAMILY.md) | Family ranking (updated) |

## Stance

Pandas Phase 1 complete. **Broker confirm done** — hub [`../monday_or_sizing_sweep_broker/INDEX.md`](../monday_or_sizing_sweep_broker/INDEX.md): EURUSD `M1_S2_R2` holds; USDJPY prefers `M2_S3_R1` over pandas `M3_S3_R2`.
