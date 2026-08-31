# NQ v2b S_1_1_3 — monthly ext-band fade opposed gate

Gate: price must **trade through** pct75 band entry (gap-through void). Then v2b ``S_1_1_3`` may fire only **opposite** the fade direction for the rest of the month.

- DSR: `TRL-2026-00126`
- Gate mode: **opposed**
- Start: **2021-03-04** · regime sessions: **1164**
- Band touches: **100** (long 23 / short 77)
- Sessions with active gate: **388**

## Results

| Trades | Units | Net $ | Stress DD | N/S | Win% | Gate OK | Violations |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 269 | 1345 | 96,678 | -165,508 | 0.58 | 55.0 | 269 | 0 |

Sibling: aligned hub `live/state/nq_v2b_mo_ext_band_fade_gate/` · ST prior-opposed resting_limit ≈ N/S **19.56**.

Stance: research.

