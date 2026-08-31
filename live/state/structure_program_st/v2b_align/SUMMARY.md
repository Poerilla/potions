# Structure keys vs v2b / OR levels (NQ)

Structure program entry key (bull LL if buy / bear HH if sell) joined to `or_profile_engine/nq/2026H2/sessions.csv`.

## Coverage

- Structure ready days: **1614**
- Joined to OR sessions: **3118**
- Program direction == first_break_side: **52.1%** (1623)

## Where entry_key sits vs breakout path (all joined days)

| bucket | pct | n |
|---|---:|---:|
| inside OR | 12.3% | 384 |
| in 0–1R beyond break | 4.3% | 134 |
| in 1–2R | 1.9% | 58 |
| beyond 2R | 3.9% | 122 |
| against break (wrong side of OR) | 77.6% | 2420 |

## Direction-aligned subset only (program matches first_break)

- n = **1623**
- in 0–1R: **5.1%**
- in 1–2R: **2.0%**
- beyond 2R: **2.8%**
- inside OR: **15.8%**
- median |key − OR boundary| pts: **206.0**
- median |key − v2b TP1| pts: **285.2**
- median key distance from break (R): **-2.38**

## Read

**Structure entry keys do not align with v2b breakout targets.**

- **77.6%** of joined days put the program's entry key on the **wrong side of the OR** relative to `first_break_side` (fade / counter-path, not continuation).
- Even when program direction matches the first break, only **~7%** of keys sit in the 0–2R band beyond the break (v2b TP1/TP2 path). Median key is **−2.4R** from the break (inside / opposite).
- Median distance to v2b TP1 ≈ **285 pts** — not co-located with OR 1R targets.

So a resting limit at the structure is **not** fishing the same levels v2b aims for on a breakout day; it is usually a pullback / mean-reversion level relative to that day's OR break.
