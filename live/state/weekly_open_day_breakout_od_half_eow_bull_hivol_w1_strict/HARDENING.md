# Week-1 causal half+EOW — strict verification

## Changes (plugin v6)

1. **`allow_weeks_of_month`** entry gate — calendar week-of-month on the
   arming **session** date (`((day-1)//7)+1`, same as HA mills).
2. **Friday flatten** fires at **13:00 NY** 4h completion (after 09:00–13:00
   bar), so 1m market closes can fill Friday afternoon instead of Sunday reopen.
3. **Strict** `CausalityGuard`, feature snapshots (`wod_open_day_levels`,
   `wod_week_of_month_gate`, `wod_regime_gate`, `wod_breakout_arm`), manifest
   hashes **4h + 1m**.

Variant: `od_half_eow_bull_hivol_w1`  
Hub: `live/state/weekly_open_day_breakout_od_half_eow_bull_hivol_w1_strict`

## Results (NAS100 ~10y)

| Book | Trades | Net | Stress | N/S | Notes |
|---|---:|---:|---:|---:|---|
| HA week-1 FILTER (old tape) | 45 | +$9,669 | ~$1.8k | **5.51** | post-hoc; Sunday-heavy EOW |
| **Plugin week-1 strict** | **53** | **+$8,031** | **$4.4k** | **1.82** | causal gate + Fri PM flatten |

- Feature snapshots: 6023 · causality violations: **0**
- Entry wom: 52× week-1, 1× week-2 fill (arm session still week-1)
- Exit DOW: **43 Friday** / 5 Sunday (residual holiday/thin Fridays)

## Stance

**Research / risk-throttle candidate.** Causal week-1 gate is real and the
Friday-exit fix largely works, but N/S collapses vs the HA overlay once stress
is measured on the same-Friday exit book. Not paper-eligible yet (no OANDA
harness; N/S < 2 promote bar for this family).
