# NQ v2b S_1_1_3 — monthly ext-band fade gate

Gate: price must **trade through** pct75 band entry (gap-through void). Then v2b ``S_1_1_3`` may fire only in the **fade direction** for the rest of the month.

- DSR: `TRL-2026-00125`
- Start: **2021-03-04** · regime sessions: **1164**
- Band touches: **100** (long 23 / short 77)
- Sessions with active gate: **388**

## Results

| Trades | Units | Net $ | Stress DD | N/S | Win% | Aligned | Violations |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 264 | 1320 | 258,105 | -99,688 | 2.59 | 57.2 | 264 | 0 |

Compare: NQ prior-opposed resting_limit S_1_1_3 ≈ N/S **19.56**, net ~$1.34M (`live/state/nq_v2b_prior_opposed_stpmc_resting_limit/`).

Stance: research — band-fade gate vs ST prior-opposed.

