# Monday OR sizing sweep — Phase 1 results

**Adapted plan:** [`ADAPTED_PLAN.md`](ADAPTED_PLAN.md)  
**Driver:** `live/monday_or_sizing_sweep.py`  
**Grid:** M1–M3 × S1–S3 × R1–R3 = **27** cells × EURUSD + USDJPY (pandas research sim, HTF on, shifted primary).

Sidecar = **shifted primary** (opposite Mon extreme after flat@50%), not same-direction SL re-entry.  
R* = max **primary** trades/week (2 / 3 / unlimited).

## Winners

| Pair | Baseline M1_S1_R1 | **Phase 1 pick** | Δ CE | Δ ≈USD net |
|---|---|---|---:|---:|
| **EURUSD** | CE **2.21** · +$125k | **`M1_S2_R2`** CE **3.28** · +$179k | **+1.07** | +$54k |
| **USDJPY** | CE **8.90** · +$205k | **`M3_S3_R2`** CE **13.37** · +$241k | **+4.47** | +$36k |

### EURUSD pick — `M1_S2_R2`
- Main: **3** = 2@30% + 1@50% (unchanged)
- Shifted sidecar: **2** = 1@30% + 1@50% (**lighter** than main)
- Max primary/week: **3** (was 2)

### USDJPY pick — `M3_S3_R2`
- Main: **2** = 1@30% + 1@50% (**smaller** main)
- Shifted sidecar: **4** = 2@30% + 2@50% (**heavier** sidecar)
- Max primary/week: **3**

## Themes

1. **R2 (max 3 primary/week)** dominates top ranks on both pairs — baseline R1=2 was too tight.
2. EURUSD likes a **lighter shifted** sidecar (S2); USDJPY likes a **heavier shifted** (S3) with a **smaller main** (M3).
3. Runner-heavy main (M2) is competitive but not #1 on either pair in Phase 1.
4. Research CE ≫ broker CE (USDJPY research 8.9 vs broker ~4.3) — confirm picks under PaperBroker before promoting.

## Per-pair top tables

- EURUSD detail: this folder `SUMMARY.md` (written by sweep) + `results.csv`
- USDJPY detail: [`../monday_or_sizing_sweep_usdjpy/SUMMARY.md`](../monday_or_sizing_sweep_usdjpy/SUMMARY.md) + `results.csv`
- Merged: [`results_all.csv`](results_all.csv)

## Next

1. ~~Broker-like confirm~~ → **done 2026-07-21** — see [`../monday_or_sizing_sweep_broker/INDEX.md`](../monday_or_sizing_sweep_broker/INDEX.md).
   - EURUSD `M1_S2_R2` confirmed #1 under broker (N/S **1.74**).
   - USDJPY broker #1 is **`M2_S3_R1`** (8.20); pandas `M3_S3_R2` is #3.
2. Optional `--phase full` (M4–M6, S4–S5) if you want capacity / probe cells.
3. Update plugin defaults to pair-specific broker winners when promoting.

```bash
python3 -m live.monday_or_sizing_sweep --phase 1 --pairs EURUSD,USDJPY
python3 -m live.monday_or_sizing_sweep --phase full --pairs USDJPY
```

*Phase 1 completed 2026-07-20.*
