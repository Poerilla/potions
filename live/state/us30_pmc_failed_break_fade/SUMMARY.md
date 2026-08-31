# US30 PMC failed-break fade — Phase 1/2

**Hub:** `live/state/us30_pmc_failed_break_fade/`
**DSR:** `TRL-2026-00187`
**Status:** Phase 1 taxonomy + Phase 2 frozen base replay complete.

## Frozen params

| Param | Value |
|---|---|
| Level | PMC only |
| MIN_PENETRATION | 0.10 × ATR_20_5m |
| MAX_FAILURE_MINUTES | 60 |
| CONFIRMATION_BARS | 1 |
| STOP_BUFFER | 1 tick (0.1) |
| TP ladder | 1R/2R/4R @ 2/1/1 lots (50/25/25) |
| Costs | fee $1.50/unit + 1-tick adverse entry/stop |
| Early closes | excluded (<300 RTH bars or last <15:45) |

## Phase 1 — event taxonomy

- Sweep events (first per side/session, early-closes excluded): **2530**
- Upside / downside: 1519 / 1011
- Reclaim within 60m: **18.1%**
- Reclaim within 15m: **12.4%**
- Median penetration (ATR): **24.69**
- Median time sweep→reclaim (min): **20.0**
- Event-day fraction: **6.0%**

Note: median penetration is large because many sessions open already beyond PMC —
first RTH bar then counts as a sweep under the frozen rule (not necessarily a
fresh cross-through). Confirmed/reclaim paths still require a 5m close back inside ≤60m.

Full table: `taxonomy/pmc_sweeps.csv`

## Phase 2 — frozen base replay

| Control | N | Net $ | Stress $ | N/S | WR | PF | Avg R | Long $ | Short $ | Runner share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| naive | 2102 | 4549 | -5863 | 0.78 | 36.9% | 1.05 | -0.35 | 6121 | -1573 | 827% |
| reclaim_only | 318 | 3968 | -8204 | 0.48 | 41.2% | 1.10 | 0.04 | 261 | 3708 | 176% |
| confirmed | 129 | 2612 | -3239 | 0.81 | 49.6% | 1.11 | 0.12 | 949 | 1662 | 72% |

_Runner share = tp_4r net / book net (can exceed 100% when other legs lose)._

### Yearly (confirmed)

| Year | N | Net $ | Stress $ | N/S | WR |
|---:|---:|---:|---:|---:|---:|
| 2016 | 1 | -6 | -148 | -0.04 | 0.0% |
| 2017 | 17 | -242 | -368 | -0.66 | 52.9% |
| 2018 | 11 | 1144 | -828 | 1.38 | 63.6% |
| 2019 | 13 | -652 | -716 | -0.91 | 38.5% |
| 2020 | 14 | 2064 | -1092 | 1.89 | 57.1% |
| 2021 | 15 | 2579 | -824 | 3.13 | 60.0% |
| 2022 | 21 | -124 | -1312 | -0.09 | 47.6% |
| 2023 | 14 | -1063 | -760 | -1.40 | 28.6% |
| 2024 | 17 | -667 | -1036 | -0.64 | 58.8% |
| 2025 | 6 | -421 | -726 | -0.58 | 33.3% |

## Stance

**RESEARCH_WEAK_POSITIVE** — Confirmed fade net positive but weak N/S — research only; no promote.

## Gates (reference)

| Result | Action |
|---|---|
| Confirmed fade negative | Retire US30 revival program |
| Reclaim-only + / confirmed − | Do not promote; early-entry study only if warranted |
| Confirmed + stable plateau | StrategyPlugin port (Phase 3+) |
| Naive + / confirmed − | Suspect artifact; do not promote |
| Runner drives all net | Keep runner dependence explicit |

Phase 3 (causality + sensitivity) and Phase 4 (adversarial) **not** run in this pass.

## Next (queued)

**4h structure-bias overlay** on confirmed fades only — hub
`live/state/us30_pmc_failed_break_fade_structure_bias/` (DSR `TRL-2026-00189`).
Pre-registered: descriptive ALIGNED/OPPOSED/NEUTRAL split → baseline vs
aligned_only vs aligned+neutral. No size-up / no extra filters. Queued behind
continuation slippage stress.
